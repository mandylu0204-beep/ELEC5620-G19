# CampMate：从零启动与人工测试操作手册

更新：2026-10-15，悉尼时间。适用：包含 A25 `fa33ac4` 和 B 本轮物流候选修复的代码。

**同日进展更新：** 本手册编写后，用户授权B补测的真实REASSESS、road_closure、最终保存后重启回读已通过，见 `a25_logistics_b_followup_acceptance.md`。下文“建议补测/尚待补测”是手册编写时的测试计划，现可作为可选独立复核步骤，不必重复付费执行。

本文是操作步骤，不代表你已完成其中测试。编写本文未调用校园模型。不要把早期文档中“物流仍为规则”“重评零模型调用”等历史描述用于当前双模型配置。

## 1. 先决定测什么，避免重复花费

当前系统不是聊天窗口，不会把所有 Agent 的完整原始回复直接打印出来。模型返回受控 JSON，经过校验后显示为行程、装备建议、预算建议和独立调用记录。

| 部分 | 当前实现 | 主要检查 |
| --- | --- | --- |
| 需求解释 | 规则 | 日期、人数、预算、偏好和必须条件是否正确；是否明确确认 |
| 营地筛选 | 规则工具 | 返回合法候选，不通过模型虚构营地 |
| 行程规划 | 校园真实模型 | 从候选选择营地、给出意见，保存行程及规划 trace |
| 装备与预算建议 | 显式启用后由物流模型选择 | 逐项补缺方法、理由、费用优先级；另存物流 audit |
| 数量、容量、金额 | 确定性程序 | 数量/容量正确，整数分/Decimal 计算，未知值不当零 |
| 安全评估 | 规则 | 缺资料、封路必须阻止放行，不被模型意见覆盖 |
| 保存、历史、权限、恢复 | 后端和数据库 | 不重复版本/审计、历史不被覆盖、他人不能读取 |

建议分两层：

1. **先免费熟悉网页**：规则模式走一次操作，或只查看已有方案；无需校园调用。
2. **再少量真实验收**：只测当前未覆盖的项目。已有候选修复证据见 `docs/a25_logistics_b_fix_handoff.md`；本轮尚待补测的重点是候选配置下的 REASSESS、road_closure，以及最终保存后的重启回读。

如果只想完成当前剩余验收，不必重做正常、缺资料、未知帐篷、预算修订全部场景。若没有现成成功方案，需要先做一次正常 PLAN 才能重评。

### 哪些操作会花校园模型额度？

| 操作 | 是否调用模型 |
| --- | --- |
| 登录、编辑/保存资料、保存草稿、生成需求摘要、确认需求 | 当前实现不调用 |
| 查看已有方案、切换行程/装备/费用/安全/记录标签、刷新读取 | 不新增模型调用；后台若已有运行，原调用仍会继续 |
| 查看模型意见、历史和已保存最终方案 | 不调用 |
| 正常完成后停止/重启服务，再回读记录 | 不因查看而调用；不要在执行中误当作零成本重启测试 |
| 开始规划 PLAN | 调用规划模型和物流模型 |
| 修改方案 REVISE | 调用规划模型生成新版本，再调用物流模型 |
| 保留行程，重新检查 REASSESS | **物流为 model 时仍会调用物流模型**，不调用规划模型 |
| 重试规划 RETRY | 取决于缺失步骤；已保存物流复用，未保存物流可能再次付费调用 |
| 最终保存/人工审核 | 本身不调用模型，不代替前置评估 |

本文真实测试配置使用每轮最多1次HTTP尝试、每角色最多3轮。通常 PLAN/REVISE 是规划2轮+物流3轮，共5次 completion；严格调用次数上限按两个角色各3轮计为6次。REASSESS 最多3次物流 completion。**这不是 token 数或费用上限**：上下文、输出和推理均影响用量；手动重试/再开新运行会额外累计。

## 2. 找到正确的代码目录

本机项目仓库位置：

```text
/Users/bibabu/_Code/github/ELEC5620-G19
```

不是 Codex 聊天所在的 `/Users/bibabu/_Code/codex/elec5620`。其他成员使用自己实际的仓库路径。根目录应包含 `backend`、`frontend`、`scripts`、`data`、`config` 和 `docs`。

macOS 终端：

```bash
cd /Users/bibabu/_Code/github/ELEC5620-G19
git branch --show-current
git status --short
python3.12 --version
node --version
npm --version
```
Windows PowerShell：

```powershell
Set-Location '你的 ELEC5620-G19 仓库完整路径'
git branch --show-current
git status --short
py -3.12 --version
node --version
npm --version
```

