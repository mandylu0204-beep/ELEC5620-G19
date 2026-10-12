# v2 浏览器演示与复现

2026-10-12：本机真实浏览器已完成四个场景。使用 B 的 v2 Adapter/规则、HTTP 登录和独立 SQLite；没有插入预生成方案或使用 stub 成功记录。数据为 synthetic_demo_v2 2.0.0、2026-10-12 修订版。输入来自同目录的 v2_inputs.json，不含 expected_*。

## 安装与选择场景

在解压后的项目根目录使用 Python 3.12、Node.js 22.12+。首次安装需要联网：

```powershell
py -3.12 scripts/setup.py
.\.venv\Scripts\python.exe scripts/demo.py --case normal
```

打开 http://127.0.0.1:5173。脚本按所选场景设置固定时钟和证据，用 var/demo-normal.sqlite3 保存历史；不会编辑个人 .env、删除已有记录或覆盖个人默认数据库。按 Ctrl+C 停止前后端，再改 --case 启动另一个场景：

```powershell
.\.venv\Scripts\python.exe scripts/demo.py --case budget_revision
.\.venv\Scripts\python.exe scripts/demo.py --case missing_evidence
.\.venv\Scripts\python.exe scripts/demo.py --case road_closure
```

每次仅运行其中一个命令。四个场景各有独立数据库。端口占用时可加 --backend-port 8001 --frontend-port 5174；脚本不会结束占用端口的其他程序。每次切换场景先退出账户，然后重新登录，避免浏览器沿用另一个数据库的会话。

重新启动同一场景会保留历史；要从空数据库重新演示，使用新的文件名，例如 --database var/demo-normal-take2.sqlite3。不要删除用户数据库。macOS/Linux 使用对应 venv 的 Python 运行相同脚本；本轮只验证了 Windows。

## 从界面准备资料和需求

1. 登录 camper.a，密码 CampMate-A-2026!。
2. 打开“露营资料”，点击“载入演示资料”，阅读并点击“保存露营资料”。载入只填写表单，不自动保存或确认需求。
3. 共用资料为 2 人、INTERMEDIATE、无儿童，CAR/1 辆/100 km；13 项装备包含数量、单位、拥有确认和帐篷人数容量。请保留餐食18 portion、水12 litre等原始值。自行修改后结果可能不同。
4. 在“露营请求”填写下表。全部为 CampMate Demo Region、2 晚/3 天、无结束日期或天数的额外冲突字段。预算填写 AUD，偏好每行一项。

| 场景 | 固定演示时钟 | 开始日期 | 小组预算 AUD | 偏好 | 必须条件 |
| --- | --- | --- | --- | --- | --- |
| normal | 2026-11-05 | 2026-11-06 | 320 | quiet；ready-to-eat meals | 空 |
| budget_revision | 2026-10-26 | 2026-10-27 | 245 | quiet；ready-to-eat meals | 空 |
| missing_evidence | 2026-10-20 | 2026-10-21 | 320 | ready-to-eat meals | showers |
| road_closure | 2027-04-09 | 2027-04-10 | 320 | ready-to-eat meals | 空 |

“露营想法”可直接复制对应句子：

```text
normal:
Two people in CampMate Demo Region from 2026-11-06 for two nights, AUD 320. We want quiet and ready-to-eat meals.

budget_revision:
Two people in CampMate Demo Region from 2026-10-27 for two nights, AUD 245. We want quiet and ready-to-eat meals.

missing_evidence:
Two people in CampMate Demo Region from 2026-10-21 for two nights, AUD 320. We want ready-to-eat meals. Must have showers.

road_closure:
Two people in CampMate Demo Region from 2027-04-10 for two nights, AUD 320. We want ready-to-eat meals.
```

5. 保存请求草稿，生成需求摘要；核对日期、预算、资料快照，勾选阅读确认，再点击“确认并保存需求”。
6. 点击“开始规划”，等待阶段全部保存。刷新会继续读取实际进度，不应重新创建方案。

## 实际验收结果与操作

| 场景 | 本轮浏览器实际结果 | 接下来的操作 |
| --- | --- | --- |
| 正常 | Wattle Rest，AUD 251；物流、安全均 PASSED | 勾选最终确认并保存，显示“已保存的最终方案” |
| 超预算 | Wattle Rest，AUD 251，超预算 AUD 6，最终化禁用 | 选择“寻找费用更低的营地”并修改；自动显示当前新运行，版本2为 Moonlit Field/AUD231，剩余AUD14，随后可最终保存 |
| 安全证据缺失 | River Flat，AUD241；WEATHER=MISSING，安全 REVIEW，天气装备条件未知，最终化禁用 | Founder 批准禁用；保存“要求修订”及理由后 Camper 仍不能最终化 |
| 道路关闭 | Moonlit Field，AUD231；物流 PASSED，安全 BLOCKED/ROAD_CLOSED，最终化禁用 | Founder 批准禁用；保存拒绝理由后 Camper 仍不能最终化 |

Founder 登录为 founder / CampMate-Founder-2026!，通过“人工审核”队列打开当前方案。审核不替代补齐证据或解除封路。

超预算版本2保存后，在当前方案点击“重新评估”：新 run 保存两份新评估，复用同一版本内容，不重复生成行程；原最终快照显示“历史最终方案”，仍能读取原修订过程和评估。

正常场景停止并重启后，重新登录可回读已保存最终方案。退出后以 camper.b / CampMate-B-2026! 登录，访问 Camper A 保存的最终链接返回“方案不存在”，不泄漏方案内容。

## 证据与范围

[浏览器与 SQLite 记录](../evidence/a14-browser-check.json)保存真实 plan/run/version/assessment/final 编号及快照摘要。[正常最终方案](../evidence/a14-normal-final.png)、[超预算](../evidence/a14-budget-before.png)、[修订版本](../evidence/a14-budget-revised.png)、[历史最终快照](../evidence/a14-budget-history.png)、[缺失证据](../evidence/a14-missing-blocked.png)、[道路关闭](../evidence/a14-road-blocked.png)、[审核限制](../evidence/a14-road-review.png)、[用户隔离](../evidence/a14-owner-isolation.png)为本轮截图。测试数据库保留在忽略的 var 下，不随源码包交付。

本轮使用当前开发安装环境，尚未完成最新版 ZIP 的新环境安装、实际 Canvas 上传后下载、另一台电脑复核或数据包全部58条验收。规则演示不代表模型版 Agent 完成；最终提交验收仍按 ../canvas_submission.md 执行。
