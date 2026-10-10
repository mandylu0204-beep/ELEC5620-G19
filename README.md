# CampMate AI

ELEC5620 Stage 2 · React + TypeScript / FastAPI / SQLite。

当前已实现 A-01 至 A-05 基础、登录、持久化、Profile 编辑和请求确认、A-06 已保存规划进度与方案展示、A-07 Founder 审核、A-08 最终化与历史快照、A-09 内部运行管理与恢复边界、A-10 部署与数据上下文准备，以及 A-11 规划启动/失败重试入口与本地任务调度。审批与最终保存绑定当前版本及证据，不能绕过 blocker；最终快照不会被后续修订或评估覆盖。解释器目前仍为 stub，需手动填写明确字段；真实 B Agent/Adapter、修订执行和四个业务联调场景仍待接入。默认规划禁用，B 接入与显式开启要求见 [规划执行接入](docs/planning_entry.md)。

> This prototype uses synthetic demonstration data. It must not be used for real trip planning, campsite availability, or safety decisions.

最终提交须满足 [Canvas 下载后演示验收](docs/canvas_submission.md)：下载 ZIP 后无需访问私有 GitHub 或使用作者电脑的配置，按随包说明可完成完整演示。当前仍待 B 工作流接入与最终包验收。

## 安装与启动

测试环境：Windows、Python 3.12.14、Node.js 22.20.0。使用 Python 3.12 与 Node.js 22.12+；其他版本尚未做完整部署验证。依赖下载需要网络，业务运行只使用本地 synthetic 数据。

