# V4 0024实际schema/provision/owner helper独立审查

日期：2026-11-03（Asia/Taipei）。**结论：HOLD_SCHEMA_COMPONENT，2 P1 / 1 P2。** 当前不能以设计c4接受或作者offline检查替代实际数据库守卫；先修以下精确缺口，再交新SHA复审。未运行PG，不把静态路径推导描述成已执行反例。

## 精确源与范围

candidate `86ca8b8c9262f1bbce9f5b28605a754f42b07a76`；tree `86037545c708c216f8865aa679ea8597e31350dc`；parent `c6c9f43412f7d727b23ddae6a0a12052a2f5c4bd`。

9文件：新增 `backend/migrations/versions/0024_v4_demo_foundation.py`、`backend/src/commerceops/infrastructure/v4_demo_seed.py`及已释放七旧测试精确兼容。只读精确Git对象及必要旧schema/grant定义，未读后续HTTP/会话WIP，未改作者源码/测试。唯一新增文件为本报告。以下M=0024迁移文件，S=v4_demo_seed.py，行号绑定candidate。

作者Ruff/type/33 offline诊断是转交事实，本轮未执行或独立重现；PG/API/Web均NOT_RUN。缺后续API不计本切片缺陷。旧139根因UNKNOWN不变。

## SQL-01 [P1] receipt只验证自身算术，未证明对应实际effect

**位置：M:301–337，尤其314–337；S:90–94授runtime INSERT receipts/events。**

session/tenant更新时要求存在匹配receipt是单向保护；反向的receipt INSERT只核owner/retain/path/key、存在一个事件及自身before/after算术，没有要求该receipt after epoch/generation对应本次session/tenant实际状态变化。

具体静态可达反例：已有有效tenant/session均epoch0/gen0，不修改它们；runtime插入reset receipt（before0/0、after1/1、正确owner/key/hash/retain）及匹配demo.reset_committed事件。新receipt的算术和事件存在检查都满足；所有deferred事件先查的当前t/s仍0/0且互相一致，没有比较receipt的1/1与当前effect。session未UPDATE，因此301分支也不触发。于是能提交“reset COMMITTED”记录而没有reset/绑定轮换。

这会使后续原key恢复/审计把不存在的效果当成功；它不是RLS缺失的一般性抱怨，而是本次显式授runtime append权后承诺的receipt-effect数据库不变量未落实。设计I:214–215要求对应before/after和effect共同提交，不能只靠未来Python调用者不出错。

**最小修正：** 建立双向、同tenant/session的effect↔receipt/event约束。新receipt必须有实际合法状态转换依据，不能仅对自己声明的数值做运算；不能借历史旧receipt签新更新。可采用精确transition绑定/当前事务内对应变更验证，但不能给runtime自设GUC免验。处理一个事务多控制步骤时须定义明确支持或拒绝边界，勿用宽泛“存在某一回执”代替。本报告不要求另起框架或新状态机。

未来新owned PG反例至少包含：只插receipt+event不改状态；只改状态不插receipt；错误before/after；旧回执重用；正确create/persona/reset/logout保持成功。当前先代码修订后Root再安排运行。

## SQL-02 [P1] event缺少复合owner/tenant/receipt及种类绑定

**位置：M:132–143的独立FK、261–339的commit_guard；事件trigger装配446–450。**

所有event INSERT确实触发commit_guard，但该函数只按NEW.tenant_id检查“这个tenant当前正常”，没有event专属分支比较NEW.owner_session_id/receipt_id对应的tenant与session，也没有核event种类/代际等于receipt。三个独立FK只保证引用各自存在。

具体静态反例：两个合法租户A/B，插event tenant=A、owner_session=B、receipt=B且选一个尚未使用的event_kind，或对A的reset receipt添加persona_changed种类。A当前binding正常即可通过前半guard；因TG_TABLE_NAME不是receipts，314之后整个receipt分支跳过。UNIQUE(receipt_id,event_kind)不保证关系正确或没有额外错误事件。原receipt在此事务未变，不会自动再次检查。

**最小修正：** event INSERT时严格核receipt.owner_session_id/tenant_id与event三者相等、epoch/generation一致，以及operation→事件kind精确集合（create允许且必须session_created+seed_materialized；其他只对应一种），拒绝不匹配/额外事件。适当复合FK可提供结构保护，语义guard仍需核种类/代际。不得依赖QA事件计数来替数据库保护。

