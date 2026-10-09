# CampMate AI 开发 A 任务与验收清单

> 本文为 1.0 接口冻结时的设计记录；其中实施状态描述保留当时语境。当前代码和验证进度见 [实施状态](implementation_status.md)。

日期：2026-10-08。基线：契约 1.0。以下是拟建立的 Jira 工作项，不是已经创建的 Ticket，也不是完成记录。全部开发任务当前为待开始；本轮只完成文档。

来源：用户指定自己为开发 A；职责取自 [五人分工](C:/Users/87901/xwechat_files/wxid_1wtdhrpq2hya22_b74c/msg/file/2026-10/ELEC5620_Stage2_五人分工.txt)。接口依据 [A/B 交接](developer_b_handoff.md) 与 [共享契约实施说明](shared_contracts_spec.md)。任务编号 A-01 等是本地规划编号，建立 Jira 后补真实 Key。

## 1 开发顺序

进入代码阶段后的第一批：A-01 项目及启动基础 → A-02 共同契约和可替换边界 → A-03 身份权限与 A-04 持久化。随后完成请求确认，再打通首轮四个业务场景。A-10 的 CI 基础在 A-01 开始时建立，干净部署验收在全部核心功能完成后执行。

B 同时交付 schema、Adapter、正常/超预算/缺失证据/道路关闭的规则流程。A 可先用 stub 验证界面与数据库，换成 B 首版实现后重新执行端到端验收；stub 检查不能用于证明 Agent 能力或真实业务规则已完成。

本清单不重新安排全组时间；与原计划的正常流程、异常流程、部署回归三个阶段衔接。发现延误时根据实际完成证据更新 Jira，不回填虚构的工作记录。

## 2 工作项与可观察验收条件

全部为 Must。基础工程项不虚构 FR 编号；业务项按正式 FR 语义关联。

| 编号 / 任务 | User Story | FR 与依赖 | 验收条件 |
| --- | --- | --- | --- |
| A-01 项目目录与启动基础 | As a developer, I want a reproducible local startup, so that the team can run the prototype consistently. | 工程基础；无前置 | 前后端可按 README 启动；健康检查能区分服务存活与必要依赖未就绪；数据路径及 demo_today 通过配置提供；没有连接真实业务 API |
| A-02 共享 schema、端口及 stub 边界 | As a developer, I want shared contracts, so that A and B can integrate independently. | 支撑 FR-02 至 FR-10；A-01，B 首版 schema | 两侧从同一 contracts 导入；字段、枚举、Decimal、错误格式一致；stub 产物明确标注；切换 B 实现无需重写页面与数据库；未符合 schema 的输出不被保存为成功 |
| A-03 登录、角色与权限 | As a Camper, I want my records protected, so that another Camper cannot access them. | FR-01/09/10，安全 NFR；A-01 | 至少两个 Camper 和一个 Founder；数据库存密码 hash；登录退出有效；跨用户读取/写入失败；Camper 无审核权限；Founder 只获取审核职责所需资源；错误不泄露他人存在性 |
| A-04 数据库、迁移与快照 | As a Camper, I want saved records and history, so that my plan remains available after restart. | FR-01/02/04/07/09/10；A-02/03 | 空数据库可迁移及 seed；服务重启后记录可读；归属和版本关联正确；Profile 修改不改历史快照；新版本保留旧内容；同一 plan 版本号唯一；当前及最终指针不会指向另一 plan |
| A-05 Profile 与请求澄清确认 | As a Camper, I want to confirm structured requirements, so that planning uses my intended trip details. | FR-01/02；A-02/03/04，B interpret_request | Profile 创建、查看、修改；请求能展示提取、错误及澄清；只给天数或日期冲突先澄清；两晚显示三天与结束日期；未确认不规划；旧 revision 无法确认；确认后需求不可原地覆盖 |
| A-06 进度与方案产物展示 | As a Camper, I want to see planning progress and results, so that I understand the current plan and its limits. | FR-03/04/05/06/07/08；A-05，B 前五项能力 | 展示持久化阶段、推荐理由、日程、装备缺口、费用、风险、来源及不确定性；未知金额不显示为零；分数/分金额格式正确；NO_MATCH、业务修订、阻止状态和技术故障有不同提示；页面刷新可恢复状态 |
| A-07 Founder 审核与修订动作 | As a Founder, I want version-specific review, so that decisions apply to the evidence I actually examined. | FR-04/08/09；A-03/04/06，B 路由与修订 | 支持 APPROVE/REJECT/REQUEST_REVISION，理由必填；保存审核人、run、fingerprint、assessment IDs；旧版本或旧 run 审批被拒绝；批准后重算 eligibility；blocker/必要证据缺失不能被批准绕过；需求变化重新确认 |
| A-08 最终化与历史页面 | As a Camper, I want a saved final plan with version history, so that I can distinguish final delivery from later revisions. | FR-04/09/10；A-04/06/07 | DRAFT、REJECTED、BLOCKED 和未解决修订不能最终化；当前版本及证据重新核对；只有最终事务成功才 FINALISED；历史版本与评估可读；存在新修订时旧最终方案明确标注为历史 |
| A-09 并发、幂等及失败恢复 | As a user, I want safe retry, so that failures and repeated clicks do not corrupt my plan. | FR-04/09/10，可靠性 NFR；贯穿 A-04 至 A-08 | 同 key 同内容返回原结果，不重复建版本或最终记录；同 key 不同内容冲突；迟到任务不推进当前版本/run；保存故障全部回滚；输入不变可恢复失败 run；证据变化开启新 run，旧批准失效 |
| A-10 联调、CI 与提交包部署 | As a team member, I want a tested submission package, so that the prototype can be demonstrated from a clean environment. | 支撑 FR-01 至 FR-10、可靠性/适配器 NFR；A-01 起建立 CI，最终验收依赖 A-02 至 A-09 与 B | 自动化检查在本地及 CI 可重复；四个首轮场景接真实规则实现；后续修订、高风险、过期/冲突及禁止营火覆盖；Adapter 替换有证据；从干净解压目录按 README 部署、重建数据库、运行正常和异常演示；记录实际结果 |

