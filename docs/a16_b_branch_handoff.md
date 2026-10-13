# A → B：A-16 完整分支交接

**最新发布：完整分支已快进合入main（9996e74），正常场景真实验收报告已发布，原分支和main CI通过。请从更新main继续开发。异常场景与受控保存恢复结果见 [A17交接](campus_exception_acceptance.md)；下文未合main/本地报告是当时历史。**

**追加：A在本机校园VPN连接及密钥配置后，已完成正常场景真实模型HTTP/浏览器闭环、最终保存、重启回读和用户隔离；报告见 [真实校园验收](campus_live_browser_acceptance.md)。以下发布时“未配置/未验收”描述保留为历史。最新报告目前只在本地分支，尚未推送。**

日期：2026-10-13。

完整分支：[feature/a16-campus-wiring](https://github.com/LyraWangDev/ELEC5620-G19/tree/feature/a16-campus-wiring)。应用提交：`2d88ad34c13c2d62b87c62c72cf14b6b4da11c9b`；后续仅补充本次发布/验收状态文档。

应用提交的远端 [GitHub CI #38322599358](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38322599358) 已完成且 conclusion=success，后端测试与前端构建均通过。本次后续发布状态变更只涉及文档。

分支已包含 A14/A15、B `5c4a093` 完整 HybridPlanningAgent 和 A16；merge提交538c716保留B原历史。A 已接好 v2/agent 工厂、PLAN-only模式/能力校验、迁移6、trace同事务保存、checkpoint恢复、方案/最终快照展示。实际端口、错误格式和开关见 [接线交付](campus_model_wiring.md)。请基于完整分支协作，不再从旧 main 接线，也不要仅 cherry-pick A16。

本机最终638 passed/44 Windows符号链接权限跳过，schema及前端构建通过，模拟模型响应的真实HTTP/浏览器流程通过。本机密钥未配置、校园代理TCP连接超时，用户选择本轮只同步与交接；真实校园模型HTTP/浏览器验收未完成。个人.env未改；新增本地空密钥模板已忽略，未上传。未创建PR、未合main。

B可以在现有可达校园代理的环境中，按接线文档的正常输入使用独立数据库进行真实验收；严格保留实际费用与安全评估结果，不强制模型选择某营地或伪造通过。需要提供正常场景真实HTTP与浏览器结果、保存trace及最终回读证据。首版模型修订/重评和另外两个模型角色仍不在本次交付范围。

如需开展后续独立工作，可从发布分支新建自己的分支；在A16合main后再从更新main开始。此文档是供用户转发的交接，没有代替用户向B发消息。
