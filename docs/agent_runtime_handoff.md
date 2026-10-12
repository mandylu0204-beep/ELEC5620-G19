# A-12 / A-13：规则运行配置与修订流程交接

## 当前更新：v2 已接入，A-14 前端联调（2026-10-12）

B 的修正版 PR #3 已合入 main 57a378f，本机已复核其 v2 路径保护和无障碍三态修复。A-14 使用该基线完成四套真实浏览器场景，见 [演示指南](demo/v2_browser_demo.md) 和 [记录证据](evidence/a14-browser-check.json)。下方 A12/A13 待接入内容保留为历史接口约定。

Profile 的已知 experience_level 和 transport_type 在用户显式 PUT 保存时统一为 BEGINNER/INTERMEDIATE/EXPERIENCED/ADVANCED、CAR/PUBLIC_TRANSPORT/WALKING/OTHER；未知字符串保留，已确认 Profile 快照不重写。前端已有小写取值的资料提示核对并保存后建立新需求。B 工厂、DTO、共享 schema 1.0、A13 revision_feedback 约定未变。

修订/重评成功后前端转到当前方案，不继续读取启动链接上固定的旧 run_id；历史 run 仍可独立回读。scripts/demo.py 从 docs/demo/v2_inputs.json 选择固定时钟、数据和证据，使用独立数据库，不改个人 .env。默认 stub/v1 不变；LLM、最新版 ZIP 干净安装和 Canvas 实际下载验收仍待完成。

日期：2026-10-12。已将验证过的 main 合入本地 A11，B 的真实 v1 RuleAgent 已接入 A 的确认/启动/重试/完成提交路径；A13 又接通修订和重新评估公共入口及审核/最终化前的当前输入复核。v2 数据已经定稿，但 v2 Adapter 仍由 B 交付，本轮没有伪装来源或修改定稿数据。默认 v1/stub、planning_enabled=false、个人 .env 保持不变。

完整 A11+A12+A13 已推送到远端 [feature/a12-agent-runtime](https://github.com/LyraWangDev/ELEC5620-G19/tree/feature/a12-agent-runtime)，应用代码提交为 230b7fb，前置提交依次包含 A11 的 69a712e、已合入最新 main 的 f253a83、A12 的 919584e。虽然分支名为 A12，它也包含 A13 的修订/重评入口。完整前置代码现已整体合入 main；不能只摘取依赖 dispatcher 的单次提交到旧基线。

## 分支与合并顺序（2026-10-12）

合并前已读取远端 main（7720863），确认它是本完整分支的祖先，工作区干净。A13 的本地完整检查为 477 passed / 2 skipped，schema 1.0 同步，最终前端构建通过。完整分支的 35fc879 和应用代码 230b7fb 的 GitHub CI 均已通过。此次合并未修改业务代码、数据或默认配置，仅更新交接状态；main 合并提交的 CI 由 GitHub 重新执行。

用户已要求合入 main，维护者采用整体 merge commit 保留完整 A11+A12+A13 历史，未创建新 PR。B 可直接从更新的 main 开始，不再需要等待 A 前置分支合并。

B 更新 main 后，从 main 创建自己提出的 feature/a13-v2-runtime-integration，实施 v2 Adapter/工厂、runtime/装备/费用/安全映射及四套实际演示输入。后续 v2 PR 的比较基线为更新的 main。

```sh
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c feature/a13-v2-runtime-integration
```

v2 分支同时必须保留本文末尾 A13 的反馈字段约定，不能仅使用旧 A12 文件说明。当前默认仍为 stub，完整运行模式由明确配置开启，v2 不回退 v1。

## 给 B 的工厂接口

位置：`backend/app/application/agent_runtime.py`。

```python
def build_v2_binding(settings, descriptor):
    # Consume v2 business/runtime bytes, validate their digests against descriptor.
    feedback = descriptor.context.selection_config.get("a_revision_feedback") or None
    # Build the actual v2 workflow configuration with feedback and registered context.
    # Return selection_config["revision_feedback"] equal to feedback or "".
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
- 已确认输入/场景/规则发生变化，旧运行的重试被拒绝。方案页已接通新 run 的修订与重新评估入口，不自动修改历史记录。
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

本轮没有接入 LLM，也未执行完整四场景、v2 或 Canvas 干净安装演示。B 下一步请提供 v2 的 AgentBinding 工厂、runtime/装备/费用/安全证据到共同 DTO 的完整映射，以及四套运行输入；A 随后完成其接线与最终提交验收。A13 已补齐修订/重评公共入口和审核/最终化前的当前输入复核。

## A13 对 B 的新增约定

工厂签名不变：build_v2_binding(settings, descriptor) -> AgentBinding。A 会在 descriptor.context.selection_config 保留 a_runtime_bound="1"；REVISE 还登记 a_revision_feedback。请将该值传入实际 workflow configuration，返回 context 时保留 A 的全部登记项，同时设置 revision_feedback 为实际配置的相同意见。普通 PLAN/REASSESS 不带修订意见。工厂遗漏意见时 A 会在登记 run 之前拒绝修订。

A 的 v1 绑定规则身份现为 a-runtime-bindings-v2（这里的 v2 是 A 接入实现版本，不代表 v2 数据 Adapter 已实现）。版本变化后的 A12 旧 run 需要重新评估。

Dispatcher、retry、RecoveryPort 的当前输入守卫均从保存的 scope 恢复本次反馈，再加载当前磁盘配置。不是读取上一个请求留在全局 Agent 上的意见。修订首次执行时，A 将原版本快照放入 OrchestrateInput.previous_version。RecoveryPort.load_checkpoint 的 previous_version 为补充信息，version 仍只代表本 run 已保存的新版本；失败重试优先复用本 run 的保存记录。

公共接口为 POST /plans/{plan_id}/revise（反馈加当前指针/revision/key）和 /reassess（当前指针/revision/key）。B 仍通过同一个 orchestrate/持久化端口执行，不能写 FINALISED。重新评估的新 run 不能使用旧评估 IDs 或旧审核。若修改涉及确认需求，继续返回 requested_requirement_changes；A 不保存未确认的新版本。

当前 v1 已通过实际规则的更换营地、新版本保存、修订丢失回执重试、同版本重评、旧批准隔离、来源变化后拒绝旧审核/最终化等 HTTP 测试。独立测试事实不作为生产演示数据。B 的 v2 四场景、LLM 与 Canvas 干净安装演示仍待完成。详细字段、用户操作和验证范围见 [A13 修订与重新评估](plan_changes.md)。