未来PG负例：跨tenant owner、跨tenant receipt、错generation/epoch、错误kind和额外kind；正向两create事件与单控制事件保留。这与SQL-01相关但可单独触发，不能只修receipt当前状态比较就关闭此项。

## SQL-03 [P2] JSON缺字段可经SQL NULL穿过拒绝谓词

**位置：M:317–319（receipt req.method），M:357–364（provision method/path及body结构）。**

例如request_text包含正确path、body.request_key/fixture_version，但省略method；`body->>'method'<>'POST'`得到NULL。其他拒绝条件为false时，IF整体NULL而非true，PL/pgSQL不会执行拒绝。receipt guard相同method写法也不会补拒绝。顶层/body未统一验证完整精确字段，`canonical_request`表约束只要求是object及hash正确，因此缺字段/额外字段可被作为规范请求接纳。

**最小修正：** 对必需常量用IS DISTINCT FROM，先验证object形状/精确键集合与各operation body、非null必需字段，再核path/key/fixture/expected epoch+generation与receipt值。不要只修method一处而继续依赖NULL敏感的整体OR表达式。错误内容应23514安全固定消息，不能回显原body/hash秘密。

未来负例：method/path/body缺失或null、错误类型、额外顶层/body字段、expected字段与receipt不符；正确canonical请求不变。本项不是要求HTTP接口提前交付，而是现有可被runtime调用的SQL受限入口自身校验。

## 其他已核事实与边界

### signature / SECURITY DEFINER /旧权限

M:342–346的13参数类型/顺序与S:24、108–110 GRANT签名一致；provision唯一SECURITY DEFINER，search_path固定pg_catalog,business，全部表schema限定，无输入对象名/dynamic SQL。迁移M:452–457对三函数PUBLIC revoke，十表PUBLIC revoke；owner helper先核当前revision/PG17.11/vector0.8.7以及新十表与旧org/credential/session真实owner（S:27–51）。它不自动提供owner连接。

provision在函数内取得cap advisory锁和bootstrap UPDATE锁，DB clock后重核key/expiry/fixture，UUID由函数生成新org/shops/personas；没有按调用者指定旧organization执行UPDATE credential的分支。新token hash与部分既有hash交叉拒绝，私有/公开生成与完整resolver仍需后续服务审查。凭据编码由原web_credentials CHECK进一步约束；最终auth_version在scope/grant/credential登记触发器之后读取（M:407）。

S:84–111显式只授新表/列/函数，不修改旧grant-runtime。原commerceops_app已有SELECT web_credentials及其他历史写权，不能称新角色或每tenant DB权限隔离；新receipt/events INSERT因此尤其必须由SQL-01/02的guard保护。没有因此建议扩大旧auth权限。

### 不可变、epoch与GC

M:195–259禁止TRUNCATE和不可变表UPDATE，bootstrap key/consumed单调、tenant期限/epoch及session绑定轮换检查存在；改变bound要求旧bound已revoked、generation+1且新nonce/digest。commit guard核tenant/session期限/epoch、两shop/三persona、当前bound元组/旧credential和shop来源。但这些前半正向检查不抵消上述反向receipt/event缺口。

GC仅owner helper显式调用（S:114–172），锁指定tenant/session与排序principals，要求reserved marker、retain到期和无business_tasks；撤旧bound/credential/principal，按依赖顺序删该tenant新行，旧base对象保留。普通runtime仅有overlay DELETE，不可GC receipt/event等；删除guard核实际current_user与表owner及retention，不接受用户GUC。

需要在后续真实PG验证：deferred guard执行角色权限、GC完整旧业务依赖/删除顺序、到期未清理与bound状态、受控并发撤权锁顺序。当前没有实测这些。未因“后续尚未运行”另报P1，但本候选不能据offline33项称全部guard已可用。

### 七旧测试diff

逐项阅读全部diff：`test_postgres.py` head和精确集合加十表；`test_p4_first_create_negatives_pg.py`当前增量集合/空表/诊断计数26→36，旧before字节比较及0013历史段保留；migration diagnostic同步fake表/head并把0024排除在固定d97历史闭包外；F02精确79→89；history/read_reply当前revision同步；M2 backup继续要求当前新head不是0018可备份schema。未见删旧ACL、Checkpoint字节、不可变拒绝或将精确集合改为包含/大于等于。

旧测试更新符合ROOT已释放的机械范围，不等于新迁移实际成功。无workflow/锁/旧auth/database.py修改。schema仅新增十表且迁移不自动seed/grant的入口安排符合设计。

## 交接

