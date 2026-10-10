# A-10 源码包与本地部署准备

本阶段交付可校验的源码包、锁定依赖安装入口与隔离 HTTP 启动检查。完整 B 工作流、业务四场景、修订数据、其他成员复核和全组 Done 仍待完成；这些工具不改变当前 stub 模式。

最终交付必须通过 [Canvas 下载后演示验收](canvas_submission.md)：以实际下载附件为基准，从干净目录安装并完成浏览器业务演示。当前源码包仅完成部署基础验证，尚不是已通过此验收的最终演示包。

## 获取和安装

从 GitHub 克隆源码，或将提供的 ZIP 解压到独立目录。Windows 使用 Python 3.12、Node.js 22.12+（本机验证版本 22.20.0）。ZIP 中不包含依赖、数据库、个人配置或 Git 历史，首次安装需要网络。

在解压后的 campmate_app 中运行：

```powershell
py -3.12 scripts/setup.py
.\.venv\Scripts\python.exe scripts/check.py
.\.venv\Scripts\python.exe scripts/dev.py
```

也可以用 Python 3.12 的完整可执行路径运行 setup.py。此入口不修改 PowerShell 执行策略。原 setup.ps1 调用同一 Python 安装器。安装器建立本地 .venv、按 requirements.lock 安装后端并在本目录 editable 安装，前端严格 npm ci；仅在 .env 不存在时复制 .env.example。

scripts/dev.py 仍启动 127.0.0.1 的开发服务器，默认 8000/5173，支持指定两个端口。已有端口占用时报错，不终止他人的服务。Ctrl+C 停止本次两个子服务。生产构建通过不代表已部署公网网站。

## 生成与核对源码包

只在 Git 项目仓库中，确认源码已提交且工作区干净后运行：

```powershell
.\.venv\Scripts\python.exe scripts/package.py
.\.venv\Scripts\python.exe scripts/package.py --verify var/releases/实际生成的文件名.zip
```

也可用 --output 指定新的 ZIP 路径。包来自 git archive HEAD，包含 PACKAGE_MANIFEST.json：commit、提交时间、默认模式、交付范围及每个源文件的 SHA-256。ZIP 旁另有 .sha256 文件。拒绝未提交源码、覆盖已有输出、运行时/个人文件、非法路径和 symlink；验证时核对完整文件列表、重复条目及每个 digest。校验保证完整性，不替代可信来源或发布者认证。

原始 synthetic 包保持原样，修订包以后使用独立目录和版本。本包明确没有真实 B Agent 或完整规划成功流程。

## 隔离 HTTP 启动检查

在安装好的解压目录中运行：

```powershell
.\.venv\Scripts\python.exe scripts/smoke.py
```

默认使用独立的 18010/15180 端口，可指定 --backend-port 和 --frontend-port。每次建立新的 var/deployment-smoke-* 文件夹，保存报告、服务日志与独立数据库。不会改默认 var/campmate.sqlite3 或已有 .env。

检查实际前端 SPA/module 文件、API proxy、健康状态、stub 功能开关、公开演示登录、Profile、明确字段请求、摘要和确认、同 key 回读、未登录/另一个 Camper/Founder 的访问守卫、migration 1–5、服务重启回读、注销和关闭后端口释放。不会插入伪装为 Agent 输出的方案。

脚本通过唯一 stop marker 协作关闭自己启动的 supervisor 及子进程；不按端口或进程名称终止其他服务。该脚本测试 HTTP 及持久化，不执行浏览器 JavaScript，也不证明真实推荐、规划、审核/最终化完整业务链路已完成。

## 验证记录

2026-10-10 已实际验证：解压 622dd779edf1 的源码包，在无依赖/配置/数据库的独立目录运行 setup.py，随后 check.py 的 129 项测试、schema 与 Vite 构建通过；smoke.py 的 7 项 HTTP/持久化步骤全部通过。报告与限制见 [实施状态](implementation_status.md)。验证后只补交付文档和证据，运行脚本与业务代码未改；最终 ZIP 的 commit/checksum 见包内清单与相邻 .sha256。

干净目录与新依赖在同一 Windows 电脑上验证，不能称为已在另一台电脑或其他系统完整部署。A-05 至 A-09 的 Linux CI 只验证测试/构建，不替代这些运行检查。
