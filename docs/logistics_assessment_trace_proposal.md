# B → A：模型物流评估保存与审计接口正式提案

日期：2026-10-14（Australia/Sydney）。提案版本：1.0。状态：**DRAFT，待 A 复核并冻结，不是已实现接口**。

开发分支：`feature/llm-logistics-agent`；共同基线：`3a1206f`，已包含 A19 `0b57197` 及 A20。组件交付说明见 [logistics_agent_handoff.md](logistics_agent_handoff.md)。本提案以该基线的 `contracts/ports.py`、`storage/port.py`、`storage/workflows.py`、`application/model_audit.py`、`application/agent_runtime.py`、`workflow/orchestration.py` 和现有 B 物流组件为依据。

本次只补文档。以下方法、配置项、checkpoint 字段和审计存储结构均为建议，尚未接入应用。共享 DTO/schema 仍为 1.0；不改六项 `AgentPort` 的正式返回类型，不复用规划 trace 表，不由 B 新建数据库。A19 的规划/修订真实验收不能充当物流模型验收。

## 1. 目标与不做的事

将一次模型物流评估的三项成功产物作为整体交付：

- `assessment`：共享 `LogisticsResult`，供安全评估、路由和审核使用。
- `plan`：`ValidatedLogisticsPlan`，保留模型选择的逐项装备安排和确定性预算分配，不只保存说明文字。
- `trace`：本次 `LogisticsTrace`，单独归属 `LOGISTICS` 角色，能够关联当前 run、保存版本、评估和实际保存 attempt。

模型只提出未确认的补缺方式、费用优先级和意见。数量、容量、库存、报价来源、整数分/Decimal 费用、预算约束和 blocker 由代码验证。模型不得确认租借/购买、增加库存、改预算、修改保存行程或批准方案。

首轮只规范 `LOGISTICS`。`SAFETY` 继续确定性评估；未来其他角色需另行冻结契约，不能把本签名直接当通用模型评估入口。正式历史、HTTP 和页面均由 A 接入。

## 2. 提议的调用签名

### 2.1 A-owned RecoveryPort 扩展

以下是后端能力扩展，不修改共享 `PersistencePort.save_assessment()`：

```python
from typing import Mapping, Protocol

from app.contracts.dto import LogisticsResult, StoredAssessment, VersionContext


class ModelLogisticsPersistencePort(Protocol):
    async def save_model_logistics_assessment(
        self,
        context: VersionContext,
        result: LogisticsResult,
        plan: Mapping[str, object],
        trace: Mapping[str, object],
        write_key: str,
    ) -> StoredAssessment: ...
```

约定：

1. `context` 必须是 A 保存版本的 `VersionContext`，不能由模型或调用者新造版本。
2. `result` 必须是 `execution_mode=agent` 的 `LogisticsResult`。方法内部固定 `kind=LOGISTICS`；不接受调用者指定角色。
3. B 通过 `outcome.plan.model_dump(mode='json')` 和 `outcome.trace.model_dump(mode='json')` 传递完整对象。`Mapping` 只是签名类型，A 必须按第 3 节严格校验，不表示任意 JSON 都可保存。
4. `write_key` 固定使用 `scope.write_keys['logistics']`，不新增 key，不拼接 attempt、时间或模型回复摘要。
5. 返回现有 `StoredAssessment`，其中 `assessment_id`、`gear_checklist_id` 及保存时间等仍由 A 生成。安全步骤继续引用这个正式评估，不能引用 B 的未保存对象。
6. A 在持有当前 claimed attempt 的 RecoveryPort 上实现此方法；不可绕开 owner、scope、版本、租约或幂等守卫。方法未实现/契约未冻结时不能调用。
7. 模型必审计配置下，普通 `save_assessment(..., LOGISTICS, ...)` 必须拒绝绕过审计的保存。规则物流和现有安全保存仍走原入口。

### 2.2 B 的调用局部产物接口

