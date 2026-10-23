# 原 v2 unknown 的完整恢复合同

本合同对应 Root 统一登记 Issue39#6219180668 / PR43#6219181443。总 cap 为 8 Agent
有效小时（A5.5/Core1.5/Root1，总额内协调）；旧 6h 及此前实际用量继续累计，机器等待单列。
原 300h/P4 50h、日期、人工 H/L、18 页冻结与旧失败均不重置。

## 原事实与目标

原源码 0461184 / 私有封存 ea67ff51 的实际 T6 已提交，原 key GET 已成功。
后续 SDK 五次均 returned/HTTP200/code0，Update/Create/IM/provider 均为 0；
原 v2 delivery 为 unknown、attempts1、INCOMPLETE_READBACK，旧 parent/once 已 SPENT。
原始 wire 未采集。三 nullable 缺省的离线反例只能证明兼容性缺口，不能认定实际唯一根因。

同原 task/item/record/v2 outbox/key 完成一次恢复，不重复登录、审批、关闭、Create、DM
或工作流执行。旧 SDK9/Create1、后续 SDK5/update0、旧提交和失败证据完整保留。
真实资产当前 HOLD；仅新 owned SQL/角色/once/进程与底层 Fake HTTP 可用于准备验证。

## 准入与持久一次性

沿用 terminal_update 和已核 queued-v1 来源，新增可选 recovery_of。旧分支继续拒绝已有
delivery。新分支必须锁定原 delivery/outbox，核对完整 v1 快照/hash/record 锚、唯一原生 T6
item/request/audit/semantic hash/v2 outbox、原任务与审批来源及当前 operator/approver/resolver
身份权限。原失败授权、Gateway/Worker 完整终止、SDK window 与完整 ledger 均绑定 hash。
仅原一次 unknown/attempt1、update0、无未结束 SDK call 的五次成功账本可准入。

独立授权 once 在读取 Secret/Factory 前提交；dispatch once 和旧 delivery 完整状态在同一次
领取事务内持久化。once 键绑定原 outbox、原失败窗口和 recovery_count1，任何失败/kill/冷重放
均不复活，也不生成第三个恢复窗口。原授权、SDK、parent permit 和 attempts 不删除或重标。

数据库原 unknown 保护保持：领取为 sending/attempt2，last_operation=reconcile；该操作从完整
对账开始。独立 audit 明确记录 read_first_conditional_update 授权。无 SQL pending/reset、迁移、
trigger/grant 放宽。原普通 unknown 的 next_operation 仍仅为 reconcile。

## 读前与写后

内部 ProjectionRequest 的 verified_v1 仅由原 store 从已验证 PG 锚提供。只在远端严格 version1、
唯一同 item/原 record 时使用该完整 v1 比较基线；仅补齐它明确为 None 的三个 nullable 字段。
Quantity/SyncVersion 继续仅接受非 bool int 或规范十进制字符串，所有 float 均拒绝。
完整 v1 的全部 15 列（含原 UpdatedAt）必须相等，不能只凭不可变字段允许更新。

单入口先读：完整同原 record v2 则仅结算，Update0；完整可信 v1 则同 record Update 至多1，
随后必须完整、唯一、同版本、同内容 v2 读回。缺必需字段、错 record、重复、不可变/终态/内容
差异、未来版本、未知写结果均 HOLD，不 Create 或盲重发。写前再次核当前角色/身份、T6/hash、
Worker lease、Gateway、stop 和原截止，权限/意图行锁持有至 SDK 方法返回。已知拒绝也不续 once。

诊断仅保存固定 stage/reason、已知字段名和形状布尔值；不记录 wire 值、外部标识、URL、token
或原响应。最终 PG 快照在全部 writers 停止/数据库连接排空后、PG down 前，以同一只读快照导出
原/当前授权、dispatch、完整 SDK window/call 行和 DB UTC；最终判断在 cleanup 后。

## 验证与释放

必须以同冻结公共源码与私有父入口，在 0015/0016 两 schema 从真实失败态完成整链、负例、
并发、中断、冷重放、native child reap 与完整清理；SQL/权限/once/key/退出不 Fake。
原 Core 整包独审后由 Root 释放一次精确新 CI，保留原 518 节点及新增节点、G1/G2/Web、
35/33 分钟总限额、300 秒命令、75 秒 CI reserve 与 60 秒 cleanup。

真实阶段另由 Root 绑定对象、最终 source/private/review/CI 与具体 UTC，PG<=600、SDK<=300、
reserve>=180、arm 剩余>=480；新 SDK auth1/bot1/table2/field2/list4/update1，总<=11。
Create/IM/provider/新业务0，unknown 或失败即停，不自动续窗。A 不自行 push、触发 CI、修改 PR
正文或合 main，C 产品和四 consumer 保持原 owner。

## 当前开发验证事实

首轮新 owned 四 PG 节点实际通过：0015/0016 各覆盖 nullable+规范数字串 v1 恢复与完整 v2 零写
结算；包括四种错误 hash、原生准入、原失败历史保留及 cold replay SDK delta0。
pytest 223.82s，tests/cleanup exit0，容器/网络0，卷保留。该轮之后加入并发与中断验证，
第二轮684.53s为10pass/2fail；两失败是测试循环覆盖child变量，误将竞争Worker交给Gateway
停止器，原生业务/冷重放断言已结束。该失败及资源完整清理事实保留，不以作者解释改签通过。

修正后12节点按完整collection规范顺序四项一组，先准备本命令选中节点的独立DB历史，使原
30秒backoff自然经过，未改时钟或next_attempt_at。三组实际CLI119.071/103.384/108.805s，
JUnit各4pass；总12pass/cleanup0/容器网络0/保卷，含双schema准入后认证中停止、写前/写后
停止、发前撤权、并发与cold SDK delta0。最终组合源码、同冻结私有完整outer、独审、精确CI
及真实同步仍待，不提前宣称通过。

CI完整collect530=518+12；拟沿原helper将34项p3_pg、2项evidence与1项pool完整模块移至
quality；两个原quality组按原完整模块合并为20与12项，新恢复三组各4项独占300s。
两分区372+158=530、交集0。旧38912191768命令/实际节点日志作为容量依据，既定35/33/300、
approval14分片、原G1/G2/Web和cleanup保护不变。新owned两个合组实际20/20与12/12通过，
CLI151.623/128.303s，cleanup0/容器网络0/保卷。本地时长不承诺Hosted必过；旧Hosted时间与
新本地测量分列，最终容量判断交Root，不以旧518绿代签新源码。
