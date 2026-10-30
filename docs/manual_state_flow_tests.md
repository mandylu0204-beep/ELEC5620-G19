# 方案状态与接口：用户手工测试步骤

日期：2026-10-30。当前功能分支 feature/human-review-completion。

本文是测试操作与输入，不代表真实校园模型或远端 CI 已验收。前端按五个主状态展示，后台原有版本、运行、审核、恢复和最终保存校验保留。

配套文件：
- manual_state_flow_inputs.json：9 套配置、已有装备、可复制请求、结构化字段及审核回复素材。
- manual_state_flow_api_matrix.md：当前源码全部 50 个应用接口的覆盖计划。

**一段自然语言不能覆盖所有接口。**登录、保存、修改、重评、候选选择、人工审核、导出和删除都需要实际点击；兼容旧接口和部分列表还需直接请求补测。超时、断网、失效与事务失败也不能由“请模拟超时”这种需求文字可靠触发。

## 1. 先用免费规则模式测试显示

为避免重复消耗校园额度，配套 JSON 的每套配置默认使用 deterministic_demo，费用和装备、安全角色使用 rules。这是在测试同一套网页与业务接口，不是宣称真实模型已执行。

之后需要真实验收时，可以在独立测试环境启用 agent / model，并使用已获准的校园配置。生成需求摘要、PLAN、REVISE、REASSESS 或恢复缺失步骤都可能调用模型；查看已保存结果、候选选择、人工回复和最终保存本身不会新增推理。不要自动增加 token、超时或重试上限。

使用独立数据库和无痕窗口，不要与日常使用的站点混用登录 Cookie。每个场景切换配置后停止测试进程，再启动；不覆盖原数据库、个人密钥或封存数据。保留当前未提交代码，不需要切分支、reset 或重新下载数据。

推荐用配套启动器，一次只启动一个场景；它把 JSON 对应设置传给子进程，不改个人环境文件、不导入资料、不主动发模型请求：

    cd /Users/bibabu/_Code/github/ELEC5620-G19
    .venv/bin/python scripts/run_manual_state_case.py normal

Windows：

    .\.venv\Scripts\python.exe scripts/run_manual_state_case.py normal

先停止当前测试进程，再把 normal 换成 budget_revision、equipment_shortage、missing_evidence、road_closure、conflict_revision、no_match、future_weather 或 high_risk。重复使用同一场景会保留该测试库的历史，不会重置。用 --show-input 只查看该场景的完整输入；端口占用时追加 --backend-port 8871 --frontend-port 5371。

下面是等价的 normal 场景手动环境配置示例；项目已有依赖可直接运行。端口占用时选择另外两个端口，不停止不明来源进程。

    cd /Users/bibabu/_Code/github/ELEC5620-G19
    export CAMPMATE_EXECUTION_MODE=deterministic_demo
    export CAMPMATE_PLANNING_ENABLED=true
    export CAMPMATE_LOGISTICS_EXECUTION=rules
    export CAMPMATE_SAFETY_EXECUTION=rules
    export CAMPMATE_CLOCK_MODE=fixed
    export CAMPMATE_DEMO_TODAY=2026-11-05
    export CAMPMATE_SYNTHETIC_EVIDENCE_MODE=sealed
    export CAMPMATE_DATASET_PATH=data/synthetic_demo_v2
    export CAMPMATE_WORKFLOW_SAFETY_CASE_IDS='["safety-15"]'
    export CAMPMATE_DATASET_SCENARIO_FILES='[]'
    export CAMPMATE_DATASET_SELECTION='{"demo_input":"normal"}'
    export CAMPMATE_DATABASE_PATH=var/manual-state-normal.sqlite3
    export CAMPMATE_SEED_DEMO_ACCOUNTS=true
    export CAMPMATE_SECURE_COOKIES=false
    .venv/bin/python scripts/dev.py --backend-port 8870 --frontend-port 5370

打开 http://127.0.0.1:5370 。接口文档位于 http://127.0.0.1:8870/docs 。

Windows PowerShell 使用同样的值，环境变量写法为：

    $env:CAMPMATE_EXECUTION_MODE="deterministic_demo"
    $env:CAMPMATE_PLANNING_ENABLED="true"
    # 其余 CAMPMATE_ 参数逐项设置为 JSON 对应 settings 的值
    .\.venv\Scripts\python.exe scripts/dev.py --backend-port 8870 --frontend-port 5370