采用 Python 3.12、Node.js 22.12+。命令找不到时先安装相应环境并重开终端。本文不要求执行 git pull/switch/reset，也不要为了测试覆盖未提交修改；先与 A 对齐共同代码版本。本轮 B 修复若仍未提交，A 仅有旧 main 时并不包含这些修改。

## 3. 首次安装依赖（已有可用环境可跳过）

在仓库根目录运行，首次需联网下载依赖，但不会发出校园推理请求。

macOS：

```bash
python3.12 scripts/setup.py
```

Windows：

```powershell
py -3.12 scripts/setup.py
```

安装器创建 `.venv`、安装锁定的后端依赖及前端依赖；没有 `.env` 时从模板创建，不覆盖已有 `.env`。此后不必每次重跑安装。

检查文件是否存在：

- macOS：`.venv/bin/python`。
- Windows：`.venv\Scripts\python.exe`。
- 前端：`frontend/node_modules/vite/bin/vite.js`。

不要把他人电脑的 `.venv`、`node_modules` 或个人密钥提交 Git。

## 4. 准备校园密钥：只放本地

真实模型需要学校发放的密钥以及可访问校园代理的网络；必要时连接 USYD VPN。

1. 在仓库根目录寻找 `.env.llm.local`。已有文件直接用编辑器打开，**不要覆盖**。
2. 仅当文件不存在时，复制 `config/campus_llm.example`，将副本命名为根目录的 `.env.llm.local`。
3. 在本地编辑器中填入 `ELEC5620_API_KEY`，不要把密钥贴到聊天、截图、报告或终端命令历史。
4. 保留学校当前提供的 endpoint/model。仓库现有模板为 `http://10.167.60.148:8000/v1`、`campus-qwen`；若教师变更，应先核对新说明。

本文件用于模型配置；根目录 `.env` 用于应用配置，两者不是同一个文件。本文启动命令通过进程环境明确设置测试参数，优先于本地文件，避免旧文件2048上限继续生效。

可用以下只读命令确认密钥文件被忽略，不显示其内容：

```bash
git check-ignore .env.llm.local
```

应输出文件名。若未被忽略，先停止提交操作并检查 `.gitignore`；不要 `git add -f`。

## 5. 可选：先用规则模式熟悉界面

macOS：

```bash
.venv/bin/python scripts/demo.py --case normal --database var/manual-rules-normal-01.sqlite3
```

Windows：

```powershell
.\.venv\Scripts\python.exe scripts/demo.py --case normal --database var/manual-rules-normal-01.sqlite3
```

打开 `http://127.0.0.1:5173`，按第8节操作。规则模式没有真实模型记录，不能据此宣称 LLM 验收通过。

**重要：`scripts/demo.py` 会把 execution_mode 明确设成 deterministic_demo。即使之前设置过 agent，也不能用这个入口测试真实双模型。** 完成规则演示后在启动终端按 Ctrl+C 停止服务，再按第6节启动真实模式。

## 6. 启动真实双模型网页：先从 normal 开始

只启动一套服务，在一个专用终端操作。不要同时使用旧测试端口5316/5317：上轮临时服务已经关闭，本文统一用5173/8000。

### 6.1 macOS：复制整段，在根目录执行

```bash
export CAMPMATE_EXECUTION_MODE=agent
export CAMPMATE_PLANNING_ENABLED=true
export CAMPMATE_LOGISTICS_EXECUTION=model
export CAMPMATE_DATASET_PATH=data/synthetic_demo_v2
export CAMPMATE_DEMO_TODAY=2026-11-05
export CAMPMATE_WORKFLOW_SAFETY_CASE_IDS='["safety-15"]'
export CAMPMATE_DATASET_SCENARIO_FILES='[]'
export CAMPMATE_DATASET_SELECTION='{"demo_input":"normal"}'
export CAMPMATE_DATABASE_PATH=var/manual-campus-normal-01.sqlite3
export CAMPMATE_SEED_DEMO_ACCOUNTS=true
export CAMPMATE_SECURE_COOKIES=false
export ELEC5620_MAX_COMPLETION_TOKENS=4096
export ELEC5620_REASONING_EFFORT=low
export ELEC5620_MAX_ATTEMPTS=1
export ELEC5620_MAX_TURNS=3
export ELEC5620_TIMEOUT_SECONDS=45
.venv/bin/python scripts/dev.py
```

### 6.2 Windows PowerShell：复制整段，在根目录执行

