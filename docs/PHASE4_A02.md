# P4-A02 固定澄清、IM transport 与真实性能补证候选

基线A01+B `545137d014e38ea8ac387139334e92095837dc85`。Root独立Core源码无P1/P2；该CI38110473072实际quality/phase3/pg-pair SUCCESS、frontendFAILURE，whole failure。Root核两安全PGJSON实际4e37/tree9c02/parents9d97+545，完整358=236+101+21精确passed；Core自身另轮只有collect21+pg-test exit0，actual count/time与rolebits not_verified保留。frontend具体为原generated read schema未同步web/feishu enum，真实24未跑；C修复/独审/精确新CI待，不能据三绿放行。

## 本批完整切片

合法operator歧义输入只持久inbox、原回执及1:1固定澄清reply，业务task/report/plan/approval/execution/item/Base/job零新增；原UUIDv4及template/reason绑定不可变。角色校验先于分类，同event/message十次返回同reply，补参数必须新完整请求/new key才创建既有T1。禁止P2 intent任务或模型调用，不建设跨轮会话。

0009窄迁移、ClarificationDeliveryStore及正式BusinessIMSDK构造固定text请求/原UUID。既有Worker维护回调依次P3 reconcile与澄清一步，无第二消费者；发送前重验当前identity/principal/role/shop/app/tenant/allowlist/群范围。持久sending后才network，ACK+原chat/message_id才sent；未知任何年龄均保留unknown、不回pending/换键。sender默认disabled，真实client只能后续Root受控运行层提供；当前Fake验证不称平台送达。

正式JSON2.0 renderer消费可信P3 frozen content/hash，全部20SKU、数量、来源窗口/规则/期限、完整未知集合与专用动作均披露；普通动作/联合动作同原T3 DTO，无probe_id/actor/客户端数量。5pure实际使用已冻结twenty collector→真实report→freeze_plan，不假技术卡。平台卡片渲染/真正outbox发送仍待。

## 作者实际证据

[安全摘要](contracts/p4-a02-author-evidence.json)含每个expected/actual/call集合；原日志/plugin/镜像/217源码hash/metadata/网络收尾留本WT ignored0600。

| 层级 | 实际结果 | 范围 |
|---|---|---|
| 新PG定向 | 30pass/56.65s（command59.113s）；8澄清+21原Gateway/API+1revision/schema，plugin集合完全相同 | 初始封存COPY image sha256:837ef8dc375827af79eb7f35c49a2d41bab88efda6f8a2b25aa3424f3ffa393f，无host源挂载 |
| 唯一Worker补充 | 1pass/6.84s（command9.5s），真实原Worker维护一步发送、无业务job，完整plugin expected/actual/call | SDK transport/entrypoint维护注入增量另层；不冒原30包含此新增node |
| 性能100 | 100本地T1 commit+锁定SDK ACK，p95=.013282208s/max.014578125s，平台网络不计 | 模拟SDK/真实PG，非human/wire |
| 20完整分析 | 预定p4-baseline-01～20、inventory-v1/baseline，无warmup排除，全部state completed/source_complete/单SKU/完整gold字段match；p95=.805768959s/max.855712708s | 含每个自有child启动/实际退出，排队深度1，provider0 |
| 真pending扫描 | idle旧before_ready child实际kill/reap+显式termination确认，官方持久interrupt实修ready .037212458s；busy同Worker真waiting CP延后1.201138s，下一点.045891333s修ready，忙时无并发scan | 固定scan1s配置；不是自然故障/默认30s SLA |
| IM/Card纯合同 | 7IM原UUID/真实ACK/429/5xx/code/错chat/timeout不重试，2窄合同、5全20/篡改拒绝 | client全Fake，不读secret/构建认证或发送平台 |
| 全check | 1284offline/88.94s、367integration deselected、2旧SDK warnings，221mypy/305format/80MD0，锁/Node24.21/typecheck/95Python与Node漏洞0/三scope0 | 文档收口后专项链接/扫描另核，完整新源CI/独审仍待 |

低权限实际读回rolsuper/rolcreatedb/rolcreaterole=false，temporaryDB0、revision0009。p4a02-6f2bcbc812bf/ownerP4-A02-WTfd38，原UTC04:22:39.414183→固定04:42:39.414183；最后04:33:01.385807 stop0/falsePID0，04:34:09正常仅own down0、network_removed/保卷/保image-private、不-v/prune/改pool，未续期。旧A01窗口/失败原样保留，没有新增paid/平台或旧secret/env/DB读取。

## 后续门槛

本A02为作者候选，新的源码独审/精确CI待。C未经Root解除P1不可合；根CI新6（或最终实际集合）由A唯一owner在审后集成添加一行run_before_cleanup，保原24/native200/锁/截止。正式通用card/result/Base outbox及v1unknown→T6v2安全对账/锚定/顺序更新、完整四读组、20runtime固定collector接线、干净Compose与真人窗口仍待，不以本批签M1。Stage/原50h/300h、人工H/L not_reported不重置。

## 新C源610 CI失败只读核对

[CI38111683908](https://github.com/aning0922/commerceops-agent/actions/runs/38111683908)实际quality SUCCESS、phase3/frontend/pg-pair FAILURE，不能由545历史PG成功放行。A按Root指令只读日志/artifact，未重跑、取消或新开PG；[Issue40实际回执](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6105516903)。

phase3原approval模块UTC04:30:39.156631开始，04:35:39.158912触达原300秒command截止，exit137/timed_out/stoppingtrue。artifact11691727583的zip SHA256=3bd3e6dbbacd74ee3fa16ecd4c97a43481d9e5c6c7a0ca7e1e29f54991703c8d；实际checkoutf54a8f2c07001458e52205fbca9597fa2624b43d/tree4141093f7a1b07e071005417cd17c4d7f4176be0，full358/selected122；首模块expected28/actual28/callpass27，后94not_run，cleanup0/stoppingtrue。没有phase-end failed或assertion trace。最后card_only的setup2.328s通过，04:35:38.951883 call start后约0.207s遇整模块截止，无call end，不将它记assertion失败或猜恢复根因。27个已结束call共226.133s（其中真实期限用例67.515s且pass），28个setup共66.683s；原300秒门槛不改。

frontend step6 locked schema/build/Mock/B04成功，step7 real read批test_exit1/invariants_passedtrue/PGfalsePID0/failure_category=null；write/items未跑，require/upload skipped，无公开具体Web failed node，根因unknown保持。新的重大未知CI及后续窗口范围由Root裁决；当前仅完成A02源码/离线收口，不以新CI超时修改既有Worker/锁/测试/截止。
