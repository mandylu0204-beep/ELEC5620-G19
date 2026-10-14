# A → B：物流模型接口复核与冻结回复

日期：2026-10-14（Australia/Sydney）。复核对象：`feature/llm-logistics-agent`，提交 `e0b25eb89cb4213ca529d664de6ac67d4f6390a4`。

## 结论与当前状态

同意提案的总体设计，L-01～L-09 按下述补充约定作为接线基线。以下是接口确认，不代表正式存储、Hybrid、HTTP 或页面已经实现；相关能力完成前不得启用模型物流。

B 分支已推送，远端对应提交 CI 成功；复核时没有开放 PR。交接文档末尾“未 commit/push”的表述已过时，请更新。B 基线 `3a1206f` 早于 A21～A23，当前 main 为 `488c961e75367ed96d1781ce7372dd0046df5178`。B 的本次变更仅新增 3 个组件文件、1 个测试文件和2份文档，尚未修改 Hybrid、Orchestrator、工厂、数据库或默认配置。

A 在独立导出的 B 源码快照上复跑组件测试：58 passed；全部使用 MockTransport/假密钥，没有读取个人 `.env.llm.local`、发送校园请求、改封存数据或改 main 应用代码。B 报告的771项全量测试属于 B 的旧基线，不能当作包含 A21～A23 和新增正式接线后的全量验收。

## L-01：签名与角色——同意

```python
async def save_model_logistics_assessment(
    self,
    context: VersionContext,
    result: LogisticsResult,
    plan: Mapping[str, object],
    trace: Mapping[str, object],
    write_key: str,
) -> StoredAssessment: ...
```

A-owned `RecoveryPort` 扩展固定 LOGISTICS，使用 `scope.write_keys['logistics']`，不增加调用方角色参数或写入键。当前 claimed attempt、owner、scope、版本和有效租约守卫继续生效。模型审计必需时普通 LOGISTICS 保存拒绝绕过；规则物流和安全继续走原入口。

Hybrid 内部方法名冻结为 `assess_logistics_with_trace(input: LogisticsInput) -> LogisticsOutcome`；共享六项 AgentPort 和 DTO/schema 1.0 不变。启用模型物流时编排只能使用带 plan/trace 的方法，不保存仅有 LogisticsResult 的退化结果。

## L-02：载荷、类型、摘要与上限——同意，补充严格保存校验

提案第3节全部 plan/trace 字段、必需 null、额外字段拒绝、金额/数量/摘要规则均接受。512 KiB 指以下完整调用载荷 canonical JSON 的 UTF-8 字节数上限，不是 Python 字符数，也不能通过截断清单或意见通过：

```python
{'context': context.model_dump(mode='json'), 'kind': 'LOGISTICS',
 'result': result.model_dump(mode='json'), 'plan': plan, 'trace': trace}
```

A 正常夹具实测为27,951字节。该结果只证明正常夹具足够，接线时必须补最大允许清单、中文长理由、上限与超限测试；A内部生成的事实快照不作为调用方能修改的载荷字段。

**实际代码与提案尚有差异，不能直接把现有类当严格保存入口：** `LogisticsTrace` 的 turns/int、validation_passed/bool 会接受数字或布尔字符串；`SupplyPlan.procurement_quantity` 的普通 Decimal 会接受浮点，confirmation_required 也会接受布尔字符串。A 用独立夹具复现了这些转换。这不意味着目前未接线的组件已绕过应用存储，但正式端口必须先拒绝错误类型，再验证完整重算结果。

B 请提供可复用的严格纯校验 schema/helper（含嵌套字段边界、非空白理由与集合唯一性），A 在保存入口独立调用并拒绝额外字段/错误原始类型。JSON Decimal 只接受有限、非负十进制字符串；整数分不接受 bool、浮点或字符串；bool 必须是 bool。共享嵌套 DTO 保持1.0，其余事实仍以完整确定性重算比较为准。

