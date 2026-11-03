# V4-0 身份桥接、SQL、ACL 与事务专项方案

状态：`DESIGN_READY_FOR_SPECIALIST_REVIEW`。这是 B 授权下的开工前专项设计，不是实现或 PG Gate 回执。2026-11-03，Asia/Taipei。

## 1. 精确基线与本次范围

- 指定工作树：`/Users/aipuli/.codex/worktrees/commerceops-v4-foundation/commerceops-agent`；branch `codex/v4-foundation-20261103`。
- 原业务源码 M3：`952e6246deb01ec763f2541d9f316753987744f3` / tree `43e4e732824e23b991660a4f7882ba8f5a265df1`。
- B 文档基线：`fa96764cf2b8e3ab9adbb579b764f600a7d17e60` / tree `10d9fad5c7457382d178086bedcab460aa01904d`。
- ROOT 释放的 CSV 机械规范化已普通 ff 合入：`eb82c9d626c210e8e982ba3d8889a4ffdd088c99` / tree `e4a9a7d51907828121ef709549ff00e0afd0a230`；不修改 A 冻结历史原件的语义。
- 本次仅写本文件和 `SEED_SPEC.md`，不建迁移/业务代码、不运行测试或 PG。旧 M3/Harness/README 工作树不动。
- 后续迁移准确为 `revision="0024_v4_demo_foundation"`，`down_revision="0023_p6_copy_drafts"`。新增十表；迁移只建空 schema，不自动 seed/grant，不占用第二新 revision。
- V40-03→04 是有限同步 PG 请求。无每 tenant Worker、Graph、jobs、cron、真实模型/embedding、飞书、Woo 或外发。六场景只是 seed refs。

本设计落实 `../baseline/{DOMAIN_SOURCE_CONTRACT,PERMISSION_DEMO_CONTRACT,API_EVENTS_CONTRACT,UI_ROUTES_CONTRACT}.md` 和 `v4-public-openapi.json`；其 PENDING/NOT_STARTED 是 A 时点，当前 B 授权以 `../IMPLEMENTATION_AUTHORIZATION.md` 为准。旧 139 根因 UNKNOWN、原失败及受测 SHA 不变。

## 2. 已定实现选择

1. 一 DemoTenant 对应一个新 synthetic organization、两个独立 shop UUID；三 persona 各有独立 principal/identity/不可公开 credential。访客之间不共享已授权业务行，只共享 immutable fixture JSON。
2. 公开 cookie 名 `commerceops_v4_demo`，Path `/api/v4`；值类型为 `v4b_`（bootstrap）或 `v4d_`（active）加 `secrets.token_urlsafe(32)`，总长 47，只有 SHA256 存 PG。cookie HttpOnly、SameSite=Lax；HTTPS 必须 Secure；显式 owned loopback `local_http` 才可 Secure=false。
3. 原 `SessionStore._session` 仅接受 43 字符 `[A-Za-z0-9_-]`（`web_sessions.py:173–175`）。V4 bearer 前缀使**改 cookie 名后仍形状拒绝**；V4 hash 也绝不写进旧 `web_sessions.token_hash`。
4. 私有 bound WebSession 的 id、独立随机 token hash、p3 CSRF digest 由服务器生成；明文 bound token 永不存储/发布/记录，生成 hash 后即丢弃。API 只通过 V4 resolver 构造 bound WebActor，不调用旧 `SessionStore.authenticate(public_bearer)`。
5. 不改 `web_sessions.py` 或旧 `WebActor`，不新增通用免密码登录。新模块 `v4_demo_sessions.py` 在同一事务复制**完整认证谓词**，再调用旧 `actor_guard`/`role_scope`；完整谓词不是只调用 actor_guard。
6. 旧 `commerceops_app` runtime 角色沿用，旧 grant-runtime 权限字节不扩大；新十表和唯一受限 provision 函数通过独立 `grant_v4_runtime` 显式授权。它仍是旧既有业务 runtime，不能宣传成全库 read-only。新组织/credential/scopes 的首次登记经窄 SECURITY DEFINER 函数，只能创建未存在的新 demo 对象，不能修改既有账号/组织。
7. 一个 tenant 只有一条稳定 DemoSession owner；persona/reset 保留公开定位 cookie，轮换 current bound WebSession、CSRF nonce、generation，reset 额外推进 epoch。旧 WebSession 必须在同一事务被撤销。30 分钟 absolute deadline 永不延长。
8. reset **保留当前 persona**（包括无业务 shop grant 的 restricted_admin）；不退回 operator，不恢复被 owner 撤销的 grant。tenant/shop/principal IDs 保留，overlay 清空；fixture 不变。新 bound 只在该 persona 全部当前 credential/identity 仍合法时建立，否则整笔拒绝。
9. 幂等 owner 是稳定 `DemoSession.id`，不是会变的 persona principal。receipt 与 effect 同一事务；通过有效当前 session 只读恢复最小控制回执。退出/到期/撤权后没有恢复特权，bootstrap 的单 key/300 秒例外除外。

## 3. 0024 的完整表集合与 SQL 形状

以下 SQL 是待独审后实现的 DDL，尚未执行。表名/键/字段为本切片冻结输入。全部对象在 `business` schema；所有时间 `timestamptz`，所有时钟判断用 `clock_timestamp()`。receipt.committed_at是本事务记录的DB时刻，只有该行成功COMMIT后才对外称COMMITTED；不是另行捕获的WAL物理提交时间。hash 为小写 SHA256 hex；canonical 采用项目 `canonical_bytes`，不另造浮点编码。没有扩展 M3 source_mode 或 TWD 至旧 DTO。

