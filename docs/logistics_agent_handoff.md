# B → A：LogisticsAgent 组件交付（尚未应用接线）

日期：2026-10-14（Australia/Sydney）。分支 `feature/llm-logistics-agent`，基线 `3a1206f`，包含 A19 `0b57197` 的完整集成/真实验收和 A20 页面整理。

本轮只实现用户指定的两项：模型真正参与装备规划，以及确定性数量/容量/费用校验。不修改 A 的审计/持久化接口、数据库、Hybrid 默认步骤、HTTP、页面、私人配置或封存数据。不能据本组件宣称应用已启用第二个模型角色。

## 1. 已实现的调用链

```text
A 提供绑定保存版本的 LogisticsInput
→ 原规则计算数量、容量、库存、必要费用、证据缺口和 blocker
→ 校园模型请求 read_logistics_facts
→ 模型选择逐项补缺方式及所有费用行的预算优先级
→ 模型请求 evaluate_logistics_plan，由 host 计算方案费用及资金缺口
→ 模型选定已计算的方案，返回 final
→ host 再校验并返回 LogisticsOutcome
```

这是应用层 JSON 工具循环，沿用学校代理的 Chat Completions 内容接口，不声称代理原生 function calling 已验证。目标是 campus-qwen，不新增 SDK 或更换模型。

模型控制的是结构化决策，不是一个说明段落：

- 按规则提供的 allowed_methods 选择每项装备的安排方式，排序形成规划清单。
- 在有实际参考价格时选择拟租借/购买，或选择费用仍未知的拟借用/询问用户。
- 对非必要物品可明确延期采购，保留原缺口，不将其改成已拥有；必要物品不能这样跳过。
- 提供完整费用行的优先顺序，host 用原确认预算计算每行的分配与未覆盖金额。
- 可以在回合上限内重新计算不同策略，最后只能选用已经计算过的同一方案。

改变补缺方式会改变明确的预计费用及确认需求；改变预算优先级会改变实际计算的资金分配。没有仅在规则结果后面追加一段 LLM 摘要冒充规划。

## 2. B 组件接口

新增文件：

| 文件 | 能力 |
| --- | --- |
| backend/app/llm/logistics_agent.py | LogisticsAgent、LogisticsOutcome、调用局部 LogisticsTrace |
| backend/app/llm/logistics_schema.py | 受控模型动作、装备选择与完整费用优先级协议 |
| backend/app/llm/logistics_tools.py | 只读事实、参考价格、确定性方案计算及二次防篡改校验 |
| backend/tests/test_llm_logistics_agent.py | 离线模型组件与安全边界回归 |

```python
agent = LogisticsAgent(dataset, campus_client,
    workflow_configuration=configuration)

outcome = await agent.assess_with_trace(saved_logistics_input)
# outcome.assessment: 共享 LogisticsResult，execution_mode=agent
# outcome.plan: 内部 ValidatedLogisticsPlan，结构化补缺和预算安排
# outcome.trace: 本次调用的内部 LogisticsTrace，无全局 last_trace

# 需要共同 DTO 的独立调用入口：
assessment = await agent.assess_gear_and_logistics(saved_logistics_input)
```

输入必须使用 A 保存、授权并绑定版本的 LogisticsInput。组件检查 DTO、模式、固定日期/最多30晚、数据版本和原规则约束，但不会自行查询数据库证明授权或声明自己创建了保存版本。A 的 owner/scope/lease/输入 fingerprint 守卫仍需在正式接线时执行。

至少3轮：读取事实、计算方案、返回已计算方案；CampusModelSettings 默认4轮可用，配置小于3轮时明确拒绝。本接口不进行连接探测，缺密钥/模型失败/非法回复没有规则回退。

## 3. 确定性校验与不可越过的边界

- required/available/missing quantity、tent capacity、需求/Profile、交通及当前证据选择均来自原规则，不由模型填写或改变。
- 帐篷缺口是 person_space。两人帐篷租借数量复用规则的 ceil(gap/2)，并使用原 CostLine 的 Decimal 数量；租借费为整个演示行程，不再次乘晚数。
- Decimal ROUND_HALF_UP、整数 cents、成本合计、预算差额、逐行资金分配/不足均由代码计算。
- 食物/饮水原人日价值 allowance 不当作每份餐/每升水的实际购买单价；不因已有物资就把其价值费用删掉。
- 参考价格缺失、库存未知、拟借用费用未知时保持 None，不能默认0；未知费用行的资金需求/分配/不足也为 None。
- 对无原报价的额外可选装备提供明确未知费用行；如选择延期采购，零是“没有计划采购”的费用，而不是虚构免费供应商/单价。原物品、缺口和必要性仍显示。
- 所有装备和全部费用行必须逐项覆盖且唯一，不能删必要行、伪造价格/来源、改变预算或借排序隐瞒未覆盖费用。
- KEEP_CONFIRMED 仅允许实际已确认且缺口为0的物品。拟租借、购买、借用均为未确认建议，不增加库存，不写 CONFIRMED_RENTAL，不移除 ESSENTIAL_GEAR_MISSING。
- 原 blocker、澄清、交通事实继续保留；原 REVISION 不能被模型变成 PASSED。额外未知预计费用可以让原通过结果保守降为 REVISION。
- 工具结果再次进入 LogisticsResult 前会从原事实重新计算并逐项比较；即使有人篡改已类型化的 plan 数量、容量、价格、分配或来源，也不能绕过校验。
- 决策摘要和逐项理由标记为未经事实验证的模型意见，不能当审核、预订、购买或安全确认。

