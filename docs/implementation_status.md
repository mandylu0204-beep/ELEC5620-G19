# 开发 A 实施状态

## 当前本地开发：A-06（2026-10-10）

分支 feature/a06-plan-display 已实现已保存运行与方案展示：列表、阶段事件、推荐/排除原因、日程、装备/物流、费用/预算、安全证据、路由及历史 run。GET /plans/{id} 和 /runs/{id} 按用户授权，单次读取事务只组合同一 run/version 的产物；历史 run 不展示当前 eligibility。活动运行按 2.5 秒轮询真实保存记录，终结或读取失败后停止。

费用未知与零分别展示，Decimal 数量不转浮点；时间按悉尼时区显示。NO_MATCH、业务修订、等待审核、阻止与技术故障分别提示。NO_MATCH 且没有版本的已保存运行可正常结束，其他完成守卫保持。共同 DTO/schema 未改变，API 开发版本为 0.4.0。

| 检查 | 实际结果 |
| --- | --- |
| 后端测试 | 68 passed（新增 14 项）；1 个已有测试工具弃用提示 |
| 共享 schema 对照 | up to date |
| TypeScript/Vite | 构建成功，46 模块 |
| 浏览器 | 读取列表、刷新恢复、未知金额/零金额、NO_MATCH、故障后部分产物保留；自动读取阶段变化 |
| 历史运行 | 新评估无旧评估产物；旧运行仍可回读原产物和路由，不沿用当前 eligibility |

浏览器仅使用明确标注的独立展示夹具与隔离数据库；原始数据、其副本和默认数据库未改。详见 [A-06 说明与证据](plan_display.md)。A-06 的 A 侧读取/展示自检完成；B 联调、工作流启动与重试、真实业务四场景、其他成员复核和全组 Done 未完成。未推送此分支，本轮 GitHub CI 未执行；下面的远端结果只适用于此前 A-05 提交。

## GitHub 首版交付：2026-10-10