```sql
CREATE TABLE business.v4_demo_fixture_versions (
 version text PRIMARY KEY CHECK (version='v4-demo-seed-1'),
 generator_version text NOT NULL CHECK (generator_version='v4-seed-generator-1'),
 canonical_content text NOT NULL,
 content jsonb NOT NULL,
 content_hash text NOT NULL CHECK (content_hash ~ '^[a-f0-9]{64}$'),
 snapshot_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK (jsonb_typeof(content)='object'),
 CHECK (canonical_content::jsonb=content),
 CHECK (octet_length(canonical_content)<=1048576),
 CHECK (content_hash=encode(sha256(convert_to(canonical_content,'UTF8')),'hex')),
 UNIQUE (version,content_hash)
);

CREATE TABLE business.v4_demo_tenants (
 id uuid PRIMARY KEY,
 organization_id uuid NOT NULL UNIQUE REFERENCES business.organizations(id),
 fixture_version text NOT NULL,
 fixture_digest text NOT NULL,
 reset_epoch bigint NOT NULL DEFAULT 0 CHECK (reset_epoch>=0),
 created_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 retain_until timestamptz NOT NULL,
 UNIQUE (id,organization_id),
 FOREIGN KEY (fixture_version,fixture_digest)
   REFERENCES business.v4_demo_fixture_versions(version,content_hash),
 CHECK (expires_at=created_at+interval '30 minutes'),
 CHECK (retain_until=expires_at+interval '24 hours'),
 CHECK (revoked_at IS NULL OR revoked_at>=created_at)
);

CREATE TABLE business.v4_demo_shops (
 tenant_id uuid NOT NULL,
 organization_id uuid NOT NULL,
 template_key text NOT NULL CHECK (template_key IN ('v4-shop-a','v4-shop-b')),
 shop_id uuid NOT NULL UNIQUE,
 PRIMARY KEY (tenant_id,template_key),
 UNIQUE (tenant_id,shop_id),
 FOREIGN KEY (tenant_id,organization_id)
   REFERENCES business.v4_demo_tenants(id,organization_id),
 FOREIGN KEY (organization_id,shop_id) REFERENCES business.shops(organization_id,id)
);

CREATE TABLE business.v4_demo_personas (
 tenant_id uuid NOT NULL,
 organization_id uuid NOT NULL,
 persona_id text NOT NULL CHECK (persona_id IN ('operator','approver','restricted_admin')),
 principal_id uuid NOT NULL UNIQUE,
 identity_id uuid NOT NULL UNIQUE,
 PRIMARY KEY (tenant_id,persona_id),
 UNIQUE (tenant_id,persona_id,principal_id,identity_id),
 FOREIGN KEY (tenant_id,organization_id)
   REFERENCES business.v4_demo_tenants(id,organization_id),
 FOREIGN KEY (organization_id,principal_id)
   REFERENCES business.principals(organization_id,id),
 FOREIGN KEY (organization_id,identity_id,principal_id)
   REFERENCES business.identities(organization_id,id,principal_id)
);

CREATE TABLE business.v4_demo_bootstraps (
 id uuid PRIMARY KEY,
 token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[a-f0-9]{64}$'),
 csrf_digest text NOT NULL CHECK (csrf_digest ~ '^[a-f0-9]{64}$'),
 key_version text NOT NULL,
 created_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 create_request_key uuid,
 consumed_at timestamptz,
 CHECK (expires_at=created_at+interval '300 seconds'),
 CHECK (consumed_at IS NULL OR
   (create_request_key IS NOT NULL AND consumed_at>=created_at))
);

CREATE TABLE business.v4_demo_sessions (
 id uuid PRIMARY KEY,
 tenant_id uuid NOT NULL UNIQUE REFERENCES business.v4_demo_tenants(id),
 bootstrap_id uuid NOT NULL UNIQUE REFERENCES business.v4_demo_bootstraps(id),
 creation_request_key uuid NOT NULL,
 token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[a-f0-9]{64}$'),
 persona_id text NOT NULL,
 principal_id uuid NOT NULL,
 identity_id uuid NOT NULL,
 bound_web_session_id uuid NOT NULL UNIQUE REFERENCES business.web_sessions(id),
 auth_version integer NOT NULL CHECK (auth_version>0),
 auth_generation bigint NOT NULL DEFAULT 0 CHECK (auth_generation>=0),
 reset_epoch bigint NOT NULL DEFAULT 0 CHECK (reset_epoch>=0),
 csrf_nonce uuid NOT NULL,
 csrf_digest text NOT NULL CHECK (csrf_digest ~ '^[a-f0-9]{64}$'),
 key_version text NOT NULL,
 created_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 FOREIGN KEY (tenant_id,persona_id,principal_id,identity_id)
   REFERENCES business.v4_demo_personas(tenant_id,persona_id,principal_id,identity_id),
 CHECK (expires_at=created_at+interval '30 minutes'),
 CHECK (revoked_at IS NULL OR revoked_at>=created_at)
);

CREATE TABLE business.v4_demo_receipts (
 id uuid PRIMARY KEY,
 owner_session_id uuid NOT NULL REFERENCES business.v4_demo_sessions(id),
 tenant_id uuid NOT NULL REFERENCES business.v4_demo_tenants(id),
 operation text NOT NULL CHECK (operation IN ('session_create','persona','reset','logout')),
 request_key uuid NOT NULL,
 canonical_request text NOT NULL,
 payload_digest text NOT NULL CHECK (payload_digest ~ '^[a-f0-9]{64}$'),
 epoch_before bigint NOT NULL CHECK (epoch_before>=0),
 generation_before bigint NOT NULL CHECK (generation_before>=0),
 reset_epoch bigint NOT NULL CHECK (reset_epoch>=0),
 auth_generation bigint NOT NULL CHECK (auth_generation>=0),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 retain_until timestamptz NOT NULL,
 UNIQUE (owner_session_id,operation,request_key),
 CHECK (payload_digest=encode(sha256(convert_to(canonical_request,'UTF8')),'hex')),
 CHECK (jsonb_typeof(canonical_request::jsonb)='object'),
 CHECK (octet_length(canonical_request)<=4096),
 CHECK (retain_until>committed_at)
);

CREATE TABLE business.v4_demo_events (
 id uuid PRIMARY KEY,
 tenant_id uuid NOT NULL REFERENCES business.v4_demo_tenants(id),
 owner_session_id uuid NOT NULL REFERENCES business.v4_demo_sessions(id),
 receipt_id uuid NOT NULL REFERENCES business.v4_demo_receipts(id),
 event_kind text NOT NULL CHECK (event_kind IN
   ('demo.session_created','demo.persona_changed','demo.reset_committed',
    'demo.session_revoked','demo.seed_materialized')),
 reset_epoch bigint NOT NULL CHECK (reset_epoch>=0),
 auth_generation bigint NOT NULL CHECK (auth_generation>=0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE (receipt_id,event_kind)
);

CREATE TABLE business.v4_demo_overlays (
 tenant_id uuid NOT NULL,
 shop_id uuid NOT NULL,
 reset_epoch bigint NOT NULL CHECK (reset_epoch>=0),
 object_kind text NOT NULL CHECK (object_kind IN ('product_attribute','fixture_note')),
 object_key text NOT NULL CHECK (length(object_key) BETWEEN 1 AND 128),
 version integer NOT NULL CHECK (version>0),
 payload jsonb NOT NULL,
 canonical_payload text NOT NULL,
 payload_digest text NOT NULL CHECK (payload_digest ~ '^[a-f0-9]{64}$'),
 PRIMARY KEY (tenant_id,shop_id,reset_epoch,object_kind,object_key),
 FOREIGN KEY (tenant_id,shop_id) REFERENCES business.v4_demo_shops(tenant_id,shop_id),
 CHECK (jsonb_typeof(payload)='object'),
 CHECK (canonical_payload::jsonb=payload),
 CHECK (octet_length(canonical_payload)<=16384),
 CHECK (payload_digest=encode(sha256(convert_to(canonical_payload,'UTF8')),'hex'))
);

CREATE TABLE business.v4_demo_rate_attempts (
 id uuid PRIMARY KEY,
 peer_digest text NOT NULL CHECK (peer_digest ~ '^[a-f0-9]{64}$'),
 operation text NOT NULL CHECK (operation IN ('bootstrap','session_create')),
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX v4_demo_capacity ON business.v4_demo_tenants(expires_at)
 WHERE revoked_at IS NULL;
CREATE INDEX v4_demo_session_live ON business.v4_demo_sessions(expires_at)
 WHERE revoked_at IS NULL;
CREATE INDEX v4_demo_receipt_retention ON business.v4_demo_receipts(retain_until,tenant_id);
CREATE INDEX v4_demo_bootstrap_expiry ON business.v4_demo_bootstraps(expires_at);
CREATE INDEX v4_demo_rate_window ON business.v4_demo_rate_attempts
 (peer_digest,operation,occurred_at);
```

