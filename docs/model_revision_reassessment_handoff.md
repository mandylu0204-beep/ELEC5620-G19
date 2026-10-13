# B → A：模型修订与同版本重评交接

日期：2026-10-13（Australia/Sydney）。分支 `feature/llm-revision-reassessment`，共同基线为 main `9996e74`，已包含完整 A14–A16 和 B Client/Coordinator/Hybrid。

本文记录本分支实现，并请 A 复核其 owned 模块扩展，不代表 A 已确认新审计语义或真实校园修订/重评验收已通过。A16 的正常场景实测仍独立保留在 [报告](campus_live_browser_acceptance.md)。没有新建数据库、表或迁移；没有修改私人配置、封存数据或共享 DTO/schema 1.0。

## 1. 功能变化

- Hybrid 支持 PLAN / REVISE / REASSESS；没有规则/stub 模型规划回退。
- PLAN、REVISE 真正调用原 CampusModelClient 和 Coordinator；解释、筛选、装备/费用、安全仍是明确标注的规则。
- REVISE 把原行程和修改意见作为不可信数据传给模型。传入的只有营地与行程内容，不含持久化 ID、旧审批、trace、write keys 或凭据。
- 继续单营地、最多30晚，固定确认预算、日期、人数、硬条件及 Profile；换营地后重新查实际候选、生成版本并独立评估。
- 标准反馈 `change campsite` / `更换营地` 必须换营地；`cheaper campsite` / `更便宜的营地` 必须降低营地每晚费用。这不保证全行程费用低于预算，所有费用仍由原算法计算。
- 其他反馈在当前单营地能力范围内由模型处理和解释，不保证任意活动/交通建议已支持，不会把任意反馈字符串当系统指令。
- 模型可返回内部 `requirements_change` 动作提出 TripRequirements 变更。非空且实际不同的提案返回 REQUEST_NOT_CONFIRMED，不修改原需求、不保存版本/成功 trace；用户需重新提交并确认。非法提案或越权字段返回 CONTRACT_INVALID。当前未增加前端展示具体提案字段的功能。
- REASSESS 使用同一版本内容、新 run 和新物流/安全评估；不请求推荐或规划模型、不生成新版本、不新增/复制模型 trace。旧评估/审核不可沿用，旧最终快照保持历史内容。

## 2. B 的反馈与 checkpoint 对齐

`build_hybrid_configuration` 增加内部可选 `feedback` 参数，传入 WorkflowConfiguration；A 工厂读取现有 `a_revision_feedback`，返回相同 `revision_feedback`。普通 PLAN/REASSESS 不带意见。

首次 REVISE 的原版本必须与 A checkpoint.previous_version 完全一致，不能只提供匹配 ID 却替换原内容。保存后 retry 直接使用 checkpoint.version，不再要求模型生成；trace 与版本仍由同一个既有 `append_model_plan` 调用原子保存。

保存前完全回滚时可以重跑模型，可能消耗更多 token；已提交且回执丢失时恢复原版本和原生成 trace/attempt，不声称模型调用 exactly-once。heartbeat、取消、过期租约及成功提交继续复用既有流程。

## 3. 本分支涉及的 A-owned 扩展（请 A 复核）

### 工厂与身份

`backend/app/application/agent_runtime.py` 透传反馈，并登记：

```text
a_model_trace_required=1
a_model_trace_contract=1.0
a_model_trace_binding=origin-version-v1
```

trace payload 字段/保存方法签名仍为原1.0；新增 binding 键区分重评引用语义，不把旧 scope 当作新语义。A 规则身份从 a-model-audit-v1 升为 a-model-audit-v2。B Hybrid、Coordinator、validator 各自升级实现后缀；原确认/运行身份不原地改写，旧进行中的 run 不应跨新实现复用。

保留全部 A 原数据/fixture 摘要、选择项和 rules_version 前缀；重评的新 fingerprint 标识新的评估上下文，而不是原模型生成上下文。

### 修订保存

`validate_trace` 从只允许 PLAN 扩展为 PLAN/REVISE，仍核对当前 scope 的模型配置、Prompt、工具、实际保存推荐、营地、完整 trace 形状。append_model_plan 签名、scope.write_keys['version'] 和版本/trace/回执原子事务不变。

### 同版本重评的原生成 trace

`backend/app/application/model_audit.py` 新增 `load_origin_trace`：

