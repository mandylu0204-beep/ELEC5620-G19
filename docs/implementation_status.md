# 开发 A 实施状态

## A-13：方案修订、重新评估与当前输入检查（2026-10-12，完整 A11–A13 已合 main）

A11+A12+A13 已发布到 feature/a12-agent-runtime，应用代码提交为 230b7fb；包含最新远端 main 7720863。用户随后要求整体合入 main，已采用 merge commit 保留完整历史，未创建新 PR。分支 35fc879 与应用代码 230b7fb 的 GitHub CI 均通过；B 可从更新 main 建立 v2 接入分支。此次合并仅更新交接状态，业务代码与已检查分支一致；具体顺序见 [分支交接说明](agent_runtime_handoff.md)。后面的 A12/A11 发布状态保留为当时历史记录。

已接通 Camper 的 revise/reassess HTTP 和方案页入口。修订传递原方案快照、登记反馈后生成新版本；重新评估复用内容并开启新 run、生成新评估。旧审批和最终快照不自动沿用。指针/revision 比较、owner/CSRF、幂等收据、旧端口失效与失败重试延续既有守卫。审核及最终化提交现在复核 A 绑定运行的当前数据/配置/时钟；来源变化时禁用页面操作并拒绝旧结果放行。

新增 13 项独立 HTTP/SQLite/真实 v1 规则联调测试全部通过（28.73 秒）；随后最终化、审核和新流程 50 项复测通过（66.29 秒）。首次完整回归发现两项读取字段一致性问题，已在 PlanQueries 中统一新增字段，不修改数据库结构或弱化守卫。最终 scripts/check.py 退出 0：477 passed / 2 skipped / 1 条既有 Starlette 警告（164.78 秒），schema 1.0 同步，前端构建通过。两项跳过仅为 Windows 符号链接权限；之后补充前端步骤显示和间距，最终前端独立重建通过（50 模块，1.60 秒）。证据见 [A13 检查摘要](evidence/a13-plan-changes-check.json)。

当前 v1 支持更换营地/更便宜营地，其他修改由实际 Agent 能力决定，需求变化必须重新确认。本轮沿用已确认的需求/Profile 快照；当前资料的新修改不会悄悄覆盖旧确认。默认配置、个人 .env 和定稿数据不变，无数据库迁移。共享 schema 仍为 1.0。新绑定身份为 a-runtime-bindings-v2，A12 旧运行需重新评估。

B 工厂接口签名保持不变，但需消费 a_revision_feedback 并返回一致的 revision_feedback。细节见 [A13 修订流程](plan_changes.md) 与 [给 B 的接入交接](agent_runtime_handoff.md)。v2 Adapter、LLM、四个完整业务场景、真实浏览器演示及 Canvas 干净安装验收仍待完成；后续同步应包含完整 A11+A12+A13。

## A-12：真实规则运行配置接入（2026-10-12，本地未发布）

已将 main 的 B01–03 和定稿 v2 数据合入本地 A11。新增受信 AgentRuntime / AgentBinding 和按数据来源注册的工厂，v1 的真实 RuleAgent 使用完整业务 context 贯穿请求解释/确认、首次规划、claim、保存、失败重试和完成提交。B WorkflowConfiguration 保留 A 的文件/manifest/场景原始摘要、选用项和规则身份；每次操作重新核对当前输入，未注册 v2 不回退 v1。

新增 10 项独立接入测试，使用实际 RuleAgent、HTTP 鉴权和临时 SQLite，覆盖正常流程至最终化回读、缺失证据、封路审批/最终化守卫、保存回执丢失恢复、输入变化、工厂遗漏摘要、v2 未就绪和并发上下文一致性。首次测试输入试图直接修改 frozen SourceRef，改为构造新快照；补充封路测试原假设批准可保存，按现有守卫调整为 Founder APPROVE 被拒绝。均未放宽应用守卫。

最终后端回归为 464 passed / 2 skipped / 1 条既有 Starlette 警告（201.48 秒），跳过仅 Windows symlink 权限测试；新接入测试 10 项通过；schema 1.0 同步；前端 50 模块构建成功（1.65 秒）。证据见 [A-12 检查摘要](evidence/a12-runtime-check.json)。并发保护前的完整 scripts/check.py 亦退出 0（463 passed / 2 skipped、schema、前端通过），之后补充并发检查并完成最终全后端回归；没有声称此次执行新的浏览器演示。