现有独立组件已经提供 `LogisticsAgent.assess_with_trace(input) -> LogisticsOutcome`。接线阶段建议 Hybrid 增加以下内部扩展，名称待 A 确认：

```python
async def assess_logistics_with_trace(
    self, input: LogisticsInput,
) -> LogisticsOutcome: ...
```

共享 `AgentPort.assess_gear_and_logistics(input) -> LogisticsResult` 保留；正式编排在模型物流启用时必须走带 trace 的扩展并保存三项产物，不能通过只返回 `LogisticsResult` 丢弃审计。无全局 `last_trace`，并发请求不能串用记录。

## 3. 保存载荷与严格校验

### 3.1 结构化 plan：所有顶层字段均必需

字段直接对应现有 `backend/app/llm/logistics_tools.py`，包括显式 `null`：

| 字段 | 类型与含义 |
| --- | --- |
| `gear_actions` | 1～64 个 `SupplyPlan`，覆盖全部规则装备且唯一 |
| `budget_allocations` | 1～128 个 `BudgetAllocation`，按模型费用优先级排列，覆盖全部工具费用行且唯一 |
| `projected_cost_breakdown` | 全部预计 `CostLine`，包含必要价值 allowance 和未知费用行，不可删行 |
| `projected_total_cents` | 非负整数分或 `null`；只要仍有未知费用就为 `null` |
| `known_subtotal_cents` | 非负整数分，仅已知费用小计，不是假定总费用 |
| `budget_difference_cents` | 有符号整数分或 `null`，完全由确认预算及预计总额计算 |
| `budget_feasible` | 严格布尔或 `null`，未知费用时不能宣称可行 |
| `unallocated_known_budget_cents` | 非负整数分，确定性分配后的剩余确认预算 |
| `requires_user_confirmation` | 严格布尔，不是用户已经确认 |
| `decision_summary_unverified` | 1～1200 字符、非空白的模型意见，不是已核验事实 |
| `source_refs` | 共享 `SourceRef` 列表，必须与确定性重算结果一致 |

`SupplyPlan` 的完整字段：`fact: GearItem`、`method`、`procurement_quantity: Decimal|null`、`procurement_unit: str`、`estimated_cost_cents: int|null`、`cost_line_id: str|null`、`price_source: SourceRef|null`、`confirmation_required: bool`、`reason_unverified: str`（1～240 字符且非空白）。

`method` 只接受 `KEEP_CONFIRMED`、`PROPOSE_RENTAL`、`PROPOSE_PURCHASE`、`PROPOSE_BORROW`、`ASK_USER`、`DEFER_OPTIONAL`，而且必须属于该物品的工具 `allowed_methods`。`fact` 必须逐项等于原规则事实，不能因为出现在 plan 中就当成模型获准填写的事实。

`BudgetAllocation` 的完整字段：`line_id: str`、`required_cents: int|null`、`allocated_cents: int|null`、`unfunded_cents: int|null`。三个金额均为非负整数分或 `null`。未知费用不能转换为 0，优先级也不能使未覆盖金额消失。

严格规则：所有层级禁止额外字段；布尔不能冒充整数；整数分不接收浮点或数值字符串；数量采用共享 Decimal 表示，JSON 中是有限、非负的十进制字符串，不接收浮点、NaN 或 Infinity。`budget_difference_cents` 允许负数，其余金额不允许。共享嵌套 DTO 继续使用现有 1.0 校验，最终以第 5 节的全量重算比较为准。

### 3.2 trace：所有字段均必需

字段直接对应 `backend/app/llm/logistics_agent.py` 的 `LogisticsTrace`：