### 3.1 十表的额外数据库守卫（不改旧表触发器）

0024 必须实现以下具名 trigger/function。它们不是任意 JSON schema runner，只有本表固定字段/操作。

| 函数/触发器 | 不变量与失败 |
|---|---|
| `v4_demo_immutable` | fixture、shop/persona映射、receipt、event禁止 UPDATE；十表普通 TRUNCATE 一律23514；receipt/event/mapping 普通 DELETE 禁止；owner 到 retention 后的有界 GC 例外见§10，不能接受用户 GUC 免验 |
| `v4_demo_bootstrap_guard` | id/token/hash/CSRF/key_version/created/expires 不可变；create_request_key只能NULL→一个key；consumed_at只能NULL→时钟；不得清空/换key或退回未消费 |
| `v4_demo_tenant_guard` | org/fixture/created/expires/retain不可变；epoch仅原值或+1；revoked_at单调NULL→时间；不允许重开/续TTL |
| `v4_demo_session_guard` | owner/tenant/bootstrap/creation_key/public token/created/expires不可变；身份/nonce/bound改变必须generation恰+1；epoch不倒退且等于tenant当前epoch；复用旧bound/nonce/digest拒绝；revoked_at不可清空 |
| `v4_demo_commit_guard`，DEFERRABLE INITIALLY DEFERRED，挂tenant/session/receipt/event变更 | tenant和session expires/epoch相等；一个tenant对应恰两shop、恰三persona；shop均属于tenant org且template对应币种时区；bound身份元组与当前session完全相等，kind=session、私有hash不等公开hash，bound的absolute/idle不晚于Demo expires；切换/reset旧bound必须已revoked；对应control receipt+event和before/after值存在；create还须seed_materialized事件；logout/tenant revoke所有bound current已revoked |
| `v4_demo_receipt_guard` | owner_session与tenant一致；canonical_request只含该operation冻结body与固定path；hash绑定operation+path+body，不包含cookie/CSRF；session_create key等于creation/bootstrap key；state只通过receipt行存在表示COMMITTED，不预插COMMITTED |
| `v4_demo_overlay_guard` | 插入/更新只能当前tenant epoch，目标shop已映射，tenant/session未到期撤销；旧epoch不可新写。V40-0不提供overlay编辑API，此表初始为空；直接造行仅作者PG故障夹具。reset删除tenant的overlay，不DELETE其他表 |

跨表复合关系不只靠不透明 UUID；deferred guard查询必须绑定tenant、org、session、receipt和epoch，不可只查全表“存在一行”。guard错误统一安全SQLSTATE23514固定消息，不回显token/body/SQL参数。`retain_until`不是授权延长，达到会话expires立即拒绝。

## 4. Owner bootstrap 与窄 ACL

