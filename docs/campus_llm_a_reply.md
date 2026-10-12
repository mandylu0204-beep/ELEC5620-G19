# A → B：校园模型接线确认与 trace 接口约定

日期：2026-10-13。已阅读提供的 campus_llm_handoff_to_a.md，并检查远端固定提交6044bc1。远端随后已有5c4a093（HybridPlanningAgent），本文以该最新包装接口为准，保留6044bc1的组件边界。

结论：C-01～C-08按以下细节确认，可继续联合接线。当前确认的是职责和接口设计；A应用工厂、trace表/端口及PLAN-only开关尚未实现，不能将本文签名当作当前main已经可调用的接口。A下一项实现为A-16；B模型分支尚未合入A本地main，本轮不调用校园代理或读取个人密钥。

## 1. C-01/C-02：工厂与执行方式

使用现有DATASET_AGENT_FACTORIES的明确键：

```python
(ExecutionMode.AGENT, 'CampMate Synthetic Demo Dataset v2')
```

A提供build_v2_hybrid_binding(settings, descriptor)，返回AgentBinding(agent, configuration.context)。构造顺序与B新文档一致：CampusModelSettings/CampusModelClient → validate_configuration（仅离线）→ V2Adapter(expected_context=descriptor.context) → PlanningCoordinator → build_hybrid_configuration（包含A登记场景）→ HybridPlanningAgent。

必须同时修改AgentRuntime的managed_mode选择：当前只将deterministic_demo纳入受管理绑定，**单加注册表键不能启用agent**。默认stub/v1、planning_enabled=false和个人.env不变。缺凭据、未注册来源或身份校验失败显式未就绪，不回退规则/stub。

不把PlanningCoordinator直接作为AgentPort注册。按5c4a093的六方法包装接入，首次仅PLAN、单营地、最多30晚；只有规划调用LLM，解释/筛选/装备费用/安全仍为确定性规则。A在meta和页面显示这些阶段的执行方式，不能标为“三个模型Agent已完成”。

ready/meta/resolve只作配置及数据验证，不进行真实probe。实际网络连通性和模型HTTP闭环另记证据；离线ready不代表VPN/校园代理可连接。

## 2. C-03/C-04：模式和上下文身份

接受Hybrid._input与显式expected_mode kernel；保留RuleAgent及validate_itinerary的默认deterministic_demo守卫。不能先改输入标签执行，再改回agent。确认、推荐、行程、两份评估、RunResult和持久化scope均必须保持agent模式。

沿用原A file_digests/fixture_digests/selection_config/rules_version前缀和a_runtime_bound登记。B当前build_hybrid_configuration中的三个键直接沿用：

```text
hybrid_agent_version
hybrid_kernel_version
hybrid_planning_fingerprint
```

继续使用B生成的Hybrid版本及Coordinator配置指纹后缀，不重新计算另一套B身份。A新增审计身份键时使用a_前缀，不覆盖B键；拟增加a_model_trace_required=1及a_model_trace_contract=1.0，将本轮必须保存trace的语义纳入确认/run指纹。

模型别名、端点、调用限制、Prompt/schema/tool/validator版本的变化需新上下文，旧run不能以原写入key重算不同内容。API key不进入公开身份、保存数据、meta或日志；served_models仅记录代理返回的身份，不据此保证底层权重一直不变。

## 3. C-05：冻结的模型规划保存接口

共享AgentPort/PersistencePort 1.0和ItineraryResult返回类型保持不变。A提供**与RecoveryPort组合的模型审计扩展**，与已有load_checkpoint/heartbeat扩展同类；B无需另建数据库或全局last_trace。

协议/审计DTO拟放在A-owned application模块（app/application/model_audit.py），SQLite实现由storage/RecoveryPort提供。该新模块当前尚不存在，A-16交付时明确实际导入位置；不要向旧main导入尚未实现的接口。

接口名称与签名定为以下设计（A-16实现后才可调用）：

