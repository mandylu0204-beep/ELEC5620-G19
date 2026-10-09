# A-05 资料与请求流程

实现及浏览器验证：2026-10-09；交接记录整理：2026-10-10，Australia/Sydney。演示业务时钟仍固定为 2026-10-08。

本轮完成 A 侧 Profile 表单与请求存储、澄清、确认流程。解释器仍为 stub：只使用用户明确填写的结构化字段，不从自然语言猜测。未接入 B 的实际解释器、规划或四个业务场景，不能据此宣称 Agent 验收通过。

## 使用流程

1. Camper 登录后在 `/profile` 保存人数、经验、儿童、装备、交通和无障碍需求。数量、容量、车辆数及距离未明确时保留 null，确认前摘要会显示未知。
2. 在 `/request` 填写想法并保存草稿。当前支持地区从 synthetic 营地 CSV 读取；原包只有 CampMate Demo Region。
3. 打开草稿，补齐目的地、开始日期、晚数、预算，并生成摘要。人数取本次 Profile 快照。只给天数时要求澄清；两晚推导三天和开始日期加两天的结束日期。明确填写的天数或结束日期冲突时保留冲突并询问，不偷偷覆盖。
4. 阅读需求与资料摘要，勾选确认后保存。缺失、冲突、超出支持地区、未保存修改或正在分析时不能确认。确认成功不创建 plan 或 run，开始规划暂时禁用。
5. 刷新可恢复草稿或已确认快照。确认后需求不能原地改写；需求变化新建请求。修改 Profile 不覆盖历史快照。

## HTTP 约定

所有路由位于 `/api/v1`，仅 Camper 可用，读取和写入按 owner 隔离。他人请求与不存在请求统一返回 404。写入要求会话、`X-CampMate-Client: 1` 与 `X-CSRF-Token`。

| 入口 | 输入 / 作用 |
| --- | --- |
| GET /request-context | 实际支持地区、execution_mode、demo_today、planning_available=false |
| GET /requests | 当前用户的已保存请求 |
| POST /requests | raw_text、explicit_fields；返回 revision=1 的草稿 |
| GET /requests/{id} | 当前状态、revision、摘要、资料快照、错误及确认上下文 |
| PATCH /requests/{id} | raw_text、explicit_fields、expected_revision；编辑后摘要失效 |
| POST /requests/{id}/interpret | expected_revision；调用 AgentPort.interpret_request，校验输出再规范化 |
| POST /requests/{id}/confirm | expected_revision、command_key（16–128 字符）、acknowledged=true |

确认回执按 owner 和 command_key 唯一：同 key、同请求及同输入回读原结果；不同输入返回 IDEMPOTENCY_CONFLICT。acknowledged 使用严格布尔类型，false 或整数 1 均不接受。共同 Agent DTO/schema 未改变；上述请求命令是 A 的 HTTP 模型。

## 状态与快照

草稿状态为 DRAFT；分析期间为 ANALYSING。输出进入 NEEDS_CLARIFICATION、UNSUPPORTED 或 AWAITING_CONFIRMATION；只有显式确认后进入 CONFIRMED。分析异常保存错误并恢复 DRAFT，保留用户输入。服务意外中断留下 ANALYSING 时，页面允许重新保存并分析；自动后台任务恢复尚未实现。

每次分析捕获 Profile revision/内容、演示模式/时钟，以及六个业务文件的摘要。`rules_version=a-request-normalization-v1` 标记 A 的规范化版本，不表示 B 的规则已实现。确认前再次核对 Profile 与数据上下文；变化返回 STALE_CONTEXT，需重新分析并阅读摘要。字段编辑也检查 revision；迟到分析结果不能覆盖新输入。

CONFIRMED 保存不可覆盖的 ConfirmedContext，含需求、Profile、演示和数据上下文以及确认时间。确认状态、回执与快照同事务保存；migration 2 保护已确认摘要/回执。已有 migration 1 数据库自动升级并保留原记录。

## 验证与交接

新增 12 个请求测试（含参数化情形），累计后端 54 个：天数/日期冲突、重复确认、旧 revision、Profile/数据变化、跨用户访问、非法解释器输出、迟到分析结果、历史快照及旧数据库迁移。测试使用独立 SQLite 与业务文件副本，不修改原始包。浏览器实际检查保存资料、冲突澄清、确认和刷新；资料改为 3 人后，原确认快照仍为 2 人。

证据：[资料表单](evidence/profile-editor.png)、[确认前摘要](evidence/request-summary.png)、[已确认快照](evidence/request-confirmed.png)。浏览器检查使用单独的 `var/e2e-a05-20261009.sqlite3` 与 5174/8001 端口；该测试数据库被 Git 忽略。默认启动仍使用 `.env` 中的数据库与 5173/8000。

B 后续注册实际 AgentPort 工厂后，仍从当前持久化流程调用 interpret_request；自然语言提取、来源与假设展示需以 B 首版产物联调。A-06 再接规划进度和产物；正式业务联调需要修订数据及正常、超预算、缺失证据、道路关闭四个场景。当前没有审批、最终化或真实 Agent 成功记录。
