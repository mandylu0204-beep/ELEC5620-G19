# A-13：方案修订与重新评估

日期：2026-10-12。基于本地 A11+A12 与已合入的 B01–03；本轮没有修改定稿数据、个人 .env 或数据库结构。默认 stub/规划禁用保持不变。

## 用户流程

当前运行结束且已有方案版本后，Camper 可在方案页选择修改目标，或重新评估当前行程。历史运行、审核页和最终快照页没有这些操作入口。

- 修改方案：传递原版本和修改意见，由 B 生成新的不可变行程版本，再独立执行物流及安全评估。
- 重新评估：复用当前行程内容，开启新 run，创建新的评估记录；旧审核不沿用，旧最终快照保留并标记为历史。
- 本次沿用已确认需求及 Profile 快照。修改人数、日期、预算或资料需要重新提交并确认需求，不能在修订过程中偷偷替换。
- 当前 v1 规则明确支持更换营地和寻找更便宜营地；不支持的意见会报错。没有替代方案会失败，要求更改需求的提案必须先确认。上述入口不代表 LLM 已实现。
- 更换营地后，原营地证据不会被复制成新营地证据。缺失来源仍会阻止最终化。

## HTTP 约定

`POST /api/v1/plans/{plan_id}/revise` 和 `POST /api/v1/plans/{plan_id}/reassess` 均返回 202：`{plan_id, run_id}`。需要 Camper 会话、owner 与 CSRF 校验。

共同请求字段：command_key（16–128 位）、expected_current_version_id、expected_active_run_id、expected_version_revision 和 expected_run_revision。两个 revision 必须为非负整数，不接受 bool。revise 额外要求非空 feedback（最多 4000 字符）。

owner 在读取运行配置前检查；版本/运行指针与 revision 在写事务中比较。当前任务尚未结束时拒绝新操作。同一 key 和同一内容只返回原收据；同一 key 用于不同意见或上下文返回 IDEMPOTENCY_CONFLICT。成功提交立即更新 active_run_id，旧端口不能继续读写当前任务。

方案详情补充 current_version_revision、revision_available、reassessment_available、current_inputs_error。运行查询仍按 run_id 隔离产物；没有新版本的修订失败也可以对原当前版本开启新评估。

## 运行上下文与 B 交接

共享 DTO、AgentPort 和 PersistencePort 仍为 1.0。反馈放入不可变的 DatasetContext.selection_config：

- a_runtime_bound = "1"：A 管理的运行身份标记。
- a_revision_feedback：A 登记的修订意见，仅 REVISE 携带。
- revision_feedback：B 工厂的配置值，必须与 A 登记值相同。

v1 工厂读取 descriptor.context.selection_config 中的 a_revision_feedback，传给 WorkflowConfiguration(feedback=...)；工厂返回完整 configuration.context。A 的绑定规则身份升级为 a-runtime-bindings-v2。Dispatcher、端口守卫和 retry 按保存的反馈重新构建当前 Agent/context，不依赖全局“上一次意见”。

首次 REVISE 时，RecoveryPort.load_checkpoint() 额外返回 previous_version（原版本快照）；checkpoint.version 仍只表示本 run 已保存的新版本。Dispatcher 将正确的 previous_version 传入 OrchestrateInput。新版本已保存后重试直接使用 checkpoint.version，不重复生成版本。

## 审核和最终化的当前输入检查

应用绑定的运行在审核提交、最终化提交之前重新加载当前数据/配置/时钟并比较完整 context。变化后拒绝提交；只读历史仍可查看。方案页隐藏最终化入口并显示原因，审核页禁用提交。新 run 必须重新形成独立评估及审批。

该检查识别新的 a_runtime_bound 标记，也识别 A12 v1 绑定身份。内部独立测试/旧 seed 的无运行绑定上下文没有声称消费应用磁盘数据，仍由原持久化守卫检查。普通 HTTP 用户不能提供或移除运行上下文。A12 旧上下文因绑定规则升级需要重新评估。

## 验证范围

新增 test_plan_changes.py 使用实际 v1 RuleAgent、明确的独立事实、HTTP 权限与临时 SQLite，覆盖修订/幂等、重新评估与历史快照、旧审批隔离、证据变更、CAS、权限/CSRF、旧端口失效、丢失回执后的修订重试、需求变化拒绝、确认 Profile 快照保留。

这些测试不是最终 v2 场景或 Canvas 演示证据。仍等待 B 的 v2 Adapter/工厂、完整场景输入和对应规则；之后需执行真实浏览器及干净解压安装演示。最终检查结果见 [实施状态](implementation_status.md)。