```python
class ModelPlanningPersistencePort(Protocol):
    async def append_model_plan(
        self,
        expected_current_version_id: str | None,
        content: ItineraryResult,
        request_id: str,
        reason: str,
        trace: Mapping[str, object],
        write_key: str,
    ) -> StoredVersion: ...
```

trace参数传outcome.trace.model_dump(mode='json')，字段采用B PlanningTrace当前形状，不传Authorization、原始提示/回复全文、私有推理或错误响应体。A负责严格校验字段、长度/数量边界、SHA-256及数值类型；配置指纹匹配scope里的hybrid_planning_fingerprint，选中营地匹配content，候选和来源能追溯到本run保存的推荐，validation_passed必须为true。缺usage的字段保持未知，不当作零或费用报告。

B在Orchestrator生成分支使用调用局部变量：

```python
outcome = await agent.plan_with_trace(itinerary_input)
version = await persistence.append_model_plan(
    scope.expected_current_version_id,
    outcome.itinerary,
    scope.request_id,
    outcome.itinerary.revision_reason,
    outcome.trace.model_dump(mode='json'),
    scope.write_keys['version'],
)
```

两次await仍放在已有Orchestrator.call的heartbeat/cancel包裹中。规则模式沿用append_plan_version；声明a_model_trace_required=1的模型运行不能降级为无trace的普通保存。generate_or_revise_itinerary仍仅返回DTO，独立CLI仍不创建应用记录。

### 原子性、恢复与权限

- A在同一个现有SQLite数据库增加模型审计表；同一事务保存version/run绑定、trace和幂等回执。trace失败则整体回滚，不能有模型版本而无必需trace。
- owner、plan_id、run_id、input_fingerprint、生成attempt_id和保存版本ID由A受限端口从scope/lease派生，B不传或决定这些关联字段。
- 写入key使用scope.write_keys['version']，不追加attempt_id。幂等输入摘要包含content与trace；同key同输入返回原StoredVersion，不同输入拒绝。
- 已提交但响应丢失时，checkpoint取得原version和对应trace；不重跑模型来补trace。重试的新attempt只恢复工作，不改写原trace的生成attempt。
- checkpoint扩展拟提供model_planning_trace，附A关联元数据与B原trace；既有version/recommendations/assessments等字段保持。模型版本存在但必需trace缺失时按持久化不一致拒绝，不偷偷补写或继续最终化。
- 版本保存前失败且没有任何持久化结果时，可按原恢复协议再次调用模型；这可能产生额外服务调用，不能宣称exactly-once模型执行。
- 成功trace可被当前owner读取；Founder仅在其审核范围中读取关联摘要。失败步骤沿用脱敏run.error/run_events，当前Coordinator失败时不返回完整trace，不伪造失败usage或完整调用统计。
- A完成提交和最终化复核必需trace及关联；trace仅审计依据，不代替物流、安全、审核或eligibility。

异常使用现有ContractFailure/ContractError格式：trace结构无效为CONTRACT_INVALID，身份/attempt不再当前为STALE_CONTEXT，版本比较失败为VERSION_CONFLICT，同key不同输入为IDEMPOTENCY_CONFLICT，事务失败为可恢复PERSISTENCE_FAILURE。不会把trace全文或私密配置放进错误context。

## 4. C-06/C-07：功能开关与执行恢复

首次agent绑定支持操作为PLAN；同一PLAN run的可恢复失败允许RETRY。REVISE/REASSESS均不支持，A在HTTP创建命令/run之前校验，并在plan详情返回revision_available=false、reassessment_available=false；页面隐藏/禁用对应入口。已有请求超过30晚也在start前拒绝，避免先建run才发现无能力。

规划还需明确planning_enabled=true、完整Hybrid工厂就绪和审计扩展存在。当前A的修订/重评flags仅判断全局available，需要改为按绑定能力判断；客户端隐藏按钮不能替代HTTP守卫。审核/最终保存继续由A检查实际结果，不因agent模式自动放行。

