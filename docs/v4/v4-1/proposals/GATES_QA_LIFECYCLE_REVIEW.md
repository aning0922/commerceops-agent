# GATES 独立审查：V4-1 owned lifecycle / HTTP / PG observer

日期：2026-11-04（台北）。结论：**HOLD_RUNTIME / NOT_ACCEPTED_FOR_EXECUTION**。本次只读审查候选代码，不运行 Docker、PG、API、浏览器、HTTP 或网络；未执行作者测试，也不签其测试结果。本文供 Root 和最终 Reviewer 核收，正式 QA 文件未改。

## 精确范围

审查 `3516e6bcda1b3badd18118b8805b5bc7ae62a03e` 的 owned_driver.py、owned_manifest.py、test_owned_driver.py、README，以及 `6b90491aaa4bfbc762754f01ff4cc3f4ceff66f6` 的 http_recipes.py、pg_observer.py、test_http_contract.py、validate_response.mjs、README。两个提交合计九个文件变更条目，README 重复计入，实际八个不同路径，约 1,200 行。引用行号均来自上述 immutable Git blob，不读取作者 WIP。

必要只读闭包包括同提交的 V4 public prepare/compose/adapter/Visitor/Supervisor、Compose 和 API launcher，以及已提交 API `b72331fa572d9d67ad176902283da721aeda4cf1` / `eb73a5eda3e94368009882ce437dc9e8760cec75` 的 effective/schema 差异。以下发现指当前精确候选，后续修复必须另给 SHA，不以本文推断已修。

## 阻断与具体整改

### 1. [P1] 宿主 source 与容器内 runtime 源码尚无可验证连接

`owned_driver.py:68–85` 的 handoff 只检查固定接口字符串和宿主文件存在；`164` 调用 public image verifier，该 verifier 仅检查 Docker image ID 等于 case ID。`211–225` 的迁移/grant/API、`301–312` 的 final facts 实际运行在 test image 内。原 Compose 没有把当前宿主源码 bind 到 `/app`，也没有读取镜像内 source/tree 或关键文件 manifest 与 case 对比。

因此完全可能 manifest 与宿主是新候选，Root 指定的 test image 却含旧源码或不同 grant/observer。固定 image ID 证明的是不可变对象身份，不能单独证明它装载当前候选代码。缺模块通常会失败，但一个兼容旧 image 仍可能运行成功并被贴上新宿主来源。

运行前须由 Root/API/QA 共同提供并核验 build/source/input provenance，或核验运行容器内不可变 manifest 与宿主精确 handoff 文件摘要；将 API、migration、grant、probe/observer 的实际执行代码绑定到同一被审来源。必须在业务动作之前拒绝错源 image。本文不要求任意 mount 源码或绕过原 no-build guard。

### 2. [P2] 跨访客 404 用例选择了可合法共享的 fixture 商品 ID

`http_recipes.py:401–413` 从当前商品列表首项取 ID，创建第二访客后直接要求该 ID 404。已核 `b72331f:effective.py:106–107` 使用 fixture 的原 product ref ID，并未为每租户重命名；新访客的同模板店铺可以合法拥有同 ID 的本租户 fixture 商品。正确隔离实现可能返回本租户对象 200，该用例会误报失败，也无法清楚证明越权。

应选第一租户独有的导入商品/不可共享对象作目标，并证明第二访客自己的正向读取正常，再要求第一租户独有对象拒绝；补授权店铺、其他店铺和角色边界。不要为了这个用例修改生产 fixture ID 语义。

### 3. [P2] 严格 DTO 校验之后仍漏核响应的 shop / organization 绑定

`http_recipes.py:182–186` 在完整 context 不同时只比较 tenant、principal、epoch、generation。组织或 shop 不同但格式正确的响应可以通过。Ajv 校验 UUID 类型和闭集形状不能补上该业务关联；`205–235` 的 facts 又仅按 tenant 聚合，无法揭露同租户跨店响应。

成功响应须另核请求 shop 等于响应 context.shop_id，组织等于当前授权组织，并结合 snapshot/source 与目标对象 shop 绑定。authorized_at 可按合同处理，不能用忽略整个 context 的方式避开时间差。需要真实跨店/角色负例，当前另一访客 404 不覆盖这些边界。

### 4. [P2] 标签/履约的“十次同键只一次”数据库证明不完整

导入路径 `273–282` 已有十次同 key POST、同 receipt 和 PG 三表各增一，属于有价值的局部候选。标签路径 `320–339` 虽十次检查返回 receipt 与最终 version，却未核 action receipt/event 行及关联效果只一次；错误实现重复追加事件同时返回旧 receipt 仍可通过。履约路径 `347–359` 只有首次提交与原 key GET，缺十次重放、最终状态/version、receipt/event/effect 增量和金额/库存不变核对。

补按原 operation/key/tenant/shop 定位的只读 PG 事实与前后对象投影。不得仅依靠 HTTP 返回相同 receipt 证明 DB 幂等。未知提交结果保持 UNKNOWN，不能自动换 key；当前 pending-before-POST 与失败后停止的方向应保留。

### 5. [P2] 新生命周期漏了启动前端口与隐式 env 文件检查

`owned_driver.py:163–193` 核镜像、IPAM、新空 namespace，随后直接启动 PG/API/Web。新 Case.validate 仅核端口范围与互异，没有原 public execute 中的 socket bind 检查；复用的是 helper，不会自动继承旧 execute 的端口拒绝逻辑。端口碰撞可能在已建资源后才暴露，也不能把任意旧监听器的 health 当新实例来源。

