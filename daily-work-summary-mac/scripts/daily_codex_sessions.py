#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
每日 Codex 会话记录提取工具
==========================
读取本地 Codex CLI 持久化的会话记录，提取用户消息和助手文本，按日期分组输出。
只读取本地文件，不调用任何远程 API。

数据来源（按优先级）：
1. ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl —— 新版 Codex CLI 的完整会话滚动记录
   - session_meta 行提供会话 cwd / session_id
   - response_item 行提供 user / assistant 消息，只保留 input_text / output_text 文本块
   - 跳过 developer 角色（系统指令）以及 reasoning / function_call 等非文本块
2. ~/.codex/history.jsonl —— 旧版 Codex CLI 的历史记录（仅用户消息，无 cwd），
   仅在找不到 rollout 文件时作为兜底
3. ~/.codex/session_index.jsonl —— 会话标题索引（尽力而为，用于美化输出）

用法:
    python scripts/daily_codex_sessions.py                          # 默认今天
    python scripts/daily_codex_sessions.py --date 2026-04-13        # 指定日期
    python scripts/daily_codex_sessions.py --since 2026-04-01 --until 2026-04-13
    python3 scripts/daily_codex_sessions.py --roots /Users/torchz/CetWorkspace
    python3 scripts/daily_codex_sessions.py --home /Users/torchz/.codex     # 指定 Codex 目录
    python scripts/daily_codex_sessions.py --json --output report.json

扫描目录等配置集中在 skill 根目录的 config.json 中，无需改代码。
配置优先级（从高到低）：命令行参数 > 环境变量 > config.json > 内置默认值。
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 脚本所在目录加入 sys.path，保证独立运行时也能 import common
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (  # noqa: E402
    DEFAULT_ROOTS,
    ensure_utf8_console,
    format_events_report,
    load_config,
    matches_roots,
    normalize_text,
    redact_sensitive,
    resolve_date_range,
    to_local_date,
    to_local_hm,
)

ensure_utf8_console()

# ==================== 配置区域 ====================

# Codex 数据目录查找顺序：--home > CODEX_HOME > config.json > ~/.codex
CODEX_HOME_ENV = "CODEX_HOME"
DEFAULT_CODEX_HOME = Path.home() / ".codex"

# ==================== 配置区域结束 ====================


def resolve_codex_home(explicit_home=None, config_home=None):
    """
    解析 Codex 数据目录。
    优先级：--home > CODEX_HOME > config.json 的 codex.codex_home > 默认。
    config.json 中 codex_home 为空时同样回退到默认自动查找。
    """
    if explicit_home:
        return Path(explicit_home)
    env_home = os.environ.get(CODEX_HOME_ENV)
    if env_home:
        return Path(env_home)
    if config_home:
        return Path(config_home)
    return DEFAULT_CODEX_HOME