输入/规则事实 hash 继续使用原 `model_dump_json()` 字节；proposal、配置和完整保存载荷 hash 使用提案 canonical。不得重排列表、删 null 或调整 Decimal 表示掩盖不同载荷。读取保存的 JSON 必须拒绝重复 key 和非有限数字；Mapping 端口收到的是已解码对象，重复 key 检查须在有原始 JSON 的解码边界执行。

## L-03：身份登记——同意，明确最终 context 构建顺序

接受四个 `a_logistics_*` 键和7项 identity seed；不把完整 context 或 configuration_fingerprint 塞回 seed/context。保留已有数据、场景、规划身份及修订反馈，冲突明确拒绝；规则身份追加 `/a-model-logistics-audit-v1`。

注册必须先取得可信 seed，再把物流标记加入注册 base，最后只构建一次正式完整 WorkflowConfiguration，之后用该最终 context 创建正式 LogisticsAgent 并验证 expected fingerprint。不要把已有完整 configuration.context 再传回构造器反复追加规则/工作流版本后假设身份不变。

正常、修订和重评分别使用本次最终 context；公开配置改变需重新确认/新 run，按现有机制处理。历史校验只使用保存 seed/context 与原验证器；换密钥不改变公开身份，无密钥只影响新的模型调用。

## L-04：权威事实、重算和事务——同意

A 从授权保存事实重建 LogisticsInput 与规则基线，按登记数据、规则及场景调用纯计算工具重算 plan/result；不接受调用方额外可信基线。完整字段、数量、费用、来源、确认状态、blocker 和澄清都必须一致。

assessment、gear checklist、物流 audit、write receipt 同事务。A生成 ID、保存时间、实际保存 attempt 和两份原始事实快照；唯一性及关联按提案执行，成功审计不可覆盖。事务内不调用模型/网络，提交前重检 active/scope/lease 及校验快照身份。

## L-05：回执、checkpoint 和恢复——同意

冻结字段名 `model_assessment_audits`，键为 `LOGISTICS`，内容按提案第7.2节；规则物流为空映射。规划 trace 原有字段/归属不变。

回执命中也校验 assessment/checklist/audit/receipt 全部关联，不能直接复用通用 write 的提前返回分支。完整成功产物丢回执时复用原产物及实际保存 attempt；任何审计缺失、损坏、关联不一致都不许重跑模型补 trace。

允许尚未整体提交的模型调用再次执行，不承诺外部调用 exactly-once。REASSESS 的物流审计属于新 run/new assessment，原行程 trace 仍使用 origin-version-v1 的原生成关联。

## L-06：开关与操作范围——同意

冻结 `CAMPMATE_LOGISTICS_EXECUTION=rules|model`，默认 rules。model 首轮支持已有 agent/v2 工厂中的 PLAN、REVISE、REASSESS；其它模式或未登记工厂显式失败，不规则回退。NO_MATCH 没有保存版本时不调用物流模型、不要求物流审计。

max_turns 至少3；缺密钥、缺能力、未完成迁移、非法公开配置或身份不一致时 readiness 失败。就绪检查只做本地验证，不发校园探测请求。不能改变开关后继续旧 run。

## L-07：读取、历史、meta 和页面——同意，补充验证器与空步骤语义

meta 只在模型物流实际启用且通过本地就绪校验时标注 `planning_stages.logistics=model`。角色审计独立展示；REASSESS 文案区分“不调用规划模型”和“本次物流调用模型”。装备拟采购/借用、数量、费用、资金缺口、未知与未确认逐项展示；不把模型建议当已拥有物资或审核事实。

审计必查覆盖 checkpoint、回执命中、产物读取、queue/detail、路由、完成、审核、最终化和最终快照读取。该运行物流尚未提交时审计为空是合法中间状态；NO_MATCH 也合法。只要模型物流评估已保存，缺少必要审计就属于完整性错误。不要在步骤尚未开始时错误要求审计存在。

