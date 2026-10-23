# 流程设计与业务一致性修正交接

> 后续连续更新入口与关联待办实施见 [同次出行更新交接](trip_update_flow_handoff.md)。以下验证记录分别注明历史范围，不能替代该轮最终验证。

## 基线和范围

- 基线：`fix/display-issues` / `74dfad7`，包含 `3ad83ea`；开始时工作区干净。
- 先核对 display_permissions_handoff.md、A42 重新规划、A33 删除、Founder 审核、当前持久化和角色读取投影。
- 接口与阶段计划先记录在 [接口实施契约](workflow_consistency_interface_proposal.md)；用户明确批准本轮使用迁移 **11**，由本轮实现。
- 没有切分支、自动 commit、push 或合并；没有调用真实校园模型、修改个人环境文件／密钥、用户原数据库或封存数据，也没有主动重启网页服务。

## 已实现

### 同一次出行的明确关联

迁移 11 新增 trip_series、plan_series_members、successor_requests、successor_commands、series_delete_commands 和 series_replacements。
外部稳定身份只有 trip_series_id，直接来源为 predecessor_plan_id；当前方案和 revision 由服务器维护。
成员、来源、命令回执及替代记录不可更新或删除；普通业务删除是逻辑 tombstone，原始版本、评估、审计和最终快照不改写。

- `POST /api/v1/plans/{plan_id}/successor-requests`：严格 body 绑定来源系列 revision、版本 ID/revision、run ID/revision 和 command_key。服务器复制原确认需求，不采信任意系列归属。
- 创建预览草稿不移动当前指针、不启动规划；确认和 PLAN 事务再次检查来源。后继请求／方案仍是不可变确认快照机制。
- PLAN 写入 run、成员、当前指针、替代记录和幂等回执同事务完成；并发只允许一个后继成为当前，同 key 丢回执重试回读原 plan/run。
- `/trip-series`、`/trip-series/{id}` 返回当前方案、最新运行、可见历史和带所属 plan_id 的旧最终记录。
- 前端每个明确系列一张主卡片；相同日期、目的地或标题的新独立请求不会归入旧系列。历史无关联数据保持独立。
- 旧 `/plans` 保留兼容的逐方案索引；新版页面使用系列端点，不在前端按标题等猜测合并。
- 新运行未完成或失败时，旧最终记录作为独立入口保留，不赋予本次新运行成功状态。

### 保存资料后显式采用

- ProfilePage 的个人资料保存、变更识别和放弃修改行为不重做；仅保存不会触发规划。
- ReplanSession 调用明确后继命令；预览显示拟采用的 profile_revision，以及人数、装备／车辆、交通、经验、儿童和特殊需求的旧／新事实。
- 自定义名称不作为物品身份，不按名称合并；对比保留每一行、实际 item_key、未知值及确认状态。
- 第一次确认前读取当前 revision，服务端 confirm 事务仍是最终并发守卫。冲突使勾选失效，需要显式重新载入差异／来源，不自动采用新资料。
- 草稿创建、确认、PLAN 都保留各自稳定的命令 key；确认丢回执后优先重试原回执，不因后来个人资料变化改写已经固定的输入。
- 取消、保存、刷新、读取和轮询不 dispatch；只有用户明确核对并确认后才启动正式 PLAN。
- 恢复继续使用 runs.confirmed_context、原 scope、checkpoint 和已保存产物；后续个人资料更新不参与恢复。heartbeat、lease 和幂等写入能力不改变。

### 审核业务分离

政策标识为 `current-evidence-risk-review-1`。它不是 display_status，也不是出行级永久审核锁。

- `/review-queue` 只收纳当前且证据完整、确有风险人工判断触发、没有其他必要缺项／修订／硬性 blocker 的审批任务。
- `/assistance-queue` 是独立 Founder 只读修正／协助索引。普通用户无权限；其详情不能提交 APPROVE、REJECT 或 REQUEST_REVISION 冒充风险审批。
- 原 Founder 详情诊断权限范围保留；协助页面明确“不是待审批任务”。
- review 命令仍精确绑定版本、run、两份 assessment IDs 和版本/run revision；在事务中增加系列当前检查。
- 后继启动时服务端记录旧任务替代，旧页面晚到审批、旧方案重试、修订、重评和最终保存均被拒绝。旧记录和旧批准仍保留历史，不自动授权新方案。
- 新结果仍触发风险审批时须重新审批；新正式结果不触发且符合既有 eligibility 时正常进入用户确认保存。
- 原 SqlitePersistencePort.decision 的 blocker、证据、费用、装备及最终化守卫不放宽。display_status 不参与这些决定。

### 装备规则与模型语言边界

不重写帐篷算法或 optional 机制、不改封存规则：

- 容量型：帐篷按已确认数量 × 每顶人数；车辆按已确认数量 × 座位数。
- 必需项：按当前规则的 essential 和 severity_if_missing 判定；饮用水、急救包、睡眠／交通等触发要求仍由规则提供，不是名称决定。
- 已支持可选不采购：如活跃规则中的非 essential 保暖内衬，通过 allowed_methods 提供 DEFER_OPTIONAL；保留真实缺口，不称免费库存，不修改 essential。
- 未知数量、容量或未核实状态不从名称补齐；三人两顶且实际总确认容量三人可通过该容量项，不代表其他必需项也已通过。
- 不加共用豁免／忽略必需项按钮，资料未知值仍可按原协议保存，正式检查继续提示缺项。

按用户后续要求，已撤回规划和物流模型输出中文化：Prompt 及组件版本恢复为基线 `b04-planning-coordinator-2`、`campus-logistics-agent-1`，不再加入中文输出指令。
没有修改模型输出 schema、安全文本协议、token 上限、timeout、retry 或计算流程；数量／容量／Decimal／整数分仍由程序计算。
既有前端中文展示保留，模型历史内容原样回读，不自动翻译，不用模板替换模型实际意见；仅为本次中文化新增的两项测试已随功能一起移除。