默认 v1/stub、个人 .env、定稿 v2 业务内容均未改；本地依赖按仓库锁文件补充 tzdata 2026.5。v2 Adapter、LLM、四个完整业务场景、修订/重评公共入口、审核/最终化对磁盘最新输入的独立复核及 Canvas 完整安装演示仍待后续。转交 B 的工厂接口见 [Agent 运行接入交接](agent_runtime_handoff.md)，此项依赖 A11，后续应同步完整 A11+A12 基线。

## 当前本地实现：A-11 规划启动与失败重试（2026-10-11）

基于 main 2c647e6，在 feature/a11-planning-entry 实现 Camper 规划启动/重试 HTTP、页面入口与本地异步 dispatcher。确认、owner、CSRF、revision、命令回执和当前数据上下文先检查；重复新 key 不能为同一请求重复建 plan。执行租约自动续期、旧 attempt 拒绝、服务退出记录失败、重启恢复 PENDING；失败清理过程中收到的重试仍可调度。B 返回内容校验后才由 A 提交成功，避免提前开放最终化。

| 检查 | 最终结果 |
| --- | --- |
| 完整 scripts/check.py | 退出码 0；172 passed，1 个已有 Starlette 测试工具弃用提示；113.09 秒 |
| 共同 schema | up to date；冻结的 1.0 Protocol/DTO 未变 |
| 前端 | TypeScript 与 Vite 构建成功，50 模块，1.64 秒 |
| 新增 A 独立验收 | 23 项：禁用模式、确认/权限/回执、checkpoint、租约、退出/重启、输入变化、返回校验、收尾竞争及事务回滚 |
| 浏览器实际操作 | 独立 18011/15181 端口、var/a11-browser-test.sqlite3；启动后注入失败、点击重试、同一运行/版本完成、刷新恢复、已有方案链接、stub 按钮禁用 |

证据见 [A-11 检查摘要](evidence/a11-planning-check.json)、[失败重试页面](evidence/a11-retry.png)、[恢复完成页面](evidence/a11-recovered.png)、[stub 禁用状态](evidence/a11-stub-disabled.png)。浏览器执行使用 backend/tests/test_planning_entry.py 中明确的 TestOnlyAgent，启动脚本和测试数据库只在忽略的 var 中；未注册到实际应用。前一轮完整回归发现 HTTP 与 PlanQueries 默认重试字段不一致，统一返回结构后重新完整通过。测试服务与标签已关闭。

默认仍为 v1/stub，个人 .env 与演示数据库未修改；真实 B 实现、修订/重评公共执行入口、修订数据和四个业务场景仍待联调。当前输入变化后的新 run 尚无页面入口；审核/最终化对磁盘最新数据的独立检查仍待下一阶段补全。此次不代表真实 Agent 已完成，也不代表 Canvas 最终 ZIP 已验收。需要转交 B 的新增接入说明见 [规划执行接入](planning_entry.md)。本轮为本地分支提交，尚未发布到 GitHub。

## 当前发布：A-10 部署与数据上下文准备（2026-10-11）