1. 校验当前 REASSESS scope 的 binding 标记、plan/version/run 和当前 fingerprint。
2. 按该 plan/version 找到唯一原生成 trace；缺失、多份或错误关联均拒绝。
3. 读取原生成 run 的保存 scope、确认和版本绑定，要求来源是 PLAN/REVISE，而不是另一个重评伪造的生成记录。
4. 按原生成上下文验证 trace hash、owner、版本、原 fingerprint、推荐和模型身份，并验证原/当前版本内容相同、确认需求/Profile 不变。
5. 返回原 trace 的 id/run_id/input_fingerprint/attempt_id/created_at，不改写成当前重评 ID，也不插入新审计行。

原模型配置与当前重评配置可能不同，因此不能强制原 trace 的模型 fingerprint 等于当前 fingerprint。当前评估/最终化仍须通过当前输入检查；原生成记录则按自己的不可变上下文验证。模型配置改变后，旧评估不能直接最终化，但可创建新 REASSESS 重新形成评估。

返回的 model_planning_trace 仍是原对象结构，checkpoint、方案详情与最终快照复用统一读取入口。重评最终快照包含原生成记录和本次新的版本上下文/评估；不冒充“本次再次生成”。

### 页面

`frontend/src/model_trace.tsx` 比较当前 run 和 trace.run_id，明确显示“本次重评未调用规划模型、usage 属于原生成”，并保留原关联编号。现有按 supported_operations 控制的修订/重评入口自然启用，HTTP owner/CAS/CSRF 等守卫不放宽。

REQUEST_NOT_CONFIRMED 的允许动作是 EDIT_INPUT，页面提示重新确认需求，而不是联系开发者或重复技术重试。当前不展示模型提出的具体字段，只提示需重新确认；不会自动保存或确认提案。

## 4. 测试与完成边界

新增 `backend/tests/test_model_revision_reassessment.py`：实际 Client/Coordinator/Hybrid、HTTP 权限/确认/dispatcher 和 A SQLite，模型传输全部为 MockTransport + 独立假密钥。

最终本机检查：新增23项通过；针对性组合142项通过；最终全量704 passed、0 skipped、0 failed（84.30秒），保留1条既有 Starlette TestClient 弃用警告。共享 schema 1.0、TypeScript、Vite（53模块）、pip check、git diff --check 均通过；封存数据静态校验68 passed/0 failed（静态检查不执行其58条应用规格）。环境为锁定的 Python3.12.14 / Pydantic2.13.5 / httpx0.28.1，Node24.19.0。没有声称在 Windows 重跑本次新增代码。

覆盖超预算首轮 → 更便宜模型修订 → 新版本评估/保存 → 同版本重评/再次最终化、历史快照保留、重复命令与不同意见冲突、证据缺失阻断、确认需求变更拒绝、非法模型输出、写入前/回执丢失后恢复、服务重启、连续重评、模型配置改变、跨用户隔离及原 trace 缺失/owner/fingerprint/hash/重复记录损坏拒绝。

旧 PLAN-only 断言随真实能力变化更新，不取消原模型失败、模式守卫、原子保存和 lease 取消回归。Windows 短 pytest ID 与基于 Event 的 heartbeat 测试保持。

本次没有校园请求或新的浏览器人工验收；离线 HTTP 成功不能当真实模型修订证据。另两个模型角色、A15 高风险/过期/禁火完整演示、其他真实校园失败场景、干净 ZIP/Canvas/另一电脑仍待完成。A16 的正常实测不能代替本次新增能力验收。

本轮使用 OpenAI Docs 技能核对 [消息角色与指令分层](https://developers.openai.com/api/docs/guides/prompt-engineering)，将修订意见与原内容放在数据消息中，host 的事实/权限校验不依赖 Prompt 自律。该文档仅作设计参考，不证明校园代理支持其他 OpenAI 特性；目标仍为 campus-qwen，沿用应用层 JSON 工具协议。

## 5. 建议 A/B 下一步

请 A 优先复核 origin-version-v1 关联语义、原子保存、权限/最终化守卫和页面提示。认可后按完整分支做 PR/CI，不单摘 B 能力开关或 Coordinator 提交到旧 main。

随后联合执行真实校园超预算修订、同版本重评、回执丢失恢复及历史回读。使用隔离数据库并明确 opt-in；不要覆盖私人配置、强制模型选择预期营地或为演示放宽安全结果。本轮未发送消息给 A，未 commit/push。
