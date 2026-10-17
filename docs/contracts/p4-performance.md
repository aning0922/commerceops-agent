# P4 最小性能批冻结（执行前）

2026-10-11，Asia/Shanghai。Root已规定M1必要增量为100受控入站持久化至ACK p95<1s、固定20次完整离线分析p95<10s，以及恢复扫描≤30s/忙时下一调度点实延迟。40例/95%/真实provider三轮留Phase6/M3，原TEST_PLAN不删；M1不新增provider调用。

## 固定输入与方法

| 项目 | 执行前冻结参数 | 断言/统计 |
|---|---|---|
| 入站 | N=100、唯一event/message、p2p文本“分析库存并生成补货建议”；同principal可信Feishuidentity；真实自有PG、锁定SDK离线WS frame/本地ACK写替身，零认证/长连接/网络 | 每个ACK200必须在对应T1提交后；100持久inbox回执，逐次perf_counter；nearest-rank p95索引ceil(0.95N)-1、max，p95<1s；不混平台网络 |
| 分析 | N=20，inventory-v1/baseline完整fixture，每次独立task/job，同自有数据库依次执行；每次队列深度1、单Worker/单Graph | 从Worker启动到完整执行/停止计时（含启动/关闭，单独说明）；每task snapshot/report各1，p95<10s，无provider |
| 空闲扫描 | 自有PG真实Worker，固定recovery_scan_seconds=1（既有许可范围1–30），poll0.02/heartbeat0.1，两个实际调度点 | 实际间隔≤30s，报告配置/实测，不外推默认30s配置或供应商SLA |
| 忙时扫描 | 同一单Worker受控technical runner忙1.2s，超过本批1s扫描间隔 | Graph忙时零并发scan，结束后下一调度点实际延迟，保存busy_hold/delay；不冒自然故障或多Worker |

source_mode=mock、model_mode=not_used、approval_mode=simulated_feishu，平台/provider调用0。机器报告Docker Linux/architecture/Python版本，测试源/fixture与命令绑定；排队与执行范围明示。测试专用临时数据库逐项finally DROP，不读取旧业务库或秘密，现有自有PG窗口原绝对截止不重置，预留75s停止保护。若余量不足，本批not_run，不延长同窗口。

## 当前状态

性能驱动已在tests/p4_performance.py实施并实际运行，候选统计见PHASE4_A01及p4-a01-author-evidence.json；初版死亡确认拒绝保留。20snapshot/report各1已核，但Root要求的预冻结sample IDs/完整gold facts，以及实际pendinginterrupt的idle/busy补证尚待新有界批；当前候选调度计数不作M1性能全验收。无warmup排除，真实平台时延和真人观察另列。
