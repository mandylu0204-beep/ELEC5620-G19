# CampMate：A 给 B 的 PR 审查与应用接入统一回复

日期：2026-10-11。

**后续数据交付更新：**已读取 B 分支后续提交 `9e086f9` 的 `data/synthetic_demo_v2`，确认修订数据及说明已交付。此前“本次协商文档未提供数据修改信息”仅描述当时文档，不再用于判断分支当前交付状态。新包实际静态校验为 67 通过、1 失败，需修复 manifest 的缺失 pycache 登记和 CSV 换行摘要；餐食、舍入及成功场景固定时钟已确认修复。v2 Adapter 接入、四个完整场景和应用守卫验收仍待完成。最新数据反馈见 [B 分支 v2 数据复核](B分支_v2数据复核_2026-10-11.md)。以下 PR 代码审查仍记录原 `f80e5de` 基线，本次数据复核未重新执行后续提交的全部后端测试。

已阅读《A_B协商事项.md》，总体接受应用接线、失败恢复及先规则联调后接入 LLM 的分工。本文合并 PR 审查、A 当前进度及后续接入建议，可作为本轮统一回复；新增细节仍需双方确认。

## 一、当前基线与结论

PR：[PR #2：B01-03](https://github.com/LyraWangDev/ELEC5620-G19/pull/2)。

本次反馈针对已审查的 head `f80e5dea21175745a2ddc4204420f5816ad95aa5`，base main 为 `2c647e64a8d302ea036839c0972bfc47503275fc`。以下测试结果均来自此前对这些提交的实际审查；本次合并回复文档没有重新检查更新后的 PR。

A11 本地提交为 `69a712e`，已实现首次规划、失败重试、任务调度、页面按钮与进度、启动恢复和租约过期处理，尚未上传到 main、尚未注册 B Agent。因此这些 A 侧基础入口可以复用，接下来主要工作是统一上下文并接入真实 B 流程。修订和重新评估的公共入口仍待开发。

PR 的两项 GitHub checks 成功且审查时无合并冲突；Windows 运行与输入验证仍发现四项需要修复的问题。建议 B 在同一个 PR 更新修复，A 并行准备应用接入，修复复核后再合并。此次没有合并 PR、发布 GitHub review/comment 或修改应用代码。

## 二、请 B 修复的四项 PR 问题

### R-01 [P1] 补充并锁定 Windows 时区数据依赖

位置：`backend/app/agents/rules/common.py:11`：

```python
TRIP_ZONE = ZoneInfo('Australia/Sydney')
```

在项目现有锁定依赖环境中，Windows 导入 RuleAgent 就出现 `ModuleNotFoundError: No module named 'tzdata'`，随后为 `ZoneInfoNotFoundError: No time zone found with key Australia/Sydney`。pytest 因此在收集阶段中断。PR 未向 `backend/pyproject.toml` 和 `backend/requirements.lock` 加入所需依赖。

最小复现：在没有额外时区数据库、仅安装仓库锁定依赖的 Windows 环境中，从 backend 执行：

```text
python -c "from app.agents.rule_agent import RuleAgent"
```

请在依赖声明及锁文件中补充 tzdata，可以采用合适的 Windows 条件依赖，并验证干净安装后的 Agent 导入和 Sydney 时间转换。保留 Sydney 的夏令时规则，不能改成固定 UTC+10/UTC+11。

这项直接影响从 Canvas 下载项目后在普通 Windows 电脑上运行演示，Linux CI 通过不足以覆盖该要求。

### R-02 [P2] 解析完整数字，拒绝非法时长与人数

位置：`backend/app/agents/rules/interpretation.py:57–60`，以及使用同类数字模式的人数解析。

独立输入复现，Profile 明确为两人：

| 请求片段 | 当前结果 | 应有行为 |
| --- | --- | --- |
| `for -2 nights` | 提取两晚，field_errors 为空 | 非法时长，需要澄清 |
| `for 1.5 nights` | 提取五晚，field_errors 为空 | 非整数时长，需要澄清 |
| `-2 people` | 没有报告人数错误 | 非法人数，需要澄清 |

完整请求示例：

```text
Two campers in CampMate Demo Region from 2026-10-20 for -2 nights, AUD 300.
Two campers in CampMate Demo Region from 2026-10-20 for 1.5 nights, AUD 300.
-2 people in CampMate Demo Region from 2026-10-20 for two nights, AUD 300.
```

原因是数字开头的 `\b` 允许从负号后或小数点后重新匹配数字后缀。请先识别整个数字 token，再验证正整数；对人数、days、nights 都增加回归测试，同时保留 explicit_fields 的既有优先级。

### R-03 [P2] v1 Adapter 拒绝混合或不支持的来源版本

位置：`backend/app/adapters/synthetic_dataset.py:342–355` 及 `_source()`。

复现步骤：复制原始 v1 六份业务文件，只将 `synthetic_profiles.json` 第一条记录的 source_name 改为 `CampMate Synthetic Demo Dataset v2`，其余内容保持不变。

当前 load() 成功，dataset.context.dataset_version 仍为 v1；该 Profile provenance 为 v2，而营地 provenance 为 v1。共同 Provenance 已允许两种版本，逐条 DTO 验证不能保证整个包属于 v1。A 的 inspect_dataset() 会拒绝这个混合包，因此双方的输入验证也不一致。

本 PR 只支持 Git v1，可以保持这个范围；请明确校验所有来源均为受支持的 v1 且 provenance 一致，对混合来源或整包 v2 返回 ADAPTER_FAILURE。未来接入 v2 时，再按登记的 manifest/runtime 处理，不能把其硬编码为 v1。本反馈不要求本 PR 完成 v2 支持。

### R-04 [P2] symlink 测试处理 Windows 无创建权限的环境

位置：`backend/tests/test_synthetic_dataset.py:420`、`:430`。

临时提供时区数据库后，两项测试在创建链接时出现 `OSError: [WinError 1314]`：

- `test_symlink_cannot_escape_dataset_root`
- `test_symlink_cannot_redirect_to_oracle_inside_dataset`

失败发生在执行 Adapter 校验之前，属于测试能力前提未处理，不是已经证明路径守卫失效。请仅在确实没有符号链接创建能力时 skip 并明确原因；在有能力的平台继续验证路径拒绝行为。不要删除生产路径守卫，也不要将所有 OSError 都当作权限不足。

## 三、接受接线分工，并复用 A11 现有入口

| 责任方 | 工作 |
| --- | --- |
| A | 应用配置/注册、HTTP 和页面入口、权限、数据库事务、run/attempt、调度/恢复、审核与最终化守卫 |
| B | RuleAgent、配置构建方法、业务规则、checkpoint 恢复编排、调用示例、后续 Prompt/模型调用和输出校验；正式数据包修正、演示输入及来源/日期/单位维护 |
| A/B | 上下文与完成语义统一、路由优先级、四个演示场景及真实端到端联调 |

按最新分工，数据部分由 B 负责；A 负责接入、确认流程与验收，不再将数据修正列为第三位负责人的任务。

首次规划和失败重试已经有以下 A11 本地接口：

- `POST /api/v1/requests/{request_id}/plan`：已确认请求创建并调度新 run。
- `POST /api/v1/runs/{run_id}/retry`：只恢复当前可恢复 FAILED、revision 和输入一致的 run，保留已有产物并撤销旧 attempt。

建议修订和重新评估从当前方案详情页启动：修订建立 REVISE 新 run，重新评估建立 REASSESS 新 run。A 提供当前版本快照、权限及版本/运行乐观锁校验，B 执行业务处理；具体公共请求格式需后续补齐。旧 run 的 retry 不承担业务修订或重新评估功能。

真实 Agent 注册、上下文接线和联调通过后，再启用规划能力提示。Stub 始终不能生成真实方案。A11 完整交接记录在仓库 `docs/planning_entry.md`，但本文已包含本轮 B 接入需要确认的关键约定。

## 四、统一完整运行上下文

接受完整 DatasetContext 包含实际业务数据摘要、Adapter/规则/workflow 版本、已选择安全场景和修订反馈；DemoContext 另行绑定演示时钟与执行模式。

已复现当前不一致：直接注册真实 RuleAgent 并启用规划，保持 A11 原有 dispatcher.context 时，POST 开始规划返回 202，随后运行 FAILED，错误为 STALE_CONTEXT。B 文档已经指出联合接线要求，这项作为 A/B 接入工作处理。

建议配置流程由 A 的受信应用服务负责：

1. 用 A 的 inspect_dataset 验证磁盘来源、摘要和适用的 manifest。
2. 调用 B 提供的构建方法加载对应数据快照及登记的场景，并核对双方消费的实际字节和完整 context。
3. 确认、start、claim、retry 与端口守卫使用一致的上下文，B 执行绑定本 run 的配置。
4. A 保留当前磁盘数据/配置的重新检查；不能用长期缓存的 B context 替换变化检测，也不能为消除 STALE_CONTEXT 移除比较。

安全场景通过受信配置按明确 scenario_id 选择，来源日期、作用营地和证据有效范围显式登记。B 按实际选中的营地匹配证据；无匹配要报告缺失，不能伪造覆盖范围或丢弃冲突证据。正常/超预算场景应覆盖预期候选及修订替代营地。

数据、规则、场景、反馈、演示时钟或模式变化应创建新 run；需求或 Profile 被编辑后应先重新确认。REASSESS 可在合法范围内保留同一业务版本，但需要新的 run 关联/fingerprint、评估和审核，不沿用旧审批。

## 五、统一恢复和成功提交时机

A 负责调度、启动恢复、租约过期处理、用户 retry 入口和旧 attempt 的写入拒绝；B 负责 load_checkpoint()、复用已保存产物和仅执行缺失步骤。已有恢复基础继续复用。

A11 启动时恢复 PENDING；RUNNING 等租约过期后，在启动扫描或当前 run 的页面读取中标记失败，再由用户通过详情页重试。当前没有持续运行的全局过期扫描服务。B 的协作式 heartbeat 可保留，A supervisor 也自动续期；异步业务/模型调用须响应取消，续期间隔按实际租约配置。

请特别补充完成提交约定。B 的 `workflow/orchestration.py:200–211` 当前假定 report_stage(COMPLETED, SUCCEEDED) 已持久化成功，随后读取最终 eligibility；A11 为验证 orchestrate 返回值，采用以下顺序：

1. B 调用 report_stage(COMPLETED, SUCCEEDED, None)，表达完成意向并校验前提，数据库仍为 RUNNING。
2. B 返回相同 run_id/mode、stage=COMPLETED、error=null、引用正确已保存产物的 RunResult；如提供 route，须与 A 保存的路由一致。
3. A 校验返回值，持久化 SUCCEEDED，再重新计算最终 eligibility，页面通过 A 查询结果展示。

在测试中显式统一上下文后，真实 B Agent + A11 HTTP 已能执行成功且 finalisation_available=true，但 B 返回的 blockers 仍包含提交前的 RUN_NOT_SUCCEEDED。

请 B 调整最终返回及“完成已保存”的异常描述：返回前读取的是提交前状态，不能声称已经取得提交后的最终 eligibility，也不应把该时序产生的 RUN_NOT_SUCCEEDED 当成最终业务 blocker。已有业务阻断信息仍须保留。最终返回细节双方一起确认，B 不调用 A 的 commit_success 绕过返回值验证。

共同增加带 context_provider 的 RecoveryPort 和真实 HTTP 测试，不能仅依据没有 dispatcher 的 WorkflowService 测试推断完成事件已经落库。

SUCCEEDED 表示本次执行及保存完成；安全评估、审核决定、版本路由与 FINALISED 各自独立。

## 六、路由优先级建议

建议采用 B 的主状态优先级：

```text
BLOCKED > ESCALATED > REVISION_REQUIRED > ELIGIBLE_FOR_FINALISATION
```

这符合此前“高风险、低置信度或未解冲突进入审核”的业务约定。A 负责同步实际路由判定和 proposed_route 校验顺序；当前 A 代码仍是修订优先，这项尚未实施。

页面同时展示审核要求、修订要求和全部 blockers。例如高风险与超预算同时存在时，主状态建议为 ESCALATED，同时显示预算修订要求。即使审核批准，预算及其他放行条件仍需满足；批准不等于最终化，修订后的新版本/新 run 不自动继承旧审批。

强制 blocker 最高优先，人工审核无法绕过必要证据缺失或道路关闭。联调断言以 A 最终路由回执为准，同时检查另一类未解决问题仍被保留。

## 七、四个演示场景与 Canvas 验收

正式数据包及修正版现由 B 负责。A/B 可先准备独立、登记清楚的合成联调输入，不改写原始 v1，不依赖测试文件自动补事实。

B 本次提供的《A_B协商事项.md》仍以 Git v1 为开发基线，没有列出已完成的数据修正清单、修正版版本/交付位置或数据检查报告，因此该文档不能作为数据修正已交付的依据。这是对本次文档的判断，不推断 B 是否在其他位置完成了尚未提供的修改。

建议业务输入放 `data/demo_scenarios/`，演示步骤放 `docs/demo_scenarios.md`，独立期望与断言放测试目录。目录是接入建议，现有加载器尚未支持该路径；A 会明确登记加载路径和摘要规则，不绕过现有路径检查。

请 B 提供四套场景的最小字段清单、费用单位、营地/替代方案及业务规则需求，并交付对应业务输入及其来源、日期、有效范围和单位。A 负责配置入口、Profile 用户确认及快照传递、接入检查、演示步骤和提交包；双方共同验证场景结果。

| 场景 | 输入及验收重点 |
| --- | --- |
| 正常流程 | 装备数量/容量、车辆/路程、餐食、费用明确；安全证据覆盖营地和整个行程；可最终化 |
| 超预算 | 晚数、费用单位明确；具备可用于修订的低成本替代营地及其证据；修订后重新评估 |
| 安全证据缺失 | 独立 scenario_id、作用营地和有效范围明确；具体缺失项可见，不能放行 |
| 道路关闭 | 关闭证据、作用营地和日期明确；人工审批无法绕过 blocker |

异常场景的其他输入需要足够完整，避免装备或费用缺失遮蔽目标问题。示例 Profile 仍须经过 A 的确认流程；不能把 expected_*、测试断言或测试 setup 传入 Agent。

接受先完成规则版应用联调，再接入 LLM。B 负责角色 Prompt、非阻塞模型调用和输出校验；A 负责配置、密钥注入和执行入口；共同验证超时、取消、失败恢复及配置身份。规则版通过不代表 LLM 部分已完成。

保留无密钥的确定性演示。Canvas ZIP 应包含真实业务实现、登记场景、锁定依赖及启动说明，并在独立解压、干净安装、普通 Windows 成员电脑上验证；不能依赖作者本机 .env、私有仓库权限或作者密钥。

## 八、已执行的审查验证

| 检查 | 实际结果 |
| --- | --- |
| 审查时 GitHub PR/push checks | 两项 SUCCESS，PR OPEN、MERGEABLE；审查结束时 head 未变化 |
| Windows 原锁定环境 | RuleAgent 导入及 pytest 收集因缺少时区数据失败 |
| PR 全部后端测试，临时提供时区数据 | 398 项：396 通过，2 项因创建 symlink 权限失败 |
| A11+B 编排及启动/重试测试，同样临时提供时区数据 | 67 项通过 |
| 独立数字解析、混合来源复现 | R-02、R-03 均复现 |
| 真实 B + A11 HTTP，未统一上下文 | FAILED / STALE_CONTEXT，无法最终化 |
| 真实 B + A11 HTTP，仅测试内统一上下文 | SUCCEEDED、可最终化；B 返回含旧 RUN_NOT_SUCCEEDED |

临时时区数据为 tzdata 2026.5 wheel，只解压到 ignored var，通过 PYTHONTZPATH 提供给测试进程；没有安装到项目 .venv 或修补 PR。因此上述补充后的测试结果不代表原 PR 在 Windows 已通过。测试有一条既有 Starlette/httpx 弃用警告。

所有复现使用隔离快照、临时 SQLite 和明确标注的独立测试 Profile/证据，没有改变正式数据、.env 或应用代码。这些验证也不等于默认演示输入或完整 Canvas ZIP 已验收。

## 九、请 B 回复和交付的内容

1. 在同一个 PR 修复 R-01～R-04，附新增回归测试和 Windows 验证结果。
2. 提供可供 A 调用的配置/Agent 构建示例：输入、返回内容、规则版本及场景选择如何登记；保留共享契约 1.0。
3. 确认完成意向 → A 验证返回 → A 提交成功 → A 查询最终 eligibility 的顺序，并提出需要调整的 B 返回细节。
4. 确认建议路由优先级，以及高风险与超预算同时存在时的联合断言。
5. 提供四场景字段清单、营地及低成本替代方案需求，并交付对应数据，明确仍缺少的项。
6. 单独提供数据修正版的交付说明：版本号及仓库路径/提交或数据包位置、针对此前反馈逐项修复的清单、未解决项、结构/引用/费用单位/证据覆盖等数据检查结果及验证报告。若使用 manifest，说明与实际文件匹配的摘要；明确与本 PR 的 Git v1 基线及后续 Adapter 的兼容范围。若尚未完成，请明确当前数据进度，避免将 Adapter/规则实现完成视为数据修正完成。

A 随后负责将 A11 基础与真实 B 接线、统一上下文及路由、补齐修订/重评入口，并共同完成恢复故障与 Windows/Canvas 演示验收。文档中的建议在双方回应后再作为冻结的接入约定。