| 字段 | 保存前必须满足 |
| --- | --- |
| `role` | 固定字符串 `LOGISTICS` |
| `requested_model` | 等于登记的公开模型配置；当前为 `campus-qwen` |
| `served_models` | 成功回复报告的去重模型名称列表；未报告可为空，不伪造 requested model 作为 served model |
| `configuration_fingerprint` | 等于第 4 节按最终 workflow context 算出的身份摘要 |
| `input_sha256` | 等于 A 重建的 `LogisticsInput.model_dump_json()` 的 UTF-8 SHA-256 |
| `rule_facts_sha256` | 等于 A 重算的基线 `LogisticsResult.model_dump_json()` 的 UTF-8 SHA-256 |
| `proposal_sha256` | 等于从 plan 重建的模型 proposal 的 canonical JSON 摘要 |
| `prompt_sha256` | 等于登记身份 seed 的 Prompt+动作 schema 摘要 |
| `tool_version` | 等于登记身份 seed；当前为 `logistics-read-only-tools-1` |
| `turns` | 严格整数，3 ≤ turns ≤ 登记 max_turns（当前配置上限为 6） |
| `http_attempts` | 严格整数，turns ≤ attempts ≤ turns × 登记 max_attempts（当前单轮上限为 3） |
| `elapsed_ms` | 非负严格整数，表示本次组件调用的耗时，不是保存耗时 |
| `tool_calls` | 长度为 turns−1；首项为 `read_logistics_facts`，至少一次 `evaluate_logistics_plan`，只允许这两个工具名 |
| `response_sha256` | 长度等于 turns，每次成功内容回复的 SHA-256；不保存回复正文 |
| `usage` | 只允许 `prompt_tokens`、`completion_tokens`、`total_tokens`，值为非负严格整数；未知字段省略，不补 0 |
| `validation_passed` | 必须是严格布尔 `true`；仍须 A 自行验证，不能仅相信该标志 |

全部摘要采用 64 位小写十六进制。`served_models` 条数不超过 turns，每项非空且最多 200 字符；工具列表允许循环内重复读取/计算，但受登记回合数约束。额外字段、重复 JSON key、非有限数字和错误类型均拒绝。

`http_attempts`/`usage` 只覆盖这次成功组件调用收到的回复及其客户端报告，不包含已失败、无可用回复的先前调用。不得将其解释为校园服务的完整账单或“模型调用 exactly-once”证明。

建议 A 对保存调用的编码载荷设置 512 KiB 上限，并在冻结前用现有正常/边界夹具确认足够；不默默截断、删除清单或缩短模型意见以通过上限。此上限目前未实现，须 A 在复核时确认或给出替代值。

禁止保存 API key、Authorization、原始 Prompt/messages、原始模型回复、私人推理或底层异常正文。结构化理由保留为未核验建议，只能按授权范围读取；哈希和 trace 不能独立证明服务真的执行过模型，真实调用证据仍需联合验收。

### 3.3 摘要编码约定

`canonical(value)` 与现有 coordinator helper 一致：

```python
json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
```

`sha256(text)` 指对字符串的 UTF-8 字节求 SHA-256。**输入和规则事实摘要沿用组件的 `model_dump_json()`，不是 canonical JSON。** proposal/configuration/保存载荷摘要才使用 canonical JSON。不得混用序列化方法、重排列表、删掉 `null` 或重新格式化 Decimal 来掩盖差异。

## 4. 身份登记：避免配置指纹递归包含自身

现有 `LogisticsAgent.identity` 的摘要输入包含完整 `workflow_context`。因此不能先把完整 `configuration_fingerprint` 放进 `DatasetContext.selection_config`，再要求同一个组件基于这个 context 重算该 fingerprint；这会形成自引用。

建议 A 为启用模型物流的 context 登记以下字符串项，保留所有已有 A/B 的数据摘要、fixture 摘要、选择配置和规划身份：

```text
a_logistics_mode = model
a_logistics_audit_required = 1
a_logistics_audit_contract = 1.0
a_logistics_identity_seed = <canonical JSON 字符串>
```

`identity_seed` 是可信注册流程取得的 `LogisticsAgent.identity`，去掉 **`workflow_context` 和 `configuration_fingerprint`** 后的对象，只含：