已创建并核实 [LyraWangDev/ELEC5620-G19](https://github.com/LyraWangDev/ELEC5620-G19) 为私有仓库，首个源码提交 `36bce3f` 推送至 main。源码、锁文件、契约、synthetic 原包副本和文档已上传；数据库、`.env`、依赖和构建产物没有提交。`.gitattributes` 保留数据包原始字节，10 个业务/说明文件在 Git 中与本地原件一致。

首次 [GitHub Actions](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/37935196604) 已成功：Ubuntu runner、Python 3.12、Node.js 22，54 passed（1 个已知测试工具弃用提示）、schema 对照成功、45 个前端模块构建成功。这是远端 CI 验证，不是完整交互演示、其他成员复核或全部 Done。公网服务、B 实现及四个业务联调仍未完成；本次仅上传私有协作源码。

## 当前记录：A-05（2026-10-09 至 2026-10-10）

A 侧 Profile 编辑与请求保存、澄清、确认已实现。装备数量/容量和交通距离未知时保留 null；两晚推导三天与结束日期；仅天数或明确日期/时长冲突时先澄清。用户须阅读摘要并勾选确认；确认快照不可覆盖，确认尚不创建方案或启动规划。

请求按用户隔离，写入核对 CSRF 和 revision；确认再次核对 Profile 与数据上下文。同命令同输入回读原确认，不同内容冲突。字段修改取消旧摘要，迟到分析不能替换新输入。migration 2 增加摘要与回执并保留旧数据库记录。

| 实际检查 | 结果 | 范围 |
| --- | --- | --- |
| scripts/check.py 综合检查 | 退出码 0 | 2026-10-10，当前 Windows 本机环境 |
| 后端 pytest | 54 passed；1 个测试工具弃用提示 | 新增 12 个请求用例，包含参数化冲突、幂等、快照、权限、迟到分析及升级 |
| schema 对照 | Shared JSON schemas are up to date | 共同 Agent DTO 本轮未改变 |
| 前端 TypeScript + Vite | 45 个模块构建成功 | 资料表单、请求列表、澄清与确认 |
| 浏览器资料 | 保存、刷新恢复；未知容量/距离保持未知 | 实际前后端操作 |
| 浏览器请求 | 仅天数/冲突时不能确认；补齐后显示两晚三天；明确确认及刷新成功 | stub 与用户明确字段，不是 B 提取验收 |
| 浏览器历史快照 | Profile 从 2 人改为 3 人后，已确认请求仍显示 2 人 | 实际快照回读 |

浏览器使用隔离测试数据库 `var/e2e-a05-20261009.sqlite3` 和 5174/8001，不覆盖默认数据库中的用户资料。原始 synthetic 包及项目中的副本保持原样。默认启动仍使用 `.env` 的数据库和 5173/8000。

交接细节见 [资料与请求流程](profile_request_flow.md)。证据：[Profile](evidence/profile-editor.png)、[待确认摘要](evidence/request-summary.png)、[已确认快照](evidence/request-confirmed.png)。

A-05 的 A 侧本机自检完成；B 的 interpret_request、自然语言提取、首轮四个业务场景及全组 Done 条件仍未完成。规划、进度/产物展示、审批和最终化待 A-06 至 A-08。本机检查时尚未提交或运行远端 CI；随后完成的 GitHub 首版交付见本页顶部。其他成员复核和干净交互部署仍未执行。

## 历史记录：A-03/A-04（2026-10-09）

本轮实现 A-03 登录/退出、服务器会话、Camper/Founder 角色检查，以及 A-04 SQLite 迁移、Profile 保存接口、确认快照/运行/版本/评估存储与九项 PersistencePort 实现。客户端不能指定账号角色或资料归属；他人方案资源与不存在资源统一返回 404。Founder 只通过审核队列取得当前 ESCALATED 索引。

迁移启动 seed 两个 Camper 和一个 Founder，密码为随机盐 PBKDF2 哈希。会话 token 只放在 HttpOnly Cookie，数据库存摘要；服务器过期、退出及写入 CSRF 检查已实现。数据库位于项目 var 下，Git 忽略。

当前前端有登录页、账户状态和退出；Camper 方案列表、Founder 审核队列读取数据库，空记录真实显示为空。Profile 编辑表单、请求确认、Agent 规划、审批提交及最终化仍待后续实现。内部版本/评估测试不能当作业务工作流已完成。

| 实际检查 | 结果 | 范围 |
| --- | --- | --- |
| scripts/check.py 综合检查 | 退出码 0 | 当前 Windows 本机环境 |
| 后端 pytest | 42 passed，1 个测试工具弃用提示 | 契约、HTTP 登录/权限、SQLite 事务与关联 |
| schema 对照 | Shared JSON schemas are up to date | Agent 共同 DTO 本轮未改变 |
| 前端 TypeScript + Vite | 43 个模块构建成功 | 包含登录与会话恢复 |
| 浏览器 Camper | 登录后读取空方案列表；刷新仍登录；审核页拒绝；退出返回登录页 | 本轮实际前后端流程 |
| 浏览器 Founder | 审核入口出现，读取真实空队列，测试后退出 | 仅身份与队列读取，不是审批验收 |
| 重启与不可覆盖历史 | 新 Database/Repository/Application 读取原文件；资料和两版内容保留 | 独立 SQLite 文件测试 |
| 存储故障 | 注入装备清单保存失败，评估/清单/写入 receipt 全部回滚；恢复后重试一次保存 | 独立故障测试 |
| 陈旧上下文与批准 | 新 run/fingerprint 不沿用旧审核；缺失证据即使注入批准仍阻止放行 | 存储守卫，非 B 业务场景 |

浏览器验证使用 127.0.0.1:5174 / 8001，未停止已有服务。普通启动仍默认 5173 / 8000；若已有旧后端，需退出原启动终端并重启以加载新源码。没有修改 PowerShell 执行策略。原样式在一次误替换后从前一版构建恢复，本轮页面截图已检查。

说明与待对齐项见 [登录与存储](storage_and_accounts.md)。证据：[登录页](evidence/accounts-login.png)、[Founder 队列](evidence/founder-queue.png)。测试夹具独立于原 synthetic 数据，尚未取得修订业务数据，尚未调用 B Agent 或运行四个业务联调场景。

A-03/A-04 本机模块自检完成；A-04 在真实业务中的集成、B 端口调用、其他成员复核、Jira 和全部 Done 条件未完成。GitHub CI、另一台电脑/Linux 和干净部署未验证；没有提交、远端或推送。

## 历史记录：A-01/A-02

日期：2026-10-08（Australia/Sydney）。这是本次实际开发与检查记录，不是全组 Done 或全部 Stage 2 验收。

## 已实现

- 本地项目目录与 Git main 初始化，源码尚未提交，无远端。
- React / TypeScript / Vite 页面骨架、路由、配置与 FastAPI 基础。
- `.env` 配置、可移植数据副本、锁定依赖和 Windows 安装/启动/检查脚本。
- 共同 DTO、枚举、异常、六项 AgentPort 与 PersistencePort 定义；校验额外字段、金额、Decimal、日期及部分评估一致性。
- 明确标注的 stub 仅回显明确字段；其他能力拒绝假成功。未注册模式不会自动回退。
- liveness/readiness 分开，来源可读、SQLite 驱动可用与业务功能实现分开展示。
- 初版 GitHub Actions 配置，未执行远端 CI。

A-01 的本机启动与构建自检已完成。A-02 的 A 侧参考实现已建立；B 首版 schema/实际工厂尚未交付，双方集成、其他成员复核及 Jira Done 仍待完成。

## 实际检查

| 检查 | 结果 | 适用范围 |
| --- | --- | --- |
| 后端 pytest | 29 passed；1 个 Starlette/HTTPX 测试工具弃用提示 | 共享契约与开发 HTTP 边界，不是 Agent 功能验收 |
| 前端 TypeScript + Vite build | 通过，42 个模块构建 | 本机生产构建 |
| 原始数据副本 | 10 文件逐字节 SHA256 一致 | 来源保留，不代表语义问题已修复 |
| 浏览器字段预览 | Demo Region / AUD 123.45 回显正确；日期和晚数未填时有缺失提示 | stub 实际前后端链路，无请求保存或确认 |
| 页面状态 | STUB、Synthetic 标签、固定时钟、待接入能力明确显示 | 本地可视化检查 |
| 导出 schema 同步 | `python -m app.export_contracts --check` 通过 | 对照当前 Pydantic DTO 的 validation/serialization 导出 |
| 最终综合脚本 | `scripts/check.ps1` 退出码 0，29 项测试与前端构建再次通过 | 当前本机源码、schema 与锁定环境 |

测试环境为 Python 3.12.14、Node.js 22.20.0、Windows；Linux/其他电脑、GitHub CI 与干净提交包部署尚未验证。Starlette 当前兼容 HTTPX 的测试接口，出现弃用提示，后续测试依赖升级时应一起处理。

浏览器证据：[概览](evidence/foundation-overview.jpg)、[请求预览](evidence/request-preview.jpg)。截图为开发支架状态，不是正式 Agent 演示。

## 当时未实现与限制（2026-10-08）

身份权限、业务数据库/迁移/事务、Profile CRUD、请求确认、持久化端口实现、workflow runs、PlanVersion 历史、审核/最终化服务、B Agent/Adapter/规则/LLM、四个联调 fixture 与真实业务测试均待后续完成。SQLite 健康检查只使用内存连接，不创建业务数据库。

冻结设计文档保留 1.0 对齐时的语境，当前进度以本文件为准。本地安装及构建曾受沙箱临时目录与 realpath 限制，经批准在沙箱外完成；也修复了测试临时目录父目录缺失。没有更改系统安全设置或公开监听地址。

原有 `Stage2/campmate_synthetic_demo` 保留不改。仓库中的副本供 B Adapter 从配置路径加载，测试 oracle 独立于 Agent 输入。后续修订数据使用独立 fixture/版本记录。
