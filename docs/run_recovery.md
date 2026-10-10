# A-09 运行管理、幂等与失败恢复

日期：2026-10-10。分支 `feature/a09-run-recovery`。本轮实现 A 侧运行管理边界，使用独立故障测试；B Agent、Adapter、业务调度器和页面启动/重试仍待实际接入。共享契约 1.0 未改，页面不会将内部恢复能力显示为已完成的真实规划。

## 内部入口

实现为 `backend/app/storage/workflows.py`，应用入口 `app.state.workflows`。用户身份、数据上下文、scope 与执行凭证由受信 A 服务提供，不接受 HTTP 或 Agent 自报。

| 入口 | 行为 |
| --- | --- |
| `start(user, request_id, demo, dataset, *, command_key, plan_id=None, operation='PLAN', expected_current_version_id=None, expected_active_run_id=None)` | A 生成 run ID、scope 与步骤 key；启动回执与 plan/run/pointer 同事务。已有方案必须匹配当前 version 和 active run |
| `claim(user, run_id, demo, dataset)` | 仅领取当前 PENDING；返回 A 内部 `Attempt(scope, attempt_id, generation)`；竞争领取只有一个成功 |
| `port(user, attempt)` | 创建该尝试的 `RecoveryPort`，保留共享持久化方法 |
| `renew(user, attempt)` / `await port.heartbeat()` | 续期仍在运行且未过期的尝试；默认真实时钟租约 120 秒 |
| `expire(user, run_id)` | 启动恢复或运维显式检查已过期 RUNNING，记录可恢复 FAILED；不接管有效租约 |
| `retry(user, run_id, demo, dataset, *, command_key, expected_run_revision)` | 仅恢复当前可恢复 FAILED，核对 revision 与输入，撤销旧尝试并记录 PENDING；保留 run、阶段、产物及写入回执 |
| `checkpoint(user, attempt)` / `await port.load_checkpoint()` | 单次读事务返回阶段、确认上下文、已有推荐/版本/评估/路由，只读取该 run |

`demo`、`dataset` 由 A 根据当前配置与数据 Adapter 获取。时钟、模式、数据版本、文件 digest 或规则版本变化时不能 retry，应以新命令开启 REASSESS/REVISE run。需求变化先重新确认。确认中的 Profile 快照不会因当前资料编辑而改变；要采用新资料时重新确认请求。

若首次规划还没有生成版本，证据变化可以在同一 plan 下新建 PLAN run，需匹配旧 active run 且 current version 仍为空；已有版本后只能走 REASSESS/REVISE。旧失败记录保留为历史，不复制旧产物。

启动和重试使用 `(owner_id, command_key)` 回执。同 key 同输入回读原 scope；不同输入或跨操作返回 `IDEMPOTENCY_CONFLICT`。回读不再次调度，不能把后续第二次失败重置为 PENDING；新的重试操作需新 key 和最新 revision。旧启动回执虽可回读，但领取仍检查当前 active run 和 PENDING。

领取后，写入、阶段更新和执行上下文读取检查当前 attempt、租约与 active run。重试立即撤销旧凭证，即使新 worker 尚未领取，迟到任务也不能写入。旧端口不能写入已纳入租约管理的 run。页面、人工审核和最终化的只读 eligibility 计算不需要 worker 租约。

迁移 5 新增 `workflow_commands`、`run_leases` 和工作流回执不可修改/删除守卫，保留旧记录。状态、事件、租约、回执与指针更新均为同一 SQLite 事务，故障整体回滚，不清空成功保存的步骤。

## B 接入要求

`load_checkpoint`、`heartbeat` 是 A 具体 Adapter 的附加方法，未修改共享 `PersistencePort` 1.0；B 恢复接入应使用 A 提供的 `RecoveryPort`。如需加入共同 Protocol，先协商版本。

1. A 登记、领取并传入该 attempt 的端口；B 不持有数据库、Repository 或其他 run 的端口。
2. B 每次执行先读取 checkpoint，复用已保存产物，仅执行缺失步骤；阶段保持单调，不能从安全评估回报推荐阶段。
3. 不能重算不同 LLM 输出并复用原 write key；此行为会冲突。路由已保存时只补结束步骤；NO_MATCH 推荐也可恢复结束。
4. A 调度器需在长任务期间持续续期，建议间隔小于租约的三分之一；不能只在 LLM 返回后续期。过期后应记录失败并显式重试。
5. 可恢复异常通过有效端口记录 FAILED。数据库完全不可写时不能假称失败已保存；数据库恢复后由过期检查记录失败。重启不自动接管其他进程的有效租约。
6. 新证据 run 不自动沿用旧评估或审核，旧任务由 active pointer 拒绝；审批和最终化继续采用 A-07/A-08 的守卫。

本轮提供恢复原语，未加入后台扫描器、重试 HTTP 接口、真实调度器或 stub 规划成功流程。B 首版交付后共同实现调度与 checkpoint 消费，验证真实输入输出和首轮四场景。

## 自检范围

`backend/tests/test_workflows.py` 使用独立 A 夹具、可控制时钟与隔离数据库，覆盖竞争启动/重试/领取、产物与回执故障回滚、租约续期/过期/重启、恢复版本/评估/路由/NO_MATCH、迟到任务、旧端口、数据/规则/时钟/模式变化、fingerprint 损坏、用户隔离与 migration 4 升级。

完整检查实际结果见 [实施状态](implementation_status.md)。这些测试证明 A 侧持久化及恢复守卫，不是 B Agent 能力、真实规则或完整 UI 恢复的证据。默认数据库与原始 synthetic 包未修改。
