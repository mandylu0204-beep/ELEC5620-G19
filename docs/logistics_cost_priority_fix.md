# 费用优先级完整性：针对性修复

日期：2026-10-27。基线 `main` / `043311c`，保留既有脱敏诊断及首页文字方向改动。未自动切分支或提交。

## 已确认的问题及不能下定论的部分

第二次失败 run `a2e6b6d597d14467b96c1a4c9108f856` 在费用覆盖校验处停止，不是 JSON 解析处。离线重建确认：基础费用 12 条，工具补充 4 条未报价占位，模型实际需要排序 16 个费用行 ID。

核对旧优化提交 `2d8f2cf`：首次事实读取没有删费用行，反馈压缩保留全部 budget_allocations 和 projected_cost_breakdown；最近安全角色压缩也没有改物流提示。因此没有证据表明“压缩时漏传了 4 条费用”。

但原提示先称“必要费用”，又要求“全部费用”，没有独立列出权威 ID 清单，也不够突出 line_id 与 item_key 的区别。离线模拟已确认：只返回 12 个普通行 ID，或用物品 ID 代替行 ID，均会触发同一条报错。

历史响应没有保存，仍不能确认真实模型漏了哪项、重复了哪项或使用了哪个错误 ID。本次修复针对明确的协议表达和诊断薄弱点，不把离线模拟写成真实模型根因证明。

## 修复

1. `LogisticsToolset.cost_priority_requirements()` 从同一个 `_costs` 提供新建的只读视图：
   - `required_cost_line_ids`：完整行 ID 列表，包括 `line-*` 和 `unpriced-*`。
   - `required_cost_line_count`：完整数量，绝不使用仅基础费用条数代替。
2. 首次事实读取和压缩评估反馈都附带这两个字段。原费用事实、每项分配、来源原始数据和完整持久化 plan 保留，不恢复重复大段事实传输。
3. Prompt 明确：cost_priority 必须是该列表的无重复排列；复制 costs[].line_id，不用 item_key；零费用、未知价格及选择 DEFER_OPTIONAL 的行也须保留。推迟采购由工具计算金额，不由模型删除行来表达。这两个 host 字段不能作为额外字段回填模型 proposal。
4. 完整性条件不放宽：缺失、重复、发明 ID 均拒绝；不自动补齐、去重、过滤或改写模型结果后放行。
5. 新增 `COST_PRIORITY_COVERAGE` 脱敏诊断：要求／返回数量、缺失的主机已知 ID、重复的已知 ID、未知 ID 所在位置及总数。未知模型值不回显，长列表截断但总数保留。
6. 解析失败和工具校验失败都附带角色、轮次及调用计数，写入既有 error context。普通用户的 run、plan、progress 读取仍裁剪这些字段；不新增数据库或诊断表。

## 身份、历史与业务边界

- JSON action/proposal schema、字段长度、计算算法、工具调用顺序、整数分／Decimal、安全规则、审核和最终保存守卫不变。
- host 工具输出增加的是清单元信息；持久化 plan/result/trace DTO 格式及工具确定性计算协议不变，保持现有工具与校验版本，历史纯重算语义不变。
- **Prompt 内容发生变化**，既有 `prompt_sha256` 与 `configuration_fingerprint` 机制会登记新身份；不覆盖历史身份、原 scope、输入哈希或已保存 trace。
- 旧成功审计和最终快照按其保存的 seed 读取。不能通过把旧 FAILED run 的 scope 改为新身份来恢复；新生成应重新核对确认，启动绑定新身份的运行。
- 本次不增加 token、超时、重试或模型调用次数；不把规则结果标成模型成功。
- 受控历史复现工具仍要求当前 Prompt 与原 Prompt 相符。修复后，它应拒绝把旧 run 冒充同协议复现；没有加绕过开关。

## 修改文件

- `backend/app/llm/logistics_agent.py`：提示、反馈权威清单、工具失败轮次诊断。
- `backend/app/llm/logistics_tools.py`：完整清单生成和严格覆盖校验诊断。
- `backend/app/llm/logistics_diagnostics.py`：有界、脱敏费用差集。
- `backend/tests/test_logistics_cost_priority.py`：Sydney 2.2 正向三轮、未知／零费用、可选不采购、错误 ID 和保密回归。
- `backend/tests/test_logistics_diagnostics.py`：实际 HTTP 失败持久化与普通用户 run/progress 裁剪。
- `backend/tests/test_model_logistics_wiring.py`：仅给离线模型夹具增加漏项开关，既有默认行为不变。

## 验证

最终源码组合：费用清单、脱敏诊断、物流组件、HTTP 接线、审计、权限读取和 Sydney 三角色相关回归 **215 项通过**，84.49 秒，1 条既有 Starlette/httpx 弃用警告。这是单次最后组合运行，不与前轮 87／212 项相加，也不称为整仓后端全量。

前端现有组合 **125 项通过**；TypeScript、Vite 生产构建、共享 JSON schema 与 `git diff --check` 通过。构建仍有既有单包大于 500 kB 的提示，不是本轮协议错误。

额外只读离线核对第二次历史失败的固定输入：新工具列出 16 个必选 ID，完整方案保留 16 条分配；模拟只提交 12 个普通行 ID 仍被严格拒绝，脱敏诊断准确列出 4 个遗漏的 `unpriced-*` ID。这是主机模拟验证，不是重新取得历史模型响应。

真实模型调用 0 次；原用户数据库只读，不修改环境文件、密钥、封存数据；未重启服务、commit 或 push。本轮未声明真实校园模型验收通过。

## 启动与人工复测

1. 修复后必须重启后端；当前统一开发脚本没有后端热重载。前端无新业务代码变化，Vite 仍在运行时刷新页面即可。
2. 若使用同一个 `scripts/sydney.py`／`scripts/dev.py` 命令管理两项服务，在原终端停止后按**原命令及原参数**重新启动即可一并恢复。不要另起实例抢占端口，不随意改变安全协议或模型角色。
3. 保留旧失败记录。由于 Prompt 身份变化，使用同一次出行的更新入口，重新核对确认后明确启动新检查，不对旧 run 强行重试。
4. 新检查如果仍失败，查看受权内部诊断：角色 LOGISTICS、具体轮次、`COST_PRIORITY_COVERAGE` 及缺失／重复／未知位置。不要通过反复新建来盲目消耗额度。