请作者按SQL-01/02/03修实际守卫并提交新SHA；不由Reviewer代改。Root可继续安排无依赖的纯组件工作，但此实际schema component目前HOLD，不签PG迁移/回归准入已接受。若Root另批专门诊断窗口，应明确仅取失败证据而非通过验收；本审查没有开窗或执行任何真实资源操作。原设计接受、旧失败及UNKNOWN均保留。

## 8e9d87a增量关闭：SQL-01/02/03

candidate `8e9d87ae500f5fab22131ab6b76d7f5bb1d505a6` / tree `ef242d0ffbc82d0553b0678b600ffbcfbdb285dd`，相对86ca逐项审查。结论：**ACCEPT_SCHEMA_COMPONENT，原SQL-01/02/03均CLOSED_AT_STATIC_CODE_REVIEW_LEVEL；本次所审范围无未关闭P1/P2。** 原首审HOLD与三反例保留；不是PG运行通过，是否开新owned窗口由ROOT决定。

### SQL-01

M:92新增内部last_receipt_id，:178–182以receipt/session/tenant/after epoch/generation复合deferred FK约束指针；receipt自身也以owner_session/tenant复合FK绑定。M:299要求每次session控制改变指针，旧bound撤销/新bound/nonce/digest与generation轮换仍强制；logout允许字段变化被单独限制。

M:359–375将queued session NEW与最终row核对，并用NEW.last_receipt_id定位精确receipt，绑定OLD before/NEW after及操作类型；create也必须对应0/0的session_create。M:394–418反向要求新receipt就是当前session指针、after与真实session相等、retain与tenant相等、规范请求正确及精确事件数；reset还要求当前tenant overlay为空。因此原“只插receipt/event、不改session effect”会因指针/after不匹配拒绝；仅换指针不轮换身份或借旧receipt背书亦有对应限制。默认deferred路径明示同session一事务一控制，不依赖全表“存在某行”。

新增PG测试源码:221–261覆盖无effect receipt、无receipt effect、错误before、旧指针和同事务双控制；:200–218正向创建/一次persona转换。这里只核已写断言，不宣称数据库已执行拒绝或正例通过。

### SQL-02

M:147–151新增event→receipt的id/owner/tenant/epoch/generation复合deferred FK；M:381–391对event独立INSERT核完整关系及operation→kind允许集合。receipt M:402–412核create恰2/其他恰1且要求对应主事件、create附seed_materialized；UNIQUE(receipt_id,event_kind)保留。历史receipt未重新INSERT时，event自身仍校验，不能通过跨tenant独立FK或错误kind绕过。

新增PG测试:264–291特意使creation receipt成为历史后再尝试跨owner/tenant、错kind/代际append，测试预期包含CheckViolation或FKViolation；没有只靠当前receipt trigger证明历史事件安全。实际SQLSTATE与异常时机待新owned PG核。

### SQL-03

M:206–245的v4_demo_request_valid限定wrapper和每operation body为object、必需/精确keys、key/fixture/persona类型与值、expected整数语法和before值；method/path采用IS DISTINCT FROM。receipt/provision两调用均NOT coalesce(...,false)，不再由SQL NULL跳过拒绝。helper是无DB访问/无提权IMMUTABLE函数；S:107–108显式授runtime EXECUTE，迁移对PUBLIC revoke；provision原13参数签名没有改变。

新增PG测试:294–334有正常reset请求及missing/null/错类型/多字段/错CAS；纯结构测试只核DDL/函数文本与SQLAlchemy参数边界，不代替该PG矩阵。runtime列权限仅按新增last_receipt_id及只读validator函数精确同步，没有追加旧凭据/旧org权限。

### 其他增量与运行界限

独立AST计数仍为十表；原七兼容测试及旧权限保护在本增量未放宽。bound.created_at与Demo有效窗新增检查。设计附录记录last_receipt双向绑定/事件/请求校验；另将已绑定bootstrap即使未consumed也不复用于新key，明确用户再次进入才签新匿名owner，保留旧300秒原key权利，符合ROOT登记Q18细化；不是已实现HTTP分支的证明。

五个新增integration节点被作者报告已收集未执行，本审查没有运行collect或PG。特别deferred trigger实际执行权限、约束插入/删除顺序、canonical错误SQLSTATE、真实cap/撤权锁序、owner GC及旧M3全量回归仍须实际窗口验证。PG测试使用新owned夹具构造低权app及真实provision，随机测试密钥不持久到报告；测试正向路径不等于实际API CSRF/Origin/身份resolver已交付。本接受不包括未提交HTTP/会话源码，不复用历史719/33offline代签。
