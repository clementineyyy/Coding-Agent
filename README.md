# Coding Agent Harness

一个真实的编码智能体框架（Python 3.11+，Windows/Linux）：以 WebUI 交互为核心，
内置治理护栏、自适应策略、反馈闭环、上下文预算与压缩；全量测试离线、确定性可复现（FakeLLM +
MockTransport），已发布至 PyPI。
## 项目组件图

![组件图](FullPic.jpg)



## 目录结构

```
Coding-Agent/
├── AGENTS.md                   # 项目开发强制纪律
├── harness/                    # 核心包（运行时）
│   ├── __init__.py
│   ├── main.py                 # REPL 入口（console script `cah`）
│   ├── agent.py                # 任务循环：记忆检索 → 迭代 → 收尾整合
│   ├── llm.py                  # OpenAI 兼容客户端（流式 / tool_calls）
│   ├── credentials.py          # 凭据：keyring → .env → 向导
│   ├── config.py               # Config 配置（支持 TOML 加载）
│   ├── guardrails.py           # 护栏：内置 deny 清单 + 判定
│   ├── policy.py               # 自适应策略（ask 升降级、/rules）
│   ├── state.py                # 状态机（HITL 交互主轴）
│   ├── hooks.py                # 钩子总线（pre/post/session_end）
│   ├── transcript.py           # SessionEnd 转录
│   ├── memory.py               # TF-IDF 记忆存储与检索
│   ├── registry.py             # 工具注册表（内置 + MCP）
│   ├── sandbox.py              # LocalSandbox / DockerSandbox
│   ├── mcp.py                  # MCP 客户端（stdio / url）
│   ├── fake_llm.py             # 离线测试用 FakeLLM
│   ├── feedback.py             # 反馈闭环：Validator + FeedbackLoop
│   ├── task_executor.py        # 冷启动任务执行器
│   ├── tools/                  # 内置工具：bash / files / search / web /
│   │                           #   notes / memory / skills / subagent / ask
│   └── webui/                  # WebUI 交互
├── harness/tests/              # 全部测试（离线、确定性）
├── .github/workflows/          # ci.yml（test+build）/ publish.yml（PyPI 发布）
├── Makefile                    # make test / demo / install
├── pyproject.toml              # 包定义（[project.scripts] cah）
└── README.md
```

运行时在工作区生成（已被 `.gitignore` 排除）：`memory/`（记忆）、
`skills/`（技能）、`transcripts/`（转录）、`.env`（密钥凭据）。

## 快速开始

1. **安装**（PyPI 分发，任选其一）： 
   -  **PyPI 安装**（推荐，主分发形态）：

   ```bash
   pip install nju-coding-agent-harness
   ```

   -  **源码分发**（获取最新/参与开发）：

   ```bash
   git clone https://github.com/clementineyyy/Coding-Agent.git
   cd Coding-Agent
   pip install -e ".[dev]"
   ``` 

2. **配置 API Key**：使用 .env 文件配置（见下文
   "凭据安全"）。

3. **运行**：

   ```bash
   python -m harness.main    # REPL 交互
   cah --web                 # 启动 WebUI（http://localhost:8756）
   ```

# 凭据安全

- **来源**：项目根目录 `.env` 文件（`LLM_API_KEY=...`）
- **`.env` 明文风险**：`.env` 文件是本地明文（`LLM_API_KEY=...`），
  且其中的值会进入进程环境、对同一用户的其他进程可见；不提交进 Git
  （仓库已通过 `.gitignore` 排除 `.env`，凭据扫描测试
  `harness/tests/test_security_scan.py` 会检查 key 不落入源码/历史/转录）。

- **兜底安全**：key 永不写入日志、转录、记忆或策略文件。


## 六维度组件

harness 的六个核心维度（决策封装、动作/工具、上下文与记忆、治理护栏、
反馈闭环、配置）按以下组件落地：

| 维度 | 组件 | 验证要点 |
|---|---|---|
| 决策封装 | `agent.py` 主循环 + `llm.py` | 组织上下文 → 调用 LLM → 解析要执行的动作 |
| 动作 / 工具 | `registry.py` + `tools/`（bash/files/search/web/notes/memory/ask） | 作用于外部世界（读写文件/执行命令/访问网络），结果回灌给 LLM |
| 上下文与记忆 | `memory.py`（TF-IDF）+ `agent.py`（预算/压缩/多轮历史） | 决定向模型提供哪些信息，多轮、跨会话组织与检索 |
| 治理护栏 | `guardrails.py` / `policy.py` / `state.py` / `sandbox.py` | 危险动作执行前拦截，必要时暂停等人审（HITL），用沙箱/边界限制行动空间 |
| 反馈闭环 | `agent.py`/ `feedback.py`（失败预算/错误回灌） | 让 agent 获得"行为是否正确"的客观信号，据此自我修正 |
| 配置 | `config.py`（TOML）/ 策略规则| 让使用者通过声明式规则约束 agent 行为（`/rules`、TOML 配置） |
## 功能规格（Function Specification）

