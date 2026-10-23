# 同一次出行的连续更新与关联待办

日期：2026-10-22（Australia/Sydney）。起点：`fix/display-issues` / `7ff400c`，保留当时工作区中尚未提交的系列后端、迁移 11 和审核分离实现。

## 用户流程

1. 原方案的装备、用餐、预算、营地比较、安全覆盖和输入失败修正入口，均保留原 plan_id。
2. 修改装备资料后，可“保存并核对本次更新”，或“仅保存资料，暂不检查”。前者进入同一更新核对页；后者只保存个人资料。
3. `/plans/{plan_id}/update` 读取正式来源状态，以既有 `POST /plans/{plan_id}/successor-requests` 准备后继草稿，再打开 `/request/{request_id}`。打开和刷新只准备草稿，不 interpret、confirm 或 dispatch。
4. 用户在同一草稿编辑需求，明确点击生成摘要；多次生成摘要使用同一 request_id。摘要展示固定的 profile_revision、原／新个人资料及需求差异。
5. 用户勾选后点击“确认采用并重新检查”，复用 ReplanSession 的 revision 校验、确认与 PLAN 幂等流程。首次不采用未展示的新个人资料；确认丢回执后重试原 key，不用最新资料改写已固定输入。
6. 新方案仍归原系列，一张主卡片展示最新检查，旧检查和最终记录保留历史。准备草稿、取消及仅保存不切换当前方案。

这是第一阶段的完整重新规划，不是采用新资料的局部 REASSESS。确认启动后营地、行程可能改变；原版本／评估／审计／最终记录不改写。
系列当前指针仍沿用既有实现：在创建后继运行的事务中切换，不改为“检查通过后才切换”。

## 入口与兼容

- 修正入口不再用 `copy_from` 假装更新原出行。
- `copy_from` 保留为“以此为模板，新建独立出行”，绝不依据相同日期、目的地或标题加入系列。
- 个人资料页从需求草稿打开时返回同一 request_id；从原方案打开时返回该方案的更新入口。
- 需求记录在折叠的“草稿与历史需求”中保留，不称为新的独立出行；后继记录有系列标识。
- 以前已生成且没有可靠来源关系的独立记录不自动合并、删除或补造关联。
- 历史／最终／审核视图无活跃更新链接；原方案历史提示与当前方案入口使用服务端系列关系。

## 接口与存储

不新增核心写 API、Agent DTO 或数据库迁移；继续使用尚待 A 复核的迁移 11 和精确来源、命令 key、revision 检查。

后继请求读取新增业务字段：

- `source_profile_snapshot`：来源命令固定的原 run 的个人资料，不是当前个人资料。
- `source_requirements`：同一原 run 的确认需求。
- 复用原有 `source_profile_revision`、`trip_series_id`、`predecessor_plan_id`。
- 来源已删除时不再返回原 profile／requirements，也不能编辑该后继草稿来复活来源。

请求列表增加只读 `trip_series_id`、`is_trip_update`（SQL 0/1）元信息；不返回运行诊断。
后继草稿 PATCH 也检查来源状态。所有正式写、恢复、审核和最终化继续使用服务端完整 DTO 与既有守卫，不使用裁剪 HTTP 视图。

浏览器 sessionStorage 只保存命令 key 与非秘密来源并发身份，不保存 profile、凭证、模型文本或 trace。
草稿创建、确认和 PLAN 使用不同的稳定 key；同一标签页刷新、重复挂载、同 key 丢回执不会重复创建。
历史来源首次建立系列的 revision 0→1 不更换原创建命令。不同标签页可存在多个明确预览，服务端 CAS 仍只允许一个后继成为当前。
若已明确删除草稿，原 key 返回 404，不自动复活或换 key；页面提供显式“新建本次更新草稿”，再次核对来源后才使用新命令。来源删除或权限失败不能借此绕过。

## 装备缺口与费用影响

- 报价投影使用结构化 cost item_key 和已保存装备检查项关联；燃料罐等直接 item_key 不再因没有 cost-xx 映射而丢失名称。
- 同一装备同时缺货和缺报价：显示一个装备待办，下挂 `cost_impacts`，明确是关联的补缺费用未知。
- 没有可关联装备缺口的报价问题仍为系统资料问题，不伪造价格编辑按钮。确实需要的未知费用不计为零。
- 既有投影能确定依赖关系时增加 `pending_checks`，提示哪些装备尚待上游资料／选择明确，不凭名称猜数量或容量。
- 每项可操作待办直接提供真实资料或同系列需求入口；历史只读不提供操作按钮。
- 修改表单不清除已保存问题。只有正式的新评估结果确认库存／缺口变化后，主卡片和待办才随权威结果更新。

