---
name: daily-work-summary
description: Use when the user asks for a Chinese daily work summary, work log, day-end review, or a summary generated from daily Git commits and local Claude Code / Codex conversation records. Output is a plain text log with "工作内容", "工作思考", and "勤奋时间" sections. Includes bundled scripts for Git commit extraction, Claude Code / Codex conversation extraction, and diligent time calculation.
---

# Daily Work Summary

## Output Format

Generate a plain text daily log following this structure:

```text
工作内容：
1. 参加低代码平台晨会，同步了当前的问题处理进度。
2. 处理了社招人员的招聘申请流程。
3. 参与讨论了图形组态工具的应用场景。
4. 和张三碰了一下分组汇总算子的设计方案。结合市面上的竞品，仔细梳理了各种应用场景，对于用户交互和配置项的设计有了更清晰的想法。
5. 编写并完善通用计算引擎一阶段的需求文档。
6. 参加技术部周例会。

工作思考：
1. 今天重点琢磨了分组汇总算子。在对比了几个主流工具后，我发现交互设计的关键在于如何平衡"灵活性"和"易用性"。之前我们的设计有点过于追求大而全，反倒增加了用户的理解成本。接下来的设计里，我觉得应该做减法，把最核心的配置项暴露出来，其他的折叠或者由系统智能推导。

[勤奋时间][17:45][19:45]
勤奋工作内容: 继续深入完善通用计算引擎的需求文档
```

### Section Rules

**工作内容** (required):
- Numbered list using `1. 2. 3. ...` format.
- Each item is one work activity, written as a complete Chinese sentence ending with `。`.
- Be specific: include project names, feature names, people's names where relevant.
- For meetings/discussions, briefly state the topic and key points.
- For code/document work, state what was being worked on.
- For interviews, briefly note the result.

**工作思考** (optional):
- Numbered list. Omit the entire section when there is nothing meaningful to reflect on.
- More conversational tone. First person is fine.
- Describe insights, design considerations, lessons learned, or follow-up plans.

**勤奋时间** (auto-calculated):
- Run `python scripts/calculate_diligent_time.py` to get the end time.
- Start time is always 17:45. End time is in 30-minute increments from 17:45.
- Followed by `勤奋工作内容:` describing what was done during overtime.
- If the script outputs no valid time (before 18:15 or before 17:45), omit the entire section.

## Record Sources

By default, run **all three** extractors before writing a daily summary: Git commits, local Claude Code conversations, and local Codex conversations. If the user explicitly asks for Git records only, use Git-only mode and skip the conversation extractors. Conversation records only read local files and never call any remote API.

### Git Commit Source

Use the bundled script `scripts/daily_git_commits.py` to extract commit data first.

Typical commands:

```bash
python scripts/daily_git_commits.py
python scripts/daily_git_commits.py --date 2026-04-13
python scripts/daily_git_commits.py --since 2026-04-01 --until 2026-04-13
python scripts/daily_git_commits.py --author heqidong --roots E:\Projects\Platforms\LowCode-All
```

### Claude Code Conversation Source

Use the bundled script `scripts/daily_claude_conversations.py` to extract local Claude Code transcripts (stored under `~/.claude/projects`). It emits user messages and assistant text only, skipping thinking blocks, tool calls, tool results, system injections, and sensitive values.

Typical commands:

```bash
python scripts/daily_claude_conversations.py
python scripts/daily_claude_conversations.py --date 2026-04-13
python scripts/daily_claude_conversations.py --since 2026-04-01 --until 2026-04-13
python scripts/daily_claude_conversations.py --roots E:\MyProjects\skills
python scripts/daily_claude_conversations.py --dir D:\some\.claude\projects   # 指定转录目录
python scripts/daily_claude_conversations.py --json --output report.json
```

Transcript search order: `--dir` argument, then `CLAUDE_CONFIG_DIR/projects`, then `~/.claude/projects`. Records are selected by the transcript `cwd` field (falling back to the encoded project folder name) relative to the project roots.

### Codex Conversation Source

