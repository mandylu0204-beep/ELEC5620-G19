# 在 VS Code 启动当前版本

适用：已集成 A26 和 `synthetic_demo_v2_1` 的版本。前后端仍在本机运行，GitHub 保存源码。旧包和旧方案保留，不需要清库。

## 首次准备

用 VS Code 打开项目根目录 `campmate_app`，不是单独打开 frontend 或 backend。终端选择 PowerShell。

本机项目位置：

```powershell
cd C:\Users\87901\Desktop\ELEC5620\Stage2\campmate_app
```

换电脑或首次克隆时，先安装 Python 3.12、Node.js 22.12+，在项目根目录执行 `py -3.12 scripts/setup.py`。本机依赖已准备好时不必重复安装。安装不会覆盖已有 `.env`。

## 使用新数据与校园模型

先连接校园网络或 USYD VPN。在根目录 `.env.llm.local` 配置自己的校园密钥，可参考 `config/campus_llm.example`。密钥不要贴到终端命令、聊天或 GitHub。

在同一个 PowerShell 终端依次执行：

```powershell
$env:CAMPMATE_EXECUTION_MODE='agent'
$env:CAMPMATE_PLANNING_ENABLED='true'
$env:CAMPMATE_LOGISTICS_EXECUTION='model'
$env:CAMPMATE_DATASET_PATH='data/synthetic_demo_v2_1'
$env:CAMPMATE_WORKFLOW_SAFETY_CASE_IDS='[]'
$env:CAMPMATE_DATASET_SCENARIO_FILES='[]'
$env:CAMPMATE_DATASET_SELECTION='{}'
$env:CAMPMATE_DEMO_TODAY='2026-11-05'
$env:CAMPMATE_DATABASE_PATH='var/campmate-trip-v2_1-model.sqlite3'
$env:ELEC5620_MAX_COMPLETION_TOKENS='4096'
$env:ELEC5620_REASONING_EFFORT='low'
.\.venv\Scripts\python.exe scripts\dev.py
```

这些变量只作用于该终端及启动的子进程，不改个人配置文件。校园规划与物流模型启用后会产生实际 API 请求；需求解释与安全判断仍使用规则。这里显式使用已验证的 4096/low 配置，因为已有个人文件可能仍指定会截断物流响应的 2048。

前端打开 http://127.0.0.1:5173，API 文档为 http://127.0.0.1:8000/docs。终端保持运行，按 Ctrl+C 同时停止前后端。端口被占用时，可在最后一行加 `--backend-port 8001 --frontend-port 5174`，浏览器相应打开 5174；脚本不会结束其他已有服务。

这里使用单独命名的持久化数据库，首次启动自动创建；下次使用相同路径会保留账号资料、请求和方案。原 `var/campmate.sqlite3` 不受影响，不要将数据库提交 GitHub。

## 不调用校园模型的规则模式

在上面的启动命令之前，改用以下三个变量，其余新数据、时钟和空场景选择配置相同：

```powershell
$env:CAMPMATE_EXECUTION_MODE='deterministic_demo'
$env:CAMPMATE_LOGISTICS_EXECUTION='rules'
$env:CAMPMATE_DATABASE_PATH='var/campmate-trip-v2_1-rules.sqlite3'
.\.venv\Scripts\python.exe scripts\dev.py
```

规则模式不需要校园密钥或 VPN，不能作为真实模型验收证据。切换模式前先停止原服务；为各模式保留各自数据库，避免误将旧模式运行当作当前结果。

## 页面操作

1. 使用 `camper.a` / `CampMate-A-2026!` 登录。
2. 打开露营资料，填写并保存同行人数、装备数量/容量、交通等信息。需要演示资料时，可载入后检查并明确保存；系统不会把未确认租借当作已准备。
3. 新建请求，填写需求、日期和预算，保存草稿、核对摘要并确认，再开始规划。
4. 方案可修改行程或保留行程重新检查。换营地会自动按实际营地重新匹配资料，不需要换内部场景。
5. 阅读行程、装备、费用与安全结果，满足条件后勾选确认并保存最终方案。

检查时钟是可配置的演示日期，与主机系统时间分开；这里使用真实验收时的 2026-11-05。例如 11-06 出发、两晚、两人、预算 AUD 320 是已验证的正常请求，属于示例，不是表单限制。用户仍可自由输入其他日期、晚数与条件。

新包覆盖十个营地及两个有限时段，但天气还受发布时间、观测日期和预报期限限制。资料不足时页面说明原因并提供查证过的可选调整，重复检查不会自动补造资料。

切换资料、模式或时钟后，旧确认需求的输入身份可能过期。请按页面提示重新确认需求或发起允许的重评，不强行重试旧运行；旧最终快照继续保留。

实际验收范围与限制见 [2.1 真实校园验收](a26_trip_live_acceptance.md)。Canvas 全新下载部署及最终提交包验证仍留到系统完成后执行。
