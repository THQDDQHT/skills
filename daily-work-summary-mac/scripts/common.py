#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
daily-work-summary-mac 共用工具
================================
供 daily_claude_conversations.py / daily_codex_sessions.py 共用：
日期范围解析、本地时间转换、目录匹配、敏感信息脱敏、文本规整、控制台编码处理。
"""

import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

# 默认扫描根目录（config.json 未配置或缺失时兜底，可被 --roots 覆盖）
DEFAULT_ROOTS = [
    "/Users/torchz/CetWorkspace",
]

# 配置文件位置：skill 根目录下的 config.json（与 scripts/ 平级）
CONFIG_FILENAME = "config.json"


def find_config_path(explicit=None):
    """定位配置文件：显式路径 > skill 根目录 config.json"""
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parent.parent / CONFIG_FILENAME


def load_config(explicit=None):
    """
    加载 config.json 并返回 dict。
    文件不存在或解析失败时返回空 dict，调用方回退到内置默认值。
    配置优先级（从高到低）：命令行参数 > 环境变量 > config.json > 代码内置默认值。
    """
    path = find_config_path(explicit)
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        print(f"⚠ 配置文件解析失败，使用内置默认值: {path}", file=sys.stderr)
        return {}


def ensure_utf8_console():
    """确保控制台以 UTF-8 输出。"""
    if sys.stdout.encoding != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr.encoding != "utf-8":
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def resolve_date_range(date_arg, since_arg, until_arg):
    """
    将 --date / --since / --until 解析为 (起始日期, 结束日期) 两个 date 对象。
    --date 优先；否则默认今天到今天。
    """
    today = date.today()
    if date_arg:
        d = date.fromisoformat(date_arg)
        return d, d
    since = date.fromisoformat(since_arg) if since_arg else today
    until = date.fromisoformat(until_arg) if until_arg else today
    return since, until


def to_local_date(ts):
    """
    将 ISO 时间戳（Z 或带时区偏移）转换为本地日期，返回 date 或 None。
    Claude Code / Codex 记录的时间戳均为 UTC ISO 格式，需先转本地时区。
    """
    if not ts:
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.date()


def to_local_hm(ts):
    """将 ISO 时间戳转换为本地 HH:MM，返回字符串或 None"""
    if not ts:
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%H:%M")


def matches_roots(cwd, roots):
    """cwd 是否位于任一 root 之下（路径匹配忽略大小写）。"""
    if not cwd:
        return False
    cwd_n = cwd.replace("/", "\\").rstrip("\\").lower()
    for root in roots:
        r_n = root.replace("/", "\\").rstrip("\\").lower()
        if cwd_n == r_n or cwd_n.startswith(r_n + "\\"):
            return True
    return False


def munged_path(path):
    """将路径转成 Claude Code 项目目录名形式：分隔符和冒号替换为 '-'"""
    return path.replace(":", "-").replace("/", "-").replace("\\", "-").replace(" ", "-")


def matches_munged(folder, roots):
    """
    当转录行内没有 cwd 字段时，用 Claude Code 编码后的项目目录名匹配根目录。
    目录名编码是单向的，因此只做前缀匹配。
    """
    for root in roots:
        m = munged_path(root)
        if folder == m or folder.startswith(m + "-"):
            return True
    return False


# ==================== 敏感信息脱敏 ====================

_REDACT_PATTERNS = [
    # PEM 私钥块
    (
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            re.S,
        ),
        "[REDACTED PEM]",
    ),
    # Authorization: Bearer xxx
    (re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    # OpenAI / Anthropic 风格 API Key
    (re.compile(r"\b(?:sk|sk-ant|sk-proj)-[a-zA-Z0-9_-]{10,}\b"), "[REDACTED API KEY]"),
    # GitHub Token
    (re.compile(r"\bghp_[a-zA-Z0-9]{20,}\b"), "[REDACTED TOKEN]"),
    # AWS Access Key
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED KEY]"),
    # URL 中内嵌的账号密码
    (re.compile(r"(https?://)[^/@\s]+@"), r"\1[REDACTED]@"),
]


def redact_sensitive(text):
    """将文本中的密钥、Token、私钥等替换为占位符"""
    if not text:
        return text
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def normalize_text(text, max_chars=2000):
    """规整文本：统一换行、压缩空行、截断超长内容"""
    text = (text or "").replace("\r\n", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


# ==================== 报告格式化 ====================

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _render_multiline(text, indent="    "):
    """多行文本渲染：首行内联，其余行缩进对齐"""
    lines = text.split("\n")
    result = lines[0]
    for line in lines[1:]:
        result += "\n" + indent + line
    return result


def format_events_report(title, source, events, since, until, assistant_label):
    """
    将会话事件渲染为 Markdown 报告。
    events: [{date, time, project, session, title, role, text}]，role 为 user / assistant。
    按 日期 → 项目 → 会话 分组，会话内按时间排序。
    """
    from collections import defaultdict

    lines = []
    lines.append(title)
    lines.append(f"**来源**: {source}")
    lines.append(f"**日期范围**: {since.isoformat()} ~ {until.isoformat()}")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    sessions = {(ev["date"], ev["project"], ev["session"]) for ev in events}
    lines.append(f"**统计**: 共 **{len(sessions)}** 个会话，**{len(events)}** 条消息")
    lines.append("")
    lines.append("---")
    lines.append("")

    by_date = defaultdict(list)
    for ev in events:
        by_date[ev["date"]].append(ev)

    for date_str in sorted(by_date.keys(), reverse=True):
        date_events = by_date[date_str]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        lines.append(f"## 📅 {date_str} ({WEEKDAY_NAMES[dt.weekday()]})")
        lines.append("")

        by_project = defaultdict(list)
        for ev in date_events:
            by_project[ev["project"]].append(ev)

        for project in sorted(by_project.keys()):
            lines.append(f"### 📁 {project}")
            lines.append("")

            by_session = defaultdict(list)
            for ev in by_project[project]:
                by_session[ev["session"]].append(ev)

            for session in sorted(by_session.keys()):
                sess_events = sorted(by_session[session], key=lambda e: e["time"])
                title_text = sess_events[0].get("title") or ""
                time_start = sess_events[0]["time"]
                time_end = sess_events[-1]["time"]

                header = f"#### 💬 {session[:8]}"
                if title_text:
                    header += f" · {title_text}"
                header += f"  ({time_start} ~ {time_end})"
                lines.append(header)
                lines.append("")

                for ev in sess_events:
                    label = "用户" if ev["role"] == "user" else assistant_label
                    body = _render_multiline(ev["text"])
                    lines.append(f"- **{ev['time']} {label}**: {body}")
                lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
