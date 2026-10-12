# PR #2：B01–03 审查反馈

审查日期：2026-10-11。PR：https://github.com/LyraWangDev/ELEC5620-G19/pull/2。

审查提交：`f80e5dea21175745a2ddc4204420f5816ad95aa5`，目标 main：`2c647e64a8d302ea036839c0972bfc47503275fc`。
本地 A11 组合验证使用 `69a712e`；该 A11 提交尚未上传，所以本 PR 的 GitHub CI 没有验证这个组合。

结论：建议修改后再合并。两项 GitHub checks 成功、无合并冲突，但 Windows 的实际运行/测试仍有问题，并发现两处输入验证缺陷。以下反馈仅保存到本地，未向 GitHub 发布 review/comment，未执行 merge。

## 1. [P1] 声明并锁定 Windows 所需的时区数据依赖

位置：`backend/app/agents/rules/common.py:11`，`TRIP_ZONE = ZoneInfo('Australia/Sydney')`。

从项目现有锁定依赖环境导入 RuleAgent 时，Windows 上立即出现 `ModuleNotFoundError: No module named 'tzdata'` / `ZoneInfoNotFoundError: No time zone found with key Australia/Sydney`。完整 pytest 也在收集阶段报错，不能开始执行。PR 没有向 `backend/pyproject.toml` 或 `backend/requirements.lock` 添加 tzdata。

这会影响用户从 Canvas 下载项目后，在普通 Windows 电脑安装锁定依赖并演示的要求。Linux 上可用的系统时区数据库不能证明 Windows 可运行。

建议：在依赖声明和锁文件中加入 tzdata（可以使用适合项目的 Windows 条件依赖）；添加 Windows 从锁文件安装后的 Agent 导入和 Sydney 时间转换验证。不要用固定 UTC+10 或 UTC+11 代替 Sydney 时区，否则夏令时切换仍会出错。

最小复现：在 backend 下，使用仅安装仓库锁定依赖、没有额外时区数据库的 Windows Python 执行 `python -c "from app.agents.rule_agent import RuleAgent"`。

## 2. [P2] 解析完整数字，避免把负数或小数截成合法整数

位置：`backend/app/agents/rules/interpretation.py:57–60`；人数解析也使用同样的数字模式。

独立输入复现（Profile 明确为 2 人）：

| 输入中的片段 | 当前结果 | 应有行为 |
| --- | --- | --- |
| `for -2 nights` | 提取 2 晚，field_errors 为空 | 报告非法时长并澄清 |
| `for 1.5 nights` | 提取 5 晚，field_errors 为空 | 报告非整数时长并澄清 |
| `-2 people` | 没有报告人数错误 | 报告非法人数并澄清 |

完整请求示例：`Two campers in CampMate Demo Region from 2026-10-20 for -2 nights, AUD 300.`；小数复现只替换 `-2` 为 `1.5`。

原因：开头的 `\b` 允许从负号后重新开始匹配，也允许从小数点后的数字开始匹配。修复需要识别整个数字 token，再验证正整数；不能只给现有模式补一个负数分支而仍允许从后缀重试匹配。人数、days、nights 都应有对应回归测试，explicit_fields 优先级按现有约定保留。

## 3. [P2] v1 Adapter 应拒绝混合或不支持的来源版本

位置：`backend/app/adapters/synthetic_dataset.py:342–355` 以及 `_source()`。

复制原始 v1 六份业务数据，仅把 `synthetic_profiles.json` 第一条记录的 source_name 改为 `CampMate Synthetic Demo Dataset v2`，其余内容保持原样。当前 `load()` 成功，`dataset.context.dataset_version` 仍为 `v1`，但该 Profile 的 provenance 为 v2，营地 provenance 为 v1。

共同 Provenance 已允许 v1/v2，因此逐条通过 DTO 验证不能证明整包属于 v1。Adapter 文档声称检查 v1 Provenance，实际缺少包级一致性验证。A 的 `inspect_dataset()` 会拒绝这个混合包，A/B 输入身份也因此不一致。

建议：本次既然只支持 Git v1，就明确验证所有来源属于受支持的 v1，且包内 provenance 一致；混合来源、整包 v2 应返回 ADAPTER_FAILURE。后续支持 v2 时再通过已登记的 manifest/runtime 入口处理，不要继续硬编码 v1 标签。此反馈不要求本 PR 完成 v2 功能。

## 4. [P2] 两项 symlink 测试应处理 Windows 缺少创建权限的环境

位置：`backend/tests/test_synthetic_dataset.py:420` 和 `:430`。

在额外提供时区数据后，完整 398 项测试中 396 项通过；以下两项在创建测试链接时出现 `OSError: [WinError 1314]`，还没有执行到 Adapter 的安全校验：