```powershell
$env:CAMPMATE_EXECUTION_MODE = 'agent'
$env:CAMPMATE_PLANNING_ENABLED = 'true'
$env:CAMPMATE_LOGISTICS_EXECUTION = 'model'
$env:CAMPMATE_DATASET_PATH = 'data/synthetic_demo_v2'
$env:CAMPMATE_DEMO_TODAY = '2026-11-05'
$env:CAMPMATE_WORKFLOW_SAFETY_CASE_IDS = '["safety-15"]'
$env:CAMPMATE_DATASET_SCENARIO_FILES = '[]'
$env:CAMPMATE_DATASET_SELECTION = '{"demo_input":"normal"}'
$env:CAMPMATE_DATABASE_PATH = 'var/manual-campus-normal-01.sqlite3'
$env:CAMPMATE_SEED_DEMO_ACCOUNTS = 'true'
$env:CAMPMATE_SECURE_COOKIES = 'false'
$env:ELEC5620_MAX_COMPLETION_TOKENS = '4096'
$env:ELEC5620_REASONING_EFFORT = 'low'
$env:ELEC5620_MAX_ATTEMPTS = '1'
$env:ELEC5620_MAX_TURNS = '3'
$env:ELEC5620_TIMEOUT_SECONDS = '45'
.\.venv\Scripts\python.exe scripts/dev.py
```

启动命令同时管理前后端，无需再开一个 uvicorn 或 npm dev。终端保持打开，显示两个服务启动后，浏览器打开：

- 网页：`http://127.0.0.1:5173`。
- API 文档：`http://127.0.0.1:8000/docs`（可选，主要测试用网页即可）。
- 配置检查：`http://127.0.0.1:8000/api/v1/meta`。
- 就绪检查：`http://127.0.0.1:8000/api/v1/health/ready`。

端口占用时，不要结束不认识的进程；将启动命令末尾改为 `scripts/dev.py --backend-port 8001 --frontend-port 5174`，前端地址随之改成5174，API地址改成8001。

这些配置只影响当前终端及子进程；新终端需要重新配置。已有数据库会保留，不自动清空。需要全新测试时换一个未使用的文件名，例如 `...-02.sqlite3`，不要删除数据库。要测试重启回读则必须保持原文件名。

### 6.3 点“开始规划”前检查，避免误用规则或 stub

在 `/api/v1/meta` 应看到：

```json
{
  "execution_mode": "agent",
  "supported_operations": ["PLAN", "REASSESS", "REVISE"],
  "planning_stages": {
    "interpretation": "rules",
    "recommendation": "rules",
    "itinerary": "model",
    "logistics": "model",
    "safety": "rules"
  }
}
```

这是应核对的字段片段，不是完整响应。还应看到 `features.planning=true`、`agent_configuration_error=null`；normal时钟为2026-11-05。

就绪接口应HTTP200、`status=ready`、`configured_agent_available=true`。接口中历史字段 `real_agents_implemented=false` 不是本轮判断标准，按实际模式、阶段和保存的模型记录核验。

**ready/meta不调用真实模型，也不证明校园上游此刻一定可用。** 若logistics为rules、模式不是agent或存在配置错误，先修正，不要启动付费测试。

## 7. 切换场景：必须同时更换时钟、证据与数据库

所有场景都使用 `data/synthetic_demo_v2`。固定演示时钟不是电脑今天的日期，不要自行改成当前日期。

| 场景 | DEMO_TODAY | WORKFLOW_SAFETY_CASE_IDS | DATASET_SELECTION | 新数据库示例 |
| --- | --- | --- | --- | --- |
| normal | 2026-11-05 | `["safety-15"]` | `{"demo_input":"normal"}` | var/manual-campus-normal-01.sqlite3 |
| budget_revision | 2026-10-26 | `["safety-16","safety-17"]` | `{"demo_input":"budget_revision"}` | var/manual-campus-budget-01.sqlite3 |
| missing_evidence | 2026-10-20 | `["safety-02"]` | `{"demo_input":"missing_evidence"}` | var/manual-campus-missing-01.sqlite3 |
| road_closure | 2027-04-09 | `["safety-18"]` | `{"demo_input":"road_closure"}` | var/manual-campus-road-01.sqlite3 |

切换顺序：网页退出账号 → 启动终端Ctrl+C → 修改上表四项环境变量 → 再运行dev.py → 刷新meta核对 → 重新登录。

例如，从 normal 切到**当前待补测的道路关闭**，其余第6节配置不变：

macOS：