```text
agent_version, tool_version, validation_version, kernel_version,
dataset_rules_version, prompt_sha256, model_client
```

当前组件分别使用 `campus-logistics-agent-1`、`logistics-read-only-tools-1`、`logistics-proposal-validation-1`；其余版本从真实规则/数据绑定获得，不能硬编码为未知数据包版本。`model_client` 使用客户端的公开 identity（client version、endpoint、requested model、timeout/token/attempt/turn 限制），绝不包含密钥。

建议注册顺序：

1. A 解析真实数据、已有 Hybrid 规划绑定和工作流选择，取得可信组件 identity seed。可使用临时完整配置构建组件读取 `.identity`，再去掉上述两项；不调用模型，不重复手写 Prompt hash 算法。
2. 将 seed 和上述模式/契约标记加入最终 workflow context；若已有同名键但值冲突，明确拒绝。
3. 在原有 `rules_version` 后附加语义标记，例如 `/a-model-logistics-audit-v1`，不删除原规则身份，也不附加物流完整 fingerprint。
4. 以最终完整 context 构建正式 LogisticsAgent。A 的预期摘要是：

   ```python
   expected = sha256(canonical({
       **registered_seed,
       'workflow_context': final_context.model_dump(mode='json'),
   }))
   ```

5. 正式组件 `.identity['configuration_fingerprint']` 必须等于 expected。完整摘要保存在审计元数据中，而不是再塞回被摘要的 context。

seed 包含全部公开配置，因此身份不仅是一个“模型开启”标签。当前 run 的 claim、heartbeat、保存、重试和完成仍按 A 的 context provider 检查实际登记上下文是否变化；数据/规则/模型公开配置变化需要新 run，不能拿旧 key 保存新内容。

历史审计使用 **该 run 保存的 seed/context 和事实快照** 验证，不依赖今天的模型设置或重新加载当前数据，更不能因为当前 API key 不存在就无法查看已保存记录。换密钥不改变非秘密模型身份，但缺密钥会阻止新调用。

## 5. A 保存前的权威校验

下列校验使用 A 掌握的授权及保存事实，不接受 B 提供额外“可信基线”参数：

1. 验证绑定 owner、run 的完整 scope、当前 plan/version、执行模式、claim attempt 和有效租约。`context` 必须精确匹配 A 保存的 `VersionContext` 和输入 fingerprint。模型审计标记及组件身份须与登记一致。
2. 从 A 的保存 `ConfirmedContext`、`StoredVersion`、`VersionContext` 和 `DemoContext` 重建 `LogisticsInput`。不能用调用方未保存的要求/Profile/行程来证明结果。
3. 用该 run 的实际数据绑定、规则版本、登记 `safety_case_ids`，调用现有规则 `logistics.assess(..., expected_mode=AGENT, ...)` 得到基线；比较 `input_sha256`、`rule_facts_sha256`。
4. 从传入 plan 的 `gear_actions` 重建 proposal 的 `item_key=fact.item_key`、`method`、`reason=reason_unverified`；从 `budget_allocations` 的顺序重建 `cost_priority`；从 `decision_summary_unverified` 重建 `decision_summary`。
5. 构造 `LogisticsToolset(server_input, server_baseline)`，调用现有 `evaluate_logistics_plan(proposal)` 和 `result(recomputed_plan)`。传入 plan/result 必须分别与确定性重算的完整对象一致，包括所有 Decimal、金额、来源、缺口、确认需求、原 blocker 和澄清。
6. 校验 proposal hash、登记 seed、完整配置摘要及第 3 节 trace 结构。`validation_passed=true` 不能替代上述检查。拒绝伪造数量/来源、漏掉必要费用、确认借用、把未知费用置 0 或把规则 REVISION 提升为 PASSED。

