---
name: daily-work-summary
description: Use when the user asks for a Chinese daily work summary, work log, day-end review, or a summary generated from daily Git commits. Output is a plain text log with "工作内容", "工作思考", and "勤奋时间" sections. Includes bundled scripts for Git commit extraction and diligent time calculation.
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

## Git Commit Source

When the user asks to generate a daily summary from Git commits, use the bundled script `scripts/daily_git_commits.py` to extract commit data first.

Typical commands:

```bash
python scripts/daily_git_commits.py
python scripts/daily_git_commits.py --date 2026-04-13
python scripts/daily_git_commits.py --since 2026-04-01 --until 2026-04-13
python scripts/daily_git_commits.py --author heqidong --roots E:\Projects\Platforms\LowCode-All
```

Use script output as raw material only. Do not paste the Git report as the final answer. Do not mention or imply in the summary that content came from Git commits. Convert commit data into the daily log format above.

If the script finds no commits, say so and ask the user for additional work content. Override `--author`, `--date`, `--since`, `--until`, or `--roots` from the user request instead of editing the script.

## If Work Content Is Missing

If the user has not provided work content and has not asked to generate from Git commits, output exactly this text and stop:

```text
您好，作为您的工作总结撰写顾问，我会按照您的要求，为您撰写一份详细且客观的工作总结。请您先简单介绍一下今天的主要工作内容，我会从全局角度进行分析和总结，突出工作中的收获、挑战及改进空间。现在，请您开始讲述今天的工作情况吧。
```

Do not add any log sections to this initialization response.

## Writing Style

- Natural, conversational Chinese.
- Be specific about what was done, who was involved, and what was discussed.
- Keep technical terms in their original form.
- Avoid overly formal or bureaucratic language.