每个功能块按五个维度描述：**输入 / 行为 / 输出 / 边界条件 / 错误处理**。

### 1. 纯 LLM（模型交互）

- **输入**：消息列表（系统提示词 + 历史）、`tools=` 模式（来自工具注册表）、
  模型配置（base_url、model、凭据来源）
- **行为**：调用 DeepSeek chat completions（`stream=True`），将流式文本实时
  转发到终端；解析回合中的 `tool_calls`；每回合统计 token 用量
- **输出**：流式文本 + 可选的 `tool_calls`；无工具调用时
  即为最终答案，任务进入收尾
- **边界条件**：模型默认 `deepseek-chat`（可配置）；上下文预算检查（超出先压缩）；步数上限（默认 50）终止失控循环
- **错误处理**：API 错误（密钥错误、限流、网络）→ 明确提示，会话存活；
  限流退避重试一次。
### 2. 动作/工具（注册表与执行）

- **输入**：模型发出的 `tool_calls`（工具名 + JSON 参数）
- **行为**：注册表查表 → 参数 JSON 校验 → 按工具选择沙箱执行器 → 执行
  （超时）→ 结果返回
- **动作即工具调用**：agent 对世界的一切干预都通过工具完成。内置工具录如下：

| 工具 | 功能（agent 能做什么） | 关键参数 | 返回内容 | 护栏覆盖 |
|---|---|---|---|---|
| `bash` | 执行 shell 命令：运行构建 / 测试 / lint / 类型检查 | `command`, `timeout` | stdout、stderr、exit_code | 是；网络切换需 ask |
| `files`(`read_file` / `write_file` / `list`) | 读写 / 列出工作区文件 | `path`, `content` | 文件内容或写入结果 | 是；敏感文件 ask、工作区外 deny |
| `search` | 在工作区内按文件名 / 内容搜索 | `pattern`, `path` | 匹配列表 | 是；仅限工作区路径 |
| `web` | 抓取 URL 内容（`fetch_url`） | `url` | 页面文本 | 是；开启网络需 ask |
| `notes` | 便签追加 / 列出（跨回合临时要点，不写入长期记忆） | `text` | 追加确认 / 便签内容 | 是 |
| `memory_save` / `memory_search` | 长期记忆写入 / 按需检索| `title`, `content` / `query`, `k` | 保存确认 / 检索结果块 | 是 |

- **输出**：`role: "tool"` 结果消息，追加进对话历史
- **边界条件**：只接受注册表内工具；参数必须通过 JSON schema 校验；单次执行超时（默认 30s）；文件/搜索类工具仅限工作区路径（规范化防 `..` 与
  符号链接逃逸）；危险操作由护栏先行把关
- **错误处理**：工具异常 → 格式化的错误信息作为结果返回给模型
  （模型可自我纠正，配合反思）。

### 3. 上下文工程（记忆、RAG、压缩）

- **输入**：长期记忆库（`memory/*.md`）、当前消息历史、上一轮对话历史、token 预算
- **行为**：任务开始时按 TF-IDF 检索 top-2 相关块注入上下文；多轮对话上一轮完整消息历史作为上下文传入（`agent.run(task, history=...)`），
  支持连续追问与补充需求；提供 `memory_save` / `memory_search` 工具；每次
  调用前做预算检查，超出则触发自动压缩（模型将较旧回合总结为一条精简系统
  消息，保留最近 N 回合完整）
- **输出**：注入的上下文消息；压缩后的消息历史；压缩/检索的近似 token 账目
- **边界条件**：检索为纯标准库 TF-IDF；
  压缩设置步数上限防死循环；任务结束时在 SessionEnd 钩子**之后**执行
  记忆整合（总结本次会话经验并写入 `memory/`）
- **错误处理**：记忆文件损坏 → 跳过并警告；检索失败 → 返回空结果，不阻塞
  任务；压缩失败 → 保留原历史并降级为丢弃最旧回合

### 4. 钩子与护栏（安全）

- **输入**：工具调用请求、策略规则表、用户回答（y/n、"总是允许"/"绝不允许"、
  菜单选择）
- **行为**：护栏先行判定（allow / ask / deny，规则表有序、最后匹配生效）；
  ask 时转入 `awaiting_user` 状态并渲染 HITL 菜单；回答反馈进自适应策略
  （"总是允许"降级该规则、"同一模式拒绝两次"自动升级 deny、反复批准自动降级 allow）；通过护栏后依次触发 PreToolUse → 执行 → PostToolUse 钩子；
  任务收尾时触发 SessionEnd 钩子
- **输出**：判定结果与策略更新；钩子观察记录；拒绝原因作为结果回传给模型
- **边界条件**：技能声明的规则仅可收紧（ask/deny，allow 声明被丢弃）；
  用户产生的规则永远优先于技能规则；ask 判定必须等待用户，不能超时放行。
- **错误处理**：钩子异常仅记日志，绝不致命；护栏判定优先于一切，拒绝不可被钩子复活

### 5. 反馈循环（自我反思与修正）