这些是读取与导航修正，没有改变 essential、容量、报价数据、整数分计算、审核触发、安全规则或最终保存资格。

## 验证与边界

后续“首次烹饪准备清单／无模型预检查”补丁见 `cooking_preparation_handoff.md`；下面 1470／90 是该补丁之前的验证记录，不代表当前新增补丁的全量结果。

本轮未发起真实校园模型调用、修改环境／密钥、写入原用户数据库、修改封存数据、主动执行服务重启或 Git 提交／推送。

已执行的定向验证：后端 51 项通过（隔离数据库），覆盖反复编辑自行烹饪／即食餐食摘要、同系列单卡片、固定来源资料、profile revision 冲突、删除及普通用户原始 HTTP 响应。
首次定向运行有两项旧展示断言不符合新设计（报价拆分、copy_from 路径），已更新为关联费用与显式系列入口；不计作最终全量通过。

最终前端组合：90 项测试通过；TypeScript 检查、Vite 生产构建、共享 JSON schema 检查和 git diff --check 通过。
后端最终组合从头全量：**1470 passed，1 warning**，796.61 秒。唯一警告为既有 Starlette TestClient 使用 httpx 的弃用提示；不是业务失败。
该结果来自最终后端源码的单次完整运行，不把定向 51 项或前轮结果与其相加。隔离目录为 `var/pytest-trip-update-final-full-kLgQID`。
组件 SSR／纯控制器与 TestClient HTTP 覆盖不等于真实浏览器或真实模型验收；本轮不操作用户现有浏览器会话。

## 本轮直接修改文件

- 更新入口与稳定命令：`frontend/src/trip_update.ts`、`replan.tsx`、`replan_session.ts`、`App.tsx`。
- 保存与核对：`frontend/src/profile.tsx`、`requests.tsx`；来源读取及 PATCH 守卫在 `backend/app/storage/requests.py`，已删除方案过滤在 `http_requests.py`。
- 修正链接与历史只读：`frontend/src/planning.tsx`、`next_steps.tsx`、`near_matches.tsx`、`trip_coverage.tsx`、`safety_information.tsx`、`plans.tsx`。
- 关联待办：`backend/app/application/logistics_issues.py`、`frontend/src/logistics_issues.tsx`。
- 回归：`backend/tests/test_trip_series.py`、`test_logistics_issues.py`，`frontend/tests/trip_update.test.mjs`、`display_presentation.test.mjs`。
- 文档：本文及 workflow_consistency_handoff.md、workflow_consistency_interface_proposal.md。工作区中其他系列／审核后端改动属于前一轮，保留未提交。

## 人工复测步骤

使用受控的隔离数据库与演示执行模式，不使用真实校园模型：

1. 创建一份出行，选择自行烹饪，使必要装备有实际缺口。
2. 从燃料／炉具待办打开资料页，只填写真实信息。点击“仅保存资料”，确认原方案问题仍是旧检查；不应启动新运行。
3. 点击“保存并核对本次更新”，应进入同一更新草稿，未自动开始检查。
4. 生成摘要，核对 profile_revision、装备变化；反复调整用餐方式并生成摘要，URL 中 request_id 不应改变。
5. 返回、刷新或重复打开原更新入口，应继续同一草稿；不能多出独立出行卡片。
6. 在另一个页面修改个人资料后尝试确认：应要求重新核对，不能静默采用新资料。
7. 明确确认并检查后，列表仍一张出行主卡片，新增结果进入历史关系；旧最终入口不冒充本次通过。
8. 若燃料有缺口且补缺报价未知，应在同一燃料待办看到关联费用影响；真正备齐并完成新检查后，才移除对应补缺待办。
9. 查看历史、最终快照及审核页面，不能从旧结果误启动更新；普通用户不能读取模型运行诊断。
10. 明确选择“以此为模板，新建独立出行”时，才应出现独立卡片。

应用若未开启后端自动重载，需要由用户安排受控重启后才加载新后端。不要只凭前端热更新宣称整套接口已部署。
未实现：采用最新资料但保留行程的局部重评、报价维护页面、自动翻译、新模型协议以及历史独立记录自动归并。