A 可以复用 B 的纯计算 helper，或封装 A-owned 验证适配层；其职责是以 **server facts** 调用，而不是信任调用方产物。校验与事务提交必须使用同一已验证事实快照，提交时再次检查 active/scope/lease；事务内不得发模型请求、读取网络或进行长时间等待。

## 6. 同事务保存与关联规则

### 6.1 原子保存边界

沿用 A 的 SQLite 事务和现有 logistics 写入操作，一次提交包含：

1. `LOGISTICS` assessment。
2. 对应 gear checklist。
3. 独立物流模型审计，完整保存结构化 plan 和 trace。
4. 对应 `scope.write_keys['logistics']` 的 write receipt。

任意插入/校验失败必须全部回滚，不能出现“评估已保存但审计随后补写”。不得调用 `append_model_plan()` 保存本角色，更不能更新/覆盖原规划 trace。

### 6.2 审计 envelope 的建议字段

表名、DDL 和迁移由 A 决定；以下是需要对外保持的逻辑内容，不要求采用某个 SQL 布局：

```text
audit_contract_version: "1.0"
audit_id: A 生成
owner_id, plan_id, run_id, plan_version_id: A 由保存关联取得
assessment_id, gear_checklist_id: A 本次保存或原回执关联
kind: "LOGISTICS"
attempt_id: 实际成功保存的 claimed attempt，由 A 取得
input_fingerprint: 保存版本的 VersionContext.input_fingerprint
configuration_fingerprint: 第 4 节计算的完整身份摘要
plan: 完整 ValidatedLogisticsPlan JSON
trace: 完整 LogisticsTrace JSON
input_json: A 重建输入的原始 model_dump_json() 字符串
rule_facts_json: A 重算基线的原始 model_dump_json() 字符串
payload_sha256: 第 7 节定义的幂等载荷摘要
created_at: A 生成的保存时间
```

`input_json`/`rule_facts_json` 是 **A 自行生成** 的已验证事实快照，用于后续查明依据及按原字节校验 trace 摘要；不是原始 Prompt/模型回复。敏感 Profile/需求只按现有 owner/审核授权读取，不作为所有页面/用户可见的公开 trace。A 可内部存储这两项，checkpoint/普通 HTTP 不必重复输出。

建议约束：每个模型物流 `assessment_id` 恰有一条审计；`(run_id, plan_version_id, kind)` 唯一；关联 owner/version/run/gear 必须一致；成功记录不可变，不以新 attempt 覆盖旧记录。审计保存值及回执摘要应能相互核对；这些检查用于发现不一致，不声称防御具有数据库修改权限的攻击者。

历史读取依据保存的原始 scope/seed/DTO 版本及快照检查关联与摘要，不强行用后来改变的模型配置或新规则重算旧决策。若需要历史重算，只能使用明确支持原规则/工具身份的验证器；不得悄悄改用当前工具计算并覆盖旧结果。

## 7. 幂等、checkpoint 和恢复

### 7.1 写入幂等

建议 write receipt 的输入摘要为以下 canonical JSON 的 SHA-256：

```python
{
    'context': context.model_dump(mode='json'),
    'kind': 'LOGISTICS',
    'result': result.model_dump(mode='json'),
    'plan': validated_plan.model_dump(mode='json'),
    'trace': validated_trace.model_dump(mode='json'),
}
```

此处 validated 表示已按第 3、5 节校验，不能通过宽松 coercion 接受错误类型。数据库生成的 ID、保存时间和 attempt 不进入该摘要；模型 trace 自身含耗时/回复摘要，因此重跑模型产生的另一条 trace 不能用原 key 静默覆盖。

- 同 run、同 key、同完整载荷：验证现有 assessment/checklist/audit/receipt 关联完整后，返回原 `StoredAssessment`，保留原 audit 和实际保存 attempt。
- 同 key 不同 context/result/plan/trace：`IDEMPOTENCY_CONFLICT`，不改旧记录。
- 新 attempt 不能改变 key；租约守卫仍必须通过。旧 worker 即使载荷正确也无权写入。
- **回执命中也必须验证伴随审计**。不能仅沿用通用 `write()` 中“读到 receipt 就返回”的分支而绕过审计检查。

