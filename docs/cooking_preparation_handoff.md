# 自行烹饪准备清单与无模型预检查

日期：2026-10-22。基线：`fix/display-issues` / `7ff400c` 及当前尚未提交的出行系列、审核分离和连续更新实现。没有切分支或覆盖既有改动。

## 原因与本次修正

现有正式燃料规则依赖登记炉具数量 `stove_count > 0`；未登记炉具按现有规则得到 0，燃料项尚不触发。因此首次可能只出现烹饪安排问题，填好炉具后才出现燃料缺口。本次不修改封存规则，不把暂未触发的规则伪造成正式缺口。

增加独立的 **准备提示／非正式规则预检查**：

- 需求摘要、方案页面以及首次 `COOKING_ARRANGEMENT` 问题同时提示炉具和燃料，不等第二次规划才让用户知道配套项目。
- 从本次需求或方案进入资料页，会同时准备炉具、燃料的空白表单行；已有自定义名称、数量、单位和确认状态不覆盖。不自动填库存、不自动勾选拥有，不把准备项标为正式 blocker。
- 用户明确点击“预检查炉具与燃料（不调用模型）”，提交本页尚未保存的两类装备；不保存资料、不生成摘要、不创建方案、不运行任何 Agent。
- 预估复用已注册数据包的 trigger/quantity JSON 表达式及既有确定性求值器，不重新实现公式。当前规则中登记一个炉具对应两个燃料罐；显示为规则示例或草稿预估，不是已确认库存或已核实的实际使用安排。
- 数量未知、单位错误、尚未核实仍保留相应状态。未登记并不展示成“已确认无需燃料”。填 0 也不能证明自行烹饪安排落实。
- 修改表单后旧预检查失效；异步响应按来源及表单签名绑定，不能把旧结果显示为当前修改已经通过。
- 正式结果仍须保存资料、核对 revision、确认采用并明确启动正式检查；沿用同一出行后继流程。旧快照、评估、审计、最终记录及恢复流程不变。

范围仅为炉具与配套燃料准备，不冒充所有装备或安全规则的完整预评估。现有政策使用登记炉具总数，不是“这次实际会使用几台”；若以后改为实际共用／使用安排，需单独冻结结构化输入及规则版本。

## 报价问题

当前燃料没有已接入的 `GEAR_COSTS` 报价映射，数据包也缺少对应的燃料参考价。需要补缺时，正式费用保持未知，不能计为零或自动判为超预算。

准备清单提前说明这一资料限制；正式检查仍将关联费用挂在燃料缺口下，独立的报价资料问题仍归系统维护，不提供虚假的个人报价编辑入口。实际库存已备齐可据实登记；不能为通过检查虚填“已拥有”。

本次不添加报价、不修改封存数据、不修改预算或最终保存守卫。真正支持补购估算需由数据负责人发布带来源、单位、适用范围、校验和身份的后续报价版本，并接入对应映射后独立验收。

## 新接口与读取投影

`POST /api/v1/preparation/cooking`

```json
{
  "request_id": "owned-request-id",
  "equipment": [
    {"item_key":"camping_stove","label":"我的炉具","quantity":1,"unit":"item","capacity_persons":null,"confirmed":true},
    {"item_key":"fuel_canister","label":"配套燃料","quantity":null,"unit":"item","capacity_persons":null,"confirmed":false}
  ]
}
```