```bash
export CAMPMATE_DEMO_TODAY=2027-04-09
export CAMPMATE_WORKFLOW_SAFETY_CASE_IDS='["safety-18"]'
export CAMPMATE_DATASET_SELECTION='{"demo_input":"road_closure"}'
export CAMPMATE_DATABASE_PATH=var/manual-campus-road-01.sqlite3
.venv/bin/python scripts/dev.py
```

Windows：

```powershell
$env:CAMPMATE_DEMO_TODAY = '2027-04-09'
$env:CAMPMATE_WORKFLOW_SAFETY_CASE_IDS = '["safety-18"]'
$env:CAMPMATE_DATASET_SELECTION = '{"demo_input":"road_closure"}'
$env:CAMPMATE_DATABASE_PATH = 'var/manual-campus-road-01.sqlite3'
.\.venv\Scripts\python.exe scripts/dev.py
```

budget_revision和missing_evidence也照表替换同样四项。不要只改网页日期、不改服务器证据。

## 8. 从空数据库完整操作一次网页

### 8.1 登录

打开网页，点击“登录”。这是公开合成演示账号，不是个人账号：

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 主要测试者 | camper.a | CampMate-A-2026! |
| 隔离测试者 | camper.b | CampMate-B-2026! |
| 审核者 | founder | CampMate-Founder-2026! |

先使用camper.a。登录本身不调用模型。

### 8.2 保存小组资料

1. 点击左侧“露营资料”。
2. 展开“想先体验？使用演示样例”。
3. 点击“载入演示资料”。此时只是填表，**还没有保存**。
4. 核对2人、中等经验、无儿童，交通汽车/1辆/100km。
5. 核对13项演示装备；帐篷1件、每件容量2人，睡袋/睡垫各2件，餐食18份、水12升。普通场景不要随意删除装备或清空数量。
6. 点击“保存露营资料”，看到保存成功后再进入“露营请求”。

### 8.3 填写本次请求

选择与服务器场景一致的一行。目的地均为 `CampMate Demo Region`，晚数均填2；网页预算单位是 **AUD，不是cents**。

| 场景 | 开始日期 | 小组总预算AUD | 偏好（每行一项） | 必须条件（每行一项） |
| --- | --- | --- | --- | --- |
| normal | 2026-11-06 | 320 | quiet；ready-to-eat meals | 留空 |
| budget_revision | 2026-10-27 | 245 | quiet；ready-to-eat meals | 留空 |
| missing_evidence | 2026-10-21 | 320 | ready-to-eat meals | showers |
| road_closure | 2027-04-10 | 320 | ready-to-eat meals | 留空 |

表中分号表示换行，不要把整串带分号填成一个偏好。“已明确天数或结束日期？”保持空白，避免同时填入冲突约束；系统从2晚推导3天和结束日期。

“露营想法”复制对应句子，并在结构化字段填入同样的日期、预算、偏好等，避免仅依赖自由文本解析：

**normal**

```text
Two people in CampMate Demo Region from 2026-11-06 for two nights, AUD 320. We want quiet and ready-to-eat meals.
```

**budget_revision**

```text
Two people in CampMate Demo Region from 2026-10-27 for two nights, AUD 245. We want quiet and ready-to-eat meals.
```

**missing_evidence**

```text
Two people in CampMate Demo Region from 2026-10-21 for two nights, AUD 320. We want ready-to-eat meals. Must have showers.
```

**road_closure**

```text
Two people in CampMate Demo Region from 2027-04-10 for two nights, AUD 320. We want ready-to-eat meals.
```

### 8.4 摘要、确认、开始规划

1. 点击“保存草稿，下一步”。
2. 点击“生成需求摘要”（有未保存修改时按钮为“保存修改并生成摘要”）。
3. 核对2晚/3天、日期、预算、偏好、必须条件和本次采用的资料。
4. 如提示澄清，先修改并重新生成摘要，不能跳过。
5. 勾选“我已阅读本次需求和资料，确认以上内容。”
6. 点击“确认并保存需求”。至此仍没有调用两个模型。
7. **确认要花额度后，仅点击一次“开始规划”。** 进入方案页后等候，不要连续新建/重复规划。
8. 到“记录”看阶段：推荐营地 → 生成行程 → 保存版本 → 装备与物流 → 安全评估 → 判断下一步 → 完成检查。

阶段耗时可能不同。页面会读取进度；刷新并不等于重试。若FAILED，按第13节记录后停止，不自动再点“重试规划”。“检查已完成”只表示工作流执行完，**不等于安全通过或可最终保存**。

## 9. 重点：在哪里看 Agent 的回复？

方案详情有“行程、装备、费用、安全、记录”五个标签。

### 9.1 行程模型的结果和意见

