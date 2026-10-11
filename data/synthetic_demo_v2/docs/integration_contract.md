# CampMate v2 接入约定

此约定根据 synthetic_data_review.md 和正式 Stage 1（第 5–7、24、49 页）修订。它是可供 A/B 采用的接口提案，未声称现有实现已经支持。

## 输入和测试隔离

请求解析输入仅包括原始 natural_language_request、明确 user_supplements、profile_snapshot 和来源元数据。
synthetic_requests.json 的 destination/start_date/duration_* 等是数据集中的候选摘要，Agent 不得将其当作提取答案。
runtime_requests.json 已删去这些候选值，以及 confirmed、expected_*、missing_fields。使用 runtime_inputs.py 从 allowlist 生成输入。
测试 fixture 的 overrides/失败注入必须由 harness 在动作前处理。Fixture setup 和 oracle 不属于用户补充信息，也不能作为 Agent 输入。
装备归一化的 confirmed=false 表示尚未确认；确认摘要应展示 null 数量和容量并要求补充。

安全 Agent 输入来自 runtime_safety_evidence.json：场景证据、限制、已知 blocker、状态及时间。severity/confidence/outcome/actions 均由实际 Agent 返回，再与 oracle 比较。
source_date 保留原包来源日；新 observed_at 与 valid_from/valid_until 是独立标注的演示观测时间/覆盖期。AVAILABLE 不代表现实验证或始终有效。

## 晚数与不可变记录

start_date + duration_nights = end_date；duration_days = duration_nights + 1。
request-01 从 2026-10-20 起两晚，截止 2026-10-22，共三天。legacy_duration_days=2 只记录 v1 输入。
request-03 既没有日期也没有晚数，不从旧的结构化 2 推导出用户已提供时长。
候选信息完整进入 AWAITING_CONFIRMATION，只有 Camper 的显式确认事件才进入 CONFIRMED，并建立 immutable request/profile snapshot。
变更已确认约束必须重新确认。Profile 更新不修改历史 Request/PlanVersion snapshot。

## 路由与最终化

三个业务 Agent：Planning Coordinator、Gear and Logistics Manager、Safety and Compliance Officer。
应用服务/Orchestrator 负责鉴权、写数据库、生成不可变版本、关联结果和最终保存。Agent 返回建议/评估，不直接写最终计划。
先 gear/logistics，再 safety。修订创建新版本，清空新版本的评估与审批引用；旧记录保留。

1. 尚有 mandatory blocker 时 finalization_eligible=false，不因 Founder APPROVE 而改变。
2. HIGH/CRITICAL 风险、未解决冲突或必要证据不足均需要人工审核；severity 与 confidence 来自实际输出。
3. 可修复问题可同时返回 outcome=REVISION 和 requires_human_review=true。现有高风险版本进入 AWAITING_REVIEW，保留修订反馈；修订新版本后必须重新评估风险。
4. safety-05 保留 REVISION，并明确同时升级且不具备最终化资格。safety-09 改为 REVIEW，保留换日期/营地及增加饮水的建议。
5. Founder 决策绑定当前最新版本且理由非空。APPROVE 不能制造缺失证据、继承旧检查或解除 blocker。
6. READY_TO_FINALIZE 需当前最新版本、确认请求、三个检查齐全、必要证据足够、mandatory blockers 为空及任何必要审核已批准同一版本。
7. 数据库原子事务保存最终方案并切 FINALIZED。失败回滚保持 READY_TO_FINALIZE；同一 idempotency_key 恢复后可重试，成功后只保存一次。
8. 已保存 FINALIZED 的显示失败不撤销保存，允许重新读取。

## 测试执行约定

每条 tests/synthetic_agent_test_cases.csv 对应一个独立 tests/synthetic_test_fixtures.json 对象。
先重置测试存储，再装载 setup 中的 profiles/requests/plans/assessments/reviews/final_plans，校验 latest_version_id 及所有版本链接。
有 confirmed=true 的 setup 记录代表具有显式 confirmation_event 的历史请求，不能由期望字段创建。
按 actor.user_id、role、authenticated 使用真实鉴权上下文。action 可覆盖 actor 以显式模拟身份切换；例如先由 FOUNDER 审核，再由 CAMPER 所有者发起最终化。随后逐个执行 actions，并对比独立 oracle。
CREATE/GENERATE/REVISE action 的目标 ID 可以尚未存在；其他非空版本必须由 setup 预置。
ADD_USER_SUPPLEMENT.normalized_equipment 代表用户明确提供并确认的完整库存替换，不能加到旧库存上而重复计数。
SET_TEST_STATE、ADVANCE_DEMO_CLOCK、CLEAR_FAILURE_INJECTION 等是 harness 操作，不应成为普通用户可调用的生产端点。
组件 fixture 不含无关 Request；其 component_context 明确日期、晚数、活动。集成测试则要求营地一致、安全数据覆盖全部行程。
模板复用采用新 safety ID 并记录 template_source_id/context_request_id，不改写原模板。

demo_clock 默认固定为 2026-10-09T10:00:00+11:00；安全组件另有明确场景时钟。每次场景运行必须在启动前设置唯一固定时钟；运行过程中不得推进时钟。如果需模拟新日期，必须启动新的 workflow run / reassess，并重新生成对应输入及证据快照。
成功路径从启动起使用 2026-11-06T08:00:00+11:00 这一固定时钟，覆盖请求确认、计划、评估及最终化；安全观测不得因中途推进时钟而变成同一 run 下的新输入。
运行日期不能来自系统 TODAY()/now()，因此 11 月现场演示不会让输入自动过期。

tests/ 中的 NOT_RUN 只能在真正运行应用后由另一个结果文件记录实际 PASS/FAIL，不得把 expected_outcome 当实际结果。
