# AGENTS.md — 项目开发强制纪律

本文件由 AI4SE 期末项目通用要求与 Coding Agent Harness 项目要求提炼生成。所有开发会话必须强制执行以下规则。

## 一、流程硬性要求（每项开发都须按序执行）

1. **brainstorming 先行**：任何功能 / 组件 / 行为修改前，必须先调用 brainstorming 技能澄清需求与设计，产出可签名确认的 Spec。禁止跳过讨论直接写代码。
2. **plan 先行**：设计签字后，调用 writing-plans 技能将设计拆为 task 列表（每 task 2–5 分钟、明确文件路径、明确验证步骤、标出依赖与可并行部分）。保存为 PLAN.md。在 SPEC 与 PLAN 完成并通过冷启动验证之前，禁止编写任何实现代码。
3. **git worktree 隔离（强制）**：每个独立功能 / 大模块必须在独立 worktree 中开发，对应一个独立分支，完成时通过 PR 合回 main。禁止直接在 main 上开发并推送。worktree 目录统一放在 `.worktrees/<功能名>/`，必须加入 .gitignore。
4. **TDD 强制**：先写失败测试得到红色结果 → 再写最小实现使其变绿 → 再重构。禁止"先写实现再补测试"。
5. **Subagent 派发**：每个 task 由新鲜且独立的 subagent 完成。
6. **两阶段评审**：每个 task 完成后先做 spec 合规检查，再做代码质量检查。Critical issue 必须修复才能进入下一 task。
7. **完成分支**：所有 task 完成后，用 finishing-a-development-branch 技能决定 merge / PR / 保留 / 丢弃。
8. **验证后才宣称完成**：提交 / PR 前必须实际运行测试与 CI 命令，报告真实结果，禁止凭预期声称"通过"。

## 二、文档维护（持续更新）

- **PLAN.md**：每完成一个 task 即标记完成，并附 commit hash，持续更新。
- **AGENT_LOG.md**：按时间顺序记录关键节点。每条包含：时间戳与 task 编号、触发的 Superpowers 技能、关键 prompt / context 配置、subagent 输出的关键片段或 commit hash、人工干预（修改了什么、为什么）、学到的教训。
- **SPEC_PROCESS.md**：记录 brainstorming 过程、至少 3 轮关键迭代对话与决策、采纳 / 推翻的 AI 建议、以及"陌生 agent 冷启动验证"的结果与对 spec/plan 的修订。
- **REFLECTION.md**：学期末写反思报告（1500–2500 字），必须由本人撰写。

## 三、凭据安全（必做）

- API key 绝不硬编码进源码、绝不提交进 Git（含历史）、绝不写入日志 / 终端 history / 明文配置文件。
- key 通过操作系统钥匙串（Windows Credential Manager / keyring）或 .env 文件存储；首次运行引导安全录入（隐藏输入）；可查看 / 更新 / 清除（查看状态不得回显明文）。.env 为明文，须在 SPEC 安全一节说明风险。

## 四、Harness 项目专属纪律（A）

- **机制必须是代码，不能是提示词**：反馈信号 = 校验器 / 传感器（解析产物 → 客观判定 → 回灌）；危险动作拦截 = 护栏代码（识别 → 拦截 → 人工确认），绝不能是系统提示里的一句"注意安全"。**禁止把"机制"写成提示词去指望 LLM 照做**：需要落地执行 / 拦截 / 判定的环节必须由你编写确定性代码完成，LLM 只负责"生成内容 / 决策方向"，是否执行、是否拦截、是否结束由代码判定。
- **判定标准**：移除真实 LLM、替换为 mock / stub LLM 后，每个核心机制（工具分发、治理拦截、反馈回灌、记忆读写、停机）仍能用确定性单元测试验证。无法脱离 LLM 验证的"机制"不计入实现。
- 核心机制必须有 mock / stub LLM 的确定性单元测试（不依赖网络与真实 LLM）。
- 提交机制演示：mock LLM 下确定性复现 ① 护栏拦截危险动作；② 注入失败 → 反馈闭环 → agent 改变下一步；③ 重点维度的确定性行为。
- 主循环自研，不允许基于现成 agent 编排框架（LangChain AgentExecutor / AutoGen / CrewAI 等）的高层循环。

## 五、测试与 CI

- 一键测试命令（make test 或等价），覆盖核心功能。
- CI（GitHub Actions）：每次 push 自动运行测试；若选容器分发还须构建镜像。
- 仓库禁止出现任何真实凭据——提交前自查 .env、history、配置文件。

## 六、提交纪律

- 完整 commit 历史与 PR 工作流：拒绝单次 commit 提交全部代码；每个 worktree 对应一个 PR。
- commit message / PR 描述标注：由哪个 subagent 完成、人工修改了哪些部分。
- **单仓库维护（强制，自 2026-08-31 起）**：旧仓库 `Coding-Agent-Harness`（remote `origin`）已弃置，不再同步、不再维护、不再推送。**所有开发、提交、发布一律只基于并只推送到新仓库 `Coding-Agent`（remote `coding-agent`）**。
  - `coding-agent` → `https://github.com/clementineyyy/Coding-Agent.git`
  - 本地若仍指向旧仓库的 checkout/worktree，仅作参考，禁止向旧仓库 push 任何内容。
  - commit 时间使用**实际提交时刻**（不重建日期）。
- **自动发布 PyPI（强制，发布源 = 新仓库 Coding-Agent）**：每完成一个修复 / 一个新功能（攒批验证通过后）即自动走发布流程，无需等待人工指令。**Python 包一律基于 `Coding-Agent`（新仓库，唯一发布源）发布**，并确保新仓库 Releases 页持续有记录：
  1. `pyproject.toml` bump 版本（patch 修复 +0.0.1；新功能 +0.1.0）。
  2. 在 `Coding-Agent` 提交一次 bump（`chore: bump version to X.Y.Z`），push 到 `coding-agent` remote。
  3. **Coding-Agent 的 CI 必须通过**（底线：CI 不绿不得发布，也禁止在 CI 未绿时打 tag）。
  4. **在 Coding-Agent（新仓库，remote `coding-agent`）打 `vX.Y.Z` tag 并 push**（触发新仓库 `publish.yml` 自动 build + trust-publisher 发 PyPI）——**不在 Harness(origin) 打发布 tag**。
  5. 同时在 Coding-Agent 创建 **GitHub Release**（tag=vX.Y.Z、标题、变更说明），确保新仓库 Releases 页有版本记录。
  6. 等待新仓库 publish workflow success，并确认 PyPI 最新版本 === X.Y.Z。
  7. `pip install --no-cache-dir nju-coding-agent-harness==X.Y.Z` 到临时 venv 真实验证安装与 import。
  8. 验证通过后才可声称"已发布"。
  - **Harness(origin) 不再承担发布**：它只负责完整工程与过程文档，发布 tag/Release 一律落在 Coding-Agent。
- 最终交付物：SPEC.md、PLAN.md、SPEC_PROCESS.md、README.md、AGENT_LOG.md、CI 配置、REFLECTION.md、源码（含 mock-LLM 单测与机制演示）。Coding-Agent 仓库不含 docs/scripts（已在历史中剔除并重建日期）。