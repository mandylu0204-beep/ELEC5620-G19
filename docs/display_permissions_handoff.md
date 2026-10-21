# CampMate 展示、文案与读取权限交接

## 基线与边界

- 起点：`fix/display-issues`，`5649359`；开始时工作区干净。未切换分支、提交、推送或合并。
- 对齐已存在的资料返回与重新规划流程、结构化物流问题、安全建议及最新数据快照隔离交接。
- 不修改装备要求、安全规则、审核触发、方案状态机、最终保存守卫、模型 Prompt、模型输出 schema、token 配置或推理流程。
- 未调用真实校园模型，未操作个人环境文件、密钥、原用户数据库、封存数据或正在运行的服务。

## 本轮展示改动

1. 帐篷改为住宿容量说明：分别显示数量、每顶容量、分行容量、登记总容量、同行人数、检查认可容量和缺少人位。不同容量分行；未知值保持未知，未确认装备不因此变为可用。
2. “放弃未保存修改”只在表单与已读取基线确有不同内容时启用。确认框列出具体修改分区，确认后才重新读取；取消不读取、不改资料。不恢复旧方案、不执行评估。
3. 保存个人资料与采用新资料完成检查明确区分。继续复用既有“使用最新资料重新规划”预览、核对、确认和新建方案流程，不假装修改原方案快照。
4. 行程顶部展示保存的选择意见、适合需求的理由和待确认事项。重评时明确标注意见来自原版本。行程时间均保守标注“建议时间／待确认”，不是已核实的入住、退房或交通时刻。
5. 安全页复用结构化装备问题，提供装备页跳转，按问题、影响、处理动作解释；来源原文、错误码、CSV 和规则细节保留在折叠记录。“资料覆盖本次日期”不代表安全放行。天气缺口显示服务端给出的日期区间、调整方式和建议重查时间。
6. 装备与预算区域保留补缺、费用、预算分配、剩余预算和待确认安排；独立诊断区仅供有权限的审核员使用。
7. 新增只读 `display_status`，区分需要用户补充、需要补齐资料、需要修改方案、等待人工审核和不能放行。它不是业务状态，不参与任何按钮授权或保存决定。执行中的新检查优先显示进行中，同时保留此前最终方案入口。

## HTTP 读取投影：接线注意

后端内部查询、恢复和最终保存仍使用完整数据。仅在 HTTP 返回前深拷贝并按角色投影：

| 读取入口 | 普通露营用户 | 现有审核权限 |
| --- | --- | --- |
| `/plans/{id}`、`/runs/{id}`，含历史运行 | 仅本人业务内容；无模型 trace、配置摘要和用量 | 原有访问规则不变，不能借身份跨过 Camper 的入口限制 |
| `/plans/{id}/finals/{final_id}` | 本人最终快照的业务投影 | 不新增跨用户最终快照权限 |
| `/review/{plan_id}` | 禁止访问 | 原审核范围内可见业务内容和独立 `model_diagnostics` |
| 确认需求和需求详情 | 不返回 `dataset_context.selection_config` 等完整运行身份 | 不新增此入口的权限 |

- 原始 `model_planning_trace` 不再直接作为 HTTP 顶层字段返回。业务说明使用 `planning_explanation`，含来源运行、选中营地和未经核实的决策摘要。
- `model_assessment_audits` 的公开部分保留 `plan` 及必要的运行、版本、评估关联字段，用于已有安全建议绑定；移除 trace、配置身份、尝试编号等诊断字段。普通读取中的 `dataset_context` 只公开资料包版本；`rules_version` 含模型配置指纹，不能作为普通规则编号直接透出。
- `can_view_model_diagnostics` 由服务器登录角色决定，不接受前端、查询参数或请求头授权。当前系统没有 Developer 角色；本轮使用已存在的 Founder 审核权限，不新增角色。
- 审核员诊断位于 `model_diagnostics.planning`、`.assessments` 和 `.dataset_context`。装备与费用面板不再直接展示这些字段。
- 普通用户的运行错误上下文仅保留少量运行关联字段，避免从失败详情旁路暴露 HTTP 次数、耗时、模型配置等内容。
- `tent_capacity` 与每个帐篷问题中的同名字段是保存资料和保存评估的只读展示事实；缺口直接沿用保存的评估值，不重新计算业务判定。
- 最终快照读取同样裁剪，但数据库中原始最终快照、审计内容与哈希完全不变。不应拿裁剪后的 HTTP 视图回填持久化 DTO 或用来恢复运行。
- 既有接线测试如需验证完整审计，显式使用测试内的内部读取辅助，并先验证 Camper HTTP 已裁剪。新增权限测试直接检查原始 HTTP 响应，不使用此辅助。

