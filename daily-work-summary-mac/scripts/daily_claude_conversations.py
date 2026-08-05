#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
每日 Claude Code 会话记录提取工具
=================================
读取本地 Claude Code 持久化的 JSONL 转录文件（~/.claude/projects 下），
提取用户消息和助手文本，按日期分组输出。只读取本地文件，不调用任何远程 API。

转录内容规则：
- 只保留 type 为 user / assistant / message 的消息，并按其 message.id 去重
- 只保留文本块（text / input_text），跳过 thinking、tool_use、tool_result、image 等块
- 跳过 isMeta 的系统注入消息（如 local-command 提示）
- 按 message.cwd 字段过滤项目范围，缺失时用项目目录名（路径编码形式）匹配
- 输出前对密钥、Token、私钥等敏感信息脱敏

用法:
    python scripts/daily_claude_conversations.py                          # 默认今天
    python scripts/daily_claude_conversations.py --date 2026-04-13        # 指定日期
    python scripts/daily_claude_conversations.py --since 2026-04-01 --until 2026-04-13
    python3 scripts/daily_claude_conversations.py --roots /Users/torchz/CetWorkspace
    python3 scripts/daily_claude_conversations.py --dir /Users/torchz/.claude/projects   # 指定转录目录
    python scripts/daily_claude_conversations.py --json --output report.json

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
    matches_munged,
    matches_roots,
    normalize_text,
    redact_sensitive,
    resolve_date_range,
    to_local_date,
    to_local_hm,
)

ensure_utf8_console()

# ==================== 配置区域 ====================

# 转录存储目录查找顺序：--dir > CLAUDE_CONFIG_DIR > config.json > ~/.claude/projects
CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
DEFAULT_HISTORY_DIR = Path.home() / ".claude" / "projects"

# ==================== 配置区域结束 ====================


def resolve_history_dir(explicit_dir=None, config_dir=None):
    """
    解析转录存储目录。
    优先级：--dir > CLAUDE_CONFIG_DIR > config.json 的 claude.history_dir > 默认。
    config.json 中 history_dir 为空时同样回退到默认自动查找。
    """
    if explicit_dir:
        return Path(explicit_dir)

    env_dir = os.environ.get(CLAUDE_CONFIG_DIR_ENV)
    if env_dir:
        base = Path(env_dir)
        # 环境变量可能指向配置目录本身，也可能直接指向 projects 目录
        if (base / "projects").is_dir():
            return base / "projects"
        return base

    if config_dir:
        base = Path(config_dir)
        if (base / "projects").is_dir():
            return base / "projects"
        return base

    return DEFAULT_HISTORY_DIR


def extract_message_text(content):
    """
    从 message.content 中提取纯文本。
    content 可能是字符串，也可能是块数组（text / thinking / tool_use / tool_result / image 等）。
    只保留 text 块的文本，跳过思考、工具调用、工具结果、图片。
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
        return "\n\n".join(parts)

    return ""


def scan_file(path, since, until, roots, max_chars=2000):
    """
    扫描单个转录文件，返回事件列表。
    每个事件: {date, time, project, session, role, text}
    按 message.id 对 user/assistant/message 三类消息去重，避免流式重复。
    """
    events = []
    folder = path.parent.name  # 路径编码的项目目录名，如 E--MyProjects-skills
    seen_message_ids = set()

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

        # 只处理消息类记录；ai-title / last-prompt / mode / attachment 等跳过
        msg_type = obj.get("type")
        if msg_type not in ("user", "assistant", "message"):
            continue

        # 系统注入的消息（local-command 提示等）跳过
        if obj.get("isMeta"):
            continue

        message = obj.get("message") or {}
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue

        # 同一消息在转录中可能以多条 type 记录出现，按 message.id 去重
        message_id = message.get("id")
        if message_id:
            if message_id in seen_message_ids:
                continue
            seen_message_ids.add(message_id)

        text = normalize_text(extract_message_text(message.get("content")), max_chars)
        if not text:
            continue

        # 过滤本地命令（/export、/plugin 等）和 local-command 提示等元消息噪音
        if text.lstrip().startswith(("<command-name", "<command-message")) or "<local-command" in text:
            continue

        local_date = to_local_date(obj.get("timestamp"))
        if local_date is None or not (since <= local_date <= until):
            continue

        cwd = obj.get("cwd") or ""
        # 缺 cwd 字段时用目录名（路径编码形式）匹配项目范围
        if roots and not (matches_roots(cwd, roots) or matches_munged(folder, roots)):
            continue

        events.append({
            "date": local_date.isoformat(),
            "time": to_local_hm(obj.get("timestamp")) or "",
            "project": cwd or folder,
            "session": obj.get("sessionId") or path.stem,
            "role": role,
            "text": redact_sensitive(text),
        })

    return events


def main():
    parser = argparse.ArgumentParser(
        description="提取本地 Claude Code 会话记录",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD (默认: 今天)")
    parser.add_argument("--since", default=None, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--until", default=None, help="结束日期 YYYY-MM-DD (默认: 今天)")
    parser.add_argument("--roots", nargs="+", default=None, help="项目根目录列表 (覆盖默认配置)")
    parser.add_argument("--dir", default=None, help="转录存储目录 (覆盖自动查找)")
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
        or config.get("claude", {}).get("max_chars")
        or config.get("max_chars")
        or 2000
    )
    history_dir = resolve_history_dir(
        args.dir, config.get("claude", {}).get("history_dir") or None
    )

    log(f"🔍 转录目录: {history_dir}")
    log(f"📅 日期范围: {since.isoformat()} ~ {until.isoformat()}")
    if roots:
        log(f"📁 项目范围: {', '.join(roots)}")
    log()

    if not history_dir.is_dir():
        log(f"⚠ 转录目录不存在: {history_dir}")
        log("   跳过 Claude Code 会话记录。")
        return

    log("📥 正在扫描转录文件...")
    events = []
    seen = set()
    file_count = 0

    for path in sorted(history_dir.rglob("*.jsonl")):
        file_count += 1
        for ev in scan_file(path, since, until, roots, max_chars):
            # 去重：同一会话同角色同文本的消息只保留一条
            key = (ev["session"], ev["role"], ev["text"])
            if key in seen:
                continue
            seen.add(key)
            events.append(ev)

    log(f"   扫描 {file_count} 个文件，提取 {len(events)} 条消息")

    if not events:
        log("\n> 🔍 在指定日期范围内未找到 Claude Code 会话记录。")
        return

    if args.json:
        payload = {
            "source": "claude-code",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "since": since.isoformat(),
            "until": until.isoformat(),
            "roots": roots,
            "events": events,
        }
        output_text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        output_text = format_events_report(
            title="# 💬 每日 Claude Code 会话记录",
            source="claude-code 本地转录",
            events=events,
            since=since,
            until=until,
            assistant_label="Claude",
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