不改旧 `entrypoints/database.py` / `grant_runtime`。新 `infrastructure/v4_demo_seed.py:grant_v4_runtime(db)` 由 `scripts/v4_demo_seed.py grant-runtime` 显式调用：检查 current_user 为新十表及旧 organizations/web_credentials/web_sessions 的实际 owner；PG17.11、vector0.8.7与精确0024先核；连接和新凭据必须来自 ROOT 已登记 owned 对象。普通 API 无 owner DSN、无环境变量自动提权。

迁移在十表和本批函数上 `REVOKE ALL ... FROM PUBLIC`；对 `commerceops_app` 默认不隐式grant。随后 owner helper 显式：

```sql
-- 所有新表先REVOKE ALL FROM commerceops_app，再逐项列出，不使用ALL TABLES。
GRANT SELECT ON business.v4_demo_fixture_versions,
 business.v4_demo_tenants,business.v4_demo_shops,business.v4_demo_personas,
 business.v4_demo_bootstraps,business.v4_demo_sessions,business.v4_demo_receipts,
 business.v4_demo_events,business.v4_demo_overlays,business.v4_demo_rate_attempts
 TO commerceops_app;
GRANT INSERT ON business.v4_demo_bootstraps,business.v4_demo_receipts,
 business.v4_demo_events,business.v4_demo_rate_attempts TO commerceops_app;
GRANT UPDATE(create_request_key,consumed_at)
 ON business.v4_demo_bootstraps TO commerceops_app;
GRANT UPDATE(reset_epoch,revoked_at) ON business.v4_demo_tenants TO commerceops_app;
GRANT UPDATE(persona_id,principal_id,identity_id,bound_web_session_id,auth_version,
 auth_generation,reset_epoch,csrf_nonce,csrf_digest,revoked_at)
 ON business.v4_demo_sessions TO commerceops_app;
GRANT DELETE ON business.v4_demo_overlays TO commerceops_app;
-- provision是唯一能首次创建新tenant/org/credentials/scopes的受限入口。
GRANT EXECUTE ON FUNCTION business.v4_demo_provision(
 uuid,uuid,text,text,text,uuid,uuid,text,uuid,text,text,text,text)
 TO commerceops_app;
```

**provision参数按顺序固定**：bootstrap_id、create_request_key、canonical_request、payload_digest、public_token_hash、new_session_id、new_bound_session_id、demo_csrf_digest、demo_csrf_nonce、bound_token_hash、bound_csrf_digest、bound_key_version、generated_password_hash。new_session_id/new_bound_session_id由可信Python端UUID4生成，函数核二者及bound hash均未被使用；调用方据new_bound_session_id预算p3 CSRF digest。tenant/org/persona/shop UUID由函数内gen_random_uuid()生成并持久映射，均非客户端输入；不新增uuid-ossp或假定PG有内建UUIDv5。返回仅内部newtenant/session/bound标识供已授权响应装配，不返回token/hash/credential。实现SQL signature的uuid/text类型必须和该顺序一致。

provision为 `SECURITY DEFINER SET search_path=pg_catalog,business`；owner不是superuser假定；无dynamic SQL、用户schema/table名或外部I/O。函数入口重新锁/核：bootstrap当前key、未消费、未到期；冻结fixture版本/摘要存在；容量锁持有并重算cap3；新session/publichash不存在且与所有bound/旧session hash不等；canonical body严格字段/fixture/key吻合；password_hash满足既有scrypt编码约束。所有旧表INSERT只能使用函数本次新生成的organization/principals/identities/shops，不能接受已有org/identity目标，也没有 UPDATE existing credential 分支。函数完整登记与各表赋值按§7.2伪码。

**没有新的旧表权限**：旧 runtime 已有 principal/identity/shop/web_sessions的既往权限，本批不扩大；它没有web_credentials/role_shop_grants/scopes的普通INSERT，本函数是窄synthetic新域例外。`grant_v4_runtime`不修改旧p3 permission函数、不更改旧schema grant，不启用paid/provider/外发。

新表没有RLS，仍是可信后端程序、固定SQL和应用授权+数据库约束的边界；不能宣称凭角色本身就有每tenant DB隔离。runtime直连新表的异常写必须被上述guard阻断；旧runtime本身已有较广表写权是保留的历史事实。

## 5. 完整 credential / bound WebSession 核验

`v4_demo_sessions.py:resolve_locked(db,bearer,expected,scope)` 将成为唯一V4认证入口；辅助的raw token语法解析只能定位，不能构造权威Actor。禁止全局缓存WebActor或把它脱离V4 guard传给未来用例。

同事务、READ COMMITTED、锁后逐项要求：

1. bearer前缀+32byte随机尾部严格形状；hash仅查相应bootstrap或active表，绝不fallback旧token。
2. 锁tenant→session后查DB时钟；tenant和session未revoked且 `now < expires_at`，两者deadline/epoch相等，key_version与本部署匹配；session的persona属于该tenant allowlist。
3. 按 `(principal_id,organization_id)` 查 enabled principal，`auth_version==session.auth_version`；多主体操作按UUID排序取得 `FOR SHARE OF p`。
4. **复制旧 `_session:183–197` 的完整JOIN**：identity `id/principal_id/organization_id`与session完全一致，provider='web'；credential `identity_id/principal_id/organization_id`一致且enabled。不仅查principal，也不以persona字符串决定role。不查询或回传password_hash；会话认证本来不验证密码，credential enabled/映射不可省。
5. 不额外锁credential/identity行：旧credential/scope trigger可能先持该行再锁principal；按旧实现只锁principal，避免新增反向锁环。新的statement在READ COMMITTED下重核当前映射，credential/scope变更的既有trigger会推进auth_version。V4未发起旧identity重映射。
6. 读取**完整旧bound session行**并 `FOR UPDATE`：id=current binding、kind=session，org/principal/identity/auth四元组相同，revoked_at NULL；DB now同时小于absolute和idle；created/absolute/idle均不越Demo deadline；其token_hash与所有公开V4hash不等。
7. 用旧 `csrf_token(WebConfig.csrf_secret,bound.id)`与digest constant-time检查bound.csrf_digest，key_version匹配，语义等同`SessionStore._csrf:165–171`。这不是公开V4 CSRF，不回传它。
8. 在同一db上调用旧 `actor_guard(db,WebActor(...))`（`web_sessions.py:59–110`），再按目标shop调用`role_scope`（113–126，DB最终permission定义在0008:12–32），不能以入口capability取代shop grant。
9. V4业务读 `seed-summary` 在同事务比较 X-Demo-Epoch/Generation；写在同事务比expected字段；这些字段是CAS，绝不据此选tenant/principal。当前session读取无需旧CAS，可以恢复当前控制状态。
10. 公开V4 CSRF=`capability(secret,"v4-demo-csrf-v1",{session_id,csrf_nonce,generation,epoch})`，只存digest；bootstrap用独立purpose。写必须匹配当前digest+可信Origin。成功序列化前，在持有tenant/session/principal/bound锁的同事务再核epoch/当前权限/DB now；响应context来自该检查的 `authorized_at`。网络发送后可能发生另一事务切换，由客户端context/request_seq/BC/5秒current屏障拒绝迟到显示；不承诺跨设备像素瞬时消失。


