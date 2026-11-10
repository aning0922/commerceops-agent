# F1 HTTP lifecycle 与真实浏览器回执独立核收

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_LOCAL_HTTP_LIFECYCLE_AND_BROWSER_FUNCTIONAL_EVIDENCE；Q16_RUNTIME_ASSERTIONS_ACCEPTED / NATIVE_200_VISUAL_UNVERIFIED。** 实际功能流程及所列自动断言可核收；200%完整视觉可读性保留证据缺口，不签无条件Q16全部通过。没有据现有材料确认新的产品P1/P2；截图缺口也不改写为已证明的产品溢出故障。

受测源码 F1 `047a43dafef90edea2eb532c2a03b6f850da0b9a` / tree `5c0699edb2d30889ce770ca9b05b56dab957ce10`。核收对象为 ROOT `.audit/v4-0/http-lifecycle-F1`、`browser-F1` 和 F2 `6e98399fb485d7a852d0e4c92923af0ef005782c` 内 tracked `HTTP_LIFECYCLE_F1.json` / `BROWSER_F1.json`。另只读原运行 case 元数据、原 browser stdout 与 PNG 以核复制关系；没有读取 owner/API 私钥，没有新服务、浏览器、PG或全链测试执行。

## 来源、报告与清理

两个原 case 的 source_sha/source_tree/project/deadline 分别与 ROOT_OUTER 和 tracked 摘要一致。独立核 F1 的五个 browser pin（config/live/waiter/profile/schema）均等于已审固定 blob，F2这五文件也逐字节相同。F1→F2 的完整文件清单仅扫描七文件与事实/审查文档，没有业务/UI/runtime改动；这只证明源码差异范围，不把F1运行改记为F2实际运行。

两 driver 均 SCENARIO_COMPLETED_PENDING_REVIEW，scenario native0；ROOT_OUTER driver_native_exit=0、forced=false、namespace_initial_empty=true、cleanup_confirmed=true。阶段顺序包含 writers_stopped → API container stopped → owner oneoffs inventory → final PG readonly → down keep volume → containers/networks gone。两次 writers 原生退出均 probe0/web0/API130；API130是停止阶段原记录，未抹成0，也不是此次scenario失败。

ROOT外层分别在 UTC 17:30:57.845184 和17:36:54.867410（台北11月4日01:30:57和01:36:54）闭合：登记进程组没有live registered members、leftover_ids为空、最终containers/networks为空、两个各自端口关闭，卷各保留1个。以上核的是原执行时回执，没有把现在的机器状态反推为当时事实。

## HTTP lifecycle E

项目 `v4qa_lifecycle_20261104e`，明确子网10.242.10/11，原全量库存记录31网，NO_OVERLAP_OBSERVED；所有启动/迁移/fixture/grant及scenario阶段native0。该入口实际启动PG/API和本地Next dev Web，然后执行真实HTTP probe，不是浏览器流程或production build验收。

固定F1 lifecycle源码使用两个独立真实httpx CookieJar（无代理、无重试），创建不同tenant、各访问两店summary、双向跨tenant商店404；A reset精确epoch+1，并用PG前后digest/epoch/generation/receipt/tombstone核B不变；随后A persona切换、logout及GET current401。HTTP response检查真实状态、no-store、Vary Cookie/Origin及adapter strict schema。scenario native0支持这些固定断言已通过，但不是所有HTTP场景、TTL或容量Gate。

final_pg.safe与tracked final_pg_facts逐对象相等：2 tenants，B epoch0/generation0/receipt1/tombstone1，A epoch1/generation2/receipt4/tombstone4，独立digest及DB UTC均保留。原库SQL详情不在此重新执行。保留卷 `v4qa_lifecycle_20261104e_pg_data`。

## 浏览器功能与真实响应

项目 `v4qa_browser_20261104a`，子网10.242.22/23。固定原生report仅1个 `LIVE: isolated demo lifecycle and browser layout`、1个结果passed、retry0、无annotations跳过、无errors；stats expected1/skipped0/unexpected0/flaky0。report总duration 6359.862ms，单test duration5660ms；二者不是同一计时口径。原config固定live.ts、workers1/retries0/forbid-only，local API/Web，未配置webServer或mock route。

独立调用F1原validate_report对已有JSON校验通过。最初对打包playwright.json与原processes/probe.raw.log做字节相等检查失败，随后核实仅序列化表示不同：3189与4391字节，config/suites/errors/stats四对象全部相等；不称逐字节副本。打包SHA256 `8c9a7d97f153120c33e1e68fa438e65efe9eb1d2f56d3c35bfa5e112e70a5906`，原stdout SHA256 `0a5c9464dd2a3cab364ddab497c26af4324485e3ee3974eb9beb3e58c588431a`。这次核对断言失败不是业务运行失败。

