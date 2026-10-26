# M2 新自有资源与 Web 消费交接 v1

本文件仅冻结运行前的交接约定；**当前 not_started，无实际资源、账号、端口、UTC 或任务ID预填。**
它衔接[业务合同](p5-m2-v1.md)与[备份合同](../M2_BACKUP_RESTORE.md)。最终组合源码、必要入口
独审和所有权核定后，由 A 在原1800有效分钟总额内执行，B 仅消费本批私有交接。
原 P4/旧 PG/原密钥与真人平台窗口不参与；不得用历史 private launcher 或旧事实目录启动。

## 1. 所有权与同源

A 是唯一 Woo/PG/API/Web/Worker 启停和数据库 owner；使用现有 Woo lab serve、固定 Compose、
当前 API/单 Worker 入口与原部署角色机制。B 不 seed、不建 PG、不启动第二 Worker，不新建父编排。
B 只为现有 live Playwright 消费者增加 M2 配置/用例选择，保留 owned-listener/build核验和原保护。
所有B consumer必须在启动Woo/PG、产生审批TTL之前完成源码冻结、独审并普通合入A候选。
A是本轮父生命周期唯一owner，沿现有受限入口按预先固定argv直接启动consumer子进程，
传本次私有目录，等待native退出、收集结果并关闭子树；运行中不依赖Root/A/B聊天通知或接力。
source与restored两个消费段均在开资源前确定，B不在资源已开后补代码或手动接续运行。
交接的 source_sha/tree、lock摘要、构建ID、进程入口hash、实际镜像ID须对应同一最终 A 组合源码；
任何不符停止消费，不靠前端文案或旧CI补签。原 Mock/M1消费批次保持独立。

一次运行使用新随机目录0700及文件0600。新 source PG 与新 target PG 是不同项目/卷；
target 的每个恢复目标数据库须先核为空并登记，拒绝覆盖。源与目标卷保留，临时单测卷删除另记。
生产业务与checkpoint版本同源；0018源登记、当前权限和角色按实际SQL核验。
备份不包含 Woo MariaDB；Woo本次合成manifest/平台ID/只读EXPECTED独立保存。

## 2. B 可消费的私有文件

继续使用 `COMMERCEOPS_B02_PRIVATE_DIR` 指向**本次新目录**，以及
`COMMERCEOPS_LIVE_WEB_URL` 指向本次 Web origin。名称沿用不意味着复用旧资源。
`COMMERCEOPS_WEB_BATCH` 使用 B 新增的窄 M2 消费分支，不冒称旧 C09/B03/B04 全矩阵已执行。
M2 分支 owner 固定为 `phase5-M2-live`，不沿用旧 `phase4-C09-Web` owner 字符串。

| 文件 | 内容与约束 |
| --- | --- |
| `window.json` | `schema_version=p5-m2-live-resource-v1`、owner/run_id、source_sha/tree、build_id、api_origin/web_origin、api_pid/web_pid/worker_pid、started_at_utc/stop_at_utc、cleanup_reserve_seconds、phase、source/target资源身份、当前active数据库别名、A的stop owner引用 |
| `consumer.private.json` | 已审consumer commit/入口hash、固定source/restored argv与cwd、允许的环境变量名、各段上限、原生PID/进程组及输出文件；只引用私有目录，不能传密码值或运行任意命令 |
| `web-accounts.json` | 仅本次合成operator与approver账号；两个不同principal。沿用现有角色键与login/password私有形状。window与公开索引只引用文件，不嵌值或秘密文件hash |
| `m2-source.private.json` | org/shop UUID、binding_id、source_config_version、config_ref、profile、anchor_day D、币种/时区、来源metadata文件引用与非秘密digest、独立EXPECTED/金标文件引用与hash；Woo key/secret/CA/pin只作私有文件引用，不给浏览器 |
| `m2-facts.private.json` | phase和原创建request文件引用；仅从真实API/PG回执填入task/source_task/report/snapshot/facts_hash、plan/version/hash、approval及其原expires_at。nonce/decision原字节只放私有文件引用，不手写或前填 |
| `m2-results.safe.json` | B自己的原生退出、实际检查项、源码/窗口绑定、响应schema验证、原键重放结果；不含密码、Cookie、Authorization、完整原始payload、trace/HAR |

兼容现有 `web-facts.json` 等消费者输入时，仅做这些真实对象的窄字段映射，不能造多个Mock场景
指向同一目标充数。对象未实际产生前必须为null；消费者不得把null当作可审批/可恢复。
每阶段文件均绑定同一run_id与原stop_at_utc；文件更新只是事实快照，不延长窗口。
固定顺序为A发布source_ready→调用source consumer并等待0/采集/关闭→A核PG并停writers/dump/restore
→发布restored_pending_verified→调用restored consumer并等待0/采集/关闭→A最终核账清理。
失败或UNKNOWN在对应阶段停止并保留原回执，不等待聊天接力决定是否换键重发。
新窗口具体端口/UTC由A运行前登记，B须用当前listener PID与BUILD_ID复核，不能仅探测端口通。

