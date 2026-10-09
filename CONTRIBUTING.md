# 小组协作

当前基线为 A-05 开发原型，实际完成范围见 [交付说明](docs/releases/a05-development.md)。共享接口的历史冻结记录与当前实施状态分别保留，阅读文档时以 [实施状态](docs/implementation_status.md) 为当前进度。

## 首次运行

取得私有仓库访问权限后克隆，在仓库根目录按 [README](README.md) 安装和启动。Python 3.12、Node.js 22.12+；依赖使用已提交的锁文件。每人使用独立的 `.env` 和 `var` 数据库，不共享服务器会话或数据库文件。

## 修改与检查

1. 从 main 建立自己的功能分支，按负责范围修改。
2. 使用项目虚拟环境运行 `python scripts/check.py`，检查后端、schema 和前端构建。
3. 提交实际实现与测试证据；PR 说明问题、结果和验证范围。其他成员检查后再合并。

共同 DTO/枚举/端口在 `backend/app/contracts`。更改契约需 A/B 对齐并重新导出 `docs/contracts.schema.json`。B 从 registry 注册实际 AgentPort 工厂；保持三种执行模式明确，不把 stub 当作已完成 Agent 的证据。

## 数据

`data/synthetic_demo` 为原始数据包完整副本，其中已知语义问题见 [数据检查报告](docs/synthetic_data_review.md)。修订包使用新目录和版本，通过 `.env` 配置，不覆盖原始包。测试中的 expected_* 属于独立 oracle，不能传给 Agent 生成输出。

不提交 `.env`、个人凭据、数据库、依赖目录或构建产物。公开演示密码仅用于本地 synthetic 开发；本轮未配置公网部署。私有仓库由所有者添加小组成员，本次上传不自动授予其他账号访问权限。
