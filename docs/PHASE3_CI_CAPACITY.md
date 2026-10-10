# Phase3 CI容量：两个隔离PG分区与精确配对

最新回执导航：Root已核A03 source052/Core5480529395/CI38079599247及B最终a65/Web5480795768/CI38085161901通过；原A05已正常集成B，最终四job/增量独审/main/合后CI/Issue33仍pending。见[A05交接](PHASE3_A05_INTEGRATION.md)及[STATUS40](STATUS.md#40-phase3-a05-正常集成与最终四作业候选)。以下原作者333/988/失败和当时待核记录为历史，不改写旧证据。

2026-10-11，Root在原CI38076119191的全局预算失败后明确批准独立受限容量批，原A为唯一workflow/scripts owner；不是第三同源business修复。本批源码/离线窗口至19:32:52UTC（03:32:52+08），不新开本地PG/Docker，不改748已审业务/P3 tests/DTO/迁移/B/npm，正常历史提交后仅一次新push触发真实CI。当前实现/离线验证不冒称新CI或整体Phase3通过。

## 原失败与业务前置

原source2e0/tree4fe/实际merge `c47f12235dcd52ea590ebc6d13fe81ce26f37452`（parents59+2e0）CI38076119191自然FAILURE：988offline/129.66s、完整325PG（236旧+89P3）通过，projection组只剩expires−75约19s而timeout/exit137/stop confirmed/cleanup0，revalidation5及后续G1未跑。见[安全负证据](contracts/p3-a03-original-ci-failure.json)，无projection死锁/旧#23根因结论。

原Core source2e0失锁用例23/1失败另记，不能用该CI或作者333通过抵消。[FIX1](PHASE3_A03_FIX1.md)两项business minfix本地commit748879e63c07185ae8c6f150827b7860ea66621e/tree634d77，Root已核原Core新自有真实101P3（28/177.78s+30/121.32s+43/165.89s）、32HTTP/22ops/actualprovider0、pure69、无新P1/P2及PG19:10:11Z早停/Exit0/PID0/保卷。原失锁失败保留，748字节继承与本CI delta仍由原Core审核；B只从已审Git对象离线接线，真实API/PG等新CI稳定Gate。

## 两个PG job与原界限

quality保留原source/工具/锁检查、完整offline/npm tooling和existing分区、原G1/G2 fullsmoke；phase3从同exact `${github.sha}` checkout执行全部P3自然模块。两个job各25min，首次登记absolute23min，各命令300s且共享本jobexpires−75预算，cleanup75不扩大、不重置deadline、不挑node或调慢例。每job沿用原supervisor随机独立Compose project/fresh凭据/自有volume/启动前登记/停止确认/cleanup；不是新增业务Worker或并发Graph。最后pg-pair是无PG/Docker的5min轻量metadata配对job。

pg_diagnostic只新增closed `all|existing|phase3`；default all仍原完整combined（包括历史无P3单命令行为）。scoped必须ci/combined，existing必须full-smoke，phase3禁止冒称full-smoke；两个job都先actual collect完整全integration337。existing=all−P3、phase3=全部现有P3路径，从完整真实集合动态派生，不硬编码236/101；两边nonempty、unique/disjoint/union/full、自身所选组扁平集和actual逐node相等。每P3既有模块独立串行原300s；未来模块自动纳入，同count换node拒绝。

## 安全产物与配对门禁

只上传`.audit/ci-evidence-existing.json`与`.audit/ci-evidence-phase3.json`两指定文件，retention1day、不上传stdout/配置/DSN/cookie/token/nonce/密码或raw SQL/业务行。exporter固定whitelist顶层及module字段，丢弃raw诊断的额外字段；失败、partial、无collection/非0终态不能自称通过。元数据仅schema/scope、精确source SHA/tree、canonical full_node_ids/UTF-8 JSON SHA256、selected/actual/实际passed节点、逐自然module绑定/exit/result、G1/G2/confirmed cleanup。

工具/锁指纹含固定九份public lock/tool/compose/Dockerfile内容摘要、实际Python3.12.13/Uv0.11.25/Node24.21.0/Gitleaks8.30.1版本及uv/node/gitleaks三二进制SHA256。UV公开build尾注规范化版本，不忽略二进制漂移。两份必须same SHA/tree/full集合和hash/tool/lock/binaries；实际集合无漏重且union完整、每module真实collection与passed集合完全相等/终态0、existing原三G1 verified与必要G2 scenarios/cleanup0。pair额外核自身exact checkout，互相相等但来自另checkout的旧artifact也拒绝；failed/skipped任何job不能通过pair。

仅新增官方固定SHA的artifact动作：upload-artifact `ea165f8d65b6e75b540449e92b4886f43607fa02`、download-artifact `d3f86a106a0bac45b974a628896c90dbdf5c8093`；本批通过官方GitHub refs实际核v4均直接commit。checkout/setup-python/setup-uv原pins保留，全局permissions仍contents:read，无新仓库权限/外部资源。名称绑定run_id/run_attempt，无跨run复用。

## 实际离线证据与待核

原partition/shutdown41＋新增完整性负例35=76passed/0.26s（后0.11s），继而增加两种mixed group丢选集反例，共78passed/0.11s。覆盖同count改node、遗漏/重复/overlap、源tree/tool/lock/binary漂移、partial/failed/unconfirmed/cleanup、G1/G2不足、额外字段、旧artifact和defaultall/未来新模块/不重置截止。首次74组73pass/1fail/0.11s是两模拟report共用同meta对象使测试变更同时改两边；exporter显式复制closed nested指纹后74pass，再78通过。不是实际PG/Docker或GitHub artifact运行证据。

workflow YAML实际parse通过：两个exact checkout PG jobs、25/首次23/固定官方40SHA动作、轻量pair、contentsread不变；本机实际固定工具版本规范化及三个binary/九文件digest读回。首fullcheck dir1/index0/git0因公开末位pytest类型注解的generic-api-key误报，改标准trailing comma/Path annotation，无凭据，无222原规则/四例外改变。完整离线初版1021passed/337deselected/86.39s；新完整check收口回执另附，未执行新CI337/两job/配对/原G1G2不提前称通过。

本批无新PG资源，原fix窗口已02:50:38早停/保卷。D1/D30/300h/A32+B18+Review10/60h与人工H/L not_reported保持；source_mode=mock/identity_mode=session/approval_mode=simulated_web，实际provider/外部业务网络写0，M1视觉冻结不追加，未合B/main/未结Issue/生产或Phase4未授权。


最终作者CI容量源码/离线收口：`python -m scripts.check` exit0，1025offline/85.07s、337integration deselected、2既有SDK弃用warnings，Ruff/249format/mypy179、66Markdown0error、Node24.21.0原tooling/typecheck、95Python和Node已知漏洞0，dir/index/git0。78分区/停机/配对专项0.11s通过；新完整integration337只collect未本地执行。对748 Git对象逐文件回读证明122个业务/P3tests/DTO/migration/frontend/lock文件字节完全继承，供Core CI delta独审；源码和离线工作在原35min截止内，提交前后与暂存扫描另按实际回执。无本地PG/Docker资源、无B文件变更；新唯一push/精确双job CI与metadata配对仍待实跑，不提前pass。
