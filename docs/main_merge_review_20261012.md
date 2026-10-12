# main 合并复核（2026-10-12）

已复核 [PR #2](https://github.com/LyraWangDev/ELEC5620-G19/pull/2) 的实际合并提交 `7720863117f2ea60d9a88ae95cf2f4ea7b9b2630`。GitHub 记录已合并；B head 为 `bec2ab1038ba4c1378506b5ef23c5d837929edbf`。

结论：没有发现本次合并的漏项或回归失败。B 的实现与数据交付已进入 main，我们的封存修复也已完整带入。尚未完成的应用接线继续作为后续开发，不把 CI 通过视为完整演示通过。

## 合入内容与验证

- B 将数据封存修复 cherry-pick 为 bec2ab1；main 的 data/synthetic_demo_v2 和 backend/tests/test_dataset_release.py 与 A 原修复提交 805ec5d 的内容无差异。
- 从 main 导出并独立解压，数据包脚本实测 68 PASS / 0 FAIL，58 条应用规格仍为 NOT_RUN。
- [对应 main CI](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38182985983)：433 passed、1 条既有弃用警告，schema 同步，前端构建成功（2.74 秒）。
- Windows 隔离快照完整后端回归：431 passed、2 skipped、1 条既有弃用警告，102.97 秒；退出码 0。跳过的是 Windows 无 symlink 创建权限的两项路径测试，不是业务失败。
- 本地共享 schema 导出检查：up to date。
- main 的依赖锁文件已包含 tzdata==2026.5；本次 Windows 回归使用现有项目依赖及该版本的独立解压副本，不修改原 .venv，不声称执行了全新环境的安装验收。

## 当前应用接入边界

- main 的 AGENT_FACTORIES 仍只注册 StubAgent，配置和个人 .env 未因本次合并切换。
- A11 提交 69a712e 尚未在 main 历史中；main 还没有 dispatcher、首次规划/失败重试的 A11 公共入口和对应测试。
- B 的 SyntheticDatasetAdapter 明确仍为 v1-only；v2 数据包已经在仓库，不代表 Adapter 已可直接读取它。
- 后续需整合 A11、提供 v2 适配、统一完整运行上下文及完成提交时机，再执行真实页面联调、四场景和 Canvas 安装演示。

本轮只 fetch 和检查隔离快照，没有 merge/rebase/pull 覆盖当前 A11 工作区，没有改应用代码、数据库、.env 或远端分支。机器可读 JUnit 位于 ignored var/main-merge-review/pytest-main.xml；隔离源和数据库也位于该审查目录。