在项目根目录打开 PowerShell：

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
```

首次 setup 建立 `.venv`、安装后端锁定依赖及前端 `npm ci`、从 `.env.example` 创建 `.env`。如需指定 Python，使用 `scripts/setup.ps1 -PythonExecutable '你的 Python 可执行文件路径'`。本机原有 Python 3.13 创建虚拟环境失败，本次使用 Codex 提供的 Python 3.12.14 建立了 `.venv`；环境目录不会提交 Git，换电脑应重新安装。

打开 [前端预览](http://127.0.0.1:5173) 与 [API 文档](http://127.0.0.1:8000/docs)。两个服务只监听 127.0.0.1。启动终端按 Ctrl+C 停止两个子服务；后端修改后需重启，前端支持 Vite 热更新。端口被占用时脚本会退出，不终止已有进程：

```powershell
.\scripts\start.ps1 -BackendPort 8001 -FrontendPort 5174
```

若 PowerShell 禁止运行 `.ps1`，已安装依赖后可直接使用 Python 启动，不需修改系统执行策略：

```powershell
.\.venv\Scripts\python.exe scripts\dev.py
# 自定义端口：
.\.venv\Scripts\python.exe scripts\dev.py --backend-port 8001 --frontend-port 5174
```

首次安装也有 Python 入口：`py -3.12 scripts/setup.py`（或使用 Python 3.12 完整路径）。源码包、校验与隔离启动检查见 [部署准备](docs/deployment_preparation.md)。安装器使用锁文件，不覆盖已有 `.env`。

Linux/macOS 可分别创建 venv、按 `backend/requirements.lock` 安装依赖、在 backend 执行 `pip install --no-deps -e .`，在 frontend 执行 `npm ci`，再以该 venv 的 Python 运行 `scripts/dev.py`。此流程有 CI 配置，尚未在另一台电脑或 Linux 上实际执行。

## 配置

在 `.env` 使用 `.env.example` 中的变量。相对路径以项目根目录为基准，不依赖当前终端目录。

| 配置 | 默认值 | 作用 |
| --- | --- | --- |
| CAMPMATE_EXECUTION_MODE | stub | 仅 stub 已注册；deterministic_demo / agent 尚未接入，配置后就绪检查失败，不能自动回退 |
| CAMPMATE_DEMO_TODAY | 2026-10-08 | 固定演示时钟，与系统时间分开 |
| CAMPMATE_DATASET_PATH | data/synthetic_demo | 原始包的完整副本；业务源文件在其 data 子目录 |
| CAMPMATE_DATASET_SCENARIO_FILES | [] | 已选数据包 data/scenarios 下的独立运行输入 JSON；摘要纳入确认/run 上下文 |
| CAMPMATE_DATASET_SELECTION | {} | 服务器场景选用项；JSON 对象，纳入上下文，不能作为测试预期 |
| CAMPMATE_DATABASE_PATH | var/campmate.sqlite3 | 启动时创建及迁移，重启保留；不提交 Git |
| CAMPMATE_SEED_DEMO_ACCOUNTS | true | seed 三个演示账号；false 只关闭新增 seed，不删除已有账号 |
| CAMPMATE_SESSION_HOURS | 8 | 服务器会话有效小时，系统时间计算 |
| CAMPMATE_SECURE_COOKIES | false | 本地 HTTP；HTTPS 部署时设为 true |

## 本地演示登录

打开前端 `/login`，使用公开的 synthetic 演示凭据：

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| Camper A | camper.a | CampMate-A-2026! |
| Camper B | camper.b | CampMate-B-2026! |
| Founder | founder | CampMate-Founder-2026! |

刷新页面会恢复登录；退出撤销服务器会话。Camper 只能读取自己的资料和方案，Founder 只能通过审核接口取得当前审核索引。数据库只存密码哈希。默认资料为空，不把原始数据中的 Profile ID 当成登录账号。启动脚本只监听 127.0.0.1；当前为本地演示版本。

## 当前页面与接口

- 项目概览：根据实际后端状态显示 source readability、数据库迁移与当前入口是否可用。
- 露营资料 `/profile`：查看和编辑人数、经验、儿童、装备数量/容量、交通及无障碍需求；未知值保留为 null。
- 露营请求 `/request`：保存草稿、生成摘要、澄清冲突、勾选确认并保存快照；从已保存列表恢复。两晚对应三天，日期冲突先澄清。确认尚不启动规划。
- 开发预览 `/dev/request-preview`：`POST /api/v1/dev/interpret`，仅回显字段，不保存请求。
- 登录：`POST /auth/login`、`GET /auth/me`、`POST /auth/logout` 管理会话。
- Profile：`GET/PUT /profile`；Requests：`GET/POST /requests`、`GET/PATCH /requests/{id}`、`POST /requests/{id}/interpret`、`POST /requests/{id}/confirm`（均在 `/api/v1` 下）。
- Plans：`/plans` 与 `/plans/{id}` 展示自己已保存的运行、推荐、行程、装备、费用和安全证据；活动运行自动读取保存进度，可选择历史 run。接口为 `GET /plans/{id}`、`GET /runs/{id}`，详见 [进度与产物展示](docs/plan_display.md)。
- Review `/review`、`/review/{plan_id}`：Founder 查看当前审核依据，提交带理由的批准、拒绝或修订要求。批准后重算 eligibility，不自动最终化。详见 [人工审核流程](docs/founder_review.md)。
- 最终保存：Camper 在当前方案中阅读并确认后保存；`/plans/{id}/finals/{final_id}` 展示不可覆盖的完整快照，明确区分当前与历史最终方案。详见 [最终化与历史](docs/finalisation.md)。
- `GET /api/v1/health/live`：进程可响应。
- `GET /api/v1/health/ready`：开发基础依赖、业务表迁移与数据包身份/输入摘要可验证；不表示完整业务规则或工作流已实现。
- `GET /api/v1/meta`：演示模式、时钟、来源标签、disclaimer 与实际功能开关。

请求预览是 loopback 开发工具；正式请求由登录后的 `/requests` 接口保存。审核使用 GET/POST `/api/v1/review/{plan_id}`；最终保存使用 POST `/api/v1/plans/{plan_id}/finalise`，快照回读使用 GET `/api/v1/plans/{plan_id}/finals/{final_id}`。规划执行尚未提供。写入要求 X-CampMate-Client: 1，已登录写入另要求 X-CSRF-Token；浏览器自动携带 HttpOnly 会话 Cookie。确认要求匹配 revision、明确 acknowledged=true 和幂等 command_key，资料或数据变化后需重新生成摘要。详见 [资料与请求流程](docs/profile_request_flow.md)。

## 文件位置与 B 接入

```text
backend/app/contracts/      DTO、枚举、异常、AgentPort/PersistencePort
backend/app/agents/stub.py  A 开发支架；B 可在 agents 下新增实际实现
backend/app/application/agent_registry.py  通过模式注册 AgentPort 工厂
backend/app/main.py         FastAPI 与健康/预览路由
backend/app/auth.py         密码哈希、演示 seed、会话认证
backend/app/http_accounts.py 登录、资料、列表及角色检查
backend/app/http_requests.py 请求保存、摘要生成及明确确认
backend/app/http_plans.py   已保存运行与方案详情读取
backend/app/application/request_rules.py A 侧字段规范化与数据上下文
backend/app/storage/        SQLite 迁移、Repository 与持久化端口
frontend/src/              页面、路由、样式与 HTTP 调用
data/synthetic_demo/        原始 10 个数据文件的完整副本
scripts/                   安装、启动、检查脚本
docs/                      冻结设计、导出 schema 与实施证据
```

A 提供的 DTO 是按基线形成的参考实现，B 首版 schema 需核对字段与规则。六个入口已在 AgentPort 定义；PersistencePort 已有按 owner/run 绑定的 SQLite 实现。A 登记 run 后向 B 传递受限端口，不让 B 创建审核或最终记录。实际绑定方式、限制与待对齐项见 [登录与存储说明](docs/storage_and_accounts.md)。B 通过 registry 注册 deterministic_demo 工厂；LLM 接入仍使用 synthetic 业务源及同一契约。

v2 的来源标识与运行输入摘要接入准备见 [数据上下文交接](docs/dataset_context_handoff.md)。当前默认仍为原 v1，修正版尚未导入；实际包版本由 manifest/来源识别，不能仅改配置就宣称完整业务演示已通过。

共同定义见 [端口代码](backend/app/contracts/ports.py) 和 [设计说明](docs/shared_contracts_spec.md)。[contracts.schema.json](docs/contracts.schema.json) 同时导出 validation 与 serialization schema；Decimal 数量输入和输出使用字符串，金额使用整数 cents。schema 更新后重新导出：

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.export_contracts
```