- `request_id` 与 `plan_id` 只能提供其一；来源必须属于当前 CAMPER。检查删除、系列当前状态或后继来源状态；不允许跨用户访问。
- 必须登录并提供既有 CSRF 请求头。POST 只是提交候选输入，本接口不产生业务写入。
- 方案来源读取固定 run 的确认需求与数据身份；当前无法提供同一规则上下文时拒绝，不使用别的版本代替。需求草稿使用来源当前需求及当前已注册规则，不是假称正式运行。
- 返回 `scope: PREPARATION_ONLY`、`official_assessment: false`、`policy_version: cooking-preparation-1`、`items`、`fuel_price_status`、可用时的 `required_fuel_quantity`、`fuel_gap`、`example`、`calculation_status`。
- 未采用自行烹饪返回 `applicable: false`；无法可靠读取单项规则则标明预估不可用，不猜测数量。无正式 `outcome`、`eligibility`、模型 trace、token 或配置摘要。
- 方案／需求／最终快照读取新增只读 `cooking_preparation`。最终快照投影根据当时确认需求与库存生成准备提示，不改保存正文和哈希。
- 需求页生成摘要后再 GET 角色裁剪投影；额外 GET 不调用模型。
- 无数据库迁移、无共享 Agent DTO/schema 或模型 Prompt 变化。原迁移 11 仍属于前轮系列实现，本轮未另占编号。

## 修改文件

- `backend/app/application/cooking_preparation.py`：非权威准备投影与规则预估。
- `backend/app/http_preparation.py`、`main.py`：显式、受权限保护的预检查读取入口。
- `backend/app/application/presentation.py`、`logistics_issues.py`：角色读取及首次烹饪问题带出准备清单。
- `frontend/src/cooking_preparation.tsx`：准备清单、未知/过期状态及费用来源提示。
- `frontend/src/profile.tsx`、`profile_guidance.ts`：同次填写两类装备、手动预检查及来源/表单绑定。
- `frontend/src/requests.tsx`、`plans.tsx`、`logistics_issues.tsx`：摘要、方案和首次问题入口。
- `backend/tests/test_cooking_preparation.py`、`frontend/tests/display_presentation.test.mjs`、`profile_guidance.test.mjs`：离线回归。

## 验证记录

针对性后端：69 项通过，涵盖准备提示、实际 TestClient HTTP、正式规则及角色读取投影。随后补充 agent 模式零调用回归，最终组合的全量结果另行记录，不与定向测试相加。

最终前端：95 项通过，含历史／最终／审核视图只读回归；TypeScript 检查、生产构建通过。共享 schema 检查和 `git diff --check` 通过。

后端最终组合从头全量：**1477 passed，1 warning**，810.25 秒（13 分 30 秒）；不是定向测试与旧全量结果相加。唯一警告是既有 Starlette TestClient/httpx 弃用提示。最终隔离目录为 `var/pytest-cooking-final-full-E09h1o`；所有测试数据库均在项目 `var/pytest-cooking-*` 隔离目录。

本轮未调用真实校园模型，未改个人环境文件、密钥、原用户数据库或封存数据，未重启服务，未 commit/push。组件 SSR 和离线 TestClient 验证不是浏览器实测或真实模型验收。

## 人工复测

1. 用演示执行模式，新建自行烹饪需求；在摘要里就应看到炉具和燃料两项准备提示，以及报价资料限制。
2. 未登记炉具时，首次正式检查仍遵循原规则，但页面应同时提示配套燃料，不能说“没有燃料需求”。
3. 点“一起核对炉具与燃料资料”，同页填写炉具和燃料。新增行数量为空且未勾选拥有；旧数据不覆盖。
4. 不保存资料，炉具填 1，燃料留未知，点击预检查：预估燃料需求 2，库存未核实，缺口未知；没有新运行或新方案。
5. 按真实库存填写并核实燃料 2，再预检查：草稿缺口可为 0，但不得显示正式通过或开放最终保存。
6. 改炉具数量：旧预检查立即过期；重新点击才更新。确认用户仍可保存未知值，不把正式最终化要求提前变成资料保存必填。
7. 选择“仅保存资料”：旧方案检查不变化；选择保存并核对、明确采用和正式检查后，才以新权威结果更新待办。
8. 历史／最终页面只显示当时资料，不出现活跃修改按钮；跨用户来源、已删除来源和无 CSRF 的预检查请求被拒绝。