若 Node / npm 未加入当前终端 PATH，先修复本机已有环境，再启动。不要为测试覆盖个人配置。

## 2. 账号与基础资料

S01：注册两个专用测试账号，用户名可用 manual.flow.a、manual.flow.b，显示名称分别“流程测试 A / B”，测试密码可用 CampMate-Manual-2026!。退出后分别验证登录、错误密码、刷新会话和退出。账号已存在时换后缀，不能覆盖账号。

人工审核需 Founder 账号。仅在本节独立新建且启用了 seed_demo_accounts 的演示库中，可使用源码已有演示账号 founder / CampMate-Founder-2026!。普通用户注册不能选择或提升为 Founder。

S02：正常场景按 JSON 对应 case.profile 填写已有装备，并保存。不要直接把整份 profile 当作需求文字粘贴。

normal 基础资料：
- 2 人，有一定经验；无儿童，儿童人数 0。
- 汽车 1 辆，载客容量 2 人，整个行程所有车辆累计 100 公里。
- 帐篷 1 顶，每顶可住 2 人；地布 1 件。
- 睡袋、睡垫、保暖衣物、雨衣、防风外套、手电、已充电手机各 2 件。
- 急救包 1 件；餐食 18 份；饮用水 12 升。
- 每条可编辑装备和车辆都勾选“已核实可用”，单位按网页固定选项填写。当前网页隐藏手机等系统准备项时无需强行添加；JSON 中的完整 profile 可用 S18 的同源 API 辅助函数 PUT /profile 精确复现，expected_revision 从刚读取的 GET /profile 获取。
- 除车辆以外的实际数量、容量，以对应 JSON 为准；high_risk 场景有更多装备，不能沿用简化清单。

S02b：另建一个草稿选择自行烹饪，在炉具／燃料核对区域填写炉具 1、燃料罐 1 并预览，再把燃料改为 0 或未确认。检查预览提示变化，已有装备不因预览自动增加。覆盖 /preparation/cooking；正式结论仍要重新确认并检查。

## 3. 请求输入与预期主状态

每个场景都按顺序操作：
1. 将启动配置改为该 case.settings。固定日期是场景的一部分，不是电脑当天日期。每套配置使用不同测试库。
2. 保存该 case.profile。
3. 新建请求，把 case.request.raw_text 复制到文本框；结构化日期、晚数、预算、偏好和必须条件逐项对应 explicit_fields。
4. 保存草稿 → 生成摘要 → 核对全部字段 → 勾选确认需求 → 开始规划。
5. 先观察“检查未完成”及当前阶段，再观察最终主状态与原标签页中的检查结果。运行快时可在浏览器 Network 使用限速辅助观察；限速浏览器不等于模拟后台模型超时。
6. 记录计划编号、运行编号、主状态、各标签页检查结果、警告内容、保存按钮是否可用。

提供的 request.raw_text 英文与 explicit_fields 组合已经在本机规则模式实际走通；raw_text_zh 是中文参考。规则解析器对复合中文条件有限制，必须条件推荐用结构化控件逐项选择，不能仅依赖一句长文本。