- `test_symlink_cannot_escape_dataset_root`
- `test_symlink_cannot_redirect_to_oracle_inside_dataset`

这不是已证明的路径守卫失效，而是测试环境前提没有被处理，会导致普通 Windows 账户的项目检查失败。建议为测试做精确的能力探测：仅在无法创建符号链接的环境标记 skip 并说明原因；保留可创建链接的平台对实际拒绝行为的验证。不要为了通过测试删除生产路径守卫，也不要把所有 OSError 都当成无权限。

## A/B 共同接线事项：不是单独归因于 B 本 PR 的回归

### 运行上下文统一

B 的 WorkflowConfiguration.context 纳入 Adapter、规则、workflow 版本及场景选择，A11 当前 dispatcher.context 来自 A 的 inspect_dataset，两者不相等。

独立 HTTP 验证：注册真实 RuleAgent、启用 deterministic_demo 和 planning，但保持原有上下文生成方式；POST 开始规划返回 202，随后运行 FAILED，错误为 STALE_CONTEXT，且无最终化入口。B 文档已指出需要联合接线，因此不能把本 PR 合并当成前端已接入。

A 应统一确认、start、claim、retry 和当前上下文守卫的来源；同时保留 A 对磁盘字节、manifest、证据变化的重新检查。不能为了消除 STALE_CONTEXT 而移除比较，或永久返回 B 进程内的缓存 context。

### A11 的成功提交时机与 B 的 eligibility 刷新

B 的 `workflow/orchestration.py:200–211` 假定 report_stage(COMPLETED, SUCCEEDED) 已持久化成功，再读取最终 eligibility。A11 为校验 orchestrate 的返回值，先接受完成意向，仍保留数据库 RUNNING；实际 SUCCEEDED 由 A dispatcher 校验返回值后提交。

独立 HTTP 组合验证在测试中显式统一 context，并使用真实 B Agent、完整的独立测试 Profile/证据。结果：

- 数据库最终 SUCCEEDED，A 查询 finalisation_available=true；
- B 返回 RunResult.run_status=SUCCEEDED，但 blockers 中仍含 RUN_NOT_SUCCEEDED。

当前前端以 A 查询结果为准，没有观察到最终化守卫被绕过。这里是返回内容不一致和完成语义差异，需要联合约定；不能让 B 自行调用 A 的 commit_success 来绕过返回值验证。最终 eligibility 可由 A 在实际提交成功后查询并提供，B 不应把提交前的 RUN_NOT_SUCCEEDED 当成最终判断。也应更正 B 对“完成已保存”的异常描述，增加使用带 context_provider 的 A11 RecoveryPort/HTTP 测试。

## 验证范围与限制

| 检查 | 实际结果 |
| --- | --- |
| GitHub PR/push checks | 两项 SUCCESS，PR OPEN、MERGEABLE，最终复核 head 未变化 |
| Windows 原始锁定环境 | RuleAgent 导入及 pytest 收集因缺少时区数据失败 |
| PR 完整后端测试，临时提供时区数据库 | 398 项：396 通过，2 项创建 symlink 时权限失败 |
| A11+B 编排及启动/重试测试，同样临时提供时区数据库 | 67 项通过 |
| 独立请求数字解析/混合来源复现 | 上述缺陷均已复现 |
| 真实 B Agent + A11 HTTP，未统一上下文 | STALE_CONTEXT，运行 FAILED |
| 真实 B Agent + A11 HTTP，仅测试内统一上下文 | 运行成功，可最终化；B 返回值有 RUN_NOT_SUCCEEDED 旧 blocker |

测试时区数据：tzdata 2026.5 wheel 只解压到 ignored var 审查目录，通过 PYTHONTZPATH 提供给测试进程；没有安装到项目 .venv，也没有修补原 PR。因此临时补充后测试的结果不代表原 PR 在 Windows 已通过。两项测试批次均有一条既有 Starlette/httpx 弃用警告。

所有数据库、输入修改、真实 B/A11 组合和探针脚本都位于 ignored `var/pr2-review`、`var/pr2-integration` 的独立快照。原应用代码、数据、.env、本地 A11 提交、main 和 GitHub PR 均未修改。本报告是唯一新增的受版本控制目录文件，但尚未提交或上传。

独立复现脚本：`var/pr2-integration/source/backend/pr2_review_probes.py`。
独立 JSON 证据：`var/pr2-integration/source/backend/var/pr2-review-probes.json`。

建议交接顺序：B 修复 1–4 并更新同一个 PR；A/B 对齐上述接线语义，再进行 Windows 干净安装与应用启动/重试联调。LLM、v2 数据、默认场景和 Canvas 最终提交包的演示验收仍需后续单独完成。