- “行程”：实际选择的营地、两晚安排、活动等；可展开“查看本次规划说明”。
- **“记录” → 展开“AI 规划说明”**：查看“模型选择与意见”、营地ID、简短决策摘要。
- 同一面板还有请求模型、服务返回模型、工具轮数/HTTP尝试、耗时、Token usage。
- 展开“审计关联与配置摘要”：查看run/version/attempt、配置和Prompt摘要。

请求别名为campus-qwen；之前实测返回身份为Qwen/Qwen3.8-27B-FP8，以本次实际记录为准。出现offline-test-only或“模拟模型响应”不能算真实校园验收。

### 9.2 物流模型的装备建议

1. 点击“装备”。
2. 上方“装备数量与缺口”主要是规则事实：所需、已具备、缺口、容量、未确认状态。
3. 下方 **“装备准备建议”** 是模型选择经过程序校验后的方案：使用已确认装备、拟租借、拟购买、拟借用、需补充信息、暂缓可选装备。
4. 每项展开“查看建议理由”，看模型为该项选择的简短理由。
5. 展开“查看模型意见”，看整体取舍摘要。

拟租借/购买/借用不是已经成交；不能增加已具备数量，也不能自动补齐缺失事实。暂缓可选装备不是删除真实缺口。模型选择每项补缺方法，而不是只生成一段说明。

### 9.3 物流模型的预算安排

1. 点击“费用”，看费用估算、已知小计、总预算、超额/剩余及费用明细。
2. 查看 **“预算安排建议”**：优先级、所需费用、计划分配、未覆盖金额和未分配预算。
3. 展开“查看模型意见”，看预算取舍说明。

模型选择供给方式/费用排序；数量、容量、整数分金额和分配额由程序计算。总费用未知时，即使有已知小计或未分配余额，也不能宣布预算充足。

### 9.4 物流模型的真实调用记录

**“记录” → 展开“AI 装备与预算说明”**：查看“本次物流模型评估记录”、实际模型、轮数/尝试数和成功响应usage；展开“查看关联记录”看run/version/assessment/attempt。

这份audit与“AI规划说明”不是同一份记录。初次PLAN成功且模型物流启用时，两份都应有。模型在保存行程后失败时，可能只有规划记录、没有物流audit，应记录失败，不是把规则结果补当模型结果。

### 9.5 不能在哪里看到什么？

- 网站不提供原始system prompt、所有原始模型回复或模型私有思维链。
- 开发终端主要显示服务/HTTP日志，不是完整聊天记录。
- 页面展示的是经过严格校验的业务产物和简短理由，不应为查看回复而新增模型调用。
- Token usage仅为成功响应报告值；失败请求可能也产生消耗，不能当完整账单。
- 安全页是规则评估，不是模型的自由回复。

## 10. 每个场景的测试目标与通过标准

真实模型可能选择不同合法营地；以下营地/金额是已有实测参考，不是允许硬编码的预期。如果选择变化，按实际费用与已登记证据判断；未覆盖目标时记“未覆盖”，不要为了命中营地不停重跑。

### T01：正常PLAN、最终保存

使用normal配置和第8节输入。此前实际为Wattle Rest、AUD251，小组预算AUD320。

检查：

- [ ] 行程已保存，日期/晚数正确；记录中两个真实模型调用分别存在。
- [ ] 装备数量不被模型改写，所有必须物品和费用未被遗漏。
- [ ] 费用计算正确、未改预算；如果实际存在未知费用或其他约束，应如实阻止。
- [ ] “安全”有适用日期、来源和检查结论。
- [ ] 仅在全部条件满足时，页面允许最终保存。
- [ ] 阅读并勾选最终确认，点击“保存为最终方案”；看到“已保存的最终方案”和保存时间。
- [ ] 保存最终链接，用于T07重启回读和T08权限隔离。

如果本次结果确实不具备资格，不能把保存禁用当成纯页面故障，也不能让Founder强行批准绕过事实。

### T02：超预算与真实模型修订

使用budget_revision配置和输入。此前原方案Wattle Rest/AUD251，超过AUD245预算。

1. 检查原费用及超额AUD6，最终保存禁用；记录原版本编号与两份调用记录。
2. 展开“修改行程或更新检查”。
3. “修改目标”选择“寻找费用更低的营地”。
4. **点击一次“修改方案”**，这会调用模型。
5. 等待新运行结束；此前实测为版本2、Moonlit Field/AUD231。

通过标准：新版本及新规划trace、新物流audit；确认预算仍AUD245；旧版本/记录仍可回看。只有真实新方案满足预算与安全条件时才可保存。不要通过增加预算假装低价修订成功。

