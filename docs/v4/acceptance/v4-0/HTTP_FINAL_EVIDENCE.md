# HTTP 场景与旧 Web/N01 来源特定回执

本包只读整合真实运行原件，没有启动服务或重跑。JSON 内原件路径指向本机运行树，SHA-256
用于核对本次读取字节；这些绝对路径不是可移植附件。复制内容仅含白名单元数据、计数和
静态测试名称，不含私有异常文件、Cookie、凭据、DSN、请求头/正文或完整 operation key。

## 11 个 HTTP 场景

权威入口为 `HTTP_FINAL_MATRIX.json`，每项链接 `http-receipts/*.safe.json`，包含完整
source/tree、exact image ID、case/project/DB、实际 UTC、原生退出、清理、计数与原件 hash。

| 来源 | 成功 case | 场景 | 结论边界 |
| --- | --- | --- | --- |
| F1 `047a43d` | HTTP01、HTTP02D | lifecycle、capacity | 仅该来源实际结果 |
| R2 `c6abe05` | HTTP03B–07B | ack_body、ack_headers、security、same_key_reset、persona_stale | 仅该来源实际结果 |
| R3 `0636d3c` | HTTP08C–11C | bootstrap_restart、identity_scopes、credential_revoke、grant_revoke | 仅该来源实际结果 |

11 项 prepare/scenario/driver/outer 均 native0，清理确认通过且未强制终止；容器、网络、
登记存活进程均为 0，各自端口关闭，新卷保留。最终 tenant 行数与 active count 分开：
capacity/bootstrap_restart 成功执行原 `CapacityFacts(3,3,3)` 断言；其余场景未单独采集
active count，不由 tenant 行数推定活跃数量。最终 PG snapshot 中的 receipts/tombstones
是原字段计数，未改称业务总量。各项用全新 namespace/DB/key/私配/卷，没有重放失败 actor。

这不是全 11 项同 R3 源码验收，不将旧源码结果转签到新源码；等待独立验收，不表示
merge、部署、发布或真人验收完成。browser、自然 TTL、Full PG、Hosted 不属于本包。

历史失败独立保留在矩阵中：旧 PG exact ID 缺失预检；F1 HTTP02 启动边界失败（原因
UNKNOWN、异常 NOT_CAPTURED）；F1 HTTP03R probe1（内部异常 NOT_CAPTURED）；R2 HTTP08B
捕获 RLock TypeError（main 传播点已记录、内部精确抛错行 NOT_CAPTURED）。后续成功不改写
这些记录，也不把后来源码定位追填为旧事件。

## legacy Web24 与 N01six

`LEGACY_WEB24.safe.json` 汇总 F1 来源真实 read/write/items 原生报告，分别 7/10/7，
共 24 项 passed；三阶段 test_exit 均 0，实际 provider 调用均 0，独立清理回执确认资源
退出、端口关闭、三卷保留。先前 parent 路径失败日志另留 hash，未被后续成功覆盖。

`N01_SIX.safe.json` 汇总 F1 来源真实报告 6 项 passed、test_exit=0；清理回执资源退出、
端口关闭、卷保留，worker/sdk_provider 未启动。child exit 原记录含 -15/143 服务停止码，
没有改写成所有子进程退出 0。这两组回执未单独记录 parent native exit，故标
NOT_CAPTURED；custom reporter 未保存 retry count，亦不补填 0。

这 30 项是旧 Web/N01 在 F1 的实际证据，不代替 V4 browser 验收。M3 另三项 flow live
仍为 **NOT_RUN**，没有由 Web24/N01six 或 HTTP 成功推定其通过。