原始 `expected_*` 及风险/置信度标注属于测试 oracle，不得直接作为 Agent 输入或成功输出。stub 不提供推荐、行程、物流、安全或 orchestrate 的成功结果。

## 检查及实施证据

从项目根目录运行：

```powershell
.\scripts\check.ps1
```

PowerShell 脚本被禁止时可运行 `.\.venv\Scripts\python.exe scripts\check.py`。

检查后端契约与 HTTP、导出 schema 是否同步，以及 TypeScript 和 Vite 生产构建。测试临时目录限制在项目 `var` 下，避免清理源码。当前实际结果、截图及限制见 [实施状态](docs/implementation_status.md)。此前 A-05 的 GitHub CI 已执行；A-06 至 A-09 的 CI 结果以功能分支 PR 检查为准。本机检查不能替代 B 的规则测试和端到端验收。

## GitHub

私有协作仓库：[LyraWangDev/ELEC5620-G19](https://github.com/LyraWangDev/ELEC5620-G19)。A-06 至 A-09 已通过 [PR #1](https://github.com/LyraWangDev/ELEC5620-G19/pull/1) 合并至 main（d83f3ba），该历史提交的 CI 已通过 129 项测试。2026-10-11 按用户授权，将 A-10 部署准备、Canvas 验收清单、v2 独立复核和数据上下文接入准备直接合并发布到 main，不创建新 PR。A-10 本地最终检查通过 149 项测试、schema 与前端构建；远端结果以 [main 的 CI](https://github.com/LyraWangDev/ELEC5620-G19/actions/workflows/ci.yml?query=branch%3Amain) 对应提交为准。协作步骤见 [贡献说明](CONTRIBUTING.md)，当前验证与限制见 [实施状态](docs/implementation_status.md)。

上传范围为项目根目录的源码、文档、synthetic 数据、schema、锁文件和 CI。`.venv`、node_modules、`.env`、数据库、构建目录和日志已忽略。克隆后需在自己的电脑安装依赖并创建本地数据库；GitHub 仓库保存源码，服务仍按安装与启动说明在本地运行。

后续修改建议使用分支和 Pull Request：

```powershell
git switch -c YOUR_FEATURE_BRANCH
git add .
git commit -m "Describe the change"
git push -u origin YOUR_FEATURE_BRANCH
```

## 参考与后续任务

当前 A-10 提供源码打包、Python 安装入口与隔离 HTTP 部署检查，见 [部署准备](docs/deployment_preparation.md)；真实 B 调度、恢复端口与页面启动/重试仍待实际接入。内部启动回执、执行租约、迟到任务拒绝和恢复 checkpoint 见 [运行恢复交接](docs/run_recovery.md)。正式四个业务场景联调需要 B 首版实现及修订数据。任务与验收见 [开发 A 清单](docs/developer_a_backlog.md)。

实现参考：[React 构建说明](https://react.dev/learn/build-a-react-app-from-scratch)、[Vite 入门](https://vite.dev/guide/)、[FastAPI 测试](https://fastapi.tiangolo.com/tutorial/testing/)、[Pydantic 标准类型](https://docs.pydantic.dev/latest/api/standard_library_types/)。CI 的 checkout、Python 和 Node 设置采用官方示例的 v7 调用形式：[checkout](https://github.com/actions/checkout)、[setup-python](https://github.com/actions/setup-python)、[setup-node](https://github.com/actions/setup-node)。