固定live代码对真实response执行Ajv2020 strict/format校验；创建key、receipt operation、tenant/org/principal、两店范围、persona、epoch/generation精确增量及恢复waiter均有明确断言。桌面tenant实际create→两店summary→approver/restricted_admin→reset→operator→logout；独立390tenant和独立headful200%tenant各create→summary→可见导航键盘Enter到设置→dialog/Tab/Esc/focus恢复→logout。三个tenant不同、cookie清除与授权context匹配在固定test内断言。

final_pg与tracked逐对象相等：3 tenants，其中桌面epoch1/generation4/receipt6/tombstone6，另外两个epoch0/generation0/receipt2/tombstone2；DB UTC与不同digest保留。保留卷 `v4qa_browser_20261104a_pg_data`。本次没有重新跑ROOT提到的25项Node pure，亦不拿该数量充作本次浏览器实际样本。

## Q16：可接受事实与具体视觉限制

已逐张查看8张PNG，并独立核全部尺寸/SHA256等于tracked清单、全部原图与原运行browser目录逐字节相同。1440/1280欢迎页及390欢迎/已登录/重置dialog样本布局可读；390导航可见、文字换行，dialog按钮和焦点轮廓可辨。Next dev标记出现在部分截图中；它们是本地dev运行样本，不是生产版视觉验收。

真实native缩放证据成立：固定代码在headful独立profile中操作chrome://settings/appearance的select#zoomLevel，从1选2并断言；原metrics与打包/摘要一致，outer1440保持，inner1440→720、DPR2→4、visualViewport.scale=1、CSS zoom=1、scrollWidth720。不是只改viewport或CSS模拟200%。metrics文件记录的是缩放后欢迎页测量；已登录与dialog的scrollWidth<=innerWidth另由固定test在截图前断言，其实际数值未独立写成第二/第三metrics文件。

**Q16-VISUAL-01（证据限制，未证明产品缺陷）：** native session/dialog的fullPage PNG右侧明显裁切，session长图底部也非完整内容；设置PNG同样只显示设置页局部，没有拍到200%选择框。因此这些PNG不能单独证明200%全页/对话框所有文字、右侧边界与控制均完整可读，也不能把设置图称作直接可见的200%选项证明。缩放事实来自真实GUI断言+尺寸/DPR数据+固定原生test结果。仅凭scrollWidth不超innerWidth也不能排除内部元素裁切，现有静态图片不能确定裁切究竟来自截图导出还是当时全部视觉状态；不作根因结论。

Q16中的宽度/原生缩放/no-horizontal-scroll断言、所测试的Tab/Esc/focus回归、可见文字及reduced-motion配置/欢迎页媒体查询可核收。Tab覆盖的是固定动作和一次dialog内部焦点断言，不等于完整键盘循环或屏幕阅读器审计；真实ARIA朗读未采集。**若要关闭200%完整视觉可读性的剩余项，所缺是同一真实200%状态下可信的未裁切viewport/窗口或有明确滚动位置的分段截图，并能看清session右侧及完整dialog；只改现有PNG、只重复viewport测试或仅援引这次pass均不足。** 此核收没有自行启动补采窗口或要求重做已通过业务流程。

## 独立证据指纹与交接

HTTP driver/finalPG/outer SHA256：`c27dc9405232e1c9c2b61bc87d20ef26ab2690e534379d5fc11b1cef44eb99c4` / `ecbb3c065ed903202dfcd6f2b565a1104bc8dfde0d77f7ae20aa3f513d94fc32` / `4fd9540e5391e31f8ff7c85f4b4c109a94a3fe1501f9540144bc2bc23f610cb2`。

Browser driver/finalPG/outer SHA256：`a885c736a0b11fa427b4faf2f593732569bf2f2aebce2d26f0428f51818b479d` / `e54c252f8dfa25cc7590752799680f50d19d9117ca97c73c7d8f26fbde801a98` / `d41f8b09f571c02ba22214e4555141d1795968dc76697dd3b9517be04c371189`。

保留旧failedHTTP02 startup unknown及其它旧失败，不能混写成本次E/browser业务失败；本次成功也不抹去旧失败。Full、TTL、Hosted、外部服务与发布均不在本次核收；external_calls=0为原摘要和受限流程口径，本次未做独立全机网络流量审计。最终Gate表应分别标记本次HTTP/浏览器功能已核收和Q16 native200完整视觉证据尚未闭合。
