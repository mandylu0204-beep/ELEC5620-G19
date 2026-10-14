# B → A：A24 模型物流运行时接线

日期：2026-10-14（Australia/Sydney）。分支：`feature/llm-logistics-agent`。基线：main `319f541`（A24），保留组件提交 `e0b25eb` 和 A21～A24 全部进度。

已按 [A24 交接](a24_logistics_audit_handoff.md) 与 [冻结回复](a24_logistics_contract_reply.md) 接入 Hybrid 和 Orchestrator。默认仍为规则物流；只有显式 `CAMPMATE_LOGISTICS_EXECUTION=model` 且当前 agent/v2 工厂通过就绪检查时才启用物流模型。本文的离线测试不等于真实校园/浏览器联合验收。

## 1. 本次代码

- `HybridPlanningAgent` 接收并保留 A 工厂提供的 `logistics_agent`，提供 `assess_logistics_with_trace()`，声明 `logistics_audit_contract='1.0'`。
- 同时校验数据对象、最终 workflow context、登记 seed、非递归配置摘要和最少3轮；等待模型返回后重新检查身份，禁止模型失败时规则回退。
- 共享六方法 AgentPort 保持不变。独立 `assess_gear_and_logistics()` 在显式模型绑定下真实调用物流角色；正式编排使用带产物的方法，不能丢弃 plan/trace。
- Orchestrator 将 `outcome.assessment/plan/trace` 交给 A 的正式保存端口，沿用 `scope.write_keys['logistics']`。安全只消费已保存 `StoredAssessment`。
- 模型启用时提前检查完整 Agent/端口能力；能力不全在模型和业务写入前失败，不改标签、不降级。
- checkpoint 在 A 已验证记录的基础上再检查物流审计关联、完整方案/结果/trace 及载荷摘要。已保存物流复用原产物、原审计及原保存 attempt；只有未提交步骤才能重新调用模型。
- 移除 Orchestrator 按 PERSISTENCE_FAILURE 自动提升 RETRY 的逻辑，与 A24 Dispatcher 对齐：临时保存失败可恢复，审计完整性错误不可恢复。
- Hybrid 实现身份升级为 `b05-hybrid-planning-3`，随新确认/run context 登记；不可跨新旧身份继续旧 run。物流 v1 业务计算、Prompt/tool/validation 身份不变，不删除 A 的历史 v1 验证器。

没有修改 A 的正式持久化接口/数据库迁移、工厂、Dispatcher、页面、共享 schema、个人环境文件或封存数据；本次只调整 A 的两项能力检查测试，使其在真实 Hybrid 已接线后继续验证“缺能力不能启用”，不再假设正常 Hybrid 永远未就绪。

## 2. 严格纯校验 helper

新增 `backend/app/llm/logistics_validation.py`：

```python
plan, trace = validate_logistics_payload(
    saved_input, trusted_rule_baseline, result,
    raw_plan_json, raw_trace_json,
    identity=registered_logistics_agent.identity,
)
```

该 helper 不读文件、不发网络、不存储，要求调用者提供可信保存输入、规则基线及已登记组件身份。校验：

- JSON 数量仅十进制字符串/null；金额严格整数分，不接受 bool/浮点/数值字符串；布尔字段不接受字符串。
- plan/trace 字段、长度、hash、工具链、成功标记、集合唯一性和非空白说明；拒绝隐式填字段及类型转换后的载荷。
- 输入/规则事实按原 `model_dump_json()` 字节求摘要；proposal/configuration 按 canonical JSON 求摘要。
- 从结构化方案重建 proposal，确定性重算完整 plan/result，精确比较来源、Decimal 表示、费用、资金分配、库存、确认需求和 blocker。

现有 `SupplyPlan`、`ValidatedLogisticsPlan` 和 `LogisticsTrace` 也收紧非共享内部字段边界。A24 保存/历史入口的独立严格校验继续保留；本 helper 不替代 owner/lease/scope、512 KiB、事务、回执和归档验证器选择。JSON 解码处继续拒绝重复 key/非有限数字。

## 3. 操作与恢复语义

