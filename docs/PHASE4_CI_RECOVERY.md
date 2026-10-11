# Phase4 610 CI只读诊断与最小runner候选

本候选parent为A02本地5ae94a2834096fa5eb80cf2e4524dc8abe909c9d；不宣称新CI已通过，不重跑610或新增PG/Web/平台。Root要求先源码/Fake校验和原Core独审，再精确新整体CI实证。

## 实际失败

610/CI38111683908的源与安全artifact、27callpass+1未结束/300秒exit137/后94not_run/cleanup0见[只读回执](https://github.com/aning0922/commerceops-agent/issues/40#issuecomment-6105516903)及[A02记录](PHASE4_A02.md#新c源610-ci失败只读核对)。最后card_only call仅运行约0.207s就到整模块原截止，没有assertion failed trace，不将其认作单node恢复挂死；原972unknown仍unknown。frontend real read失败具体node和原因仍unknown，public日志只安全汇总，无已上传failed-test明细；交原C单owner处理捕获/有限复验合同，A不写其产品/test/tooling。

## 唯一模块两子批

scripts/pg_diagnostic.combined_groups仅对tests/test_p3_approval_pg.py实际collection超过14时规范排序分14-node子批，本次原28为14+14。必须基于完整原collection，绝不从历史passed集合选取。为了安全artifact可精确复核，顺序采用原node ID完整集合的规范排序，不依赖丢失于safe export的原pytest插入顺序。每子批以完整node ID传pytest，不会传同整文件而误跑两遍28；其他自然模块和旧existing组原命令不改。保留原每命令300s、job25min、绝对deadline、75s cleanup以及完整G1/G2和停止证据。

paired checker使用同一runner既定group计划核子批label和每批expected=actual=callpass/exit0；原fullnodehash/selected/双scope来源、tools/锁/union去重一致、cleanup仍全部强制，不只相信总数/union相等。原module字段schema不扩、新job/诊断框架不增。未完成/失败任何子批停止后续并被pg-pair拒绝。

实际68offline/0.11s（旧59+新增9）通过：14+14完整29业务节点Fake union、第一/第二批超时后停止、actual漏/重复、同union的label/交换/合并/遗漏伪造拒绝；旧动态模块/全配对负例全部保留。专项Ruff/format通过，类型/文档/敏感扫描于冻结前补核。真实精确完整PG/Web/四CI为not_run；不能依据Fake通过放行M1。A03sender/BaseDelivery未提交源码与本runner候选分开，不混独审delta。