若原PLAN实际已选预算内营地，本次没有覆盖“超预算修订”，记未覆盖，先与A确认，不连续付费抽结果。

### T03：同版本REASSESS（当前建议优先补测）

在一个已成功方案上操作，可用T01或T02结果。不要在“最终快照”页找操作按钮，先进入“查看当前方案”。

1. 到“记录”，记下版本编号/ID、原规划trace的run和内容摘要、当前物流评估/audit关联编号。
2. 如有已保存最终方案，保留其链接，待会只读比较。
3. 展开“修改行程或更新检查”。
4. **点击一次“保留行程，重新检查”**，不要误点“修改方案”。这会调用物流模型。
5. 完成后检查：
   - 版本编号、版本ID、行程内容未改变。
   - 新run、新物流assessment/audit；装备、费用、安全重新评估。
   - “AI规划说明”明确这是原生成记录，并提示本次重评未调用规划模型。
   - “AI装备与预算说明”是本次新物流记录，不混入原规划trace。
   - 原最终快照仍可读，未被本次重评覆盖。

不要只对比input_fingerprint：同输入同配置时可能相同。应同时核对run、版本、assessment和audit编号。与run绑定的物流input_sha256可能改变。

### T04：缺安全资料

使用missing_evidence服务器配置和对应输入，必须条件showers。此前实际选River Flat，安全REVIEW，费用AUD241。

- [ ] 两个模型与后续评估完成；物流audit真实保存，不再卡在502阶段。
- [ ] 安全页天气信息仍“资料待核实”，能看到适用日期及缺少发布时间/其他不足的原因。
- [ ] 风险未知不得显示成安全低风险；重新检查不能凭空补齐资料。
- [ ] 最终保存禁用；Founder也不能靠批准绕过缺失安全证据。

若物流502，属于模型流程未完成，不算“安全REVIEW已验证”。

### T05：道路关闭（当前建议优先补测）

按第7节切换road_closure，再按第8节创建请求。此前实际Moonlit Field，安全BLOCKED/ROAD_CLOSED。

- [ ] 安全页显示道路关闭及覆盖日期，明确不能放行。
- [ ] 物流/规划意见不能覆盖道路约束。
- [ ] 最终保存按钮禁用。
- [ ] Founder打开对应审核记录时，不得批准绕过封路。

模型若实际选择不在这条封路证据覆盖范围的其他营地，不能直接宣称已验证ROAD_CLOSED；记录实际选择与未覆盖状态，先让A判断，不反复重跑。

### T06：未知帐篷数量

建议独立数据库，服务器沿用normal时钟、证据、选择项，只把数据库名换为 `var/manual-campus-unknown-tent-01.sqlite3`。启动后：

1. 登录，载入演示资料。
2. 找到帐篷，仅清空“数量”，保留单位item和每件容量2；其余资料不变。空白表示未知，**不能填0**。
3. 保留原拥有确认状态，仅将数量设未知，以复现本轮变体；即使勾选拥有，数量未知也不能被程序推成已知库存。
4. 保存资料。此后新建normal请求并确认；不能复用此前快照仍有帐篷数量1的旧已确认需求。
5. 点击一次开始规划。

通过标准：帐篷数量/缺口保持未知，建议为“需补充信息”（ASK_USER）、待确认；补缺费用未知，总费用/预算是否可行未知，物流REVISION，最终保存禁用。地布等依赖帐篷数量的条目也可能未知，这是规则依赖的正常结果。安全单独PASSED不代表整个方案可保存。

### T07：停止/重启与历史最终快照回读（不需新模型调用）

1. 确认所有运行已完成，不在执行中。保存当前方案、最终快照链接及两个调用记录截图。
2. 在启动终端按Ctrl+C，等待两个服务退出。
3. **同一终端、同一配置、同一数据库路径**重新运行第6节的dev.py启动命令，不要换空数据库。
4. 登录，打开原最终链接。核对版本、行程、费用、评估、模型记录及最终ID与保存时间相同。
5. 只看结果，不点击开始规划/修改方案/重新检查/重试。

若先前因修订/重评已有新运行，原快照可以显示“历史最终方案”，但内容不应变成新方案。若找不到记录，先查数据库路径是否变了，不要靠重新生成恢复旧结果。

### T08：用户权限隔离（不需新模型调用）

1. 用camper.a复制自己方案和最终快照的URL。
2. 正常退出，登录camper.b。
3. 在地址栏粘贴camper.a的两个链接。
4. 应显示方案不存在/无法读取；Network对应GET应404，不泄漏内容。
5. 不要仅凭camper.b列表为空就算完成隔离测试，应实际访问已知他人的链接。

