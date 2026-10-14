# A24：物流模型保存、读取与工厂交接

日期：2026-10-14。基于 A23 `488c961` 并完整合并 B 组件 `e0b25eb`；接口确认见 `a24_logistics_contract_reply.md`。本轮提供 A 侧能力，应用默认物流仍为 rules。

## B 现在可以使用的能力

```python
stored = await persistence.save_model_logistics_assessment(
    saved_version.version_context, outcome.assessment,
    outcome.plan.model_dump(mode='json'), outcome.trace.model_dump(mode='json'),
    scope.write_keys['logistics'],
)
```

该方法位于 A-owned `RecoveryPort`，返回共享 StoredAssessment，不改变六项 AgentPort、共享 DTO/schema 1.0 或原普通 save_assessment 签名。模式固定 LOGISTICS，模型必审计 scope 禁止普通物流保存。A严格类型边界在 `application/logistics_audit.py`，复用 B 的只读 LogisticsToolset 计算，不需要 B 另建数据库。

保存时从数据库确认与保存版本重建输入，经 A 当前运行数据 provider 重算基线，对完整 plan/result、输入/规则/配置/proposal摘要和 trace结构进行比较。512 KiB 按完整调用 canonical UTF-8字节计数，错误类型/额外字段/不一致产物不写入。assessment、gear checklist、独立审计及回执同事务。

新增迁移7：`model_logistics_audits`。启动自动迁移，不删除旧数据，不回填旧规则物流审计。事实快照只内部保存，公共读与 checkpoint 不返回 input_json/rule_facts_json/owner_id。

`load_checkpoint()` 新增 `model_assessment_audits`；键 LOGISTICS，envelope按原提案，包含 audit_contract_version/audit_id/kind、plan/run/version/assessment/gear/attempt关联、输入/配置/载荷摘要、created_at、plan、trace。未提交物流或规则模式为空映射；NO_MATCH无版本也为空。

同key/完整载荷复用原评估、原审计和实际保存attempt；不同载荷幂等冲突。新attempt先读取checkpoint，不能为原保存物流补跑模型。已保存评估缺失或损坏审计时不可恢复，不准补写。读取检查覆盖 checkpoint、恢复领取/重试、回执、route、完成、评估/审核读取、最终化及最终快照。审计检查使用归档scope/事实，不重读当前数据或依赖当前凭据；不支持的验证器明确拒绝，未来工具/规则升级必须保留v1验证实现。

## B 需要接入的 Hybrid 能力

工厂已准备身份seed登记与最终context计算，启用前要求以下真实能力（当前 B 组件分支尚无这部分）：

```python
class HybridPlanningAgent:
    logistics_audit_contract = '1.0'

    def __init__(..., workflow_configuration=None, logistics_agent=None, ...):
        self.logistics_agent = logistics_agent

    async def assess_logistics_with_trace(self, input: LogisticsInput) -> LogisticsOutcome:
        ...
```

上例省略号只说明接线约定，不是可执行实现。rules默认时 logistics_agent允许None，原规则路径不变。`logistics_audit_contract='1.0'` 必须在完整编排/恢复能力完成后才声明，不能只加属性让 readiness 通过。

PLAN/REVISE/REASSESS 有保存版本时，模型分支调用带trace方法并通过A端口保存；普通安全评估引用保存后的StoredAssessment。恢复用checkpoint整体产物，角色不混入原规划trace。REASSESS重新生成本次物流audit，不调用规划模型、不复制原行程生成记录。NO_MATCH跳过物流。

`CAMPMATE_LOGISTICS_EXECUTION=rules|model`，默认rules；model仅限现有agent/v2工厂。组件能力不齐备、缺密钥、回合数小于3、数据库未就绪或身份冲突时明确失败，无规则回退。A工厂传入已登记的logistics_agent，Hybrid必须保留该实例。身份seed去除自身fingerprint与workflow_context，最终身份基于完整一次构建的context计算，公开配置包含原规划与修订反馈身份。

meta在实际就绪时才标注logistics=model。页面装备/费用展示逐项补缺及预算分配，记录页折叠显示独立物流调用，最终快照保留该记录；原规划说明不再把启用模型后的物流误标为rules。

## 不可恢复错误

A Dispatcher已取消按PERSISTENCE_FAILURE统一提升RETRY；逻辑审计损坏为recoverable=False/CONTACT_OPERATOR。数据库结构、确定性关联约束错误也不提升临时恢复；原临时IO/锁定故障与整体回滚保留恢复。

**B仍须修改 `workflow/orchestration.py` 的统一提升逻辑。** 当前主编排还未接物流，故model开关保持未就绪；没有执行或声称已有完整双模型HTTP工作流。不要依据A已有能力提前宣布接线完成。

## 本轮证据

- 物流审计针对性测试36项通过：四插入点回滚、未知借用费用和缺口保留、严格类型、事实篡改、UTF-8上限、幂等、丢回执/新attempt复用与旧worker拒绝、同版本重评/新版本修订各有独立审计、历史/快照/权限、配置就绪和身份seed无自引用、schema6升级。
- 中间集成回归67项通过，覆盖既有规划审计、模型修订/重评和审核摘要。
- 本机全量回归：767 passed、44 skipped、1条既有Starlette警告（全量执行时尚未加入最后一项工厂身份测试；最终以提交CI为准）。Windows符号链接及Git依赖检查在本机未能执行，不能称为0 skipped。
- 共享schema导出检查通过；前端TypeScript/Vite构建通过。最后提交的CI需再次检查全量。
- 实际浏览器登录、装备建议、预算分配、物流记录、显式最终保存及快照读取通过；390窄屏clientWidth=scrollWidth=375，检查的浏览器错误为空。
- 浏览器使用独立数据库和真实B组件的MockTransport物流产物，原行程是独立保存夹具。数据库为1run、1version、2assessments、1gear checklist、1logistics audit、0planning traces、1final record；物流3轮模拟响应。此证据不等同于正常确认/双模型编排或真实校园验收，也不能计作API账单。

本轮未修改个人配置、封存数据或已有用户数据库，也未生成正式Canvas ZIP。真实校园PLAN/REVISE/REASSESS、综合恢复与HTTP/browser联合验收由下一轮完成。

## 建议发给 B

> A24正式端口、迁移7、checkpoint/读接口、身份工厂、开关和页面已经完成，请基于包含A24的最新main继续接Hybrid/Orchestrator。Hybrid接收A传入的logistics_agent，提供assess_logistics_with_trace，并在完整恢复接线完成后声明logistics_audit_contract='1.0'；编排须保留不可恢复错误语义。保存与恢复约定见docs/a24_logistics_audit_handoff.md。默认仍rules，接线完成后再联合做真实校园HTTP/浏览器验收。