按用户授权，feature/a10-submission-preparation 的累计改动直接合并发布至 main，不创建 PR：安装/打包/隔离部署检查、Canvas 下载验收清单、v2 独立复核，以及数据来源/版本/运行输入摘要。功能代码自已验证的 f1450ae 未变，本次只更新发布说明。远端检查结果以 [main CI](https://github.com/LyraWangDev/ELEC5620-G19/actions/workflows/ci.yml?query=branch%3Amain) 对应提交为准，不沿用 A-09 的 129 项结果。

## A-10 数据上下文接入准备（2026-10-10）

继续在本地 feature/a10-submission-preparation 分支开发。新增 A-owned DatasetDescriptor，支持原 v1 与具有 manifest 的 v2 来源/版本；六份业务文件、runtime 输入、manifest、配置场景及选用项纳入上下文。请求确认快照和 meta 使用实际版本；来源或输入无法验证时显式未就绪。Provenance 新增 v2 来源枚举并重新导出共享 schema，保留 v1 默认与端口 1.0。

新增 20 项独立边界测试。最终完整 scripts/check.py 退出码 0：149 passed，1 个已有 Starlette 提示，89.18 秒；schema up to date；Vite 49 模块构建通过，1.58 秒，见 [检查证据](evidence/a10-dataset-context-check.json)。首次目标测试发现新测试调用 append_plan_version 参数不完整，修正测试调用后回归通过；随后补齐 null manifest 拒绝检查，最终完整回归再次通过。沙箱内 TestClient 停滞后停止，仅在沙箱外项目内独立测试数据库完成检查。

只读检查用户 v2 副本，识别 2.0.0、v2 来源及 9 个输入文件摘要。默认业务数据、个人 .env、演示时钟、数据库迁移和业务枚举未改；未复制 v2 到应用业务数据目录。没有运行 B Agent、56 条应用验收规格或 Canvas 完整演示。

交接见 [数据上下文交接](dataset_context_handoff.md)。B 需更新共同 DTO/schema，并在实际 dispatcher 使用重新读取的上下文；文件变化自动监控、实际规划/重评与所有业务入口检查仍待联调。meal_mode、Decimal/cents 参考算法、审核测试身份和场景时钟问题仍按 [v2 独立复核](synthetic_data_review_v2.md) 修正。已有 42981fe ZIP 不包含这些后续代码，最终交付须重新打包并验收。

## 历史本地开发：A-10 部署准备（2026-10-10）

分支 feature/a10-submission-preparation 从已合并的 main d83f3ba 建立。新增 Python 锁文件安装入口、源码 ZIP 及每文件 SHA-256 清单、隔离 HTTP 部署 smoke；PowerShell 安装脚本调用同一安装器。启动器增加可选的 stop marker，使自动检查只关闭自己创建的子服务。页面、共同契约、业务规则和原始数据未修改。

实际先打包提交 622dd779edf1e765c1e3250e1989f769b23891eb：118 个源文件，ZIP SHA-256 为 3296111f81a065cdb732606c7fc97e2d3ce9288e963f348a66aa308615ceb813。在 Stage2/a10_clean_20261010/campmate_app 独立解压；起初没有 .venv/node_modules/.env/数据库或 .git，随后从锁文件建立新的 Python 3.12.14 环境与 npm 依赖，editable 导入确认来自解压目录。没有复制原工作区依赖、数据库或个人配置。

| 检查 | 实际结果 |
| --- | --- |
| 新环境安装 | setup.py 退出码 0；pip check 无冲突；npm ci 成功 |
| 新环境完整 check.py | 退出码 0；129 passed，1 个已有测试工具弃用提示；schema up to date；Vite 49 模块构建成功 |
| 实际 HTTP 部署检查 | 7 步通过：本目录 interpreter/import、前端 SPA/module/API proxy、登录/资料/请求确认与回执、权限、重启回读/迁移、注销、服务关闭及端口释放 |
| 数据与打包 | 原始 10 个数据文件逐字一致；ZIP 文件清单与全部 SHA-256 一致；拒绝未提交源码的 guard 已实际触发 |

smoke 使用独立 18010/15180 端口与 var/deployment-smoke-* 数据库；默认数据库未创建或改动，已有服务未终止。报告见 [HTTP 部署证据](evidence/a10-deployment-smoke.json)，完整输出见 [新环境检查证据](evidence/a10-clean-check.txt)，操作见 [部署准备](deployment_preparation.md)。验证完成后仅补充 README/交付文档及证据，运行脚本和业务源码保持与上述已测包一致；最终源码 ZIP 的 commit 与 checksum 以其 PACKAGE_MANIFEST 和 .sha256 为准。

这是同一 Windows 电脑的干净目录/新环境验证，不是另一台电脑、完整浏览器渲染、Linux 启动或真实 B 业务链路验证。A-10 的提交包/本机部署准备已自检；B 首版 Agent/Adapter、规划/修订调度及页面启动/重试、修订数据、四个业务场景、成员复核、Jira 和完整提交 Done 仍待完成。发布情况见本页顶部。

## 历史本地开发：A-09 恢复边界（2026-10-10）

分支 feature/a09-run-recovery 基于 A-08 本地提交，新增内部 WorkflowService、启动/重试回执、当前 run/version 比较、执行租约、失败恢复 checkpoint 和迟到任务拒绝。重复启动不新建 plan/run；重复重试不重置后续失败；输入未变保留已保存版本及评估；证据变化开启新 run。首次尚无版本时可在同一 plan 新开 PLAN run。migration 5 保留旧记录，共同 schema 1.0 和现有 HTTP 接口未改。

| 最终检查 | 实际结果 |
| --- | --- |
| 完整 scripts/check.py | 退出码 0；128 passed，1 个已有测试工具弃用提示；schema up to date；前端 49 模块构建成功 |
| 最后一项边界补充后回归 | test_workflows.py 与 test_storage.py 共 34 项全部通过；本轮恢复测试共 24 项 |
| 并发与迟到任务 | 启动/重试竞争、单 worker 领取、旧 attempt/旧端口/旧 run 写入拒绝 |
| 故障恢复 | 保存、领取、重试回执失败整体回滚；租约续期/过期及数据库重启后恢复；版本/评估/路由/NO_MATCH checkpoint |
| 数据与权限 | 数据/规则/时钟/模式变化拒绝 retry；fingerprint 损坏拒绝；跨 Camper/Founder 操作拒绝；旧数据库升级保留记录 |

首轮完整回归发现旧 migration 3 测试在升级前调用当前端口，因缺少新租约表失败；已改为写入真实旧版存储记录，再升级校验，修复后完整检查通过。最后补充无版本时换证据重开 run，随后对全部受影响的运行管理/持久化测试回归通过。

原始数据和默认数据库未改；A-09 未修改前端页面。B 接入签名及限制见 [运行恢复交接](run_recovery.md)。当前是 A 侧恢复原语与自检，不含真实 B 调度器、后台恢复扫描、HTTP/页面启动与重试或业务联调。按用户要求，A-06 至 A-09 累计开发通过 feature/a09-run-recovery 功能分支同步到 GitHub，合并走 PR 审核；本轮远端 CI 以 PR 检查为准，不沿用 A-05 的结果。其他成员复核、Jira、全组 Done 与 A-10 干净环境完整演示仍待完成。

## 历史本地开发：A-08（2026-10-10）

分支 feature/a08-finalisation 基于 A-07 本地提交，新增 Camper 最终保存和不可覆盖快照；保存前重新校验版本/run/fingerprint/两份评估/审核/revision 与 eligibility。同事务保存快照、FINALISED、最终指针及回执，故障时全部回滚。当前/历史最终方案根据 version 与 run 同时判断，同版本重评也会使旧快照成为历史。migration 4 升级保留数据；共享 schema 1.0 未改，API 0.6.0。

| 最终检查 | 实际结果 |
| --- | --- |
| scripts/check.py | 退出码 0 |
| 后端 pytest | 105 passed；新增 23 项最终化测试；1 个已有测试工具弃用提示 |
| 共享 schema 对照 | up to date |
| TypeScript/Vite | 构建成功，49 模块 |
| 浏览器 | 明确确认、批准后保存、完整快照回读及刷新、关闭道路禁用、新评估后历史标记和历史链接 |
| 并发/回滚/历史 | 同 key 回读、不同 key 竞争、保存回执失败全部回滚；旧版本/证据/审核失效；旧快照不可更新/删除 |

浏览器仅使用独立保存夹具、var/e2e-a08-final-20261010.sqlite3 与 8001/5174；原始数据、副本及默认数据库未改。详见 [最终化与历史说明及证据](finalisation.md)。A 侧本机实现与自检完成；B 实际输出与修订执行、四个真实联调场景、其他成员复核、Jira 和全组 Done 尚未完成。本轮仅本地提交，尚未推送 GitHub、创建 PR 或运行本轮远端 CI。

## 历史本地开发：A-07（2026-10-10）

分支 feature/a07-founder-review 基于 A-06 本地提交，新增 Founder 审核队列、当前证据详情与带理由的 APPROVE/REJECT/REQUEST_REVISION；审核绑定当前 version/run/fingerprint/两份评估和 revision，批准后同事务重算 eligibility，不能绕过 blocker、未知必要费用、超预算或未解决修订。重复提交回读原结果，竞争审批仅一个保存，故障时审核/状态/回执一起回滚。migration 3 升级保留旧记录；共享 schema 1.0 未改，API 0.5.0。

| 最终检查 | 实际结果 |
| --- | --- |
| 后端 pytest | 82 passed；新增 14 项审核测试；1 个已有测试工具弃用提示 |
| schema 对照 | up to date |
| TypeScript/Vite | 构建成功，47 模块 |
| 浏览器 | 三种决定、理由必填、关闭道路禁止批准、批准刷新回读、队列移除 |
| 事务/并发 | 重复 key、竞争决定、回执保存故障回滚、旧 run 与旧版本拒绝审批 |

浏览器使用独立测试夹具和 var/e2e-a07-review-20261010.sqlite3；原始数据和默认数据库未改。审核通过仍不最终化；修订动作当前只保存反馈，B 修订执行尚未接入。详见 [人工审核流程与证据](founder_review.md)。A 侧本机实现/自检完成；B 实际联调、其他成员复核、Jira 与全组 Done 仍待完成。本轮仅本地提交，尚未推送 GitHub、创建 PR 或执行本轮远端 CI。

## 历史本地开发：A-06（2026-10-10）

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
