# 删除露营想法后的结构化摘要交接

日期：2026-10-29。用户授权完成后 commit，不自动 push。保留本轮此前的结构化选择、人工协助、装备及车辆数量保存语义和展示调整。

## 用户流程

完善资料 → 选择日期、预算、用餐、偏好及必须条件 → 如有未明确的其他要求，进入人工协助 → 核对摘要 → 显式确认并开始规划。

页面删除“你的露营想法”输入及其非空限制。没有任何占位句或固定描述写入数据库：新请求省略 raw_text，HTTP 层默认保存真实的空字符串。历史列表根据实际目的地、日期、晚数显示标题；不往原文列补写标题。

## 新、旧请求分离

- 新的无原文请求使用 `application/structured_summary.py`，直接整理已填写字段及已固定资料。此步骤不调用模型，也不伪造模型 trace 或 usage。
- 摘要读取明确返回 `summary_origin=STRUCTURED_FORM`；页面提示这是表单整理结果，尚不代表营地、装备或安全检查通过。
- 日期下限、晚数／天数／结束日期一致性、预算、小组人数、用餐冲突及条件矛盾仍在确认前校验。
- 私有 `structured_summary_metadata`（版本 structured-form-summary-1）绑定分析 revision、原字段、固定 profile_snapshot 和 demo_context 指纹。确认前重新核对；普通 HTTP 响应移除此元数据，不暴露指纹。
- 历史非空原文仍使用原来的规则／模型解释能力及原身份校验；旧模型 Prompt、输出协议和共享 InterpretRequestInput 1.0 不改。
- PATCH 没有 raw_text 时保留旧原文；旧页面将其只读折叠展示，不将不可见原文静默清空。
- 从已有方案新建后继请求时，复制该运行已确认的 requirements，raw_text 留空，不重新带入旧原文。这让用户能通过选项修改条件，旧原文不会悄悄把取消的条件加回来。
- 原请求、已确认上下文、旧方案内容、模型审计及最终记录不改写。既有系列关系、checkpoint、heartbeat、恢复与幂等接口保持。

## 人工协助与模型角色

未匹配的其他要求继续在摘要前阻止进入模型流程，使用迁移 12 的需求协助队列。Founder 只能建议已有条件或退回补充，用户确认采用后仍需重新生成摘要。

Host 摘要不改变正式规划的 agent 身份。离线生产工厂集成覆盖：摘要与确认 0 次模型请求；随后 Planning 2、Logistics 3、Safety 3 次模拟模型 HTTP，均执行实际组件；最终记录可在重启后回读而不产生额外调用。这是 MockTransport 验证，不是真实校园模型验收。

## 接口与存储

- HTTP RequestInput.raw_text 改为可省略、默认空字符串，保留最大 8000 字符限制。
- 共享旧模型输入 DTO 仍要求非空原文，新结构化路径使用独立的应用层输入，避免修改冻结契约。
- 请求摘要接口、请求 revision、确认与命令 key 保持；新增结构化摘要来源及私有身份绑定。
- 请求列表增加所有者自己的 explicit_fields，以提供真实标题，不包含模型诊断。
- 没有新增迁移编号或修改封存数据。之前的迁移 12 已在用户明确要求重启时部署到本地数据库，并保留迁移前备份；本次没有进一步迁移或重启运行中的服务。

## 本轮未执行

未调用真实校园模型；未修改个人环境文件、密钥或数据包。尚未用交互式浏览器验收最新摘要路径。当前运行的后端仍为本次修改前进程，需要重启后端加载新的可省略原文接口；仅刷新前端不能完成后端更新。

## 修改重点

backend/app/application/structured_summary.py、http_requests.py、storage/requests.py、storage/trip_series.py、application/presentation.py；frontend/src/requests.tsx、requirement_help.tsx。相关既有人工协助及数量确认改动一同保留。

## 最终组合验证与提交范围

- 后端全量 1923 项通过，0 失败／错误／跳过；四组 481＋481＋481＋480，已核对收集清单无重复或遗漏，并确认测试期间源码不变。
- 证明文件：var/structured-summary-final-full/verified-summary.json；源码 SHA256：91f9a1d91c53620120ccb1fac360e31aa08bd6f8461e6b6c20170eee3c40b2c9。
- 前端全量 170 项通过；TypeScript、生产构建、共享 schema 检查及 git diff --check 通过。
- 真实 HTTP transport 尝试 0；未进行真实校园模型调用。
- 现有 Starlette TestClient 弃用和 Vite bundle 大小提示仍保留，未出现测试失败。
- 本轮提交包括此前尚未提交的界面调整、装备／车辆数量保存确认、迁移 12 的需求协助，以及本次去除新请求原文与 Host 摘要。数据包、个人环境文件、备份和测试产物不纳入提交。
- 按用户明确要求 commit，不自动 push。验证结果针对本次最终组合，不把此前中间测试次数累计成最终通过数。