账号/状态只在本消费者内存持有；关闭trace、video、HAR和密码截图。登录值沿现有DOM赋值方式
避免测试调用日志记录秘密，离开登录页清空输入。401/403仍不自动刷新登录或重发。
restore阶段明确创建新browser context并按当前授权登录一次，不把前阶段内存会话当恢复凭证。

## 3. 新正向来源与业务定位

来源固定为 `woocommerce_test / positive-v1 / CNY / Asia/Shanghai`。D在prepare前明确指定，
不晚于本次实际店铺日期；now为D当地00:00，订单为其前七个完整自然日。serve/reseed不滚动D。
A先在新source PG登记真实org/shop UUID，再把该shop UUID显式交给已审lab prepare的shop-id；
服务端source版本与非秘密digest登记后不可变，不用运行结果反造EXPECTED。

独立金标为4 SKU（2 simple、2独立库存变体）、4 pool、4订单行、0退款、4库存；
L/R/S=3/7/2，需求D=10/4/5/2，Q=100/40/60/19，总219，税前CNY994，四项inbound均未知。
每项金标按positive.json的analysis_gold及实际平台ID映射定位，不能按报告排序猜对应SKU。
实际source采集必须与独立EXPECTED完整比对，不只比较计数；UNKNOWN/质量与执行性保持分开。
不能从mixed样本删除坏SKU拼正向金标。报告来源以冻结provenance为准。

本次首个目标任务优先由B在真实Web上完成N01/显式确认/原请求准备与一次创建；A只准备资源和
绑定，不预建另一个相同目标任务。初始phase=`source_ready`且业务ID为空；B保留原key/字节与
API回执，A核真实PG后发布`source_pending`事实，供双方只读定位。同一目标保持一任务对。
若创建响应UNKNOWN，仅按原key查询回执，不换键/重发/新建样本。容量或来源失败则HOLD。

## 4. 同一原任务的备份与恢复顺序

1. source_ready：核当前operator权限、Woo capability/version、N01零业务写入及严格DTO；
   完成一次明确Web创建。等待原Worker产生真实Woo报告与pending审批，核金标、四在途确认要求，
   记录原task/thread/plan/version/hash/nonce/expiry/报告绑定；B此时只读，不批准。
2. source_pending_verified：B完成源只读定位后退出写入页面，A停止并reap API、Worker与其他writers，
   核全部writer已退出，再采集含DB UTC的原绑定与官方checkpoint。源PG此段仅供一致dump。
3. dump：实际pg_dump覆盖同库business/checkpoints及必要依赖，保留native exit/长度/SHA；
   正文仅私有0600。随后源PG停机保卷，确认不会与任何恢复目标同时写业务。
4. target_restored：预置新target owner/app角色，用原生pg_restore恢复到已核空的新目标；
   不二次seed、不SQL修checkpoint/job/approval/once、不改原期限。核实际schema/revision、
   owner/app最小grant与完整原绑定；新DB认证独立，Web nonce/CSRF密钥按原私有引用保持。
5. restored_pending_verified：启动同源API/单Worker，B显式换到该阶段的新context登录，先只读复核
   同一task/report/plan/version/hash/expiry及原四项假设。API/Web origin若复用端口，必须原PID已停，
   window更新为新PID与目标别名；不从旧listener或内存缓存取证。
6. explicit_resume：当前授权/期限/20秒重观测允许时，B在原版本上逐项确认四个在途假设并明确批准
   一次；保留原decision key/字节。核一execution、4唯一内部项、Q219、审计/官方checkpoint及
   API/Web读回，随后用原key核十次重放零新增。外部sender始终关闭，真实飞书/paid新增0。
7. stop：各writer→API/Web→PG/Woo按登记顺序停止，取得native/reap/PID absent/listener及
   容器/网络清理回执；源与目标卷保留。清理UNKNOWN不写资源0或通过。

拒绝矩阵不能消耗或破坏正向待审批对象来换取通过。错误hash/nonce/角色、过期/撤权与恢复失败
分别记录；必要时从同一冻结dump恢复到另一个预登记的**空负例数据库**，与正向目标串行停写，
不复制新业务样本或改变原TTL。过期必须等待真实时间，不能SQL改expires_at或冻结DB时钟。
需要的负例目标/权限变更和原件定位由A在运行前的具体资源登记中列明，B不自做DB控制。

## 5. 容量与停止

计划采用不超过3600秒的新owned总窗口，清理预留至少180秒；具体T0/绝对stop运行前登记。
已审lab serve支持300–3600秒，原90秒自身cleanup保持，A在总窗口预留点提前停止消费者。
源码build/依赖准备可先离线完成，不挤占真实报告/restore验证机会，也不重开旧serve窗。
新场景审批TTL计划在首次创建前显式配置900秒并全链保持，以便单列自然过期反例；
若容量核算不足，调整新的运行计划后再创建，不改既有计划期限或续旧窗口。
所有消费者应在剩余时间不足其原测试上限加cleanup reserve时拒绝开始；失败不盲重试。
此计划值不是已测容量、RPO/RTO或通过承诺，真实量测与完整Gate仍待实际回执。
