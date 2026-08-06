#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
每日 Kimi Code 会话记录提取工具
================================
读取本地 Kimi Code CLI 持久化的会话记录（~/.kimi-code/sessions 下），
提取用户消息和助手文本，按日期分组输出。只读取本地文件，不调用任何远程 API。

数据来源：
~/.kimi-code/sessions/<workspace>/session_*/agents/main/wire.jsonl

解析规则：
- turn.prompt（origin.kind == user）→ 用户消息
- context.append_loop_event 中的 content.part（part.type == text）→ 助手文本
- 跳过 agents/agent-* 等子代理 wire、thinking、工具调用/结果、系统注入、
  后台任务通知（turn.steer）等非对话内容
- 会话工作目录取自 state.json，缺失时回退 session_index.jsonl / workspaces.json，
  并按 --roots 项目范围过滤（与 Codex / Claude 提取器一致）

用法:
    python scripts/daily_kimi_sessions.py                          # 默认今天
    python scripts/daily_kimi_sessions.py --date 2026-04-13        # 指定日期
    python scripts/daily_kimi_sessions.py --since 2026-04-01 --until 2026-04-13
    python3 scripts/daily_kimi_sessions.py --roots /Users/torchz/CetWorkspace
    python3 scripts/daily_kimi_sessions.py --home /Users/torchz/.kimi-code   # 指定 Kimi 数据目录
    python scripts/daily_kimi_sessions.py --json --output report.json

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
)

ensure_utf8_console()

# ==================== 配置区域 ====================

# Kimi Code 数据目录查找顺序：--home > KIMI_CODE_HOME > config.json > ~/.kimi-code
KIMI_HOME_ENV = "KIMI_CODE_HOME"
DEFAULT_KIMI_HOME = Path.home() / ".kimi-code"

# ==================== 配置区域结束 ====================


def resolve_kimi_home(explicit_home=None, config_home=None):
    """
    解析 Kimi Code 数据目录。
    优先级：--home > KIMI_CODE_HOME > config.json 的 kimi.kimi_home > 默认。
    config.json 中 kimi_home 为空时同样回退到默认自动查找。
    """
    if explicit_home:
        return Path(explicit_home)
    env_home = os.environ.get(KIMI_HOME_ENV)
    if env_home:
        return Path(env_home)
    if config_home:
        return Path(config_home)
    return DEFAULT_KIMI_HOME


