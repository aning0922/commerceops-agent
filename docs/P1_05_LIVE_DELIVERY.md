# P1-05 真实联调最小源码与脱敏证据快照

快照：2026-10-10，Asia/Shanghai。交付目标为`phase/1-integration`的`75efbbab3a13007636b94504b5ca94a06a7cd07f`。这是新的Draft联调交付，不替代此前离线PR14；G3 **incomplete**，Issue #6仍未完成，不记Phase1验收或main完成，不进入Phase2。

[公开核心与复现](../scripts/feishu_probe_harness/README.md) · [SHA映射](P1_05_PUBLIC_SOURCE_MAP.json) · [脱敏机器可读摘要](P1_05_LIVE_SUMMARY.json) · [Issue #6](https://github.com/aning0922/commerceops-agent/issues/6)

## 交付范围与证据区分

仅新增必要技术harness核心、合成回归、空配置与本快照，不改业务backend、migration、Worker/Graph、共享依赖锁、CI配置或权限。实际运行包、配置、inputs、原始SDK/PG记录与manifest均保留在ignored本地0600文件中，未上传。摘要中的SHA是整artifact校验值，不是用户ID、nonce或幂等键指纹。

公开源只做相对import、类型/格式及无运行副作用cast适配，规范化核心AST与冻结原版一致。原版曾实际运行；公开版本次只有离线测试。冻结原版与公开文件的whole-file SHA逐个独立列出，不把原版实际结果归给新公开路径。

真实样本仍`feishu_technical_probe`/`simulated_probe`，不表示真实业务审批或补货执行。官方文档解释、SDK源码验证、离线Fake、真实平台窗口与真实PG只读核对分开列证。

## 已有真实事实

| 样本 | 实际事实 | 仍不能推出 |
|---|---|---|
| W1 | 六消息回调；A私聊/群@各接受1，B/C各私聊/群@固定IDENTITY_DENIED；只读PG核对九映射及A各1 receipt/key、B/C各0 | baseline C在allowlist之外，不能证明空roles的原DAL拒绝；非@/bot/真人Toast/wire未据此通过 |
| M1 | 发卡1；B批准、同批准重复、相反拒绝冲突、同批准重复共4回调；原handler commit-return与success/info/warning/info DTO；PG一张卡/四receipt/四key完整字段与hash关联通过 | 不从四回调推四次独立真人意图，Toast类别与wire未观察；PG created_at是事务开始时间，不是因果顺序 |
| M1只读修正 | 第一版argv失败、已消耗attempt/空archive/noresult永久保留；新增第二版实际只读核对通过，parent1.030327秒 | 不能把失败第一版写成通过，也不重置失败历史 |
| M2 | 发卡1；B拒绝回调1，handler至DTO-ready24.190792ms；PG一张卡/一receipt/一key/九身份完整核对，parent0.973831秒 | 真人报告完整显示、提示出现和目测不到2秒，但Toast类别未观察，非精确<3秒；主控通知晚于退出，不能用通知推回调因果 |
| M3 | 首窗A批准1；既有卡callback-only消费者重启后A同批准重复、B相反拒绝冲突各1；原handler/commit-return均返回，DTO-ready24.336667/15.403833/4.015250ms | 只证明受控死消费者后再交付，不证明同事件重放或自然网络断线；末批PG实际核对M3三receipt/key完整通过；A首次1.5秒为人眼计时报告、工具/分辨率未报告，重复/冲突约1秒为目测 |
| C1 | 专用C卡1、C回调1，原DAL IDENTITY_DENIED、commit-return false、handler error DTO10.987042ms；同原连接实际启用C空roles及完整value/nonce/context/expiry资格见证1通过，原异常传播/回滚 | 末批PG实际核对零decision/receipt/key，与同回调见证共同通过；人眼“技术探针已拒绝”、计时1秒，完整渲染未报告；DTO不代替wire或精确客户端时限 |
| Base原尝试/R1 | 原创建响应unknown；R1 query-only list1 READ_TIMEOUT仍unknown，所有原键与失败历史保留 | 不推断无远端创建或权限根因 |
| Base R2 | list1 HTTP200/code0，唯一原创建行六字段/marker完整匹配，原PG技术行succeeded；parent9.588482/CLI12.076884秒 | 不表示当时已update，不证明长期幂等 |
| Base原键第二create | 用户明确批准后实际create1/list2/update0；同原UUIDv4键与payload；第二create HTTP403/code1254608，pre/post均原anchor唯一六字段匹配；parent10.601592/CLI12.364920秒 | 原runner保守replay unknown，不把完整查询改成HTTP0成功，不自动update，不自宣幂等Gate |
| Base默认update | 主控另派后update1/list1/create0；update READ_TIMEOUT、HTTP/code未知；一次受控list HTTP200/code0完整确认updated六字段/pending hash/原anchor，PGsucceeded；parent10.168843/CLI12.328133秒 | 字段恢复verified不等于update API ACK成功；原403重投历史不改 |

两次Base收口scope合计create1/update1/list3，未突破用户追加范围；原初次创建和两次恢复计数另保留。旧启动授权窗因不足完整30秒被拒绝，SDK/SQL/Docker0且attempt未消耗；后续由Root同范围新派发，不是执行者自行续期。每个已结束窗口都核对CLI/SDK实际回收、自有容器absence、四锁独立重获释放和barrier清理；Base没有启动WS或卡片。

[官方创建接口](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/create)错误码将403/1254608描述为重复提交相同API请求，与权限错误不是同一分类。这是官方文档解释；实际原runner unknown与原归档不改，独立Reviewer与主控已裁决其足够支持高层Base必要技术观察和unknown停止恢复，见[Issue6裁决](https://github.com/aning0922/commerceops-agent/issues/6#issuecomment-6083307234)与[Issue7同步](https://github.com/aning0922/commerceops-agent/issues/7#issuecomment-6083307807)，这不把ACK或原runner replay状态改写为成功，未延长token有效期假设或继续诊断。

实际结果已记录：[Base R2](https://github.com/aning0922/commerceops-agent/issues/6#issuecomment-6082073975)、[第二原键请求](https://github.com/aning0922/commerceops-agent/issues/6#issuecomment-6082936681)、[默认更新恢复](https://github.com/aning0922/commerceops-agent/issues/6#issuecomment-6083163142)。全部评论只含分类、布尔、方法计数与artifact摘要，真实标识与秘密未回显。

## 本Draft的验证与未完成项

公开适配核心合成回归161 passed；以`75efbbab`归档加公开文件的精确组合执行完整离线测试322 passed、79 deselected、2项SDK warnings，strict mypy82文件、Ruff及109文件格式检查通过。归档初次缺少项目内Gitleaks导致31项工具前置失败；复制现有项目工具后重跑上述完整离线测试通过，未改测试或全局环境。当前目录、索引和全部可达历史敏感扫描0命中，另核48个当前私有值在拟公开23文件及历史中0匹配；原版/公开版7组whole-file SHA和22项核心定义规范化AST均复核通过。Markdown链接检查在原checkout核26文件0错误；归档目录受父仓库ignored规则影响，自动枚举0文件，不把该次结果记为文档验证。Draft精确head正常CI待创建后实际核对。

原M1自然过期实际回调1：A/EXPIRED、commit-return false、error DTO-ready13.479209ms，人眼约1秒与“技术探针已拒绝”，计时方式未报告。原行锁READY/最多60秒实际成立，但主控通知未及时到达，锁内DB故障回调未取得，不能记通过；A确认发群普通非@消息，窗口无相应平台投递，不记backend过滤通过。该窗无新卡，CLI299.451475秒，SDK/清理核对通过。

一次末批app-role PG只读repeatable-read实际核对9身份/4卡全部binding：M1四receipt/key、M2一、M3三、C零且无决定；C同回调qualified witness另行关联通过。parent1.001995/CLI2.881196秒，无写SQL/锁定SELECT/SDK/API/WS；original once-only attempt已消耗，不重置。此核对发生在待协调的DB故障补测之前，不能表示未来动作后的PG状态。

DB单项补测已取得：原行锁READY后A/M3回调1，DB_FAILURE，handler/commit-return均false，DTO未见，观察耗时362.493417ms；客户端另报“出错了，请稍后重试”、计时1秒，工具/分辨率未报告，wire未测。原≤300秒窗口尚在收尾，补测后M3持久状态最小差异回读未运行，不改写为已完成。

仍缺：补测后M3只读差异证据、实际投递的非@/bot过滤，以及精确客户端Toast/wire证据。M3/C私有包保持`97154d8232b78de07b95be999345bc5a8b1347e24f990a623477c5f08672c53e`冻结；基线已消耗3张/cap3，C已消耗1张/cap1，未知发送槽不能重置。

现有group_at scope可能不投递非@或机器人样本；未投递不记backend过滤通过，不扩权限补样本。不扩T3/A01–A08/100事件p95或长期幂等验收；1254290/1254291显式重试与1255006特定分支本轮未触发、不得制造触发，不重新诊断#23（主控risk_accepted/not_identified已关闭）。Phase1最终独审/Gate/CI与合并由主控据完整证据裁决，Draft不得自行合并。