`228–240` 使用白名单 Web env，但 Next dev 会读取 checkout 中忽略的 `.env*`；clean Git 和五项 public inputs 不排除这些文件。Docker compose_environment 也保留 HOME，不能将白名单环境等同于已经核定本机 Docker context/客户端配置。

启动前拒绝已占 API/Web 端口及非批准 env 文件；明确 Docker context/socket 和工具路径的宿主前提。不给未知 listener 发信号。核当前新增配置只来自新 owner/runtime 目录，保留现有 API 不挂 owner 目录的隔离。

### 6. [P2] 成功清理结论未包含实际保卷身份，且 final facts 只有 schema

`owned_driver.py:341–357` 将当前 project 卷名列表写为 volumes_preserved，但 `372–379` 的 confirmed 不要求任何预期卷存在，也没有与已创建的 PG volume 身份比对。全部卷被额外移除时，空列表仍不妨碍 completed-pending-review。保卷义务不能由未使用 `-v` 推断。

`301–312` 调用 pg_observer schema --final；observer `60–78` 该分支只证明 revision/表集合/DB UTC，不证明业务末态。应记录真实创建的卷 ID/名称并最终逐项核存在；最终业务事实需按 case tenant/shop/key 采集，区分 schema-only 与提交/回滚证明。容器/网络/端口库存方向正确，但受管进程、卷、源不变仍应在父层完整收口。

## 已有保护及未证明事项

正向结构：新 project/DB/目录约束、source/tree/clean、五项 public input hash、固定 scenarios/images/UTC、至少 180 秒余量；prepare 新随机 0700/0600 配置，owner/runtime 分目录；config seal 和 execution.once 防正常重入；固定参数数组、no-build/no-pull、现有 IPAM/空 namespace 验证。HTTP Visitor 禁代理/redirect/retry，写前持久 pending；只读 observer 用固定标识、参数化 tenant、READ ONLY、5 秒 statement / 1 秒 lock timeout。未发现任意 SQL/任意 action/任意 shell 接口。

finally 对 writers stop、final facts、down 和库存分别捕获失败；采集失败仍继续 scoped down，不用杀 Compose CLI 代替 Docker 库存。这个顺序有合理基础。与此同时 checked() 的 timeout native 保持 None，没有真实 wait 的返回值；这应明确为 UNKNOWN，不能回填 0。新 execution CLI 的 print 也在最终 outer wait 之前，必须继续使用 QA 父监督分账，不能从 execution.json 存在推断 CLI native。

作者新增 owned-driver 测试只覆盖新文件准备和 handoff-before-Docker 拒绝，并未覆盖真实 PG/API/Web 启动、stop-finalfacts-down 的失败链、超时 one-off 清理、namespace 竞争、保卷和原生退出。HTTP 纯测只证明合成 CSV/XLSX 与实际 Ajv 的有限响应形状，不证明真实 HTTP/PG 语义。上述运行证据全部 NOT_RUN。

此外，执行前后缺少 lifecycle 自身的源码/工具/锁/input 重核；source 字段写入报告不等于结束后再次读取当前源。若由 Root 已审外层 wrapper 完成，必须在 handoff 中明确其精确代码与实际回执；当前不可直接声明该保护已存在。

## schema 与 runtime 接缝：另列 HOLD

当前审查的 `6b90491:test_http_contract.py` 把合成 validator fixture 固定到 b723 schema，运行时 validate_response 却从实际 checkout 读 API_CONTRACT。eb73 已新增 ImportJobRef 的必需 data_revision，以及 parser/schema 版本字段和 EMPTY_DATA issue。最小 UNKNOWN/job-null 测试继续通过不能证明这些新增成功 DTO 已对齐。必须补 eb73 或后续核准来源的 preview/job/confirm 成功与失败金标，更新 schema provenance 后再审。

在 `6b90491`，runtime_handoff.json 实际不存在；`3516e6b` 的预留 v41_database.py 也不存在。这是 fail-closed 的明确阻断，当前没有因它启动资源。不要创建占位 handoff 把 file-exists 当 router/grant 接入证明。API owner 必须先提交并独审真实 0025、grant/verify、create_app router、schema 导出和 fixture 兼容，再绑定新 runtime image/source；最终具体路径若不同应窄改合同与驱动，而不是套旧 0024。

`dashboard_same_source` 当前 `http_recipes.py:441–445` 仅比较 data_revision，相等并不证明完整 KPI 算法、fixture digest、时区窗口或明细金标。import 用例的 product_count 增一有局部价值，但不足同源全部 KPI。catalog 的订单商品关联仅确认返回相同 ID，没有验证 SKU/数量/金额/同快照。Shell scenario 在 manifest 中允许、HTTP main 中却明确抛 pending，不应拿它启动后才确认缺浏览器 recipe。非法导入用例验证 INVALID/409 与三个计数不变，只覆盖一种负价混合文件，不涵盖事务内部故障、竞争、解析预算、其他 epoch/shop 对象或更新既有行的无部分效果证明。

结案要求：QA 按以上 findings 提交精确修复，API 补 runtime/schema 接缝，Root/Astra 重新核源码与资源窗口后再进行新 owned 实测。本次不改正式 QA、规范 helper、业务代码或 scanner；结果不代表运行验收、合并、部署或发布。
