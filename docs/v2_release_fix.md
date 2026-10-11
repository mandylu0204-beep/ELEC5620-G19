# v2 数据包发布修复与定稿记录

日期：2026-10-11。基于 B 的 `9e086f949944f6b2cebe1be5f69e832e62c254c3`，本地分支 `fix/v2-release-seal`。

修复 Git 下载数据包的 manifest 问题：Python 缓存不再纳入封存；CSV 与其他发布文件统一 UTF-8/LF；独立数据子目录也包含 .gitattributes，不受父仓库缺失或 Windows core.autocrlf=true 影响。生成报告后同步记录报告摘要，失败校验不会自动重新接受改变的发布输入。

`scripts/release_files.py` 维护 31 个明确发布文件的清单，manifest 自身除外。作者新增发布文件时需同步登记。普通 validate_dataset.py 校验只读；显式作者命令才重建封存。输入、日期、费用规则、fixture/oracle 语义均与 B 修订版一致。

## 已执行验证

- 数据目录原地校验：68 PASS / 0 FAIL。
- backend/tests/test_dataset_release.py：7 passed，覆盖缓存/本地结果排除、CRLF 与旧 pycache 登记修复、报告重复生成、篡改后不自动重签、fixture 修复重复执行及 Windows Git 子目录导出。
- 从 Git index tree 导出 ZIP 后独立解压：68 PASS / 0 FAIL。子目录导出已在 core.autocrlf=true 下验证，不依赖根仓库属性。
- 八份业务/runtime 文件与 fixture/oracle 对照 B 基线，Git diff 无差异；默认 v1、应用配置和 A11 工作区均未改。
- git diff --check 通过。

## 数据交付包

文件：`var/releases/campmate_synthetic_demo_v2_20261011_final.zip`。

SHA-256：`d0baf9d3630cd46c2ac708be981625dfaa351b374f777bb6d24386cdcafac0bf`。

ZIP 内根目录为 campmate_synthetic_demo_v2；解压后执行：

```text
python -B scripts/validate_dataset.py
```

无需 API Key、GitHub 权限或第三方包即可执行数据静态校验。此 ZIP 是数据包，不是完整 CampMate 应用提交包。

发布封存问题已解决，可以冻结此份 v2 修订数据作为接入基线。仍有 58 条应用验收规格 NOT_RUN，v2 Adapter、四个完整演示场景和 Canvas 完整项目安装演示继续单独完成。版本保留 2.0.0 / revision_date=2026-10-11，通过 manifest 摘要区分本次发布修复。

修改已保存到本地修复分支；本轮没有推送 B 分支或 main，没有创建 PR。可将本地提交导出的 patch 交给 B 应用，避免覆盖 B 后续未审查的修改。