Founder有审核职责，不用Founder替代另一个普通用户做owner隔离测试。

### T09：审核页面守卫（一般不需新模型调用）

退出camper.a，登录founder，打开“人工审核”。若目标方案进入队列，进入其审核详情，核对当前行程、费用、安全依据及限制。缺安全资料/道路关闭时批准不得放行；可见的修订要求/拒绝也需真实理由，不自动最终保存。

若队列中没有目标，不要造审核记录来通过；记录当前路由状态与可见入口交A确认。测试后重新登录camper.a检查方案仍受约束。

### T10：异常、checkpoint及丢回执恢复（代码成员专项）

普通成员不需人为断网、杀模型请求或编辑SQLite。刷新/重启回读并不证明“物流事务已提交但响应丢失”的故障恢复。

受控专项应在独立数据库由A/B注入一次正式保存端口**提交后丢回执**，保留真实已保存模型产物，再同身份重启并RETRY；检查新增模型调用0、原物流audit/评估、版本内容和原规划trace不变，无重复行。未提交前失败则可能重做缺失物流，不能承诺零消耗。

本项已有本轮真实产物受控验收及离线回归，通常不用为交接再消耗真实额度重做。具体边界见 `a25_logistics_b_fix_handoff.md` 和 `a24_logistics_audit_handoff.md`。

## 11. 可选：不写代码查看接口数据

网页显示足够完成大多数验收。需要核对编号时：打开浏览器开发者工具 → Network → Fetch/XHR → 刷新方案页 → 找到下列只读GET并查看Response。

| 响应字段 | 用途 |
| --- | --- |
| `run.run_id`、`run.operation`、`run.status`、`run.stage` | 本次运行及失败阶段 |
| `version.version_number`、`version.version_context.plan_version_id` | 版本编号与身份 |
| `model_planning_trace` | 原行程生成记录，重评时应复用 |
| `model_assessment_audits.LOGISTICS` | 本次物流方案、独立audit和trace |
| `assessments` | LOGISTICS/SAFETY结果及关联 |
| `finalisation_available` | 当前是否允许最终保存 |
| `eligibility.blocking_reasons` | 不能保存的原因 |

只读路径：`/api/v1/plans/<plan_id>`、`/api/v1/runs/<run_id>`、`/api/v1/plans/<plan_id>/finals/<final_id>`。最终快照响应业务内容通常在`final_record`内，与当前方案响应结构不要混淆。

规划/修改/重评POST返回202只是接收任务，不是模型已成功。应等GET中的运行结束、对应产物已保存。也不要把本地应用HTTP503与校园上游502混为一谈；上游状态可能在`run.error.context.http_status`里。

不要导出或分享完整HAR、Cookies、Authorization、CSRF token或带私人资料的请求体。无需为了测试在API文档里手工拼接写请求；前端负责revision、幂等key、会话与CSRF。

## 12. 给代码成员的离线回归命令（不消耗校园推理token）

运行已提交的自动测试，使用模拟模型传输，不把它当真实校园验收。先保证第3节依赖安装完整，保留正常个人密钥文件，不需打印或提供密钥。

完整检查，macOS根目录：

```bash
.venv/bin/python scripts/check.py
```

Windows根目录：

```powershell
.\.venv\Scripts\python.exe scripts/check.py
```

包含后端测试、schema同步和前端构建；运行可能数分钟，并非每次浏览器点击后都要执行。当前候选完整验证为871 passed，后续代码新增测试时数字可能变化；以实际失败/跳过原因判断。

只跑物流针对性测试，先进入backend：

macOS：

```bash
cd backend
../.venv/bin/python -m pytest tests/test_campus_model_client.py tests/test_llm_logistics_agent.py tests/test_model_logistics_wiring.py tests/test_logistics_audit.py -o addopts='' -q
cd ..
```