## 4. 本轮 trace 与 A 的后续协商

正式接口提案已补齐：[模型物流评估保存与审计接口提案](logistics_assessment_trace_proposal.md)（版本 1.0，DRAFT，待 A 复核/冻结）。请将该提案与本交付说明一并交给 A；接口尚未实现，不能据此调用建议方法或宣布应用已接线。

LogisticsOutcome 中的 trace 是调用方持有的本次结果，记录角色 LOGISTICS、模型身份、配置/输入/规则事实/方案 hash、Prompt/tool 身份、回合/HTTP尝试、耗时、回复 hash、usage 和验证结果。配置身份包含完整已登记 workflow context、规则/数据身份和模型公开配置，不包含 API key。

没有写入模型规划 trace 表或调用 append_model_plan，不能将评估角色的调用伪装为原行程生成记录。组件也不保存数据、不发送租借/购买请求、不改变原版本或当前方案指针。失败时只返回脱敏错误，不伪造成功 trace 或 usage。

正式提案已明确以下方案，应用接线前仍需 A/B 确认：

1. LogisticsResult、结构化 plan 和物流 trace 如何通过 A 的评估保存入口一起关联 run/version/assessment/attempt。
2. 幂等 key 继续使用 A 登记的 logistics key；保存回执丢失后如何从 checkpoint 复用已保存物流产物及 trace，不重跑模型补记录。
3. PLAN/REVISE/REASSESS 哪些评估步骤启用该角色；重评仍不调用规划模型，但若启用本组件，会产生新的物流模型调用，不能继续标为“完全没有模型调用”。
4. 配置指纹、meta 的物流阶段、页面的拟采购/未知费用/确认需求显示方式，以及缺凭据时的就绪行为。

提案包含具体 `save_model_logistics_assessment()` 签名、完整 plan/trace 字段、A 权威事实重算、assessment/checklist/audit/receipt 同事务、checkpoint 增量、回执丢失恢复、默认规则开关和逐项冻结清单。另明确用不含完整 context/fingerprint 的 identity seed 避免摘要自引用，以及 A/B 都须保留不可恢复审计完整性错误的语义。

这些仍不是 A 已实现/确认的新接口。文档补齐不提前改 Hybrid、Orchestrator、注册表、数据库或共享 schema，也不另建数据库。

## 5. 验证与剩余工作

本轮所有模型传输为 MockTransport/独立假密钥，没有读取 .env.llm.local、没有实际校园请求或浏览器验收。

本机检查：新增组件58项通过；装备组件/原费用规则/校园客户端组合133项通过；全量后端771 passed、0 skipped、0 failed（81.78秒），保留1条既有 Starlette TestClient 弃用警告。共享 schema 1.0、前端 TypeScript/Vite（54模块）、pip check、空白检查通过；数据静态校验68 passed、0 failed（不执行其中58条应用验收规格）。测试使用原锁定 Python3.12.14/Pydantic2.13.5/httpx0.28.1 环境，未新增依赖或更改锁文件。

组件覆盖：完整3轮工具闭环、实际租借/借用策略差异、数量/容量/Decimal 四舍五入、预算优先级、未知库存/价格、不可遗漏清单、禁止伪造确认/预算/来源/审批、延期可选但不能跳过必要装备、二次防篡改、错误/取消/超限/并发隔离、调用中配置/价格/证据选择漂移、加载后不读文件/oracle，以及现有 Hybrid 物流仍是规则的防误接线验证。

正式模型物流角色的 HTTP/页面、checkpoint/保存回执恢复和真实校园验收尚未完成；不能把 A19 规划/修订的实测证据计作新角色验收。Safety 模型角色、A15 高风险/过期/禁火完整场景及最终 Canvas 部署也仍待完成。

工具边界设计参考 OpenAI Docs 的 [函数调用指南](https://developers.openai.com/api/docs/guides/function-calling)：应用执行受控工具，已知事实/参数由代码提供，而不是让模型重填。该文档不证明学校代理支持全部 OpenAI 特性；当前仅使用已验证的内容 JSON 协议。

本轮未 commit/push，也未向 A 发消息。正式提案现已可随组件提交并交 A 复核；下一步按提案 L-01～L-09 冻结物流评估保存与 trace 契约，A 实现正式能力后再接 Hybrid/HTTP/页面并进行联合验收。