def load_workspace_roots(home):
    """读取 workspaces.json，返回 {workspace_id: root} 映射（尽力而为）。"""
    workspaces_file = home / "workspaces.json"
    result = {}
    if not workspaces_file.is_file():
        return result
    try:
        with open(workspaces_file, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        for ws_id, info in (data.get("workspaces") or {}).items():
            root = info.get("root") if isinstance(info, dict) else None
            if ws_id and root:
                result[ws_id] = root
    except (OSError, json.JSONDecodeError):
        pass
    return result


def load_session_index(home):
    """读取 session_index.jsonl，返回 {session_id: workdir} 映射（尽力而为）。"""
    index_file = home / "session_index.jsonl"
    result = {}
    if not index_file.is_file():
        return result
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
                if obj.get("sessionId") and obj.get("workDir"):
                    result[obj["sessionId"]] = obj["workDir"]
    except OSError:
        pass
    return result


def load_state(session_dir):
    """
    读取会话 state.json，返回 (workdir, title)。
    文件缺失或解析失败时返回 (None, "")。
    """
    state_file = session_dir / "state.json"
    if not state_file.is_file():
        return None, ""
    try:
        with open(state_file, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return data.get("workDir") or None, data.get("title") or ""
    except (OSError, json.JSONDecodeError):
        return None, ""


def resolve_session_workdir(session_dir, workspace_roots, session_index=None):
    """
    解析会话工作目录。
    顺序：state.json > session_index.jsonl > 父目录（workspace id）在 workspaces.json 中的 root > 空字符串。
    """
    workdir, _ = load_state(session_dir)
    if workdir:
        return workdir
    if session_index:
        session_id = session_dir.name
        if session_index.get(session_id):
            return session_index[session_id]
    workspace_id = session_dir.parent.name
    return workspace_roots.get(workspace_id, "")


def iter_main_wire_paths(home):
    """递归查找主会话 wire 文件，跳过 agents/agent-* 等子代理 wire。"""
    sessions_dir = home / "sessions"
    if not sessions_dir.is_dir():
        return
    for path in sorted(sessions_dir.glob("*/session_*/agents/main/wire.jsonl")):
        yield path


def iter_in_scope_main_wires(home, roots, workspace_roots, session_index=None):
    """
    遍历主会话 wire 文件，只产出工作目录位于项目范围之内的 (path, workdir)。
    工作目录缺失时视为不在范围内，避免把无关会话混入日报。
    """
    for path in iter_main_wire_paths(home):
        workdir = resolve_session_workdir(
            path.parent.parent.parent, workspace_roots, session_index
        )
        if roots and not matches_roots(workdir, roots):
            continue
        yield path, workdir


def _epoch_ms_to_local(ms):
    """将 Kimi Code 的 epoch 毫秒时间戳转换为本地 datetime，失败返回 None。"""
    try:
        return datetime.fromtimestamp(float(ms) / 1000).astimezone()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def extract_text_blocks(blocks):
    """
    从消息 content / input 块数组中提取纯文本。
    只保留 type == text 的块，跳过 image_url / video_url / file 等非文本块。
    """
    if not isinstance(blocks, list):
        return ""
    parts = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
            parts.append(block["text"])
    return "\n\n".join(parts)


def scan_wire_file(path, since, until, workdir, max_chars=2000):
    """
    扫描单个主会话 wire 文件，返回事件列表。
    事件: {date, time, project, session, title, role, text}
    """
    events = []
    session_id = path.parent.parent.name  # session_xxx
    _, title = load_state(path.parent.parent.parent)

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []

    # 助手文本按 (turnId, stepUuid) 合并，同一步的多个 text part 拼成一条
    pending_assistant = {"key": None, "text": "", "time": None}

    def flush_assistant():
        if not pending_assistant["text"]:
            return
        text = normalize_text(pending_assistant["text"], max_chars)
        local_dt = pending_assistant["time"]
        if text and local_dt is not None:
            local_date = local_dt.date()
            if since <= local_date <= until:
                events.append({
                    "date": local_date.isoformat(),
                    "time": local_dt.strftime("%H:%M"),
                    "project": workdir or "unknown",
                    "session": session_id,
                    "title": title,
                    "role": "assistant",
                    "text": redact_sensitive(text),
                })
        pending_assistant["key"] = None
        pending_assistant["text"] = ""
        pending_assistant["time"] = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        line_type = obj.get("type")

        if line_type == "turn.prompt":
            flush_assistant()
            origin = obj.get("origin") or {}
            if origin.get("kind") != "user":
                continue
            text = normalize_text(extract_text_blocks(obj.get("input")), max_chars)
            if not text:
                continue
            local_dt = _epoch_ms_to_local(obj.get("time"))
            if local_dt is None:
                continue
            local_date = local_dt.date()
            if not (since <= local_date <= until):
                continue
            events.append({
                "date": local_date.isoformat(),
                "time": local_dt.strftime("%H:%M"),
                "project": workdir or "unknown",
                "session": session_id,
                "title": title,
                "role": "user",
                "text": redact_sensitive(text),
            })
            continue

        if line_type == "context.append_loop_event":
            event = obj.get("event") or {}
            if event.get("type") != "content.part":
                continue
            part = event.get("part") or {}
            if part.get("type") != "text":
                continue  # think 等内部推理不输出
            part_text = part.get("text")
            if not part_text:
                continue
            step_key = (event.get("turnId"), event.get("stepUuid"))
            if pending_assistant["key"] == step_key:
                pending_assistant["text"] += "\n\n" + part_text
                continue
            flush_assistant()
            pending_assistant["key"] = step_key
            pending_assistant["text"] = part_text
            pending_assistant["time"] = _epoch_ms_to_local(obj.get("time"))
            continue

        # context.append_message / turn.steer / 工具事件 / usage 等均不直接产出消息

    flush_assistant()
    return events


def main():
    parser = argparse.ArgumentParser(
        description="提取本地 Kimi Code 会话记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD (默认: 今天)")
    parser.add_argument("--since", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--until", default=None, help="结束日期 YYYY-MM-DD (默认: 今天)")
    parser.add_argument("--roots", nargs="+", default=None, help="项目根目录列表 (覆盖默认配置)")
    parser.add_argument("--home", default=None, help="Kimi Code 数据目录 (覆盖自动查找)")
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
        or config.get("kimi", {}).get("max_chars")
        or config.get("max_chars")
        or 2000
    )
    home = resolve_kimi_home(
        args.home, config.get("kimi", {}).get("kimi_home") or None
    )

    log(f"🔍 Kimi Code 目录: {home}")
    log(f"📅 日期范围: {since.isoformat()} ~ {until.isoformat()}")
    if roots:
        log(f"📁 项目范围: {', '.join(roots)}")
    log()

    if not home.is_dir():
        log(f"⚠ Kimi Code 目录不存在: {home}")
        log("   跳过 Kimi Code 会话记录。")
        return

    workspace_roots = load_workspace_roots(home)
    log("📥 正在扫描会话记录...")
    events = []
    seen = set()
    file_count = 0

    session_index = load_session_index(home)
    for path, workdir in iter_in_scope_main_wires(
        home, roots, workspace_roots, session_index
    ):
        file_count += 1
        for ev in scan_wire_file(path, since, until, workdir, max_chars):
            # 去重：同一会话同角色同文本的消息只保留一条
            key = (ev["session"], ev["role"], ev["text"])
            if key in seen:
                continue
            seen.add(key)
            events.append(ev)

    log(f"   扫描 {file_count} 个主会话文件，提取 {len(events)} 条消息")

    if not events:
        log("\n> 🔍 在指定日期范围内未找到 Kimi Code 会话记录。")
        return

    if args.json:
        payload = {
            "source": "kimi-code",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "since": since.isoformat(),
            "until": until.isoformat(),
            "roots": roots,
            "events": events,
        }
        output_text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        output_text = format_events_report(
            title="# 🚀 每日 Kimi Code 会话记录",
            source="kimi-code 本地会话记录",
            events=events,
            since=since,
            until=until,
            assistant_label="Kimi",
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