沿用A dispatcher的lease与退出/重启协议，以及B Orchestrator.call的异步heartbeat。当前默认lease_seconds=120，heartbeat_interval=20满足小于lease/3；测试或配置改变lease时相应调整。模型等待中失去lease需取消并拒绝迟到结果。网络/限流失败按recoverable错误恢复，缺密钥/无效输出不能冒充模型成功。

首次真实正常闭环从本人登录、Profile保存、请求摘要和明确确认开始，按真实保存推荐把全部合法候选交给模型。模型若选另一合法营地而证据不足或超预算，保留真实结果，不强制Wattle Rest。正常成功验收要记录实际模型选择、trace、评估、最终记录和浏览器证据。

## 5. C-08：资料规范与共同基线

A14已在本地完成经验/交通已知取值的大写规范化、v2装备key/unit和拥有数量/容量表单；历史确认不重写，未知输入仍需澄清。A15补齐审核后引导、复制本人需求重新确认、冲突修订和无匹配浏览器验证。

本地A14提交4ac059d、A15提交1639b7e，尚未推送；远端B基线57a378f仍不含这些前端修复。联合分支必须包含完整A14+A15和B6044bc1+5c4a093，再加A16工厂/trace/能力开关。不要把单个模型组件提交摘到旧main就开启agent。

## 6. Windows独立复核与给B的修正要求

固定5c4a093的隔离源码副本，仅运行四个组件文件，MockTransport/独立测试密钥，不连接校园模型。原始结果：108 passed、1 failed、1 skipped、2 errors，耗时6.96秒；111个用例，2个errors是同一用例的setup和teardown。未重复整套规则后端，不把B的macOS全量结果说成本机结果。

请B修复以下两个测试问题后复测：

1. tests/test_campus_model_client.py:107–109：参数body的262145字节内容自动成为pytest用例ID，设置PYTEST_CURRENT_TEST时触发Windows环境变量32767字符上限，用例根本未执行。加短ids，例如invalid-json/duplicate-key/oversized-body。A只在隔离审查副本修改ids，三个原始响应校验用例随后3 passed（0.33秒），未改客户端/断言/测试数据；此结果不代表B提交已包含修复。
2. tests/test_hybrid_planning_agent.py:282：要求tracked.beats>25依赖平台时间调度。本机流程SUCCEEDED、两次请求、实际22次heartbeat，但断言失败。建议用asyncio.Event等同步信号验证模型等待期间实际续租及租约仍有效，保留失去lease取消且不保存迟到结果的测试；不要仅放宽次数阈值冒充稳定验收。

1项skip是git ignore策略测试在无.git的源码审查副本中明确跳过，不是模型能力失败。现有源码不泄露key、无规则回退、保留模式守卫和checkpoint恢复的方向可以接受；Windows两项测试修正及应用接线仍未完成。

本轮不读取个人.env.llm.local、不安装/更改密钥、不执行真实probe/plan，不合并B分支或推送远端。CLI现场证据来自B提供的记录；不能计为A重新调用或模型HTTP/browser验收。

## 可直接发给B的简短回复

> 已检查6044bc1及后续5c4a093，C-01～C-08按这份回复确认。Hybrid保持agent身份，首次只开放PLAN/同run恢复，不开放REVISE/REASSESS；解释、装备费用和安全规则步骤会明确标注。trace定为A RecoveryPort扩展append_model_plan，使用scope.write_keys['version']，版本+trace+回执同事务保存，丢失回执从checkpoint恢复，不重跑模型补trace。签名和关联/幂等规则见本文；目前只是接口冻结，A16实现后才可调用。我本地A14/A15尚未推送，后续共同基线要完整包含它们。另外请修复超大body的pytest参数ID和依赖heartbeat精确次数的Windows测试问题。正常模型HTTP/browser闭环尚未执行，准备好共同分支及A16后再联合验收。