| 场景 | JSON case | 可复制请求概要 | 预期 |
|---|---|---|---|
| S03/S04 正常 | normal | Two people in CampMate Demo Region from 2026-11-06 for two nights, AUD 320. We want quiet and ready-to-eat meals. | 检查未完成 → 待确认；各项完成，可确认保存，不显示空警告 |
| S09 超预算 | budget_revision | Two people in CampMate Demo Region from 2026-10-27 for two nights, AUD 245. We want quiet and ready-to-eat meals. | 需要调整方案；费用和装备类说明超预算，安全仍可通过 |
| S08 装备不足 | equipment_shortage | 与 normal 相同，但帐篷每顶容量 1 人，删除急救包 | 需要调整方案；指出装备与容量缺口，不能勾选免责直接放行 |
| S10 无可行营地 | no_match | Two people in CampMate Demo Region from 2026-11-06 for two nights, AUD 1. We want ready-to-eat meals. | 需要调整方案；行程类说明无匹配，后续未执行的检查不能标为通过 |
| S11 资料缺失 | missing_evidence | 2026-10-21 出发、两晚、AUD 320、即食餐食、必须淋浴 | 需要调整方案；说明安全资料不足，可能同时存在依赖天气的装备问题 |
| S11b 远期天气 | future_weather | 2026-11-20 出发、悉尼及周边、两晚、AUD 1000、即食餐食 | 可以保留行程；天气超出 7 天覆盖范围，不能保存；不是要求用户填写天气 |
| S11c 修订后资料冲突 | conflict_revision | 2026-10-27 出发、两晚、AUD 400、即食餐食、必须淋浴 | 初始可待确认；换营地修订后出现资料冲突，不能靠旧评估或旧批准保存 |
| S11d 道路关闭 | road_closure | 2027-04-10 出发、两晚、AUD 320、即食餐食 | 需要调整方案；安全类明确道路关闭，不能显示“等待批准即可出行” |
| S12 人工风险判断 | high_risk | 悉尼及周边、2026-11-01 出发、两晚、AUD 1000、即食餐食；必须有淋浴、必须能轮椅通行、必须公共交通可达；固定检查日 2026-10-30 | 满足完整配置且选中 Bonnie Vale 后等待人工审核；仅复制日期和预算不能保证触发 |

S12 可复制完整输入（此前表格只列日期和预算的摘要，遗漏了关键设施条件，已修正）：

    我们两个人计划在悉尼及周边露营，2026年11月1日出发，住两晚，总预算1000澳元，采用即食餐食。必须有淋浴。必须轮椅通行。必须公共交通可达。

提交前务必在“必须条件”控件中同时选中“必须有淋浴”“必须能轮椅通行”“必须公共交通可达”，生成摘要后再次确认三项没有丢失。自由文本只是输入，真正生效的是保存且明确确认后的条件。不能只勾选“希望有淋浴”等偏好。

在当前全校园模型环境中，检查日同为 2026-10-30、同一滚动合成资料和上述完整条件时才对应这个测试世界；如果日期或选中的营地不同，不能要求仍出现人工审核。Cattai 在该日是温和天气，低风险通过是正确结果。切勿为了测试把正常方案强行改成高风险。

high_risk 的结构化必须条件：showers、wheelchair_accessible、public_transport_access。这是要求营地具备对应设施，不是把同行资料强制改成公共交通。该 case 固定检查日期为 2026-10-30，读取当日独立合成资料快照；规则选择 Bonnie Vale，天气为大雨，当前唯一阻断应为 REVIEW_REQUIRED。它不是实时天气或真实旅行建议。完整装备和配置必须使用 JSON 内这一套，不能混用其他场景。

自然语言本身不能制造封路、过期证据或高风险天气；上述覆盖依赖 case.settings 指定的现有合成资料与日期。真实模型可能选择不同合法营地，以实际保存结果为准，不应为追求固定答案反复付费生成。

## 4. 正常方案后的操作：S04～S07

S04 最终保存与回读：
- “待确认”时看到“保存为最终方案”和“修改方案并重新评估”。未勾选确认时保存按钮不可用。
- 勾选后保存，状态变成“最终方案已保存”。刷新、重新登录、重启同一测试配置后读取内容一致。
- 下载已保存方案 PDF，检查日期、费用、装备、安全内容，不出现开发者 token / trace。
- 当前最终快照有“更新本次出行”；历史快照不直接编辑旧内容。
- 以 B 账号访问 A 的计划和最终快照地址，应不可读取；不能依靠隐藏按钮代替权限校验。

S05 修订与候选选择：
- 在待确认方案点“修改方案并重新评估”，选择“更换营地”或“寻找费用更低的营地”。自定义意见可以填写：
  请保留已确认的日期、人数和预算，更换另一处符合必须条件的营地，说明区别。
- 候选运行期间顶部为“检查未完成”，不能继续显示原最终方案已保存来代表新候选；下方原方案内容须明确属于原方案。
- 完成后分别测试“保留原方案”和“采用新方案”（需要两次独立修订）。选择尚未确认时不能最终保存、重评或再发起修订。
- 采用不等于最终保存；重新核对候选的费用和安全。若“找更便宜营地”确实无解，应提示原方案保留，不得伪造更低价格。
- 在 budget_revision 场景先走降费修订，以实际评估检查是否已低于预算；不能仅凭营地费降低就认定总费用合格。

