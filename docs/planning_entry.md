# A-11 规划启动、重试与 B 调度接入（2026-10-11）

本轮实现 A 的 HTTP 入口、页面按钮和本地异步 supervisor。默认仍为 v1 数据和 stub，未注册 B Agent/Adapter，因此规划保持禁用。本轮独立测试中的 Agent 是测试替身，不属于 B 实现或课程业务演示证据。

## 给 B 的接入约定

共享入口仍为 `backend/app/contracts/ports.py`，DTO 为 `backend/app/contracts/dto.py`，schema 1.0 无变更。A 的调度器为 `backend/app/application/dispatcher.py`。

1. 在 `backend/app/application/agent_registry.py` 的 `AGENT_FACTORIES` 注册对应非 stub 模式的工厂。工厂返回完整 AgentPort；保持 async 接口，网络/LLM 调用设置超时并响应取消。Adapter 必须消费本次 scope 登记的数据和场景，核对当前 digest，不能把 expected_* 或测试 oracle 传给 Agent。
2. 对应模式注册和联调完成后，设置 `CAMPMATE_EXECUTION_MODE=deterministic_demo`（或 agent），并显式设置 `CAMPMATE_PLANNING_ENABLED=true`。只开开关或只切模式均不能使缺失的 Agent 可用；stub 始终不能规划。原个人 `.env` 未修改。
3. A 登记 run，并领取新的 attempt/执行租约，调用 `await agent.orchestrate(OrchestrateInput(...), persistence)`。A 传入的端口只允许操作当前 owner/run/attempt。B 不创建 scope、attempt、审批或 FINALISED 状态。
4. 首先调用 `await persistence.load_checkpoint()`，读取已保存的推荐、版本、评估和路由。`OrchestrateInput.previous_version` 同时提供此 run 已绑定的版本；新 PLAN 首次执行为 null。恢复时不要重新生成已保存的内容、复用旧 key 写不同结果、或倒退阶段；所有阶段 key 从 scope.write_keys 取。
5. A 自动续租，B 无需另起调度器。A 在端口访问、完成检查和 HTTP 重试时重读当前配置/数据上下文；时钟、模式、文件内容或场景选择变化拒绝旧 run 继续执行。Profile 的已确认快照保持不变。
6. `report_stage(COMPLETED, SUCCEEDED, None)` 在此 dispatcher 端口上只验证完成前提并返回拟提交快照，**尚未持久化成功事件**。B 最后必须返回有效 RunResult：相同 run_id、execution_mode，`run_status=SUCCEEDED`、`stage=COMPLETED`、error=null。route 如提供须等于 A 保存的 route；artifact_refs 如提供须引用此 run 保存的产物 ID。A 核对返回后提交成功，页面此前仍为 RUNNING，禁止最终化。推荐 NO_MATCH 且没有版本也可以作为正常流程结束。
7. 失败可返回 `FAILED` 与结构化 ContractError（stage 对应已保存阶段），或通过端口先保存 FAILED 再返回一致错误。可恢复故障设置 recoverable=true、allowed_actions 包含 RETRY。未处理异常/服务退出由 A 保存可恢复失败；输出契约错误与上下文变化不能直接重试。审批不能绕过 blocker。

`load_checkpoint()` / `heartbeat()` 是 A 的具体 RecoveryPort 扩展，冻结的 PersistencePort 协议未增加方法。A 自动续租不代替 B 的请求超时。业务修订/重评的公共启动入口、真实业务规则和四个演示场景仍待后续联调。本轮没有修改或导入待修订的 v2 数据。

## HTTP 与页面行为

所有写操作需要 Camper 会话、X-CampMate-Client:1 与 X-CSRF-Token。先核对 owner，再访问 Agent 和数据；外部不接受 run scope、产物或审批字段。

| 入口 | 请求体 | 行为 |
| --- | --- | --- |
| POST /api/v1/requests/{request_id}/plan | command_key（16–128 位）、expected_request_revision（整数 ≥1） | 只允许 CONFIRMED；202 返回 plan_id/run_id。相同 key/输入回读命令回执；不同 key 也不能为同一请求重复建 plan |
| POST /api/v1/runs/{run_id}/retry | command_key（16–128 位）、expected_run_revision（整数 ≥0） | 当前可恢复 FAILED、revision 与输入均一致才能重置 PENDING；复用 run 和产物，撤销旧 attempt；202 返回相同 plan/run |
| GET /api/v1/requests/{id} | — | 返回 planning_available 与 planning_plan_id。已登记时直接进入现有方案 |
| GET /api/v1/plans/{id}、/runs/{id} | — | 返回 retry_available/retry_unavailable_reason；原历史产物展示仍独立按 run 读取 |

页面确认后可开始规划并进入保存进度。重复点击/网络重试使用同一次命令 key；已有 plan 展示继续查看链接。失败页面说明原因，只有服务器许可时显示“重试规划”；历史、快照和审核页面不提供执行按钮。运行中继续每 2.5 秒轮询已保存记录。

## 生命周期与恢复边界

正常服务退出取消自己的任务并保存可恢复失败。异常进程崩溃后，启动扫描恢复仍为 PENDING 的命令；RUNNING 必须等待 120 秒租约到期才标记失败。启动扫描和当前 run 的页面读取可识别过期租约；不会偷取仍有效的执行租约。过期任务经用户显式重试恢复。失败任务收尾时收到的重试也会重新调度，避免留在 PENDING。

本地 supervisor 适用于当前单机演示，无独立消息队列。保存失败导致无法登记错误时，保留原持久化记录，由租约过期恢复；不会声称完成。B async 调用须正常传播取消，避免阻塞服务退出。

当前资料确认/规划/重试/dispatcher 读写有输入守卫；既有审核和最终化对磁盘最新数据的独立核对、修订/重评页面仍需后续完善。不能把本轮检查描述为所有业务入口已具备自动数据监控。

## 验证与 Canvas 交付

独立验证入口 `backend/tests/test_planning_entry.py` 的 23 项测试覆盖禁用模式、不确认/旧 revision、CSRF 与隔离、启动/重试回执、checkpoint 复用与旧任务拒绝、当前输入变化、输出校验、NO_MATCH、退出/重启、租约与失败清理竞争、数据库回滚。完整检查为 172 passed、schema up to date、前端 50 模块构建成功。浏览器使用独立测试替身验证启动/失败/重试/刷新回读和 stub 禁用按钮，见 [检查摘要](evidence/a11-planning-check.json) 与 [实施状态](implementation_status.md)。

继续保留无密钥的默认 stub 安装路径。最后 Canvas ZIP 必须包含实际 B 实现、修订数据、开启方式和四个可重复的端到端场景，并重新打包、独立解压安装与成员电脑验收。旧 ZIP 不包含 A-11。