## 需要 A 配合的接口：出行系列关联

目前一个 `plan_id` 内的运行和版本已经归于同一张卡片，但采用最新资料重新规划会建立独立请求和方案；没有服务端出行系列字段。此轮不按相同日期、目的地或标题合并。

建议另行冻结并实现：

- 服务端维护 `trip_series_id`、`predecessor_plan_id`，在创建后继需求／方案时校验原方案所有权，以明确命令和幂等 key 建立关联。
- 列表返回系列的最新方案／运行状态、历史方案入口，以及跨方案保留的最终记录引用（须包含所属 `plan_id`）。
- 新检查进行中时仍可返回“此前最终方案已保留”，但不把旧最终成功当作新检查结果。
- 没有系列身份的历史方案继续单独展示，不进行猜测迁移。
- 此接口不应顺带改变原确认快照、审核权限或最终保存资格；具体事务和数据库迁移由 A 评审后另行实施。

## 未完成范围与限制

- 不实现跨独立方案的系列合并；等待上述关联接口。
- 旧模型任意英文自由文本无法在“不改 Prompt、不新增模型调用、不猜测翻译”的边界内全部可靠翻译。本轮中文化固定界面与可精确对应的既有固定理由；已有中文意见直接展示，未知英文原文折叠保留，并明确提示没有可直接展示的中文说明。不得把前端模板写成模型实际给出的理由。若要求每条自由文本都有中文，需要单独批准内容本地化方案。
- 当前覆盖接口提供重查日期时显示精确日期；旧记录没有该字段时不编造，建议临近出发且资料覆盖缺失日期后重查。
- 未新增“将最新个人资料直接写入原方案并重评”的能力；现有入口是核对确认后生成新方案。
- 本轮使用 HTTP、纯函数与组件／整页服务端渲染验证，不操作现有浏览器业务会话，不宣称已完成真实模型或交互式浏览器联合验收。

## 验证命令与结果

使用仓库根目录的 `.venv`（匹配 `backend/requirements.lock`），不要误用 `backend/.venv` 的不同依赖环境。

```sh
cd /Users/bibabu/_Code/github/ELEC5620-G19
.venv/bin/python -m pytest backend/tests --basetemp=var/pytest-display-full --tb=short -q
cd backend
../.venv/bin/python -m app.export_contracts --check
cd ../frontend
node --experimental-strip-types --test tests/*.test.mjs
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/vite/bin/vite.js build
```

- 新增后端容量、读取投影、权限、审计不变性测试：10 项已在最新投影上复跑通过。
- 前端纯函数、组件和历史／最终／审核整页渲染：59 项通过。
- 共享 schema 检查、前端类型检查和生产构建通过。
- 后端全量共 1451 项：首次 1440 项通过、11 项失败。完成读取投影测试适配及旧夹具补齐后，相关 65 项复测全部通过；未在最后适配后重新从头执行第二遍全量。新增权限 10 项另在最新投影上复跑通过。

## 修改文件索引

- 后端展示边界：`backend/app/application/presentation.py`、`application/logistics_issues.py`、`http_plans.py`、`http_requests.py`、`http_reviews.py`、`storage/plan_queries.py`。
- 前端展示组件与事实：`display_facts.ts`、`display_panels.tsx`、`plans.tsx`、`finals.tsx`、`profile.tsx`、`requests.tsx`、`replan.tsx`、`logistics_issues.tsx`、`logistics_plan.tsx`、`model_trace.tsx`、`safety_information.tsx`、`safety_advisory_panel.tsx`、`trip_coverage.tsx`、`plan_language.ts`、`styles.css`。
- 固定中文界面：`App.tsx`、`session.tsx`、`register.tsx`、`reviews.tsx`、`near_matches.tsx`。
- 测试：新增 `test_display_projection.py`、`audit_test_reads.py`、`display_presentation.test.mjs`，并适配原有读取／审计接线测试及安全建议组件的导入测试。`test_near_matches.py` 的旧 `SimpleNamespace` 夹具缺少 main 新增的 `has_v2_policy` 属性，仅补齐此假对象属性，不改生产筛选或装备规则。
