# M3 日报原请求键只读回执 v1

这是日报创建与模板追问已有功能的恢复入口，不接通用P3回执，不扩调度管理或新写操作。
本片只改DailyOperations/daily_http/http_models、独立OpenAPI资产和必要测试；
主API/Worker/database装配、DDL及原POST受理语义均保持。

## 1. 固定GET路径

| 操作 | 路径 | 必填query |
|---|---|---|
| 日报创建原键查询 | `/api/v1/daily-reports/requests/{request_key}` | `shop_id=UUID` |
| 追问创建原键查询 | `/api/v1/daily-reports/{task_id}/questions/requests/{request_key}` | `shop_id=UUID&report_id=UUID` |

task_id是原日报父任务，report_id是原提交追问明确绑定的报告；request_key沿用原POST的UUID。
两个端点均GET，成功200，走原Cookie session/current auth和operator shop scope。
每次重验当前身份、组织、店铺和requester；追问额外绑定同owner父日报/报告/同conversation。
已认证但无scope、非本人、对象不存在、错误shop/父task/report均404 RESOURCE_NOT_FOUND；
当前session失效仍按原边界401。响应保持Cache-Control:no-store。

查日报时只查daily_report/p6-daily-report-v1的顶层request_key；
查追问时只查daily_question/p6-daily-question-v1的input.request_key。
同UUID可在两个operation中各自受理，GET不会把两种回执混为同一项。
查询从原持久business_task/normalized_request及原冻结report读取，
不读取当前source文件、Woo秘密、模型或平台，不重采、不创建task/job、不运行answer。
配置轮换或当前metadata不可读，不把原受理任务换绑到新来源。

## 2. 实际DTO与OpenAPI

响应真实类型为 `application/daily/http_models.py::CreationReceiptRead`，
外层schema_version=p3-web-v1、identity_mode=session、server_time、trace_id、receipt。
receipt为以下两个strict/extra=forbid类型的标准anyOf；operation literal区分两分支。
生成资产为docs/backend同字节 `p6-daily-read-v1.openapi.json`，
由原 `python -m scripts.export_daily_schema` 直接导出，无手补schema约束。

两个分支公共必填字段：

| 字段 | 类型/含义 |
|---|---|
| schema_version | p6-m3-web-v1 |
| lookup_status | accepted，找到原持久受理记录，不表示业务报告已成功 |
| operation | daily_report.create或daily_question.create |
| request_key/shop_id/task_id | 原键、当前授权店铺、原受理任务UUID；追问task_id即question_id |
| state | queued/analyzing/completed/failed/needs_attention |
| failure_code | 原安全failure code或null |
| request_hash | 原POST持久的64位规范请求hash，不是对当前表单重新生成的证明 |

DailyCreationReceipt另外必填source_config_version与business_day；它们来自原受理任务。
business_day是受理时解析出的业务日，原POST省略/null时返回当时确定的日期，不用现在的昨日替换。
其request_hash沿既有受理语义：shop、原输入day（可null）、source_version和固定daily-rules-v1；
它不等于任意JSON.stringify(CreateDailyInput)的sha256。

QuestionCreationReceipt另外必填parent_task_id/report_id/snapshot_id/content_hash/facts_hash/question。
question是原kind/metric_key/finding_id规范三键，未用目标显式null；request_hash为原QuestionInput规范hash。
这些引用与原冻结report交叉核对；返回的是原请求，不从“最新报告”重建。

## 3. UI的UNKNOWN处理

POST响应丢失或结果未知时，保留原operation、原request_key、原shop和追问父报告引用，用上述GET续查。
找到后核对返回operation/key/shop及原报告/问题引用，显示原受理状态并导航同task_id；
不得将原键回执误称当前已修改表单的受理结果。同key异文的原POST仍409，不被GET改写。

**GET 404不证明原POST回滚或从未提交**：事务可能仍在提交、权限已变化或本次绑定不匹配。
UI继续保留UNKNOWN，提供只读续查，不自动生成新key或重发POST。
503同样保留原键和UNKNOWN；401按原session流程恢复当前身份后查同原键，不能把重登录当重发授权。
GET不进行写重试，也不把没找到原任务变成空成功/新任务。

## 4. 作者证据

实际receipt/Read纯批 **49passed/1.83s/native0**，包括两分支wire、缺父引用拒绝、operation隔离、
实际ASGI query UUID解析及strict模型响应序列化；这些不冒充身份/SQL证明。
固定Node24.21.0和项目锁定Ajv8.20.0+ajv-formats，使用真实CreationReceiptRead serialization schema，
Draft2020 strict实际 **11cases/native0**：两合法分支、两错误operation、五缺引用、非法hash、额外actor字段。
全仓Ruff通过、format560文件通过、mypy434文件通过。
新增PG模块仅collect **2节点**：同UUID不同operation/原回执/缺来源文件/GET业务计数不变与错误绑定404；
当前session撤权401、重新登录后scope不足404。实际PG均NOT_RUN，待Root新owned组合验证。

开发中首mypy发现纯测试receipt字典值类型推断过窄，显式dict[str,Any]后通过；
未改模型strict策略或SQL/来源权限。7848的两P2修正/原S3 HOLD及Root95PG实际结果另行核收，
不以本片纯测试覆盖或提前预填通过。
提交前changed-content扫描首1项为测试UUID字段的链式比较，非秘密值；改为等价UUID集合断言，
不改扫描规则、豁免或编码隐藏内容。
