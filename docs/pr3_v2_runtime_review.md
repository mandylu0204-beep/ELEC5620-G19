# PR #3：v2 接入独立审查与给 B 的回复

2026-10-12 后续状态：A-14 已解决资料取值大小写并完成四套真实浏览器场景，当前检查为507 passed / 44权限跳过，见 [A-14实施状态](implementation_status.md) 与 [浏览器指南](demo/v2_browser_demo.md)。以下待浏览器/取值修正内容属于当时审查记录；Canvas最终包与模型版仍待验收。

## 最新 main 核对：57a378f（2026-10-12）

PR #3 已合并，远端 main 为 57a378f65bb810eeeac577309562b8acb8f5a500；合并提交的 main CI 成功。整个 Git 文件树与复测过的 882ba45 完全相同，无额外合并改动或修复丢失；两项问题保持关闭。

本地 main 已快进更新，保留个人 .env 和本地审查文件。对实际检出的 v2 数据再次执行静态检查：68 passed / 0 failed；schema 1.0 同步。以独立临时数据库验证启动：个人配置 stub/v1、规划禁用、ready=200；按正常 v2 场景显式配置 deterministic_demo/2.0.0、规划可用、ready=200，无配置错误。该启动检查不是新的浏览器或完整 Canvas 演示。

未重复运行相同代码的全部后端测试：已复测版本的 504 passed / 44 权限跳过结论适用于一致的代码/数据树，main 自身 CI 另已成功。main CI：https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38224073226 。

README 和旧 A 交接/实施说明中的“v2 Adapter 等待 B”状态已落后于本次合并，当前准确交接为 docs/v2_runtime_integration.md。建议下一步同步这些状态，并处理已有经验等级大小写及真实浏览器验证。模型版和 Canvas 完整验收仍未完成。

下文“未合并”是先前审查时的历史状态，以本节最新合并记录为准。

---

## 最新修复复核：882ba45（2026-10-12）

结论：R-01、R-02 均已关闭，可以合并本次规则版 v2 接入；当前未发现新的合并阻碍。本次没有合并 PR，也没有修改 main 代码。以下结论对应固定提交 882ba45ae7210fe48eee20c405a269b6dd6e772e，PR/push 两个远端 CI 均已成功。

- R-01：A 检查、B v2 Adapter 共用真实路径保护，业务/runtime、manifest 和登记场景在读取前检查。重跑原始 Windows junction 绕过副本：A/B 均返回 ADAPTER_FAILURE，禁止目录的 read_bytes 调用数为 0。
- R-02：True 满足、False 拒绝、None 才兼容旧设施文本。原始明确 False 复现已被拒绝；12 项 v1/v2 推荐和物流无障碍回归均通过。
- 完整 Windows 回归：548 总项，504 passed、44 skipped、0 failures/errors（261.39 秒），保留 1 条既有 Starlette 警告。44 个跳过均为文件符号链接权限限制，不能当作 Windows 已执行。B 在 macOS 报告 548 passed 与此不冲突。
- 新路径测试 49 项中，7 通过、42 权限跳过。6 个目录 junction 用例均实际执行并通过：data 指向 tests/包外各 A/B 两种读取入口，以及 scenarios 父目录重定向的检查/绑定两入口。另 1 项正常数据摘要兼容检查通过。
- 四个 HTTP 场景、修订/重评、失败恢复及旧规则身份阻止最终化均通过。静态数据 68 passed，schema 1.0 同步，pip check 通过；远端前端构建通过。
- 修复提交未改封存数据、默认配置、依赖锁或前端。新身份为 b01-v2-adapter-2 / b02-v2-rules-2；共用 v1 规则为 b02-v1-rules-2。旧规则运行必须重新评估，不能沿用旧放行结果。

Windows 原始复现结果与完整 JUnit 保存在 var/pr3-recheck/recheck-probes.json、review-summary.json、source/var/pytest-pr3-fixed.xml。初审原始证据保留。

给 B 的当前回复：

> 修复版 882ba45 已完成 Windows 独立复测。R-01/R-02 均关闭，6 个目录 junction 用例实际通过；全量 504 passed、44 个文件符号链接权限跳过，schema/pip check 与 68 项静态检查通过，远端 CI 通过。可以合并本次规则版 v2 接入。已有经验等级大小写问题、实际浏览器、模型版 Agent 和 Canvas 完整验收仍按后续任务处理。

模型版 Agent、四场景实际浏览器与 Canvas 干净安装/最终提交包、全部 58 条规格的应用执行仍未完成。此处“可以合并”不是宣称 Stage 2 或 Canvas 演示验收已完成。

---

## 以下为 bd44ce1 初审历史（R-01/R-02 已由上述修复关闭）

审查日期：2026-10-12。PR：https://github.com/LyraWangDev/ELEC5620-G19/pull/3 。审查固定提交：bd44ce10c2b121144a0435e29012859af46dffd6；main 基线：de732932ad94255626acadd18e67e4b3fdef7eac。

结论：完整前置路径、v2 工厂与四个后端 HTTP 主场景已接通，但发现两项可复现的中等优先级问题，建议修复并补回归后再合并。此次仅审查，不修改业务代码、不合并 PR、不在 GitHub 发布评论。

