# 首版协作交付：A-05 开发原型

日期：2026-10-10，Australia/Sydney。这是源码协作基线，服务通过 README 在本地运行。

## 已实现

- React/TypeScript/Vite、FastAPI 和 SQLite 项目基础、配置与启动脚本。
- A/B 共同 DTO、六项 AgentPort、九项 PersistencePort 的 A 侧实现与 JSON schema。
- 两个 Camper 和一个 Founder 的演示登录、服务器会话、角色和用户隔离。
- 数据迁移、Profile 编辑、不可覆盖快照、内部版本/评估持久化与事务守卫。
- 请求草稿、摘要、日期/时长澄清、明确确认、幂等回执及刷新恢复。
- 原始 synthetic 包完整副本、数据检查报告、接口交接与实施证据。
- push/PR 自动执行后端测试、schema 对照和前端构建的 GitHub Actions 配置。

## 验证

Windows / Python 3.12.14 / Node.js 22.20.0，本机 `scripts/check.py` 退出码 0：54 项后端测试、schema 对照、TypeScript/Vite 构建通过。浏览器检查资料保存、冲突澄清、确认和历史快照保持，见 [实施状态与截图](../implementation_status.md)。原始与仓库数据副本共 10 文件，SHA256 逐文件一致。

本机结果不能代替 GitHub runner、另一台电脑或完整业务联调；远端 CI 结果在仓库 Actions 查看，未运行前不记为通过。

## 下一阶段

A-06 规划进度与产物展示、A-07 审核、A-08 最终化仍待实现。当前解释器为明确标注的 stub，不执行自然语言提取或推荐、行程、装备/物流、安全推理，也不生成成功方案。B 的 schema/Adapter/规则实现与修订数据尚未交付；正常、超预算、缺失证据、道路关闭四个业务场景未执行。

资料与请求可供成员本地检查，审批和最终化尚无产品入口。项目不得用于真实出行或安全决策；synthetic 标签与固定演示时钟必须保留。
