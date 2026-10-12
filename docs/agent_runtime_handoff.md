# A-12：真实规则流程的应用配置接入

日期：2026-10-12。已将验证过的 main 合入本地 A11，B 的真实 v1 RuleAgent 已接入 A 的确认/启动/重试/完成提交路径。v2 数据已经定稿，但 v2 Adapter 仍由 B 交付，本轮没有伪装来源或修改定稿数据。默认 v1/stub、planning_enabled=false、个人 .env 保持不变。

这份接入依赖 A11 和本轮代码，尚未发布到远端 main。后续同步应带上完整 A11+A12 分支，不能只摘取依赖 dispatcher 的 A12 提交到没有 A11 的旧基线。

## 给 B 的工厂接口

位置：`backend/app/application/agent_runtime.py`。

```python
def build_v2_binding(settings, descriptor):
    # Consume v2 business/runtime bytes, validate their digests against descriptor.
    # Build the actual v2 dataset, workflow choices and corresponding Agent.
    return AgentBinding(agent=agent, context=configuration.context)

DATASET_AGENT_FACTORIES[
    (ExecutionMode.DETERMINISTIC_DEMO, 'CampMate Synthetic Demo Dataset v2')
] = build_v2_binding
```

上面是待 B 实现的接口示例，不是可直接运行的 v2 工厂。descriptor 来自 A 的 inspect_dataset，包含 context、provenance、regions。工厂返回实际消费同一字节快照的 Agent 和完整 DatasetContext；A 验证它保留所有 file_digests、fixture_digests、selection_config，以及 A 规范化规则身份。工厂可以追加自己的输入/选择/规则版本，不能遗漏或替换 A 已登记的身份。

调用方类型仍为共享 AgentPort、PersistencePort、DTO/schema 1.0。无参数的 AGENT_FACTORIES 保留 stub/受信测试替身注册；带数据工厂独立注册，避免用无输入工厂长期缓存旧数据。默认模型 agent 模式未注册，仍不回退 stub。

当前 v1 工厂调用 SyntheticDatasetAdapter，核对实际读取字节，加载明确登记的 ScenarioContext 文件及 safety_case_ids，再构建 WorkflowConfiguration 和 RuleAgent。B 的 WorkflowConfiguration 新增可选 registered_context 参数，用于保留 A 的 manifest/场景原始摘要和选择项；不传时保留独立内部调用行为。WORKFLOW_VERSION 更新为 b03-checkpoint-2，改变配置实现后不会复用旧规则身份。

RuleAgent 的配置检查核对其实际消费的全部源摘要，同时允许 A 追加原始 manifest/场景等摘要。登记内容遗漏时应用未就绪，不放行开始规划。

## 应用中的同一份运行上下文

- 请求解释与确认通过 AgentRuntime.resolve() 使用真实业务 context、Profile 确认快照和 DemoContext。
- 首次规划、claim、retry、端口 active 守卫及完成校验均使用同一个配置构建入口。
- 每次 resolve 重新验证当前磁盘输入；开始执行时取得明确的 Agent 快照，不在后续其他请求修改全局 Agent 后改用另一份配置。
- 已确认输入/场景/规则发生变化，旧运行的重试被拒绝。现有新 run 的业务公共入口仍待下一步补齐，不自动修改历史记录。
- 同步场景文件加载时验证读取字节与刚检查的 digest 相符，文件变化不能藏在两次读取之间。
- report_stage(COMPLETED, SUCCEEDED) 为完成意向；A 核对 RunResult、route、实际产物 IDs 后提交 SUCCEEDED，随后页面查询最终 eligibility。此顺序延续 A11，B 不自行最终化。

Agent 和配置校验错误通过 meta/ready 的 agent_configuration_error 提供。默认 Stub 无规划能力；v2 模式在工厂未注册时，live 仍可用、数据身份可识别，但 ready=503、planning=false，保留草稿而不登记虚假的 run。

## 当前可开启的 v1 规则模式

在进程配置/另建演示配置中设置，个人 .env 本轮未改：

```dotenv
CAMPMATE_EXECUTION_MODE=deterministic_demo
CAMPMATE_PLANNING_ENABLED=true
CAMPMATE_DATASET_PATH=data/synthetic_demo
CAMPMATE_DEMO_TODAY=2026-10-08
CAMPMATE_WORKFLOW_SAFETY_CASE_IDS=["safety-01"]
CAMPMATE_DATASET_SCENARIO_FILES=[]
CAMPMATE_DATASET_SELECTION={}
```

这组配置启用真实规则调用，但 v1 安全来源缺少完整有效期，不能保证正常最终化。A 不为成功演示补造事实。注册的原始 ScenarioContext 补充可通过 data/scenarios 下的独立 JSON 提供，原文件摘要和规范化内容摘要均纳入上下文；需先由 B 提供可信演示数据及适用范围。普通 HTTP 用户不能上传 scope、审批或任意运行证据。

## 独立验证及剩余工作

`backend/tests/test_agent_runtime.py` 使用真实 RuleAgent、实际 HTTP 鉴权和临时 SQLite；装备/交通和 ScenarioContext 是明确标注的独立测试输入，不来自 expected_*，不作为默认用户资料或 v2 演示数据。

覆盖正常解释→确认→推荐→保存版本→物流→安全→提交成功→最终化/快照回读；缺失证据阻断；封路时 Founder APPROVE 被拒绝且 Camper 仍无法最终化；保存版本后回执丢失再重试复用版本；原场景字节变化拒绝旧 retry；加载期间数据变化；manifest 与场景双摘要保存；工厂不允许遗漏 A 场景摘要；v2 工厂缺失显式未就绪。现有 A11 的权限、旧 attempt、关闭/重启和返回校验测试继续保留。

本轮没有接入 LLM，也未执行完整四场景、v2 或 Canvas 干净安装演示。B 下一步请提供 v2 的 AgentBinding 工厂、runtime/装备/费用/安全证据到共同 DTO 的完整映射，以及四套运行输入；A 随后完成其接线验证、修订/重评公共入口与最终提交验收。当前审核/最终化对最新磁盘输入的独立复核仍是后续工作，不把保存时的 guard 宣称为所有入口的实时检查。