完整credential查询采用旧认证JOIN闭包（参数来自已锁的DemoSession，不来自body）：

```sql
SELECT p.* FROM business.principals p
JOIN business.identities i
 ON i.principal_id=p.id AND i.organization_id=p.organization_id
JOIN business.web_credentials c
 ON c.identity_id=i.id AND c.principal_id=p.id
 AND c.organization_id=p.organization_id
WHERE p.id=%s AND p.organization_id=%s AND i.id=%s
 AND i.provider='web' AND c.enabled
FOR SHARE OF p;
```

结果必须存在且p.enabled、p.auth_version等于当前session记录。接着锁旧bound session并验证完整四元组、kind/key/CSRF/期限，再调用actor_guard。不会以SQL返回一行便跳过后面的bound/session/V4 epoch核验。

新bound absolute/idle都设为原Demo expires，不做touch/滑动续期。旧bound被persona/reset撤销后，旧actor_guard即使不知V4字段也会401；新context只用新bound。credential撤销/停用通过旧principal auth_version阻断旧actor，tenant/session显式revoke则本事务撤旧bound。到期由bound时钟本身拒绝，无需后台清理先运行。

## 6. 锁顺序、时间与并发

所有V4代码统一使用：

1. 仅create：`pg_advisory_xact_lock(1446261840,1)`（两int键域，与旧Worker bigint锁不同）；cap guard不得控制/终止Worker。
2. bootstrap行 `FOR UPDATE`（仅bootstrap/create恢复）。
3. tenant行 `FOR UPDATE`；session行 `FOR UPDATE`。V4-0请求短小，同tenant请求串行；不对全表加锁。
4. 当前与目标principal按UUID排序 `FOR SHARE`；之后当前旧bound session行 `FOR UPDATE`。
5. shop按UUID排序share；通过现有permission函数按稳定shop顺序锁scope/grant；不锁credential行。
6. overlay目标行/receipt唯一键/append事件；最终deferred约束检查。

sessiontoken最初SELECT仅定位tenant_id，不作认证；加锁后再次核token/session全部字段。owner revoke/GC也必须相同tenant→session→principal→bound顺序；旧M3代码不会锁V4表，V4不反向持bound再取principal。无自动deadlock/serialization重试，返回安全503/UNKNOWN，原key只读核对。

DB statement_timeout=5000ms、lock_timeout=1000ms、单事务客户端总预算10s（拒绝无限等待）；scrypt不持tenant/cap锁。connection异常不将已提交状态判回滚。PG命令300秒/旧诊断清理期限不因本设计改变。

速率记录独立短事务，按`pg_advisory_xact_lock(1446261841,hashtext(peer_digest))`串行窗口后INSERT并COMMIT，包括拒绝前已接受的尝试，不能随着业务rollback清零。peer_digest用新部署secret HMAC过peer，不存原IP/UA/凭据；bootstrap每peer20/300s，session_create每peer10/300s；active cap3由create主事务容量锁内再次统计。密码散列新随机一次性secret，每次create只算一次供该tenant三persona复用（各login/identity不同）；原secret立即丢弃，不是可用演示口令。单进程非阻塞Semaphore(1)保护scrypt，不无限排队；忙返回429 RATE_LIMITED，peer限流及bootstrap key仍保留。编码沿旧scrypt，credential check不借此跳过。

容量按未revoked且expires>DB now的tenant+session计数；丢Set-Cookie的已提交tenant仍占位；后台未清的expired不占位。credential被外部撤销但未显式revoke的tenant保守占位至期限，不擅自踢掉。五访客竞争恰≤3commit，其他429 CAPACITY_LIMIT/Retry-After；Retry-After取最早active expires的剩余秒向上取整，至少1，DB故障不补宿主时钟。bootstrap总活跃记录额外上限128，在专用bootstrap容量锁内检测，拒绝不删除他人。

## 7. 八端点的事务伪码（本文件没有实现）

### 7.1 GET bootstrap

```text
check Origin/HTTPS/Host/fetch policy before any session mutation
if active cookie authenticates: reject conflict; do not overwrite active cookie
if valid bootstrap cookie AND create_request_key IS NULL: return same CSRF/absolute deadline
otherwise: peer-rate attempt; lock bootstrap-capacity; DB now
  insert new 300s bootstrap with random v4b_ hash, key_version and CSRF digest
  COMMIT; only then Set-Cookie bootstrap; return anonymous BootstrapEnvelope
```