def load_session_titles(home):
    """读取 session_index.jsonl，返回 {session_id: thread_name} 映射（尽力而为）"""
    index_file = home / "session_index.jsonl"
    titles = {}
    if not index_file.is_file():
        return titles
    try:
        with open(index_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("id") and obj.get("thread_name"):
                    titles[obj["id"]] = obj["thread_name"]
    except OSError:
        pass
    return titles


def _path_date_in_range(path, since, until):
    """
    rollout 文件路径形如 sessions/2026/07/02/rollout-...，直接用路径日期做快速过滤，
    避免逐行解析范围外的文件。
    """
    try:
        parts = path.parts
        # 形如 .../sessions/YYYY/MM/DD/rollout-xxx.jsonl
        idx = parts.index("sessions")
        y, m, d = parts[idx + 1], parts[idx + 2], parts[idx + 3]
        file_date = datetime(int(y), int(m), int(d)).date()
    except (ValueError, AttributeError, IndexError):
        return True
    return since <= file_date <= until


# Codex 注入的系统内容标记（AGENTS.md 指令、环境上下文、审查模板、中断通知等）
_META_TEXT_MARKERS = (
    "# AGENTS.md instructions for",
    "<INSTRUCTIONS>",
    "<permissions instructions>",
    "<environment_context>",
    "<turn_aborted",
    "## Code review guidelines:",
)
# 审查类注入消息中用户真实请求的前缀，命中时只保留其后内容
_REAL_REQUEST_MARKER = "## My request for Codex:"


def _clean_injected_user_text(text):
    """
    从注入的 user 角色消息中提取用户真实输入：
    - 含真实请求标记时，只保留标记后的内容
    - 纯注入内容（无真实请求）返回 None，表示跳过
    """
    if _REAL_REQUEST_MARKER in text:
        idx = text.index(_REAL_REQUEST_MARKER)
        rest = text[idx + len(_REAL_REQUEST_MARKER):].strip()
        return rest if rest else None

    head = text[:200].replace("\r", " ").replace("\n", " ")
    if any(marker in head for marker in _META_TEXT_MARKERS):
        return None

    return text


def extract_response_item_text(payload):
    """
    从 response_item 的 payload 中提取纯文本。
    只保留 input_text（用户输入）/ output_text（助手输出）块，
    跳过 reasoning、function_call、function_call_output 等非文本块。
    """
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("input_text", "output_text") and block.get("text"):
            parts.append(block["text"])
    return "\n\n".join(parts)


def scan_rollout_file(path, since, until, roots, titles, max_chars=2000):
    """
    扫描单个 rollout 文件，返回事件列表。
    先用 session_meta 取会话 cwd / session_id 做项目范围过滤，再逐行解析消息。
    """
    events = []
    cwd = ""
    session_id = ""

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        line_type = obj.get("type")
        if line_type == "session_meta":
            payload = obj.get("payload") or {}
            cwd = payload.get("cwd") or ""
            session_id = payload.get("session_id") or path.stem
            # 提前过滤：会话目录不在项目范围内则整文件跳过
            if roots and not matches_roots(cwd, roots):
                return []
            continue

        if line_type != "response_item":
            continue

        payload = obj.get("payload") or {}
        if payload.get("type") != "message":
            continue

        role = payload.get("role")
        if role not in ("user", "assistant"):
            continue

        text = normalize_text(extract_response_item_text(payload), max_chars)
        if not text:
            continue

        if role == "user":
            text = _clean_injected_user_text(text)
            if not text:
                continue
            text = normalize_text(text, max_chars)

        local_date = to_local_date(obj.get("timestamp"))
        if local_date is None or not (since <= local_date <= until):
            continue

        events.append({
            "date": local_date.isoformat(),
            "time": to_local_hm(obj.get("timestamp")) or "",
            "project": cwd or "unknown",
            "session": session_id or path.stem,
            "title": titles.get(session_id, ""),
            "role": role,
            "text": redact_sensitive(text),
        })

    return events


def scan_history_jsonl(home, since, until, max_chars=2000):
    """
    兜底：旧版 Codex CLI 的 history.jsonl，格式为 {"session_id", "ts"(unix秒), "text"}。
    只含用户消息且没有 cwd，因此不做项目范围过滤。
    """
    events = []
    history_file = home / "history.jsonl"
    if not history_file.is_file():
        return events

    try:
        with open(history_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = normalize_text(obj.get("text"), max_chars)
                if not text:
                    continue
                try:
                    local_date = datetime.fromtimestamp(obj["ts"]).date()
                except (KeyError, TypeError, OSError, ValueError):
                    continue
                if not (since <= local_date <= until):
                    continue
                events.append({
                    "date": local_date.isoformat(),
                    "time": datetime.fromtimestamp(obj["ts"]).strftime("%H:%M"),
                    "project": "unknown",
                    "session": obj.get("session_id") or "history",
                    "title": "",
                    "role": "user",
                    "text": redact_sensitive(text),
                })
    except OSError:
        pass
    return events


def main():
    parser = argparse.ArgumentParser(
        description="提取本地 Codex 会话记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD (默认: 今天)")
    parser.add_argument("--since", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--until", default=None, help="结束日期 YYYY-MM-DD (默认: 今天)")
    parser.add_argument("--roots", nargs="+", default=None, help="项目根目录列表 (覆盖默认配置)")
    parser.add_argument("--home", default=None, help="Codex 数据目录 (覆盖自动查找)")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径 (默认: 打印到控制台)")
    parser.add_argument("--max-chars", type=int, default=None, help="单条消息最大字符数 (默认取 config.json)")

    args = parser.parse_args()

    # --json 模式下进度信息走 stderr，保证 stdout 只输出纯 JSON 供管道解析
    def log(*a, **kw):
        print(*a, file=sys.stderr, **kw) if args.json else print(*a, **kw)

    config = load_config()
    since, until = resolve_date_range(args.date, args.since, args.until)
    roots = args.roots if args.roots else (config.get("scan_roots") or DEFAULT_ROOTS)
    max_chars = (
        args.max_chars
        or config.get("codex", {}).get("max_chars")
        or config.get("max_chars")
        or 2000
    )
    home = resolve_codex_home(
        args.home, config.get("codex", {}).get("codex_home") or None
    )

    log(f"🔍 Codex 目录: {home}")
    log(f"📅 日期范围: {since.isoformat()} ~ {until.isoformat()}")
    if roots:
        log(f"📁 项目范围: {', '.join(roots)}")
    log()

    if not home.is_dir():
        log(f"⚠ Codex 目录不存在: {home}")
        log("   跳过 Codex 会话记录。")
        return

    titles = load_session_titles(home)

    log("📥 正在扫描会话记录...")
    events = []
    sessions_dir = home / "sessions"
    file_count = 0

    if sessions_dir.is_dir():
        for path in sorted(sessions_dir.rglob("rollout-*.jsonl")):
            if not _path_date_in_range(path, since, until):
                continue
            file_count += 1
            events.extend(scan_rollout_file(path, since, until, roots, titles, max_chars))
    else:
        log("   未找到 sessions 目录，尝试旧版 history.jsonl...")

    if not events:
        events = scan_history_jsonl(home, since, until, max_chars)

    log(f"   扫描 {file_count} 个 rollout 文件，提取 {len(events)} 条消息")

    if not events:
        log("\n> 🔍 在指定日期范围内未找到 Codex 会话记录。")
        return

    if args.json:
        payload = {
            "source": "codex",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "since": since.isoformat(),
            "until": until.isoformat(),
            "roots": roots,
            "events": events,
        }
        output_text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        output_text = format_events_report(
            title="# 🤖 每日 Codex 会话记录",
            source="codex 本地会话记录",
            events=events,
            since=since,
            until=until,
            assistant_label="Codex",
        )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_text)
        log(f"✅ 报告已保存到: {args.output}")
    else:
        if args.json:
            # JSON 模式用 UTF-8 字节流写 stdout，与控制台编码（GBK）解耦，
            # 保证管道接收端按 UTF-8 解码即可得到合法 JSON
            sys.stdout.buffer.write(output_text.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")
        else:
            log("=" * 60)
            print(output_text)


if __name__ == "__main__":
    main()
