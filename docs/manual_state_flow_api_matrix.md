# 当前应用接口覆盖清单

按当前源码的路由装饰器枚举，共 50 个应用接口；不把 Swagger、OpenAPI 和静态资源地址计入业务接口。未访问这些接口，不能仅凭页面无报错认定覆盖。

场景步骤见 manual_state_flow_tests.md。网页未调用的兼容／辅助接口必须按 S16、S18 在 Swagger 或浏览器 Network 重放补测。下面是覆盖计划，不是已经通过的远端验收。

| 方法 | 地址 | 场景 | 触发方式 |
|---|---|---|---|
| GET | /api/v1/health/live | S00 | 启动页／直接访问 API |
| GET | /api/v1/health/ready | S00 | 启动页／直接访问 API |
| GET | /api/v1/meta | S00 | 启动页／直接访问 API |
| POST | /api/v1/dev/interpret | S18 | Swagger 补测；正式网页不调用 |
| POST | /api/v1/auth/register | S01 | 网页 |
| POST | /api/v1/auth/login | S01 | 网页 |
| GET | /api/v1/auth/me | S01 | 网页 |
| POST | /api/v1/auth/logout | S01 | 网页 |
| GET | /api/v1/profile | S02 | 网页 |
| PUT | /api/v1/profile | S02 | 网页 |
| GET | /api/v1/plans | S18 | Swagger 补测；当前列表主读 trip-series |
| GET | /api/v1/plans/{plan_id}/versions | S18 | Swagger 补测；网页历史不保证调用此旧列表 |
| GET | /api/v1/review-queue | S12/S13/S15 | 网页（含审核员账号） |
| GET | /api/v1/trip-series | S04/S07/S19 | 网页；单系列 GET 须 Swagger 补测 |
| GET | /api/v1/trip-series/{series_id} | S04/S07/S19 | 网页；单系列 GET 须 Swagger 补测 |
| POST | /api/v1/trip-series/{series_id}/delete | S04/S07/S19 | 网页；单系列 GET 须 Swagger 补测 |
| POST | /api/v1/plans/{plan_id}/successor-requests | S07 | 网页更新本次出行 |
| DELETE | /api/v1/plans/{plan_id} | S19 | 网页删除测试方案 |
| POST | /api/v1/plans/{plan_id}/revise | S16 | Swagger 补测；兼容旧接口 |
| POST | /api/v1/plans/{plan_id}/reassess | S06 | 网页重新检查 |
| POST | /api/v1/plans/{plan_id}/revision-proposals | S05 | 网页修订对比 |
| POST | /api/v1/plans/{plan_id}/revision-proposals/{proposal_id}/decision | S05 | 网页修订对比 |
| POST | /api/v1/requests/{request_id}/plan | S03 | 网页开始规划 |
| POST | /api/v1/runs/{run_id}/retry | S17 | 网页；须已有可恢复失败运行 |
| POST | /api/v1/plans/{plan_id}/finalise | S04 | 网页最终保存／回读／PDF |
| GET | /api/v1/plans/{plan_id}/finals/{final_id} | S04 | 网页最终保存／回读／PDF |
| GET | /api/v1/plans/{plan_id} | S04/S05/S06 | 网页读取当前／指定运行 |
| GET | /api/v1/runs/{run_id} | S18 | 网页启动过程或 Swagger 直接读取 |
| GET | /api/v1/runs/{run_id}/progress | S03/S05/S06 | 运行时网页轮询 |
| GET | /api/v1/plans/{plan_id}/finals/{final_id}/pdf | S04 | 网页最终保存／回读／PDF |
| POST | /api/v1/preparation/cooking | S02b | 网页烹饪准备预览 |
| GET | /api/v1/request-context | S02/S03 | 网页自动读取 |
| GET | /api/v1/requirement-choices | S02/S03 | 网页自动读取 |
| GET | /api/v1/requests | S03 | 网页 |
| POST | /api/v1/requests | S03 | 网页 |
| DELETE | /api/v1/requests/{request_id} | S19 | 网页 |
| GET | /api/v1/requests/{request_id} | S03 | 网页 |
| PATCH | /api/v1/requests/{request_id} | S03 | 网页 |
| POST | /api/v1/requests/{request_id}/interpret | S03 | 网页 |
| POST | /api/v1/requests/{request_id}/confirm | S03 | 网页 |
| POST | /api/v1/requests/{request_id}/requirement-help | S14 | 网页（含审核员账号） |
| GET | /api/v1/requirement-help | S14 | 网页（含审核员账号） |
| GET | /api/v1/requirement-help/{task_id} | S14 | 网页（含审核员账号） |
| POST | /api/v1/requirement-help/{task_id}/decision | S14 | 网页（含审核员账号） |
| POST | /api/v1/requirement-help/{task_id}/adopt | S14 | 网页（含审核员账号） |
| GET | /api/v1/assistance-queue | S12/S13/S15 | 网页（含审核员账号） |
| GET | /api/v1/review/{plan_id} | S12/S13/S15 | 网页（含审核员账号） |
| POST | /api/v1/review/{plan_id} | S12/S13/S15 | 网页（含审核员账号） |
| POST | /api/v1/review/{plan_id}/assistance | S12/S13/S15 | 网页（含审核员账号） |
| GET | /api/v1/review-history | S13/S15 | 审核员历史页 |