### 7.2 checkpoint 增量字段

建议 `load_checkpoint()` 保留所有现有字段，新增：

```text
model_assessment_audits:
  LOGISTICS:
    audit_contract_version, audit_id, kind,
    plan_id, run_id, plan_version_id, assessment_id, gear_checklist_id,
    attempt_id, input_fingerprint, configuration_fingerprint,
    payload_sha256, created_at,
    plan, trace
```

这是后端扩展映射，不改共享 `StoredAssessment`。规则物流时为空映射，不伪造模型 trace。原 `model_planning_trace`、version、assessments、route 字段和恢复语义保持。

loader 必须先验证 envelope 与本次保存 `StoredAssessment`、版本、scope、保存输入 fingerprint、gear 和回执摘要一致，再输出。归档事实快照和 owner 可在 A 内部核验，不必放进 B 的 checkpoint。审计仍标识原保存 attempt，不能改成当前 retry attempt。

### 7.3 恢复决策表

| 已保存状态 | 恢复动作 |
| --- | --- |
| 物流整体尚未提交 | 可以重新执行物流模型；没有承诺外部模型调用 exactly-once |
| assessment+checklist+audit+receipt 完整，客户端没收到回执 | checkpoint 复用原产物，不重跑模型或补造 trace |
| 物流完整，安全尚缺 | 跳过物流模型/保存，安全使用原正式物流 assessment 继续 |
| 两项评估完整，route 尚缺 | 复用原两项评估继续路由 |
| route 已保存且所需审计完整 | 不执行任何模型/评估，仅走原完成恢复 |
| 模型必审计的物流 assessment 存在，但 audit 缺失/损坏/关联错误 | 完整性错误，阻止路由/完成/审批，联系开发负责人；禁止重跑模型补 trace |
| 原物流 key 下收到不同模型内容 | 幂等冲突；不得生成不同结果后借旧 key 保存 |
| 配置/数据/版本已漂移，或旧 attempt 失效 | 拒绝继续旧 run，按现有 stale/lease 规则处理 |

REASSESS 是新 run 的新物流评估：若启用模型物流，就基于保存行程及本次确认事实调用该角色，保存 **本次** audit，不复用上一 run 的物流 trace。原行程生成 trace 仍按 A19 的 origin-version 关联复用，不复制成“本次规划调用”。

## 8. 模式开关、操作范围及页面约定

### 8.1 建议能力开关

建议新增 A-owned `CAMPMATE_LOGISTICS_EXECUTION=rules|model`，默认 `rules`，名称由 A 确认。不因为模块存在或全局处于 `agent` 就自动启用。

- `rules`：现有物流算法及保存路径保持，不产生物流模型记录。
- `model`：仅可结合真实 `agent` 运行；必须登记第 4 节身份、具备第 2 节保存能力和第 3～7 节审计校验/恢复能力。不能与 stub/deterministic 组合后改标签冒充模型。
- 显式请求 model 但条件不满足：明确就绪/配置失败，不退回 rules，不能把开关临时改成 rules 后继续同一 run。
- 无密钥、模型客户端配置不合法、`max_turns<3`、缺扩展方法/迁移或身份不匹配：不允许开始模型物流运行。readiness 校验不需要付费连通性探测。

建议首轮冻结后同时支持 `PLAN`、`REVISE`、`REASSESS` 中有保存版本的物流评估；三者共用同一个调用/保存契约。`NO_MATCH` 没有行程版本，不调用物流角色，也不要求凭空保存物流审计。若 A 希望分阶段只开放 PLAN，需要明确缩小能力并在 HTTP/meta/测试中一致体现，不能静默降级其他操作。

### 8.2 展示和下游必查位置