- **输入**：工具结果（含错误、护栏拒绝、失败的命令/测试）
- **客观反馈信号**：每次工具结果都会回灌给模型，作为"行为是否正确"的
  确定性证据——`exit_code`（非 0 = 失败）、`is_error`（工具级错误）、
  stdout/stderr 输出（测试 / lint / 类型检查的实际结果）、护栏拒绝 reason。
  这些信号客观、确定、可回灌，构成自我修正的输入；错误处理已保证错误以格式化文本返回、绝不抛异常，模型因此总能读到反馈
- **行为**：工具失败或护栏拒绝后，模型自主反思，追加进上下文，再继续迭代；反思结果计入步数
- **输出**：反思消息；修正后的新一轮工具调用或最终答案
- **边界条件**：连续失败预算（默认 3 次同类失败）→ 停止并汇总问题报告给用户，不再盲目重试
- **错误处理**：反思本身失败 → 直接继续，不阻塞任务
  
### 6. 配置

- **输入**：三来源叠加——① `Config` dataclass 字段默认值；② 当前目录 `.env` 文件（`DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` / `SANDBOX_BACKEND`）及同名环境变量；③ TOML 配置文件（`cah --config config.toml`）
- **行为**：`Config.load()` 按优先级叠加——先取默认值，再读 `.env` / 环境变量覆盖，最后 TOML 覆盖（仅识别 `Config` 已知字段）。
- **输出**：`Config` dataclass 实例
- **边界条件**：`.env` 不存在或解析异常 → 静默跳过，不报错；TOML 文件不存在 → 返回默认值；TOML 解析失败 → `warnings.warn` 并返回默认值，不崩溃；TOML 中未知字段 → 静默忽略；`workspace` 自动转为 `Path` 类型
- **错误处理**：TOML 解析异常 → 仅警告，不影响后续启动；`.env` 读取异常 → 返回空 dict，不阻塞；缺失必要字段（如 API Key）→ 在启动时引导录入，Config 不负责校验








## 测试

[![CI](https://github.com/clementineyyy/Coding-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/clementineyyy/Coding-Agent/actions/workflows/ci.yml)

**一键运行**（GitHub Actions CI 与本地使用同一命令）：

```bash
make test
```

- `make test` 自动完成：`.venv` 不存在则创建 → `pip install -e ".[dev]"`
  → `pytest harness/tests -q`（Windows 用 `.venv\Scripts\python.exe`，
  POSIX 用 `.venv/bin/python`，Makefile 内通过 `$(OS)` 自动判断）。
- **GitLab 镜像仓库 CI**：仓库根目录 `.gitlab-ci.yml` 提供名为 `unit-test`
  的 job（与本地同一命令，push 时触发）。
- **Windows 无 make** 时的等价命令：

  ```powershell
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -e ".[dev]"
  .venv\Scripts\python.exe -m pytest harness/tests -q
  ```

- 只安装不跑测试：`make install`。

### 机制演示

`make demo` 顺序运行三个机制演示脚本（全部退出码 0 即通过）：

-  **demo_1_guardrail_deny** — 护栏拦截危险动作：FakeLLM 请求
   `rm -rf` 系统根目录等**不可逆破坏操作**时，护栏在**执行前**拒绝（deny），
   绝不让危险命令进入沙箱执行；敏感但可能正当的动作（如网络访问）
   走 **ask 审批**（HITL 菜单）而非 deny，任务不会被"一刀切"卡死；

-  **demo_2_feedback_change** — 反馈闭环：工具失败的错误信息回灌下文后，模型的**下一步动作发生改变**（重试 → 换用替代命令）；.
-  **demo_3_hitl_trace** — HITL 状态机全轨迹确定性复现：
   `ask → awaiting_user → 执行 → completed` 完整状态迁移。



### 离线确定性测试

- 全部测试**无网络依赖、不访问真实 LLM**：由 FakeLLM 客户端与
  `httpx.MockTransport` 驱动，可离线、确定性复现；MCP 测试使用手写的
  假 stdio 服务器子进程，不联网。
- 主要测试文件：
  `test_agent_core.py` / `test_agent_feedback.py` / `test_agent_context.py` /
  `test_agent_end.py`（六维度组件单测）、`test_repl.py`（REPL 行为）、
  `test_acceptance_matrix.py`（验收矩阵，逐条对应）、
  `test_mechanism_demo.py`（机制演示包装，对应上文 demo ①②③）、
  `test_llm.py`（LLM 客户端，httpx MockTransport）。
- 其余覆盖：护栏/状态机/策略/记忆/沙箱/钩子/MCP/凭据扫描
  （`test_security_scan.py`）/性能冒烟（`test_perf_smoke.py`）/文档一致性
  （`test_docs.py`）。


## 已知限制

- 平台：Windows 10+ / Linux，Python 3.11+；需 DeepSeek 账号与网络连通。
- `mcp_servers` 的 stdio/url 服务器需用户自备；连接失败自动停用，不影响其余。
- Docker 沙箱后端需 Docker Desktop（可选）。