S06 保留行程重新检查：
- 点击“修改方案”里的“保留行程，重新检查”。
- 再次显示“检查未完成”；行程为“复用已保存行程”，费用和装备、安全显示本轮进度。
- 检查结束再显示本轮结果；原审核不能自动授权新证据，旧最终快照不变。
- agent / model 配置下此操作仍可能调用费用装备和安全模型。

S07 修改需求或已有资料：
- 从“修改需求与资料并重新确认”进入，把预算 AUD 320 改为 AUD 500；或者把同行人数 2 改为 3，并补足实际装备。
- 保存资料后在更新页面核对差异，再生成摘要、确认需求并开始新检查。
- 新结果归于同一次出行，旧方案在历史中；旧最终快照和旧审核不能替代新结果。
- 未确认的新草稿不能直接开启正式规划。

## 5. 审核与需求协助：S12～S15

S12 正式风险批准：
- 生成 high_risk 场景后，A 用户看到“等待人工审核”，安全区提示需要人工审核，暂不能保存。
- Founder 登录，从“人工审核”的风险审批队列打开该方案，核对风险和资料日期。
- 选择“批准”，理由可复制 JSON 的 review_notes.APPROVE，再保存决定。
- A 刷新后，只有其他条件仍满足才进入“待确认”；用户仍需亲自勾选并保存。
- 若出现装备缺口或资料不足，当前应进入协助范围，不能为了测试批准而跳过真实阻断。

S13 要求修订、拒绝与历史：
- 使用另外两份 high_risk 方案，分别选择 REQUEST_REVISION 和 REJECT，理由用 JSON 对应文案。
- A 收到“需要调整方案”，查看具体审核意见。“采用这条审核意见”只填入修订意见，点击生成待选方案才执行。
- 新修订／重评后旧决定留在历史中，不授权新结果。
- Founder 在“已处理／历史”查看决定，分页或刷新；普通用户不能进入审核或读取其他用户的审核详情。

S14 规划前需求协助：
- 在“其他必须条件”填写“可供冲澡的固定设施”，仅保存；这是要求设施，不是请求特殊户外活动。
- 若它未匹配现有词汇，提交人工协助。若页面已经识别成“淋浴”，不属于未知条件，不应强行制造协助任务，可改用另一个尚未登记的表述。
- Founder 在需求协助中提出“必须有淋浴”的对应建议，说明“将用户所说冲澡设施对应为淋浴设施；是否存在由正式筛选检查。”
- A 查看回复并明确采用，再生成摘要、确认需求。采用词义建议不能宣称营地满足条件或安全通过。
- 另建两份协助请求，分别测试退回补充和当前不支持。未知要求不应静默丢弃，已修改草稿不能继续采用旧版本回复。

S15 方案生成后的修正协助：
- 对 missing_evidence 场景，Founder 在修正／协助队列选择 WAITING_EVIDENCE，填 JSON 的 problem / reason / next_action；建议重查日期选不早于固定检查日期的日期。
- 对 equipment_shortage 场景选择 NEEDS_CAMPER_INPUT；对真正不支持的安排可使用 UNSUPPORTED，不把“不支持”当作批准。
- A 应能看到独立处理意见，但主状态仍按原检查问题判断，最终保存继续不可用。
- 等待资料、需要补充、当前不支持这三种意见都不应写成风险批准。

## 6. 不能靠普通输入触发的补测：S16～S18

打开浏览器开发者工具的 Network，勾选 Preserve log。先用页面完成一次相应操作，核对请求方法、地址、响应状态和实际生成的 ID。不要在文档中填写或提交真实密钥、Cookie、CSRF 值。

对网页没有入口的接口，可以在同一测试站点的 Console 用下面的辅助函数。只在自己的独立测试库操作，地址使用矩阵里的真实路径。切换账号后先刷新页面，再重新执行辅助函数，避免沿用上一账号的 CSRF。

    const manualSession = await fetch('/api/v1/auth/me').then(r=>r.json());
    async function manualApi(path, method='GET', body){
      const r=await fetch('/api/v1'+path,{
        method, credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CampMate-Client':'1',
                 'X-CSRF-Token':manualSession.csrf_token},
        ...(body===undefined?{}:{body:JSON.stringify(body)})
      });
      const value=r.status===204?null:await r.json();
      return {status:r.status,value};
    }