## 3 首轮联调交付条件

| 场景 | B 与数据负责人提供 | A 提供 | 本轮状态 |
| --- | --- | --- | --- |
| I-01 正常流程 | 完整输入、装备数量/容量、交通估算、五类费用及覆盖整个行程的安全证据；规则生成产物 | 确认 UI、保存评估、eligibility、最终事务与回读 | 待准备、未执行 |
| I-03 超预算 | 明确两晚及费率单位；低成本替代方案；真实计算结果与来源 | 费用和预算差额展示、修订入口、当前版本禁止最终化 | 待准备、未执行 |
| I-04 缺失证据 | 独立场景 ID、营地、适用范围和具体缺失项；MISSING 规则 | 审核页显示缺失、批准不能绕过必要证据不足 | 待准备、未执行 |
| I-06 道路关闭 | 匹配营地/日期的关闭证据和 blocker | 显示阻止原因，人工及最终保存均无法绕过 | 待准备、未执行 |

低成本替代方案应按全部必要费用检查。若 AUD 50 在该输入下没有可执行方案，应真实返回无法满足及必要的需求变化，不能为了成功演示编造费用或偷偷增加预算。

## 4 验收证据与 Done

实现完成后，每项记录：真实 Jira Key、负责人、关联 FR/NFR、代码位置、环境与运行模式、输入 fixture 版本、测试步骤、预期、实际结果、证据路径、复核成员和日期。失败项有复现步骤与 Bug Key；修复后记录回归结果。

按五人分工要求，交付物保存、自检、至少一名其他成员检查、Jira 更新、测试步骤明确、synthetic 标签正确、版本关联正确、权限隔离、未完成方案不能显示为 Final、干净环境可运行，均满足后再进入 Done。对基础模块填写适用检查和整体验收依赖，不用空白模板冒充通过。

代码与自动化测试目前未执行；Jira Ticket、复核、CI 结果及部署记录均未生成。当前文档只能作为实施与验收计划。

## 5 当前可以交付给 B 的材料

- [接口基线 1.0](developer_b_handoff.md)：已确认决定、六项能力、首轮范围。
- [共享契约实施说明](shared_contracts_spec.md)：共同位置、签名、异常格式与数据链接。
- [数据检查报告](synthetic_data_review.md)：原包问题、修订与 fixture 缺口。
- 原始数据包：`C:/Users/87901/Desktop/ELEC5620/Stage2/campmate_synthetic_demo`，10 个文件，仍保持原样。

下一次进入代码阶段时，从 A-01 与 A-02 开始；不会把 B 尚未实现的工作标记为完成。