1. A 的 meta 阶段信息中，只有真实启用并通过就绪检查时才能标注 `planning_stages.logistics=model`；解释/营地筛选/安全仍按实际实现标注。
2. 页面将“原行程模型生成记录”和“本次物流模型评估记录”分开，分别展示真实关联 run/version/assessment、模型及 usage，不合并或重复计数。
3. REASSESS 文案应是“不重新调用规划模型；本次物流评估调用模型”（若开启），不能再声称整个重评没有模型调用。
4. 展示逐项拟租借/拟购买/拟借用/询问/延期、计算数量、预计费用和资金分配/缺口；明确未确认建议、未知费用以及模型意见非已核验事实。
5. 缺少必需物流审计时，route、成功提交校验、Camper 审核/确认、Founder 的授权审核和 finalisation/snapshot 均不能放行。读接口也必须发现关联损坏，不能仅在写入时校验。
6. 最终快照保存当时的规划 trace 与物流审计，角色独立、引用准确。历史规则评估保持可读且不补模型标签；历史读取不重新调用模型，也不因当前模型未就绪而失败。

## 9. 错误语义及当前集成风险

沿用共享 `ContractError` 和现有错误码，不添加模型私有的 HTTP 错误结构：

| 情况 | 建议错误和处理 |
| --- | --- |
| 非法模型动作/载荷/角色、费用或事实重算不一致 | `CONTRACT_INVALID`，不可自动重试，不保存成功产物 |
| 实际数据/公开模型配置/版本/保存输入与 scope 漂移 | `STALE_CONTEXT`，不继续原 run |
| 同 key 的不同成功载荷 | `IDEMPOTENCY_CONFLICT`，保留原记录 |
| 临时数据库故障且整体事务回滚 | `PERSISTENCE_FAILURE`，recoverable=true，按原恢复入口重试 |
| 必需审计缺失、损坏或和保存评估不一致 | `PERSISTENCE_FAILURE`，recoverable=false，`CONTACT_OPERATOR`，禁止生成补记录 |
| 超时、429/503 等模型传输故障 | 按现有客户端 `AGENT_FAILURE`/重试上限语义，不规则回退 |
| 缺少调用凭据/未冻结能力 | 就绪失败，联系配置负责人；不声称已执行模型 |
| 越权读取/写入 | 沿用 A 的授权/`NOT_FOUND` 等既有语义，不泄露他人的对象存在性 |

**当前必须在接线时修正的风险：** `workflow/orchestration.py` 会把不可恢复的 `PERSISTENCE_FAILURE` 改成 RETRY；`application/dispatcher.py` 也会统一将该码设为可恢复。新增完整性校验不能直接依赖这两处目前的行为。

建议共同冻结为：端口明确区分临时事务失败与不可恢复完整性失败；B Orchestrator 和 A Dispatcher 尊重端口的 `recoverable/allowed_actions`，不按码统一提升。相应调整需覆盖既有临时失败恢复测试，保证旧流程可重试，同时审计损坏不会被重新运行模型掩盖。本提案不提前修改上述代码。

## 10. A/B 分工与验收条件

| 工作 | 负责人 |
| --- | --- |
| 物流模型动作、工具、确定性 plan/result、局部 trace | B（独立组件已完成） |
| 提供纯校验 helper/严格 schema 配合、Hybrid 内部扩展、模型/规则编排分支 | B，在接口冻结后继续 |
| RecoveryPort 扩展、审计存储/迁移、幂等回执、checkpoint 读取 | A |
| 工厂注册、身份 seed 登记、能力开关、readiness/meta | A；B 配合组件 identity 验证 |
| 审核/完成/finalisation 的审计必查，读接口、最终快照和页面 | A |
| 不可恢复完整性错误不被改成 RETRY | B 修改编排，A 修改 Dispatcher/端口，联合回归 |
| HTTP/重启/真实校园/浏览器验收 | A/B 联合，A 汇总正式集成证据 |

最低联合验收清单：