Use the bundled script `scripts/daily_codex_sessions.py` to extract local Codex CLI sessions (stored under `~/.codex`). It reads the rollout JSONL files (with `history.jsonl` as fallback for older versions), emits user messages and assistant text only, skipping injected system instructions (AGENTS.md, environment context, review templates) and sensitive values.

Typical commands:

```bash
python scripts/daily_codex_sessions.py
python scripts/daily_codex_sessions.py --date 2026-04-13
python scripts/daily_codex_sessions.py --since 2026-04-01 --until 2026-04-13
python scripts/daily_codex_sessions.py --roots E:\MyProjects\skills
python scripts/daily_codex_sessions.py --home D:\some\.codex   # 指定 Codex 数据目录
python scripts/daily_codex_sessions.py --json --output report.json
```

Data search order: `--home` argument, then `CODEX_HOME`, then `~/.codex`. Records are selected by the session `cwd` field relative to the project roots.

### Using the Output

Use script output as raw material only. Do not paste any generated report as the final answer. Do not mention or imply in the summary that content came from Git commits or conversation transcripts. Convert all record data into the daily log format above, following these evidence rules:

- A conversation request, proposal, or plan without an observed result is a discussion or pending work; never write it as completed work. A user's explicit statement that a task was completed may be recorded as a user-provided fact.
- Assistant text alone is context, not completion evidence; pair it with a user statement or a Git change before describing handled work.
- A Git commit with its file/diff evidence is stronger delivery evidence. When conversation activity and a commit describe the same topic, merge them into one work item instead of repeating.
- Mark unresolved questions, blocked items, and unfinished changes as pending follow-up; do not turn them into completed items.
- Do not expose transcript paths, complete tool output, internal reasoning, passwords, tokens, or other sensitive data in the final summary.

If a conversation extractor finds no records (missing directory, unreadable files, or empty range), continue with the remaining sources instead of stopping; only in Git-only mode, say no matching Git records were found and ask the user for additional work content. Override `--date`, `--since`, `--until`, `--roots`, or source-specific arguments from the user request instead of editing the scripts.

## Configuration

All scan directories and per-source settings live in `config.json` at the skill root, so the user can adjust them without editing code:

```json
{
  "scan_roots": ["E:\\Projects\\Platforms\\LowCode-All"],
  "max_chars": 2000,
  "git": {
    "author": "heqidong",
    "max_depth": 4
  },
  "claude": {
    "history_dir": "",
    "max_chars": null
  },
  "codex": {
    "codex_home": "",
    "max_chars": null
  }
}
```

- `scan_roots`: root directories scanned by all three extractors (Git, Claude Code, Codex); `--roots` overrides it.
- `max_chars`: max characters per message for both conversation extractors. A source's `max_chars` of `null` (or missing) inherits the top-level value; a non-null value overrides it. Set a per-source value only when that source needs a different cap.
- `git.author`: Git commit author; `--author` overrides it.
- `git.max_depth`: max recursion depth when locating Git repos.
- `claude.history_dir`: Claude Code transcript directory; empty string means auto-discovery (`CLAUDE_CONFIG_DIR`, then `~/.claude/projects`); `--dir` overrides it.
- `codex.codex_home`: Codex data directory; empty string means auto-discovery (`CODEX_HOME`, then `~/.codex`); `--home` overrides it.

Configuration priority (high to low): command-line arguments > environment variables (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) > `config.json` > built-in defaults.

## If Work Content Is Missing

If the user has not provided work content and has not asked to generate from daily records (Git commits, Claude Code, or Codex conversations), output exactly this text and stop:

```text
您好，作为您的工作总结撰写顾问，我会按照您的要求，为您撰写一份详细且客观的工作总结。请您先简单介绍一下今天的主要工作内容，我会从全局角度进行分析和总结，突出工作中的收获、挑战及改进空间。现在，请您开始讲述今天的工作情况吧。
```

Do not add any log sections to this initialization response.

## Writing Style

- Natural, conversational Chinese.
- Be specific about what was done, who was involved, and what was discussed.
- Keep technical terms in their original form.
- Avoid overly formal or bureaucratic language.