Windows：

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest tests/test_campus_model_client.py tests/test_llm_logistics_agent.py tests/test_model_logistics_wiring.py tests/test_logistics_audit.py -o addopts='' -q
Set-Location ..
```

当前针对性为197 passed，包含四套离线HTTP场景。pytest会使用项目var下的隔离目录，不要自行把basetemp指向项目根目录或其他资料目录。封存包相关7项回归包含在全量中。

可选，只读静态校验，根目录：

```bash
# macOS
.venv/bin/python data/synthetic_demo_v2/scripts/validate_dataset.py
```

Windows将Python路径换为 `.\.venv\Scripts\python.exe`。应报告68项静态检查通过；不要加`--write-report`或运行封存修复命令。静态检查不执行包内全部58条业务验收规格，也不调用模型。

## 13. 失败时怎么处理，避免烧token

| 现象 | 先做什么 | 不要做什么 |
| --- | --- | --- |
| 网页打不开/连接被拒绝 | 看启动终端、实际端口，确认dev.py仍运行 | 不把旧5317链接当永久服务 |
| Port occupied | 改backend/frontend端口，网页地址跟着改 | 不随意kill其他人的进程 |
| 缺依赖/ModuleNotFoundError | 确认使用项目.venv，按setup安装，检查命令目录 | 不反复发送真实模型探针 |
| 开始规划不可用 | 查ready/meta、是否确认需求、是否agent/v2+model | 不先反复点按钮 |
| 配置缺密钥或代理不可达 | 核对本地密钥、VPN与endpoint，保留错误 | 不发密钥给A/B或贴日志 |
| 第二轮502 | 记录LOGISTICS/轮次/耗时/错误后停止，请A联系维护方 | 不无限恢复、不只加本机timeout就宣布修复 |
| CONTRACT_INVALID | 记录阶段和错误；可能是截断、JSON或最终方案不一致 | 不把HTTP200当业务成功，不绕过校验 |
| STALE_CONTEXT | 配置/提示/数据变更后复制需求、重新解释确认，开新运行 | 不用新配置强行继续旧FAILED运行 |
| 费用未知/REVIEW/BLOCKED | 查看装备和安全原因，按实际事实处理 | 不改成0、不让Founder解除硬约束 |
| 保存版本已有、物流未完成 | 先保留现有run和版本，确认是否要付费重试 | 不删除数据库、不为同key重造不同版本 |

改low参数、token/轮数/重试上限、Prompt、数据选择都会影响登记身份。**切换省额度配置也是配置变化**；不要拿上轮2次尝试/4轮的失败run用本手册1次/3轮直接继续。新确认需求才能采用新身份。

每个待测场景最多先执行一次。失败后保留截图与编号即可让开发定位，不需要先自行试两三遍。关闭浏览器标签不会可靠取消后台模型调用；若要终止本地测试，在启动终端Ctrl+C停止服务，保留中断记录，不保证已发出的上游请求不计费。

## 14. 发给A/B的测试记录模板

复制以下内容到单独的测试记录，每个场景一份；不要记录密钥、cookie或私有推理。

```text
测试人 / 悉尼时间：
代码分支 / git rev-parse --short HEAD / 是否有未提交修改：
场景：normal / budget_revision / missing_evidence / road_closure / unknown_tent
操作：PLAN / REVISE / REASSESS / 只读回读 / 权限隔离
数据库路径（仅文件名和相对路径即可）：
模式：agent；itinerary=model；logistics=model；safety=rules
固定时钟 / 证据ID：
公开模型配置：4096 / low / max_attempts=1 / max_turns=3 / timeout=45
请求日期 / 晚数 / 小组预算：
实际选中营地：
版本编号 / plan_id / run_id / plan_version_id：
规划记录ID与其原run：
物流audit_id / assessment_id：
规划轮数/HTTP次数 / 物流轮数/HTTP次数：
本次成功响应usage（规划和物流分开；重评不要重复计原规划记录）：
物流结果 / 总费用 / 是否有未知项：
安全结果 / 阻断原因：
最终保存是否允许 / 实际是否保存：
重评前后：原版本/规划trace是否相同；是否产生新物流audit：
失败：error.code / context.http_status / logistics_turn / elapsed_ms / trace_id：
截图文件名：
结论：通过 / 不通过 / 因模型选择变化未覆盖 / 未执行
后续是否停止真实调用：
```

### 最少复测路线

如果已有同一候选配置的成功方案：**只读核对 → 一次REASSESS → 保存资格满足时最终保存 → 完成后重启回读 → owner隔离 → 切换封路配置做一次PLAN → 停止**。如果没有可复用方案，先做一次normal PLAN，再走上述流程。

本手册1次尝试/3轮与此前实际验收2次/4轮不是同一配置；跨配置不得直接重试旧失败run。若要复用既有成功方案做重评，应先由A确认当前输入/配置变化是否允许登记新的重评上下文；页面不开放时不要绕过后端或改数据库。

只想给A交接时，可直接提供本手册和本轮候选修复报告，不必为了再截一张图重跑已经通过的付费场景。PR #5仍应等待A复核和共同验收决定，本文不执行提交或合并。
