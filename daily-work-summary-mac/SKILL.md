---
name: daily-work-summary-mac
description: 在 macOS 上生成中文每日工作总结。当用户请求日报、工作日志或日终复盘时触发，从Git 提交记录和本地 Claude Code / Codex / Kimi Code 对话记录中提取数据，输出包含"工作内容"、"工作思考"和"勤奋时间"三个部分的纯文本日志。内置 Git 提交提取、Claude Code / Codex / Kimi Code 对话提取和勤奋时间计算脚本。
---

# macOS 每日工作总结

## 输出格式

生成如下结构的纯文本日志：

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

### 各部分规则

**工作内容**（必填）：
- 使用 `1. 2. 3. ...` 编号列表。
- 每条写一项工作活动，用完整中文句子，以 `。` 结尾。
- 要具体：写明项目名、功能名、相关人员。
- 会议/讨论类，简述主题和要点。
- 代码/文档类，写明在做什么。
- 面试类，简述结果。

**工作思考**（选填）：
- 编号列表。没有值得反思的内容时整个部分省略。
- 语气更口语化，可以用第一人称。
- 写收获、设计思考、经验教训或后续计划。

**勤奋时间**（自动计算）：
- 运行 `python scripts/calculate_diligent_time.py` 获取结束时间。
- 起始时间固定为 17:45，结束时间以 30 分钟为单位递增。
- 后接 `勤奋工作内容:` 描述加班期间做了什么。
- 如果脚本输出无有效时间（当前时间早于 18:15 或 17:45），则整个部分省略。

## 数据来源

默认在生成日报前运行**全部四个**提取器：Git 提交记录、本地 Claude Code 对话、本地 Codex 对话和本地 Kimi Code 对话。如果用户明确要求仅使用 Git 记录，则跳过对话提取器。对话记录仅读取本地文件，不调用任何远程 API。

### Git 提交记录

先使用内置脚本 `scripts/daily_git_commits.py` 提取提交数据。

常用命令：

```bash
python scripts/daily_git_commits.py
python scripts/daily_git_commits.py --date 2026-04-13
python scripts/daily_git_commits.py --since 2026-04-01 --until 2026-04-13
python3 scripts/daily_git_commits.py --author heqidong --roots /Users/torchz/CetWorkspace
```

### Claude Code 对话记录

使用内置脚本 `scripts/daily_claude_conversations.py` 提取本地 Claude Code 主会话转录（存储在 `~/.claude/projects` 下）。仅输出用户消息和助手文本，跳过子代理旁路、思考块、工具调用、工具结果、系统注入和敏感值。

常用命令：

```bash
python scripts/daily_claude_conversations.py
python scripts/daily_claude_conversations.py --date 2026-04-13
python scripts/daily_claude_conversations.py --since 2026-04-01 --until 2026-04-13
python3 scripts/daily_claude_conversations.py --roots /Users/torchz/CetWorkspace
python3 scripts/daily_claude_conversations.py --dir /Users/torchz/.claude/projects   # 指定转录目录
python scripts/daily_claude_conversations.py --json --output report.json
```

转录搜索顺序：`--dir` 参数 → `CLAUDE_CONFIG_DIR/projects` → `~/.claude/projects`。通过转录的 `cwd` 字段（回退到编码后的项目文件夹名）相对于项目根目录来筛选记录。`subagents/` 下的文件以及标记了 `isSidechain` 或 `agentId` 的记录会被排除。

### Codex 对话记录

使用内置脚本 `scripts/daily_codex_sessions.py` 提取本地 Codex CLI 会话（存储在 `~/.codex` 下）。读取 rollout JSONL 文件（旧版本回退到 `history.jsonl`），仅输出用户消息和助手文本，跳过注入的系统指令（AGENTS.md、环境上下文、审查模板）和敏感值。

常用命令：

```bash
python scripts/daily_codex_sessions.py
python scripts/daily_codex_sessions.py --date 2026-04-13
python scripts/daily_codex_sessions.py --since 2026-04-01 --until 2026-04-13
python3 scripts/daily_codex_sessions.py --roots /Users/torchz/CetWorkspace
python3 scripts/daily_codex_sessions.py --home /Users/torchz/.codex   # 指定 Codex 数据目录
python scripts/daily_codex_sessions.py --json --output report.json
```

数据搜索顺序：`--home` 参数 → `CODEX_HOME` → `~/.codex`。通过会话的 `cwd` 字段相对于项目根目录来筛选记录。

### Kimi Code 对话记录

使用内置脚本 `scripts/daily_kimi_sessions.py` 提取本地 Kimi Code 会话（存储在 `~/.kimi-code` 下）。读取 `~/.kimi-code/sessions/<workspace>/session_*/agents/main/wire.jsonl` 下的主会话 wire 文件，仅输出用户消息和助手文本，跳过子代理 wire（`agents/agent-*`）、思考块、工具调用/结果、系统注入和后台任务通知。

常用命令：

