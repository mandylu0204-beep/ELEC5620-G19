# B → A：LogisticsAgent 组件与 A24 接线交付

日期：2026-10-14（Australia/Sydney）。分支 `feature/llm-logistics-agent`。组件提交为 `e0b25eb`，本次接线基线已更新为 A24 main `319f541`，包含 A19～A24 的完整应用能力。

独立组件实现模型参与装备规划及确定性数量/容量/费用校验。A24 已提供正式审计/存储/读取和工厂；本次 B 接入 Hybrid、Orchestrator，并保留不可恢复错误语义。默认物流仍为 rules，显式 model 配置才使用第二模型角色。不修改私人配置、封存数据或共享 schema，也不另建数据库。最新接线与验收范围见 [运行时接线交付](logistics_runtime_integration.md)；离线接线通过不等于真实校园已验收。

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

输入必须使用 A 保存、授权并绑定版本的 LogisticsInput。组件检查 DTO、模式、固定日期/最多30晚、数据版本和原规则约束，但不会自行查询数据库证明授权或声明自己创建了保存版本。正式接线复用 A24 的 owner/scope/lease/输入 fingerprint 守卫和权威事实重算。

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

## 4. A24 已冻结接口与正式接线

初版 [接口提案](logistics_assessment_trace_proposal.md) 已由 A 按 [冻结回复](a24_logistics_contract_reply.md) 确认。当前实际可调用能力以 [A24 交接](a24_logistics_audit_handoff.md) 为准，不再等待初版接口复核。

LogisticsOutcome 中的 trace 是调用方持有的本次结果，记录角色 LOGISTICS、模型身份、配置/输入/规则事实/方案 hash、Prompt/tool 身份、回合/HTTP尝试、耗时、回复 hash、usage 和验证结果。配置身份包含完整已登记 workflow context、规则/数据身份和模型公开配置，不包含 API key。

物流组件没有写入模型规划 trace 表或调用 append_model_plan，不能将评估角色的调用伪装为原行程生成记录。独立组件本身不保存数据、不发送租借/购买请求、不改变原版本或当前方案指针；正式编排交给 A 保存物流 audit。失败时只返回脱敏错误，不伪造成功 trace 或 usage。

本次 B 已按冻结约定接入：

1. Hybrid 保留 A 传入的 logistics_agent，声明完整审计能力 1.0，提供 assess_logistics_with_trace；检查同数据对象、最终 context、seed 和配置摘要，模型等待后再检身份。
2. Orchestrator 将 LogisticsResult、完整 plan/trace 交给 A 的 save_model_logistics_assessment，使用原 logistics key，安全步骤依赖返回的正式 StoredAssessment。
3. checkpoint 检查独立 LOGISTICS envelope 的版本/评估/gear/fingerprint/载荷摘要及业务产物；已保存步骤整体复用，不重跑模型补 trace。
4. PLAN/REVISE/REASSESS 都支持显式模型物流；REASSESS 不调用规划模型，但本次物流生成新的审计。NO_MATCH 跳过两角色模型和物流保存。
5. 默认规则路径和共享接口保持；B 提供可复用严格纯校验 helper，并移除不可恢复 PERSISTENCE_FAILURE 的统一 RETRY 提升。

沿用 A24 已实现的原子事务、幂等/读取/最终化守卫、迁移7、工厂和页面，本次未另写一套存储。A 的正式保存入口独立验证事实，B 的纯 helper 不替代数据库授权或回执/归档审计检查。

## 5. 验证与剩余工作

本轮所有模型传输为 MockTransport/独立假密钥，没有读取 .env.llm.local、没有实际校园请求或浏览器验收。

组件提交 `e0b25eb` 的历史检查：新增组件58项通过；装备组件/原费用规则/校园客户端组合133项通过；旧基线全量771 passed、0 skipped、0 failed（81.78秒）。这些数字不是 A24 接线后的全量结果。最新全量859项通过及其他结果单列在 [运行时接线交付](logistics_runtime_integration.md)。测试继续使用锁定 Python3.12.14/Pydantic2.13.5/httpx0.28.1 环境，未新增依赖或更改锁文件。

组件覆盖：完整3轮工具闭环、实际租借/借用策略差异、数量/容量/Decimal 四舍五入、预算优先级、未知库存/价格、不可遗漏清单、禁止伪造确认/预算/来源/审批、延期可选但不能跳过必要装备、二次防篡改、错误/取消/超限/并发隔离、调用中配置/价格/证据选择漂移、加载后不读文件/oracle，以及现有 Hybrid 物流仍是规则的防误接线验证。

模型物流的离线 HTTP、checkpoint/保存回执恢复由本次接线验证；页面沿用 A24 的已交付能力，真实双模型校园 HTTP/browser 联合验收尚未执行。不能把 A19 实测或 A24 独立 MockTransport 页面报告计作本次真实验收。Safety 模型角色及最终 Canvas 部署仍待完成。

工具边界设计参考 OpenAI Docs 的 [函数调用指南](https://developers.openai.com/api/docs/guides/function-calling)：应用执行受控工具，已知事实/参数由代码提供，而不是让模型重填。该文档不证明学校代理支持全部 OpenAI 特性；当前仅使用已验证的内容 JSON 协议。

组件与初版提案已于 `e0b25eb` 提交并推送、纳入 A24。当前接线改动尚未 commit/push，也未向 A 发消息。下一步提交接线变更供 A 集成复核，并按运行时交付中的清单联合验收真实校园流程。