S16 兼容旧 revise 接口：
- 当前网页使用 /revision-proposals，不会自动覆盖 /revise。
- 在可修订、无未决候选的独立方案上，先 GET /plans/{plan_id} 获取最新版本和运行修订号。
- POST /plans/{plan_id}/revise。请求结构与页面“修改方案”实际发出的 body 相同：新的 command_key、expected_current_version_id、expected_active_run_id、expected_version_revision、expected_run_revision、feedback。
- 返回运行编号后读取该运行，确认形成新的合法检查结果；不能手写其他人的编号或沿用已过期修订号充当正常成功测试。
- 旧接口直接修订，不用于证明新候选比较界面经过测试。

S17 恢复与检查异常：
- 输入仍用 normal。前置条件是已有一条后台实际失败、且服务端 retry_available 为 true 的运行。
- “继续未完成的步骤”应重用已保存产物；没有保存的步骤才可再执行。重复提交同一次恢复不得创建重复版本。
- 普通输入不能保证校园模型超时，断开浏览器网络也不等于后台模型失败。若没有失败运行，需要开发者在独立测试环境提供可控故障，或执行已有离线恢复回归，不要反复调用真实模型等待随机失败。
- 保存按钮的网络失败可用浏览器离线模式核对错误提示；未收到保存回执时先恢复网络、刷新检查，不要直接认定未保存并新建另一份。

S18 辅助读取与预览：
- 用 manualApi 直接 GET /plans、/plans/{plan_id}/versions、/trip-series/{series_id} 和 /runs/{run_id}。当前页面不保证用到每个旧列表接口。
- GET /runs/{run_id}/progress 应包含轻量状态；完成后重新读取完整详情。不能只看进度就认定可保存。
- POST /dev/interpret 的 body 是 {raw_text: normal 的原文, explicit_fields: normal 的字段}；这是开发预览，不是正式确认。是否开放取决于当前环境，禁止访问的配置应返回拒绝，不能擅自开放。
- S00 另直接访问 /health/live、/health/ready、/meta；未就绪时不能假定规划可用。

## 7. 删除与拒绝路径：S19 / S20

S19：仅使用专门的测试草稿、测试方案和测试出行系列。先读取历史，再分别删除草稿、单个历史方案、当前方案和整次出行；刷新确认不可再读。删除历史不能偷偷替换当前方案，删除当前方案不能自动恢复旧方案。

S20：在同一接口再覆盖必要的拒绝分支：
- 未登录读取私有资源；普通用户提交审核；B 读取 A 的计划、最终快照和 PDF。
- 缺少 X-CampMate-Client 或 CSRF 写入；无效字段／缺少确认勾选。
- 使用过期版本 revision 提交；未决候选期间再次修订、重评或最终保存。
- 同一命令同一内容重试；同一 command_key 改了内容应拒绝。
- 道路关闭、缺证据、超预算、装备不足时尝试保存，应被服务端拒绝。
- 已取消、已被替代、旧历史记录不得显示当前可执行的修改／恢复／保存操作。当前网页没有承诺提供通用“取消运行”按钮，此项需已有退出记录或离线测试补测。

## 8. 如何判断你测完了

按 API 矩阵逐行记录：场景、方法和地址、返回状态、plan/run ID、页面主状态、三项检查、预期结果、实际结果、是否通过。只看到“界面正常”不代表 50 个接口都被访问。

人工批准、要求修订、拒绝、采用候选、保留原方案分别需要对应独立操作；不能把同一次批准后显示正常算成所有分支已覆盖。有前置条件的接口缺少准备数据时，记录“未测及原因”，不要勾选通过。

本机已做的验证范围：
- 配套 8 个常规输入场景在隔离 HTTP/SQLite + 规则模式下实际走通；另已核对 high_risk 稳定进入只剩 REVIEW_REQUIRED 的人工审批分支。
- 这只证明输入、配置和分支可复现，不表示你已经在浏览器执行上述全部接口，也不表示真实模型验收通过。
- 未执行任何真实校园模型请求，没有改个人配置、原用户数据库或封存包。
