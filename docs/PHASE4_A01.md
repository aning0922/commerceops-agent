# P4-A01 正式身份、入站与 T3 首批候选

2026-10-11，Asia/Shanghai。WTfd38/codex/phase4-feishu，从干净已核main9d97c19009d932036809ac3e2638bb68f4b7f765起步；原P3结案/资源/失败不重开。原[PR43](https://github.com/aning0922/commerceops-agent/pull/43)继续，A不合main、不关Issue、不合未审B。

## 实现与边界

新增正式BusinessGateway、配置verify-config及PG身份桥。平台identity以app/tenant/open_id映射到已有principal，FeishuActor与原WebActor均锁后校验当前身份/组织店铺角色，不伪造Web session。T1/T3核心提取同事务方法，原P3状态机/Worker/Graph/nonce/hash/完整确认集合/永久执行保持。inbox、原请求回执、任务/source/job或决定/resume同commit；event/message两层去重及原principal快照阻止身份重映射泄露回执。真实平台入口尚未启用，当前卡片绑定只接受offline_fake。

0008增量迁移仅加入正式receipt/card-binding两表及Feishu权限/decision_source分支；旧probe原字节、旧outbox禁发与unknown约束保持。共享Web OpenAPI保留21paths/22operations，DecisionReceipt来源扩web/feishu且文档与wheel asset同字节。真实Cookie/API定向证实共用principal跨入口可见/原决定/撤权，不增加SSO。前端/npm/Web产品源码未改。

Root授权的CI最小分区增量让test_p3/test_p4自然模块同属现phase3业务分区，旧existing仍全旧236/G1/G2；closed metadata、精确union、两job、每条300s/23min/25min/75s及根workflow不变。新增纯测试实际覆盖P4/未来Base文件、旧归属和完整pair验证，无第二调度器。

## 实际作者验证

完整命令/安全摘要见[p4-a01-author-evidence.json](contracts/p4-a01-author-evidence.json)，私有原始日志/镜像构建记录/每文件hash与ledger留本WT ignored0600目录。

| 层级 | 实际结果 | 限制 |
|---|---|---|
| 最终本地check | 1120offline/89.90s，358integration deselected，2旧SDK warnings；204mypy/285format/77MD0，原锁/Node24.21/frontend typecheck，95Python和Node漏洞0，三scope0 | 新source候选作者证据，不替独审/CI |
| 原337+新19真实PG | 实际collection356；旧236、全部101P3自然模块及19P4全pass，各组expected/actual/call-passed精确一致、union无漏重；最长203.710s | 封存Docker COPY镜像无host源挂载；不把之后的API/driver增量归给旧镜像 |
| 跨入口定向PG/API | 额外2pass/11.70s（command15.001s），Feishu任务→共用principal Web读取/原决定/同语义重复1resume；撤销后两个入口拒绝 | 与前356分记；全体358的精确同源CI仍待 |
| SDK/config | 12离线含typed503传播、真实SDKdispatcher/schema，verify-config明确secret_read/sdk_auth/pg/平台验证false | 无真实SDK认证/长连接/平台调用，不算human_feishu |
| 分区/pair | 59pure/0.68s及mypy4通过，后含于1120全离线 | 当前新CI实际双artifact另核 |
| 性能候选 | Linux aarch64/Python3.12.13：100本地commit+SDK ACK p95=0.024504792s/max0.146103292；20baseline分析含自有子进程启动/已核退出p95=0.770881250s/max0.780443708；idle配置1s实测1.002318167s、busy1.202142333s后下一点0.007012458s，忙时无并发scan；command31.574s | 当前只核20snapshot/report各1，预冻结sample IDs/显式完整gold facts及真实pendinginterrupt idle/busy补证待Root新批；不将候选统计写为M1性能全验收 |

无warmup排除。source=mock/model=not_used/approval=simulated_feishu；平台/provider调用0，未读旧secret/env/DB。每轮命令与源码镜像分层，不把partial或原失败改写成成功。

## 失败与窗口保护

首CLI直接文件入口ModuleNotFoundError scripts发生在任何Docker创建前，改为模块上下文运行；首18PG全部failed/41.71s已捕获去重IS NOT NULL参数$4 IndeterminateDatatype，text cast后第二18pass/44.03s。首旧组235pass/1fail/189.47s为新增两表未列入精确schema预期，后101+19not_run；只加新表名保留旧集合，后完整356通过。新principal-remap负例19中18pass/1fail/60.53s捕获真实guard漏比较，补原principal比较后19pass/44.57s。OAS首62pass/1fail为asset与文档不同步，修正后最终1120全通过。性能初驱动反复启动仍存活同OS进程，被TerminationRequired正确拒绝；改为已核退出自有child/单Worker扫描，不改backend死亡确认规则。全部负证据保留。

唯一自有project p4a-core-61e8f8f962ea，登记UTC03:19:10.740082→固定03:54:10.740082（北京时间11:19→11:54），所有重建/复验沿原截止不续期；每轮stop/PID0保留，最后实际UTC03:51:14.468721 stop0/runningfalse/PID0/保卷。没有hostport，测试临时DB按fixture finally DROP；额外post-stop metadata因启动余量不足直接拒绝、Docker0，不宣称role-bit-flags新读回或cleanup0。窗口已结束，不自行重启/延长。

## 已审与剩余

共享合同d039由Root独立P1复审无P1/P2，CI38107924795四job SUCCESS；Root核实际checkout080501824d4e8f9f106197b885576fe91a4516f2/parents9d97+d039/treec1915同源、337/G1三/G2六/两cleanup0及PG配对，四frontendJSON另由Root核。本回执只合同/继承回归，不覆盖本WIP主体。原d75 P1/两个旧取消run及pg-pair failure保留。

主体新freeze/独审/精确CI待；formal完整20SKU卡片、ready sender、IMunknown>1h、Base/R13–16与B审后集成、完整四组Web读DTO、确定性needs_clarification零写与安全new_cycle链接、真实pendinginterrupt性能补证/cleanCompose/真人平台/M1逐AC仍待。Root新D16范围承诺纳入后续接口，BC02跨轮/F02/B47与原地重算BC03不外推。D1/D30/300h/P450h、人工H/L not_reported保持；无Phase5/生产/Woo/扩权/新成员/新增paid。