## R-01 [P2] v2 缺少业务文件真实路径隔离

位置：backend/app/adapters/synthetic_dataset_v2.py:175–179。

v1 在读取文件前 resolve(strict=True)，并检查解析路径位于固定的 data 目录。v2 只解析根目录，随后直接读取 root/data/filename 和 manifest。字节摘要相同无法证明真实路径仍属于允许的业务目录。

已在隔离副本复现：将 data 设为指向 package/tests/source-lookalike 的 Windows junction，目标内为复制的合法源文件，manifest 和 A 的摘要均未改变。v2 成功加载 10 个营地并返回 2.0.0；解析后的真实营地文件路径位于 tests。相同路径由 v1 拒绝，原因是 Business source escapes the business data directory。

这不是声称现有正常数据含有 oracle，而是说明当前 v2 的“不读取 tests/oracles”边界能被目录/文件链接绕过。现有两项链接隔离测试只覆盖 v1，不能作为 v2 的验收。

建议：八个业务/runtime 文件在 read_bytes 前逐一解析真实路径，验证落在允许的业务目录；manifest 也检查真实位置。拒绝链接指向 tests 或包外的情况，包括父目录 junction。添加 v2 链接/父目录重定向回归，不只检查 SHA256。

## R-02 [P2] 明确的无台阶否定值被旧设施文本覆盖

位置：backend/app/agents/rules/planning.py:53。

当前判断是 step_free_path is True 或 wheelchair_accessible is True 且设施含 accessible path。故 v2 的 step_free_path=False 仍可能被后半句判为满足硬性要求。

独立组件复现：以 River Flat 记录构造合法 CampsiteRecord，将 step_free_path 设为 False，wheelchair_accessible 保持 True，并保留 accessible path 设施文本。Profile 要求 step-free path。violations() 返回空列表，该营地被错误接受。

该复现是矛盾属性输入，当前封存的正常四场景没有这组属性组合；不能因此认定这条规则正确。新布尔字段明确为 False 时应拒绝或要求澄清，不能让旧泛化描述覆盖它。

建议：新属性为 True 时满足；为 False 时不满足；只有 None 的旧格式记录可以按经过约定的兼容规则回退。添加 True/False/None 三种映射的回归，并确认推荐与物流硬约束检查使用一致判断。

## 已核对通过的部分

- PR 正确基于完整 main，包含 A11+A12+A13；当前 PR 未合并，且 GitHub push/PR 两个检查均成功。
- 使用独立 archive、实际分支 app 导入、临时 SQLite 执行全部后端测试：486 总项，484 passed、2 skipped、0 failures/errors（179.58 秒）。两项跳过为既有 Windows 符号链接创建权限测试；B 在其他平台报告 486 passed 并不冲突。
- v2 Adapter 和 HTTP 新测试共 7 项；加上已有封存发布回归 7 项，重点范围共 14 项。
- 正常最终化及快照回读；超预算后更便宜营地修订；缺失证据/封路不能被批准或最终化；重新评估、新评估 IDs、反馈清空、历史最终快照保留；丢失保存回执后的重试不重新生成，均通过。
- 数据静态检查 68 passed / 0 failed；共享 schema 1.0 与 main 同步；pip check 通过。
- 前端文件未被此 PR 修改；远端 CI 前端构建成功。此次没有执行四场景实际浏览器验收或干净安装。

## 数据和范围说明

此 PR 也修改了先前定稿数据：当前安全记录共 18 条，revision_date 为 2026-10-12，业务/runtime 与封存摘要同步。因此旧的 2026-10-11 最终 ZIP 不能再作为本版 v2 演示数据；合并时需要把代码与新数据一起交付，最终 Canvas 包也要使用新的数据摘要。

模型版 Agent、四场景浏览器、Canvas 干净安装与提交包、全部 58 条验收规格的实际执行仍未完成。B 明确标注了这些范围，不能将 68 个静态检查或四个 HTTP 场景当作全部验收通过。

另外发现已有 A/B 枚举不一致：前端发送 beginner，v2 DSL 比较 BEGINNER，真实规则对两者分别遗漏/包含 emergency_contact_card。此问题在旧 v1 的比较中也存在，不归因于本 PR 新增回归；由 A/B 在浏览器接入时统一经验等级，并补 UI 输入测试。

## 初审阶段给 B 的回复（已由上方最新回复替代）

已独立复测 PR #3，四个 HTTP 场景、修订/重评/恢复通过；本机 484 passed + 2 个 Windows 权限跳过，静态数据 68 passed，schema/pip check 通过。建议先修复 R-01（v2 实际源路径隔离，包含目录 junction）和 R-02（step_free_path=False 不得被旧设施文本覆盖），补对应回归后再合并。代码与 2026-10-12 的 18 场景数据请作为同一交付版本。已有 experience_level 大小写问题由 A/B 后续共同统一；浏览器、模型版与 Canvas 完整验收仍待完成。

原始隔离证据保存在本机 var/pr3-review：source/var/pytest-pr3-review.xml、path-probe-result.json、step-free-probe-result.json、beginner-probe-result.json。证据文件不是业务输入，没有传给真实 Agent。