- 原规则模式、stub/deterministic 默认、共享 schema 1.0 和原规划审计行为不变；没有默认启用/假模型标签。
- PLAN/REVISE/REASSESS 各验证实际角色调用次数；NO_MATCH 不触发物流；REASSESS 保留原规划记录并产生本次物流审计。
- 数量/容量/来源/价格/预算/确认字段篡改、未知费用置 0、漏行、伪造 PASSED、必要装备延期全部拒绝；可选延期不删除原缺口。
- 四个保存产物逐点故障注入均全部回滚；成功提交但回执响应丢失，重启/新 attempt 恢复不重复调用模型。
- 相同 key/载荷返回原记录；不同 plan、trace 或 result 幂等冲突；旧 attempt/过期租约和跨 owner 不能写入。
- assessment 已存在而 audit 缺失/损坏时，checkpoint、回执命中、route、成功提交、审核、最终快照均拒绝；不可被 RETRY 提升或模型补生成绕过。
- 物流恢复后的安全 dependency 指向原正式 assessment；route 保存后的恢复不重复任何模型步骤。
- 身份 seed 不包含自身摘要或完整 context；最终组件 fingerprint 与 A 计算一致；调用中配置漂移拒绝；历史在配置/凭据变化后仍按旧 scope 可读。
- 严格 schema、载荷边界、重复 key、布尔冒充整数、浮点 Decimal、未知金额和 trace 长度/hash/角色错误均覆盖。
- 页面准确区分原规划和当前物流，展示具体装备安排/资金缺口/未知/未确认；授权隔离、重启后历史和最终快照可查。
- 真实校园请求及 HTTP/browser 正常闭环单独执行、脱敏记录，不以 MockTransport 或 A19 的旧报告替代。

目前已有物流组件 58 项、组件/原规则/客户端组合 133 项和全量后端 771 项通过，详见组件交付说明；这些是前一轮组件实现的结果，不表示本提案接口已实现或上述联合验收已完成。本次文档补齐不新增应用执行证据。

## 11. 请 A 明确回复的冻结项

以下 L-01～L-09 仅是本提案的协商编号，不是 Jira 工单或新的 A/B 阶段编号。请逐项回复“同意”或替代签名/字段/语义：

| 编号 | 需要确认的决定 |
| --- | --- |
| L-01 | 第 2 节方法名/签名、返回 StoredAssessment、固定 LOGISTICS、沿用 logistics key；Hybrid 内部扩展名称 |
| L-02 | 第 3 节完整 plan/trace schema、严格类型与摘要序列化规则、512 KiB 建议上限 |
| L-03 | 第 4 节 identity seed 登记方式及字段名，完整 fingerprint 不写入被摘要 context |
| L-04 | 第 5～6 节 server facts 重算、四产物同事务、A 生成事实快照和审计关联/唯一性 |
| L-05 | 第 7 节 checkpoint 字段、回执命中审计校验、恢复不重跑模型、损坏禁止补写 |
| L-06 | 第 8 节默认 rules/显式 model 开关、只限 agent、首轮同时支持三种操作或明确替代范围 |
| L-07 | readiness/meta、历史/页面分角色显示、审核/完成/快照所有读取入口的审计必查 |
| L-08 | 第 9 节错误语义，A/B 分别修正统一提升 PERSISTENCE_FAILURE 的行为 |
| L-09 | A 的实现分支/共同基线、存储迁移兼容策略及联合验收安排 |

建议推进顺序：A 复核并冻结上述决定 → A 实现正式持久化/读取能力，B 按同一基线接 Hybrid/编排 → 离线故障恢复及全量回归 → 真实校园 HTTP/browser 联合验收 → PR 合入 main。

本提案已经可以随组件一起 push 交 A 复核；但在 A 确认并提供正式能力前，不能声称应用已启用模型物流，也不能调用文中的建议保存方法。B 可以准备对应离线测试及接线方案，不另建数据库或提前伪造 trace 保存。