| 情况 | 模型及保存行为 |
| --- | --- |
| PLAN | 行程规划模型 + 当前物流模型；分别保存规划 trace 和物流 audit |
| REVISE | 使用已登记反馈生成新版本，再产生本次物流 audit；旧审核不沿用 |
| REASSESS | 不调用规划模型、不生成新版本；同版本的新 run 生成新物流 assessment/audit，原规划 trace 不复制 |
| NO_MATCH | 不调用两个模型、不生成版本或物流 audit |
| 物流保存前整体回滚 | 复用已保存行程，只重做缺失物流；可能发生额外模型调用 |
| 物流提交后丢失回执 | 重启/新 attempt 读取 checkpoint，跳过物流模型及保存，复用原产物 |
| 安全/route 回执丢失 | 复用已保存的对应步骤，无新增模型调用 |
| 已保存物流审计缺失/损坏 | PERSISTENCE_FAILURE、不可恢复、CONTACT_OPERATOR；禁止重跑补 trace |
| 配置或 lease 漂移 | STALE_CONTEXT，取消等待并拒绝迟到产物 |

模型与保存调用均留在现有 Orchestrator.call 的 heartbeat/cancel 包裹内；新测试用 Event 验证等待期间实际续租，而不是依赖精确 heartbeat 次数。外部模型调用不承诺 exactly-once。

## 4. 验证结果

本轮使用 MockTransport/独立假密钥，覆盖完整确认 → HTTP dispatcher → 两个真实组件 → A24 SQLite 保存链。不读取 `.env.llm.local`，不调用校园服务，不操作已有用户数据库。

本机锁定环境 Python3.12.14 / Pydantic2.13.5 / httpx0.28.1，未增加依赖或改锁文件：

- A24 基线加本次接线的全量后端：**859 passed、0 failed、0 skipped**，118.95秒；1条既有 Starlette TestClient 弃用警告。
- 新增接线测试47项，包含在上述全量中；原组件58项、A24审计36项及原规划/修订/规则恢复回归也通过。
- 共享 schema 1.0 导出检查通过；前端 TypeScript 检查及 Vite 构建通过（56模块）。
- pip check：No broken requirements found。
- 数据静态验证68 passed、0 failed（另58条数据包验收规格仍为 NOT_RUN，不由静态脚本执行）；使用默认只读模式，不带 `--write-report`，未改报告或重封存。
- Git 空白检查通过；本次没有封存数据、私有环境文件或共享 schema 的修改。

新增测试覆盖四套 HTTP 场景、真实能力/meta 就绪、超预算修订、同版本重评、NO_MATCH、四保存点整体回滚、重启/丢回执恢复、checkpoint 篡改、不可恢复规划/物流错误不提升 RETRY、模型失败无规则回退、能力缺失、身份漂移、等待续租/取消、权限隔离/历史快照及严格类型/清单/UTF-8 边界。

四场景的模拟规划回复只在测试夹具中指定合法营地，以覆盖登记证据；生产代码仍接受全部合法候选，真实验收不应强制模型选预期营地。schema 最大清单测试只证明形状边界，构造的假事实仍被业务校验拒绝；512 KiB 精确字节测试也不等于非法大载荷能通过事实验证。

## 5. A/B 下一步：真实校园联合验收

无需再等待 A 实现保存接口；A24 能力已经具备。请 A 复核本分支的完整接线和新纯 helper，按同一基线集成后联合执行：

1. 使用隔离数据库、已配置的本地凭据和可访问校园代理的网络，显式开启 agent/v2 + 模型物流；不要修改默认 rules 配置或原用户库。meta/readiness 不进行真实 probe。
2. 从本人登录、Profile 保存、需求解释和明确确认开始执行 PLAN；检查真实行程规划及物流工具循环、实际选择、两个独立记录和安全依赖。
3. 用超预算需求执行低价 REVISE；验证新版本、新物流记录及未清除的真实费用/安全约束。再执行同版本 REASSESS，确认仅产生新物流调用而原规划记录保持。
4. 用登记的缺证据、封路场景验证真实结果；若模型选择不同合法营地，按实际数据解释结果，不改结果或伪造安全通过来完成演示。
5. 核对物流建议的未确认标记、未知费用和资金缺口；正常可最终化时明确保存最终记录，重启回读并验证 owner 隔离、历史和最终快照中的独立物流审计。
6. 在隔离环境验证保存提交后丢回执恢复，确认数据库与 trace 不重复；只记录脱敏关联 ID/计数和浏览器证据，不输出密钥、原始个人资料或私人推理。

真实验收尚未执行，也未声称校园网络已连通或实际 token/账单已验证。本轮不 commit/push、不主动发消息给 A；由用户提交完整接线分支后继续联合验收。