## 删除语义和权限

- 删除历史方案：不改变当前指针；该历史的方案／run／final 入口及聚合引用消失。
- 删除当前方案：有活动 run 时拒绝；否则清空当前指针，系列保留未删除历史，**不自动提升历史方案或恢复旧待办**。
- `POST /trip-series/{id}/delete`：需 command_key 和 expected_series_revision；任何成员有活动 run 时拒绝，否则同事务逻辑删除整次出行和成员、隐藏所属请求。重复命令返回同一无内容成功结果。
- 所有跨方案最终链接都使用其所属 plan_id，不从当前方案拼旧 final_id。
- 普通用户的新系列／后继请求入口也不能读到 trace、usage、模型配置或文件摘要；包括重放后继创建命令时已确认的 request。HTTP 响应经过既有请求投影。
- 恢复、持久化、eligibility 使用内部完整数据，不把裁剪 HTTP 结果写回 DTO。

## 迁移与运行注意

11 只在测试隔离数据库执行过。A 合并前须核对并行分支的迁移编号，不要把已应用的 11 改号或复用。
没有回填旧系列身份，不更新旧快照内容或哈希；升级测试确认旧数据保留。
现有正在运行的后端尚未由本轮重启／升级；不要仅凭 Vite 热更新就宣称新接口已在旧服务接通。需要用户安排一次受控启动，优先新隔离数据库。
中文化已撤回，但若测试运行是在此前临时中文 Prompt 下创建，其身份仍与恢复后的运行配置不同；不得改写已有 scope、trace 或哈希来绕过检查。正在运行的服务不会由本次修改自动重启，安排受控启动时须注意活动运行兼容性；历史纯读取仍保留。

## 修改文件

- 系列、迁移和守卫：storage/trip_series.py、database.py、repository.py、requests.py、workflows.py、port.py、plan_queries.py、finalisation.py；HTTP 入口在 http_plans.py。
- 审核：application/review_policy.py、storage/reviews.py、http_reviews.py、frontend/src/reviews.tsx。
- 采用资料和卡片：frontend/src/replan_session.ts、replan.tsx、profile_changes.ts、plans.tsx。
- 模型语言改动已撤回：llm/coordinator.py、llm/logistics_agent.py 恢复为基线，不再作为本轮功能改动提交。
- 新回归：test_trip_series.py；扩展装备、读取投影／组件和后继控制器测试。历史升级断言从 10 更新到 11，旧审核队列断言按审批／协助正式拆分。

## 验证记录

撤回模型中文化后的定向验证（2026-10-22）：

- 规划、物流及 Hybrid 组件离线回归：**122 passed**，1.89 秒；未调用真实模型。
- 两个模型组件与 test_model_planning.py 已确认与 HEAD 无差异；git diff --check 通过。
- 仓库保护拒绝首次使用 /private/tmp 作为 pytest basetemp，该次未执行测试；改用 var 下全新临时目录后得到上述结果。
- 未重新运行撤回后的后端全量；下列 1465 项仅作为撤回前的历史验证记录，不与本次 122 项相加。

撤回模型中文化前的历史组合验证结果（2026-10-22；不是撤回后的最终全量结论）：

- 后端最终组合 **1465 passed，1 warning**，790.39 秒；从最终后端源码重新完整执行，不是首轮与局部结果相加。
- 前端最终组合 **79 tests / 79 passed**，覆盖既有展示／权限组件，以及资料差异、revision 冲突、创建／确认／启动丢回执、旧审批文案和系列跨方案最终链接。
- TypeScript 检查、Vite 生产构建、共享 JSON schema 导出一致性、git diff --check 全部通过。
- 唯一警告为既有 Starlette testclient 的 httpx 弃用提示。
- 首轮全量在迁移保护／测试补充期间中止；其中两处历史迁移计数固定为 10 的断言已改为 11。没有将该轮通过数用于上述最终 1465 的结论。
- 角色组合、checkpoint／heartbeat、三角色审计丢回执和恢复、权限读取投影均包含在最终后端全量中。权限新增断言直接检查原始 HTTP JSON；没有用内部审计辅助替代可见性证明。
- 这些是离线组件和 TestClient HTTP 验证，不是浏览器交互或真实校园代理验收；没有实际模型请求或付费翻译。

复现命令（使用仓库根 .venv，不使用 backend/.venv；先准备锁定依赖和 Node）：

```sh
cd backend
../.venv/bin/python -m pytest tests --basetemp=../var/pytest-workflow-final-combination --tb=short -o addopts='' -q --durations=8
../.venv/bin/python -m app.export_contracts --check
cd ../frontend
node --experimental-strip-types --test tests/*.test.mjs
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/vite/bin/vite.js build
```

## 独立后续范围

1. “仅装备变化、保留行程并采用新资料重评”没有实现。现有 REASSESS 仍采用原确认资料；如新增操作，需另与 A 冻结新输入绑定、审计身份及 trace 原始来源。
2. 更丰富的每日活动／准备／待确认 schema 没有引入，需独立有界协议评审。
3. A 的接口／迁移联合复核、受控部署和浏览器交互验收尚未完成；没有本轮流程功能的真实校园模型验收，也未承诺代理可用。后续安全 Agent 独立诊断不替代流程功能验收。

建议交接 A：先复核迁移 11 的唯一性、系列 CAS 与删除边界，再复核风险审批／协助分离及旧最终所属 plan_id；随后安排隔离数据库的浏览器联验。未获用户许可不要自动升级原用户数据库或发起付费调用。