已绑定create_request_key的bootstrap（不论是否consumed）均不复用为新建owner；原行与300秒单key回读权保留，用户明确重新开始调用GET才签新bootstrap，不清空旧绑定。确定性429后重新开始不会被旧key永久404卡住；UNKNOWN客户端不自动调用此GET。消耗过的bootstrap仍保留供原key GET；UI只有用户明确“重新开始”才请求新bootstrap再显式POST。GET本身只建匿名nonce，不创建新tenant；它替换旧bootstrap cookie并不证明旧create回滚。unknown页不得自动走此分支。bootstrap响应也丢失时，原匿名行到期，不能推断业务已创建。

### 7.2 POST sessions 与受限 provision

```text
strict validate {request_key,fixture_version}; allowlisted Origin + bootstrap CSRF
separate short transaction: lock bootstrap; DB now + key version + expiry
  bind first valid create_request_key if NULL; different key =>404
  COMMIT this owner/key reservation (not a COMMITTED business receipt)
record create attempt independently; bounded single scrypt; generate public v4d_ token in memory
BEGIN; capacity advisory -> bootstrap FOR UPDATE; check current bound key/expiry/CSRF
if bootstrap already consumed: no new tenant/token; see recovery below
ensure live cap<3; SELECT exact fixture/version/digest; validate canonical request/hash
call v4_demo_provision(...):
  generate fresh tenant/org + fresh two shops/three principal+identity IDs; persist immutable mapping
  INSERT organization with reserved synthetic name/app_id/tenant_key ('v4-demo-'+uuid)
  INSERT tenant and two shops (adapter_kind=mock, environment=mock, unique config_ref)
  INSERT three principals roles {operator}/{approver}/{admin}, identities provider=web
  INSERT scopes and role grants from SEED_SPEC; INSERT opaque random web logins+hash
  -- all original scope/credential triggers run; read FINAL auth_version afterwards
  INSERT new bound session for operator using that final auth_version and new private hash
  INSERT DemoSession (epoch=0,generation=0; deadline same as tenant)
  INSERT session_create receipt + session_created and seed_materialized events
  mark bootstrap consumed; leave owner/key row until300s expiry for restricted GET
verify full current credential/bound guard + exact two-shop/source/count summary
deferred constraints; COMMIT
issue public v4d_ cookie once; return 201 CreateEnvelope, DB context, original receipt
```

生成秘密只在新owned进程内存；不把随机密码、bound token、cookie/CSRF或hash放日志/receipt/event。失败在COMMIT前全回滚business effect（仅独立rate/key reservation可保留），不留部分组织/凭据/seed。COMMIT结果未知时不重试。

**duplicate create与丢cookie**：创建POST仅接受有效原bootstrap、其CSRF与精确原key；active cookie在该入口拒绝，不增加active POST兼容路径。active会话丢body后只GET current核creation_request_key，再GET原receipt。consumed bootstrap重复或并发POST不重发新cookie或旧敏感CreateEnvelope，返回409 OWNER_RECOVERY_REQUIRED，原bootstrap+原key的GET仅返回冻结最小COMMITTED状态；原事务尚未提交时按原锁序等待或返回安全UNKNOWN，不产生第二效果。客户端从不自动POST。并发两个同bootstrap create至多一个新tenant；后者无新cookie，不能用数据库hash还原第一cookie。整header/cookie丢失的300秒最小回读边界不变。

### 7.3 GET current / GET seed-summary

```text
BEGIN; lookup+lock tenant/session; resolve full credential/bound guard; DB now
GET current: enumerate current persona's actual current scope/grants; 0–2 shops
  include creation_request_key, persona, original expiry, current CSRF, source + context(shop=null)
GET seed-summary: strict shop UUID + required epoch/generation headers
  compare CAS; role_scope(operator OR approver) for that shop else404
  exact immutable fixture + that template; current tenant overlay count join
  actual bounded counts only, snapshot_at from fixed fixture (not current server_time)
recheck DB clock/permission/CAS while locks held; serialize strict DTO; COMMIT
```

restricted_admin的SessionData.shops=[]，但拥有切persona/reset/logout自己的控制能力；该权限不意味着业务grant。seed-summary只有四个已冻结count字段，不增KPI/六链执行接口。

### 7.4 POST persona / reset

```text
BEGIN; lock tenant/session -> sorted principal(s) -> oldbound; full auth and CURRENT Origin/CSRF
look up receipt by stable owner+operation+key
  if found: compare exact canonical request digest (including original expected fields)
    equal => safe original receipt + CURRENT authorized context; no side effect
    different =>409 IDEMPOTENCY_CONFLICT
  else compare expected_epoch/generation; mismatch=>409 with no data
persona: allowlist target; revalidate target credential+identity/principal + actual grants
reset: same persona; fixture_version must equal frozen binding; increment tenant epoch exactly1
  DELETE overlay WHERE tenant_id=currenttenant (no other tables)
mark old bound WebSession.revoked_at=DB now (never mutate old principal in-place)
create independent new private bound with target/current identity+final auth_version and original expiry
update session persona/bound/auth_version; generation+=1; new csrf_nonce+digest
reset sets session epoch=new tenant epoch; persona preserves epoch
insert one receipt + one persona_changed/reset_committed event in same transaction
recheck full new guard/DB now; deferred oldbound-revoked check; COMMIT
return ControlEnvelope receipt + context of new current identity, next_step READ_CURRENT_SESSION
```

**旧CSRF仍拒绝**：receipt查重不绕过当前session/Origin/当前CSRF。两个同时带旧CSRF的reset请求，首个commit一次，后者可能403而非再次200；客户端只读GET原key确认。用当前新CSRF提交同key同body可回原receipt，CAS不会误当新写；该幂等服务端保证不是自动POST重试许可。若新context与旧receipt的epoch不同，这是最小历史控制回执，不携带旧业务data，客户端再GET current。

切到当前同persona仍是一次明确control：generation+1、换bound+CSRF；同key重放无再次推进。不恢复原先撤权grant，不给restricted_admin填两店。