```bash
python scripts/daily_kimi_sessions.py
python scripts/daily_kimi_sessions.py --date 2026-04-13
python scripts/daily_kimi_sessions.py --since 2026-04-01 --until 2026-04-13
python3 scripts/daily_kimi_sessions.py --roots /Users/torchz/CetWorkspace
python3 scripts/daily_kimi_sessions.py --home /Users/torchz/.kimi-code   # 指定 Kimi Code 数据目录
python scripts/daily_kimi_sessions.py --json --output report.json
```

数据搜索顺序：`--home` 参数 → `KIMI_CODE_HOME` → `~/.kimi-code`。每个会话的工作目录从 `state.json` 读取，回退到 `session_index.jsonl` / `workspaces.json`；仅扫描项目根目录下的会话。

### 使用提取结果

脚本输出仅作为原始素材使用。不要将任何生成的报告直接作为最终输出。不要在总结中提及或暗示内容来自 Git 提交记录或对话转录。将所有记录数据转换为上述日志格式，遵循以下证据规则：

- 对话中的请求、提议或计划，如果没有观察到实际结果，视为讨论或待办事项，不能写成已完成的工作。用户明确声明任务已完成的，可以作为用户提供的事实记录。
- 助手文本本身只是上下文，不能作为完成证据；需要配合用户声明或 Git 变更才能描述为已处理的工作。
- 带有文件/diff 证据的 Git 提交是最强的交付证据。当对话活动和提交描述同一主题时，合并为一条工作项，不要重复。
- 未解决的问题、阻塞项和未完成的变更标记为待跟进，不要变成已完成项。
- 不要在最终总结中暴露转录路径、完整工具输出、内部推理、密码、令牌或其他敏感数据。

如果某个对话提取器未找到记录（目录不存在、文件不可读或时间范围内无数据），继续使用其余数据源，不要停止。仅在 Git-only 模式下，如果没有匹配的 Git 记录，提示用户补充工作内容。用户请求中的 `--date`、`--since`、`--until`、`--roots` 或数据源特定参数覆盖默认值，不要修改脚本。

## 缺少工作内容时

如果用户未提供工作内容，也未要求从日常记录（Git 提交、Claude Code、Codex 或 Kimi Code 对话）中生成，则输出以下文本并停止：

```text
您好，作为您的工作总结撰写顾问，我会按照您的要求，为您撰写一份详细且客观的工作总结。请您先简单介绍一下今天的主要工作内容，我会从全局角度进行分析和总结，突出工作中的收获、挑战及改进空间。现在，请您开始讲述今天的工作情况吧。
```

不要在这个初始化回复中添加任何日志部分。

## 写作风格

像跟同事口头说今天干了啥，不是写书面报告。

### 禁止项

- **不用破折号（——）**：用逗号或句号代替。
- **不用书名号《》包裹内部文档、规则、工具名**：直接写名字，如"骨架提取规则 v2"而不是"《原型图布局骨架提取规则》"。
- **不写嵌套从句**：一个句子只说一件事。"排查并解决了 X 导致 Y 的问题，定位为 Z"应拆成两句。
- **不用总结式动词链**：避免"分析了……确定……让……能……"这种链式结构。
- **不凑三段式并列**：两项就够了，不要凑三个。
- **不用"进行了""开展了"等万能动词**：直接说做了什么。

### 句式规则

- 一条工作内容只说一件事，15-30 字为宜，最长不超过 50 字。
- 能用短词就不用长词："搞定"优于"排查并解决"，"改了"优于"修改完善"，"加了"优于"新增"。
- 主语可以省略（日报默认主语是"我"）。
- 具体的项目名、功能名、人名要保留，但不需要解释它们的作用。
- 技术术语保持原样（如 JSON、schema、agent）。
- 变化句式，不要每条都是"动词+了+对象+目的"结构。

### 反面示例 → 正面示例

**反面（AI 味重）：**

```
1. 根据《原型图布局骨架提取规则》分析南网充电站运营看板原型图，提取布局骨架并生成 JSON 配置文件，多轮迭代产出 v3 版本。
2. 分析了视觉模型与 LLM 的协作契约设计，确定在组件列表中增加结构化的 style（样式）和 data（数据）描述字段，让 lowcode agent 能根据骨架直接创建出具体组件。
3. 排查并解决了 LowCode-Agent-Service 启动时 14010 端口被占用导致 EADDRINUSE 报错的问题，定位为同项目残留的旧实例进程。
```

**正面（像人说的）：**

```
1. 分析南网充电站运营看板原型图，提取布局骨架生成 JSON 配置，迭代到了 v3。
2. 梳理了视觉模型和 LLM 怎么协作，在组件列表里加了 style 和 data 字段，方便 lowcode agent 直接建组件。
3. LowCode-Agent-Service 启动报 EADDRINUSE，查下来是旧进程没杀干净占了 14010 端口，解决了。
```

### 交付前检查

- 有没有破折号（——）？换成逗号或句号。
- 有没有书名号《》？去掉。
- 单条超过 50 字？拆成两条或精简。
- 连续三条以上结构相同？调整其中一两条的写法。
- 读出来像在跟同事说话吗？不像就改。
