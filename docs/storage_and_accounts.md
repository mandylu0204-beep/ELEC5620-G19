# A-03/A-04 登录与持久化基础

实施日期：2026-10-09，Australia/Sydney。固定业务演示时钟仍为 2026-10-08。本模块无需等待修订后的业务数据。

## 本轮入口

| HTTP | 用途 | 权限 |
| --- | --- | --- |
| POST /api/v1/auth/login | 登录，返回公开用户资料与 CSRF token | 演示账号；要求 X-CampMate-Client: 1 |
| GET /api/v1/auth/me | 刷新页面时恢复服务器会话 | 已登录 |
| POST /api/v1/auth/logout | 服务器撤销会话并清 Cookie | 已登录；CSRF |
| GET /api/v1/profile | 自己的资料与 revision，尚无资料返回 null / 0 | Camper |
| PUT /api/v1/profile | 保存资料，校验 expected_revision，服务器生成 profile_id | Camper；CSRF |
| GET /api/v1/plans | 自己的持久化方案列表 | Camper |
| GET /api/v1/plans/{id}/versions | 自己方案的不可覆盖版本内容 | Camper；不存在及他人记录统一 404 |
| GET /api/v1/review-queue | 当前 ESCALATED 版本的审核索引 | Founder |

公开的开发字段预览仍不保存请求。A-05 已增加 Profile 编辑表单和登录后的请求草稿、摘要与确认接口，见 [资料与请求流程](profile_request_flow.md)。规划启动、审批决定及最终化 HTTP 服务尚未接入；当前方案/审核页读取真实空列表，没有演示成功记录。

## 登录边界

数据库存 PBKDF2-HMAC-SHA256 密码哈希、每个密码的随机盐和 600000 次迭代。会话随机 token 只在 HttpOnly / SameSite=Lax Cookie 中，数据库存其 SHA256 摘要，JSON 不返回 token。CSRF token 保存在前端内存，刷新时通过 /auth/me 获取；不把会话写入 localStorage。登录换发 token，退出撤销服务器记录。会话过期使用系统 UTC，与 demo_today 分开。

演示账号见 README 与登录页，公开凭据只用于本机 synthetic 演示。seed 可重复且不会重置已存在密码或资料。CAMPMATE_SEED_DEMO_ACCOUNTS=false 只关闭新增 seed，不会删除或禁用已有账号。本轮不提供注册、密码修改、找回或公开部署配置。

角色从服务器用户表读取，客户端不能传 owner/reviewer/role 来获得权限。Founder 只读取审核队列，不通过 Camper 接口查看其他人的资料和普通方案。

实现参考：[Python PBKDF2](https://docs.python.org/3/library/hashlib.html#hashlib.pbkdf2_hmac)、[OWASP 密码存储参数](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#pbkdf2)、[FastAPI Cookie](https://fastapi.tiangolo.com/advanced/response-cookies/)。

## SQLite 与迁移

启动 lifespan 执行 schema version 1、2 迁移与可选账号 seed。版本 2 增加摘要及确认回执，不重建已有数据文件；迁移语句在同一事务中执行。使用 SQLite rollback journal、foreign_keys=ON、synchronous=FULL；写事务 BEGIN IMMEDIATE。连接在每次操作后关闭。迁移、保存异常和提交阶段外键失败均回滚；未支持的数据库版本拒绝启动，不静默重建文件。

| 表 | 保存内容 |
| --- | --- |
| schema_migrations / users / sessions | 迁移版本、身份及可撤销会话 |
| profiles / requests | 可修改资料与已确认需求快照 |
| request_summaries / request_confirmations | 分析 revision、资料/数据快照、摘要或错误、明确确认的幂等回执 |
| plans / versions | 当前/最终指针与不可覆盖的版本内容 |
| runs / run_versions / run_events | 登记运行、输入快照、fingerprint 与阶段事件 |
| recommendations / assessments / gear_checklists | B 产物保存位置；物流评估与装备清单同事务 |
| reviews | 精确关联 run/version/fingerprint/assessment IDs 的审核存储位置 |
| write_receipts | 同一步骤 key 的内容摘要与原结果 |
| final_records | 最终交付存储位置，最终化服务尚未实现 |

复合外键约束 plan 当前/最终指针和 run-version 关联不能跨 plan。触发器保护版本内容、评估、run 输入/绑定及已确认请求。每次新 run 保存独立快照；Profile 修改不改变历史。新版本递增版本号，保留旧内容。

## 给 B 的实际持久化端口

代码位于 backend/app/storage。Repository 的 begin_run / bind_port 只供 A 的受信任应用服务调用，不是 HTTP 参数，也不把创建 run、审核或最终化权限交给 B。record_confirmed_request 保留为受信任内部存储方法；A-05 HTTP 确认通过 RequestRepository 校验摘要、revision、资料及数据上下文后原子保存，不接受客户端提供 confirmed_context。当前没有可跳过确认的公开端点。

SqlitePersistencePort 已覆盖共享 PersistencePort 九项签名。A 登记 run 后生成各步骤 write_keys，将已绑定端口传给 B。每次调用核对授权 owner、登记 scope、active run、当前版本与 fingerprint。

同 key 同内容回读原结果；不同内容返回 IDEMPOTENCY_CONFLICT。陈旧 run 返回 STALE_CONTEXT，不能推进新版本。物流与装备清单原子保存；安全评估必须依赖同 run/version 的已保存物流。状态只允许单调阶段推进，终结 run 不能重开。需求变化要求重新确认；新证据重新登记 run，旧审核不自动沿用。

路由会保留 B 更严格的建议，并在 A 侧检查必要费用、未知物流、预算、装备、证据日期/有效范围、道路和审核关联。stub 无法获得 eligibility。必要证据不足及道路关闭不能被已有批准绕过。route 返回后仍需成功结束 run 才可能 eligible；任何端口都不能写 FINALISED。最终事务重算和审批提交服务属于后续 A-07/A-08，不以本轮端口测试代替。

**仍需 A/B 核对：** 当前保守的 Evidence 覆盖检查要求四类 WEATHER/FIRE/ROAD/RESTRICTION 且每个适用营地有 source_refs 记录关联、日期覆盖全行程；B 第一版需核对营地来源关联的表达方式。来源时效阈值、规则/场景适用性还需与 B Adapter 及修订 fixture 对齐。当前没有 B orchestrate 调用、业务场景或真实端到端通过证据。

## 数据与测试范围

backend/tests/test_storage.py 中的 Test Region、camp-test、金额、装备和证据是独立存储测试夹具，execution_mode=deterministic_demo 仅用于校验已注册 scope 的保存格式。它们不属于原 demo 包，不是修订后的四个业务场景，也不是 Agent 已实现的输出。部分审核由测试直接注入数据库，用来证明旧审核及强制批准无法解除阻止条件；产品尚无审批入口。

后续联调需要的数据：正常输入的装备数量/容量、交通和五类费用；超预算低成本替代；缺失证据的独立场景 ID 与适用范围；道路关闭的营地和日期。现在原始数据保留不改。