### 7.5 POST logout / GET operations

```text
logout BEGIN: current guard + current CSRF/CAS; lock order as above
  existing receipt equal only while current session valid; conflict409
  revoke current bound + DemoSession + tenant at same DB now; append logout receipt/event
  no epoch/generation虚增; response context是提交前身份（不是后续授权）
  COMMIT; clear only v4 cookie; next_step LOGGED_OUT
```

GET operations：

- active cookie：完整current认证；固定白名单operation+key；仅查询`owner_session_id=current.id`；有行返回Receipt，无行返回UNKNOWN语义的固定FailureEnvelope/404，不能证明回滚，不返回canonical_request或旧persona数据。
- bootstrap cookie：仅`session_create`，当前bootstrap未过期且精确`create_request_key`相同；其他key/operation统一404。已commit最多返回 `{operation,request_key,status:COMMITTED,recovery:OWNER_RECOVERY_REQUIRED}`；已绑定但receipt缺失返回`UNKNOWN/WAIT_READ_ONLY`。不返回tenant/org/principal/shop/session_id、CSRF、新cookie或receipt_id。
- bootstrap过期/丢失、active退出/过期/credential撤销：401，不给予恢复特权。logout丢ACK后current401只能表示目前未登录，不能伪造logout COMMITTED。

## 8. HTTP/response/多标签冻结接口

八路径保持 `baseline/v4-public-openapi.json` 精确request/response名；实现的Pydantic strict/frozen/extra=forbid对象必须逐一匹配，不修改baseline原件“修成通过”。新生成独立OpenAPI可作为后续代码产物交ROOT，差异必须说明。

- 新专属boundary仅 `/api/v4/demo/*`，默认关闭 `create_app`显式v4配置；原 `/api/v1` middleware、旧OpenAPI/错误DTO保持回归。`api.py`插入V4装配在旧schema导出完成后；不让`export_web`把新paths当未批准P3操作拒绝，也不把旧schema偷偷扩为V4。
- 无Origin GET仅配置允许的同源Host+Sec-Fetch-Site=same-origin；跨origin必须受信Origin+credentials。loopback非浏览器例外只能新owned config显式开启；POST永远精确Origin+CSRF。不信任任意X-Forwarded-*。
- 新HTTP配置复用 WebConfig 的secret与database基础信息，额外V4 enabled/可信API origin/transport/same-origin-test策略由新模块限定参数承载；不能读取旧私配自动启用。原config_file和环境默认不变。
- success server_time与context.authorized_at均DB UTC；不可读DB的503为null。业务敏感响应都有tenant/org/principal/shop|null/epoch/generation context；匿名bootstrap/最小operations不伪造context。失败无旧data。
- WEB以request_seq+servercontext渲染，切换/reset/logout开始先清屏，BC只发invalidate，hidden/offline清屏，恢复先GETcurrent，可见5秒只读poll失败清屏。这个客户端责任由WEB独立实现，服务器新请求立刻核epoch/generation；不宣称立即撤去已绘像素。

## 9. 后续作者/独立PG验收矩阵（当前NOT_RUN）

| ID | 必须验证的可观测事实 |
|---|---|
| ID-01 | v4b_/v4d_改名commerceops_session对/api/v1 auth/session及业务端点401；bound私有hash不等公开hash且响应/日志无秘密 |
| ID-02 | credential disabled、identity/principal/org映射任一错、principal disabled/auth版本变化、bound过期/撤销/元组错/keyversion错/CSRF digest错逐一拒绝；不是仅测试principal |
| ID-03 | persona/reset旧actor_guard直接401，旧公开CSRF拒绝；新bound与原deadline相同；同persona切换仍轮换；reset admin保持admin/shops空 |
| ID-04 | 两访客org/principals/shops不同；猜ID/跨店/去scope/admin无grant拒绝，无payload；直接错误租户FK/epoch写23514或FK拒绝 |
| ID-05 | 五个并发create只有3成功；丢cookie已commit空间占位；429不踢旧session；过期释放count但不删receipt；peer limits和bootstrap cap128 |
| ID-06 | 同key同payload一effect、异文409；并发reset只一次epoch推进；旧CSRF403后GET原key可确认；ACK body丢与整cookie/header丢分别测 |
| ID-07 | reset与read/fixture-note夹具写/owner revoke并发线性化；current授权响应context时刻明确；迟到UI数据另由WEB/QA注入 |
| ID-08 | 本批新窄grant前后逐表/列/function权限实测；普通runtime不能写fixture/mapping/credential/grants或删receipt/event，PUBLIC不能调用provision；provision不能指向既有org |
| ID-09 | migration旧source byte/checkpoint数据不变；十新表精确集合、全部为空；runtime角色非superuser/createdb/createrole；旧G1/G2与当前动态全量PG不缩减 |
| ID-10 | create/seed/reset每个持久步骤注入异常：commit前无部分business、commit后未知只查原key；所有stage只safe类别，不输出secret或原SQL |

作者tests路径依TASK_PLAN，仅tests/v4三文件；独立QA owns tests/e2e/v4。资源project/卷/端口/UTC/deadline尚未释放，不运行。新integration节点自然进入既有combined-existing普通组；实际collect与模块测时后判断300秒内覆盖，不能预先改timeout、分片、断言或漏纳节点。历史719不是新集合常数。

## 10. 明确retention与清理边界