历史验证器按 `audit_contract_version + tool_version + validation_version + kernel_version` 选择；A注册、B维护对应纯校验实现。首版保留v1，升级不能删除旧验证器后默默用当前规则重算历史。没有支持的旧验证器时返回明确不可放行错误，不冒充验证成功，也不调用模型修复。

历史只读不依赖当前密钥、数据目录或模型开关；当前新操作仍需当前上下文验证。旧规则运行/旧最终快照缺少新扩展字段时按空映射兼容，不回填模型标签。原最终快照所需物流审计损坏时不能把摘要或成功卡片当验证通过；可提供错误提示和原有历史索引，但禁用依赖审计的操作。

## L-08：错误与恢复——同意，属于接线前必改项

已经核实当前 `workflow/orchestration.py` 和 `application/dispatcher.py` 都会把不可恢复的 PERSISTENCE_FAILURE 提升为 recoverable/RETRY。这两处必须分别由 B/A 修改，保留端口原 recoverable 和 allowed_actions，不能只按错误码提升。

新物流完整性错误统一 `PERSISTENCE_FAILURE / recoverable=False / CONTACT_OPERATOR`。临时事务失败、整体回滚则 recoverable=True/RETRY。非法调用方载荷 CONTRACT_INVALID，与保存记录损坏的完整性错误分开；scope/配置漂移仍 STALE_CONTEXT；幂等冲突仍 IDEMPOTENCY_CONFLICT。

迁移缺失、结构损坏和确定性约束失败不能仅因底层出现 sqlite3.Error 就当临时锁故障；A实现时分类处理。还需覆盖已有规划审计完整性错误不被提升，以及旧临时保存失败继续可恢复，避免修新角色时破坏既有恢复路径。

## L-09：共同基线、迁移与分工——同意以下实施安排

共同基线建议更新为当前 main `488c961`。B先将 origin/main merge到 `feature/llm-logistics-agent`，保留组件提交，再在最新基线继续 Hybrid/Orchestrator；不要从旧 `3a1206f` 继续修改 A-owned 工厂或 Dispatcher。

A拟在 `feature/a24-logistics-audit` 实施正式能力（本轮仅复核，该分支尚未创建）：新增迁移7及只读/保存验证，保留迁移1～6和旧数据。旧规则及旧规划模型运行默认无需物流 audit；只有新 scope 明确登记模型必审计时要求该记录。新安装及由schema6升级都需独立测试，不删除/重建用户数据库，不伪造旧物流审计。

B提供严格schema/纯校验helper、Hybrid扩展与编排、对应规则/恢复测试；A负责存储/读取、身份工厂/meta/开关、Dispatcher、审核/最终化/页面；仍按提案分工，不由B新建正式数据库。

推进顺序：

1. B确认本回复补充项、更新基线并准备严格helper；A按冻结接口实现正式能力。
2. 合成一条完整集成分支，离线验证 PLAN/REVISE/REASSESS/NO_MATCH、原规则默认、身份漂移、四产物逐点回滚、丢回执恢复、旧worker、授权、完整性损坏及历史兼容，再跑全量检查。
3. VPN/本地凭据就绪后，单独执行本轮物流角色真实校园 HTTP/浏览器闭环，记录角色、run/version/assessment、实际回复和恢复证据。MockTransport与A19旧记录不作为新角色真实验收。
4. 验收通过后按小组当前合并方式同步 main；组件交付和正式启用分开记录，不提前宣布应用已有第二模型角色。

## 可以先回给 B 的短消息

> A已复核e0b25eb，58项组件测试独立复跑通过。L-01～L-09按回复文档补充项确认，特别是严格载荷schema、历史验证器及不可恢复错误不能提升为RETRY。请先merge最新main（488c961），提供严格纯校验helper并继续Hybrid/Orchestrator；A将实现RecoveryPort、迁移7、审计读取/身份/meta/页面。默认仍为rules，正式能力与联合验收完成前不启用模型物流。详细约定见A24_logistics_contract_reply.md。