- session/tenant 30min；bootstrap恢复权300s；业务/控制授权不因tombstone存在而延长。
- tenant所有控制receipt/event及最小映射保留至原 `expires_at+24h`，reset不延长。bootstrap owner行因session FK保留至同tenant retain_until，但300s之后绝无token恢复权；未consume bootstrap可在expires+24h后owner清理。rate保留24h，无IP原文。
- 初期无自动janitor/Worker。显式新owner CLI `gc --tenant <id>` 先核实际owner、reserved synthetic marker、当前DB clock>=retain_until、旧bound已revoked且expired、无business_tasks/jobs/旧业务依赖，然后tenant→session锁序删除**该tenant的新V4 overlay/events/receipts/session/bootstrap/persona/shopmap/tenant**。删除历史行guard只对实际表owner且retain过期放行，普通role无权，不能用自设GUC。baseline版本不删除。
- 旧base org/shop/principal/credential/web_session行不被GC DELETE；bound全部撤销，凭据/主体按既有触发器安全停用（auth_version随权限变化推进），保留历史。reset从不触碰这些登记。若已有非V4旧业务引用，GC拒绝并报告，不cascade删除。
- 标准PG新临时卷删除与独立Web保卷由ROOT各资源合同处理，不将删除新测试卷记作tenant级GC已验。本次不实际清理资源。

## 11. 0024 兼容断言的精确释放申请

以下行号绑定当前父提交eb82c9d（相关测试与M3字节相同）。**仅列申请，没有修改这些文件**；ROOT专项审查后才可释放同一作者最小更新。十表使business75→85，business+checkpoints79→89；不是放松到包含或`>=`。

| 旧文件/符号/行 | 必要最小变化 | 必须保持 |
|---|---|---|
| `tests/test_postgres.py:test_revision_and_schema:50,55–131` | head改0024；全量精确business集合加入本方案十个具名表 | public无表、PG17.11、CP migration最大版本、旧75表一个不删；不能从运行库动态取expected骗过多表 |
| `tests/test_p4_first_create_negatives_pg.py:test_forward_0012_upgrade_preserves_original_c0_rows_and_checkpoint_bytes:390–417,422–448,523,530,533` | migrate-current之后精确增量集合26→36个，逐新十表空行验证；current_head改0024，诊断new_tables_empty=36 | 0012构造/固定d97闭包、0013 revision断言381、before旧行和CP字节相等418、原ACL/不可变权限断言450–518完全保留；grant-runtime仍不隐式V4授权 |
| `tests/test_p4_migration_diagnostic.py:Fake execute:155–194,199–226,276` | fake head新增十个表名，row_to_json新表空集合；仅current分支0023→0024 | historical snapshots==2仍0013；故障分类/原清理和原current-grant精确列不变 |
| 同文件 `test_fixed_d97_closure_hashes_and_isolated_imports_are_offline:419–431` | 排除新增0024_，保持固定d97仅旧迁移闭包精确相等 | 不改manifest/hash或解包历史源码 |
| `tests/test_p4_f02_pg.py:test_persistent_partial_cross_process_round_history_and_zero_business_until_confirm:177,181` | 当前head=0024；完整business+CP计数89 | 七列UPDATE grant及所有旧无权限/业务保护断言保留 |
| `tests/test_p4_history_pg.py:test_0016_upgrade_preserves_original_rows_payload_and_unknown_attempt:769` | head字面0024 | 0017历史迁移/原FK/TRUNCATE SQLSTATE0A000与CASCADE23514/byte保持 |
| `tests/test_p4_read_reply_pg.py:历史关联分支revision集合:283–291` | 只加入0024具名revision，使head继续走原有关联FK失败分支 | 旧0015/0016分支、FeatureNotSupported0A000与CASCADE保护不变，不改异常期望 |
| `tests/test_p5_m2_backup_pg.py:test_current_m3_head_is_not_an_m2_backup_schema:61,71` | 动态head两个字面0024，可保留函数名历史或只注释当前V4head | M2精确0018 fixture、60表、M2_SCHEMA_REVISION拒绝、只读事务不改；不宣称0024备份可用 |

最终改动前再以rg核所有0023/current精确断言；若出现额外影响先报告申请，不能扩成全库替换。数据库owner迁移可到0024，但旧M2备份仍应拒绝，不为绿灯放宽支持版本。

## 12. 交付到下一Gate

本次只冻结两设计文件普通commit交Astra；实际tokens/cost不可见为UNKNOWN。待ROOT明确专项准入才实现0024+v4_demo模块/API/CLI/作者测试，并按V40-03→04串行交付；旧compat测试与任何旧文件helper必须另获精确释放。本方案选择无需改旧web_sessions.py/database.py，若实现发现做不到则停对应路径并交具体diff申请，不自行降guard。


## 13. SQL-01/02/03 专项纠偏（实现候选，PG仍NOT_RUN）

十表数量不变。DemoSession新增内部last_receipt_id（不进入API DTO），其与session id/tenant/after epoch/generation一起通过deferred复合FK指向receipt；每次控制更新必须更换指针。session的deferred guard将该次NEW与事务最终session全行比较，明确拒绝同session同事务的第二控制步骤（包括create后再control）。再以NEW.last_receipt定位唯一receipt，并逐项对照捕获的OLD before和NEW after；历史receipt不得替新effect背书。receipt INSERT反向要求自己正是当前session.last_receipt、after值完全相同。只插receipt/event不改状态、只换指针不做真实轮换、历史回执复用、只改epoch/撤销而无匹配receipt均拒绝。reset还要求本tenant overlay已清空。

event新增receipt_id/owner_session_id/tenant_id/epoch/generation复合FK及operation→kind语义guard；create恰两种各一，其余恰一种一条。event独立INSERT也要核原receipt关系，不因旧receipt本轮未更新而漏验；额外错kind不得追加。

新增固定v4_demo_request_valid(jsonb,text,uuid,bigint,bigint,text,text)检查wrapper与各operation body的object/exact keys/non-null types/constants/key/fixture/persona/expected CAS；missing/null/错类型均返回false。守卫以NOT coalesce(...,false)拒绝，不用NULL敏感的不等式。该无DB权限提升函数由owner helper单独授runtime EXECUTE，不新增通用schema解释器或免验GUC。实际SQL负例将在ROOT新owned窗口验证；当前不以结构纯检查关闭PG Gate。
