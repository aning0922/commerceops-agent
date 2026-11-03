# V4 headful原生200%准备增量693专项审查

日期：2026-11-04（Asia/Taipei）。**结论：P2_REQUIRED_CHANGES，0 P1 / 1 P2；新增原生200%段暂不签准备接受。** 唯一待修为启动未返回context时的profile删除条件，原363移动nav/生命周期准备接受不被撤销。

candidate `6937a39d4ebb6d77f653d489db9964083a179d68` / tree `d72d15861696e157e00297a8cccab1e2446df22a`，parent363。只改lifecycle.live.ts一个文件，在原single title尾部追加headful段，未改config/120秒上限、产品或API。只读精确提交；未启动浏览器、访问Chrome设置/HTTP/PG或实际截图。ROOT的方法探针保持独立，不转记为本spec运行。

## ZOOM-01 [P2] launch未返回context时未经关闭即删除profile

位置：lifecycle.live.ts最后`finally { await zoomContext?.close(); await rm(profile,{recursive:true,force:true}); }`。

profile由mkdtemp创建后，若launchPersistentContext抛出而未返回，zoomContext仍为null；optional close直接完成，rm仍执行。此路径没有任何关闭完成的证据，却删除了本批profile及可能的启动失败诊断材料。不能仅凭launch promise拒绝就把所有部分启动情况统一记作已关闭；ROOT明确要求“关闭成功后才删，失败保留”。context存在且close抛错时rm不会执行，这条分支正确。

独立抽取精确finally语句作纯Node控制流/临时目录探针：null context时closeCalls0、profile被删除；close抛错时profile保留；close成功时profile删除。三条均未启动浏览器，所删只为Reviewer本次新建合成目录。反例证明的是删除条件，不声称已观测Chromium泄漏进程。

最小修正：只有确实取得本批context且await close成功，才删除mkdtemp返回的该目录；launch失败/context缺失及close失败都保留private profile，并让原错误保持失败。不要任意寻找/删除其它profile，也不要吞launch错误。补这三种清理分支的纯用例；若用明确的更底层进程退出证明处理launch失败，应单独提供可审事实，不能凭null变量推断。

## 已核原生缩放与真实交互准备路径

profile使用本批evidence目录下mkdtemp新前缀，未传既有用户profile；没有持久化storageState或接管真实用户浏览器。headless=false、viewport=null、仅固定window-size1440×1000及reducedMotion，未设置CSS zoom、viewport缩小或deviceScaleFactor伪造倍率。

先在真实V4页记录未缩放outer/inner/DPR/visualScale/cssZoom，再进入chrome://settings/appearance，要求select#zoomLevel初值1、真实选择2并读回；回V4页面要求outer维持1440、inner恰减半、DPR恰翻倍、visualScale仍1、CSS zoom仍1及无横向溢出。设置截图与非秘密metrics JSON均计划保存。ROOT原生方法探针只证明方法可行，此处严格断言若环境不支持应失败，不能将其改成模拟缩放通过。

第三个独立context内通过页面真实创建新tenant/key，并与前两个生命周期不同；current与CreateEnvelope关联的waiter沿用strict schema/精确context校验。随后真实选店summary，核shop/header代际/context和UI计数；键盘focus+Enter点击可见移动nav进入设置，核URL/aria-current与原身份；真实打开dialog、核按钮/Tab内焦点/Escape返回，再真实logout并核敏感UI与cookie清除。没有route mock/伪造API response，也没有实际确认200%下reset（这里只开关dialog）；不能扩大该段覆盖。

请求监听仍只匹配固定API origin和既有/api/v4/demo路径，真实环境由ROOT driver的canonical loopback配置/新owned source和后续精确pins绑定；spec本身的env不是独立资源授权。profile路径不接受外部profile变量，只删本次mkdtemp返回值，但需要ZOOM-01补闭环。trace/video未启用，截图页面仅合成业务，metrics不含token/CSRF；异常保留的profile仍可能含本批cookie，应保持新private目录并由ROOT按具体对象处理。

## 独立验证与交接

精确693快照仅Playwright --list：**1 test / 1 file / native0**，同一LIVE标题。清理纯探针native0，结果如上；未复跑无关pure/type/build，也未启动headful或真实200%。临时收集/合成目录已清理。旧35fixture/原live准备与本追加段运行结果分列。

请WEB只补profile删除条件后交普通精确commit。QA当前2c4仍固定363，应在新spec最终接受后另交机械pin更新，不放宽source/blob/命令。当前不得用693或ROOT旧方法探针签signed spec的native200；实际GUI仍须新owned窗口及对应输出/退出/清理事实。


## f18（含e8a）清理专项复审：ZOOM-01关闭

日期：2026-11-04（Asia/Taipei）。candidate `f18ba5bf5c9de88d113eb5a5bff244cd66416c2b` / tree `37503a2cd0c5bd3e8fb6ac08ff56e6ad50e5a6ac`，parent `e8a04cc15b5fbd89bc0951fbbcbc5256b4c74ef8`（tree `dde7f9523859ee1aded3d560c48f5cbf03315d4c`），前接693。**结论：ZOOM-01 CLOSED，清理增量0 P1 / 0 P2；ACCEPT_PREPARED_NATIVE_ZOOM_DELTA。** 本次只复审原d052清理问题、三分支纯测及双失败原因保留，其余693原生缩放/交互审查范围沿用上文，不重做全审或声称实际运行通过。

live finally实际接入新增closeAndCleanOwnedProfile helper。无context直接返回false且不调用remove，launch错误仍由原catch重抛；有context先await close，close拒绝即传播且不调用remove；只有close正常完成才对该调用者传入的本次mkdtemp profile执行rm(recursive/force)，不发现或删除其它profile。正文失败而close成功时仍保留正文原错误，已确认关闭的本次目录可以清理；close失败则保留目录。

f18新增独立zoomFailed布尔与zoomFailure记录，避免throw undefined等falsy值丢失原失败判断。正文与清理同时失败时抛AggregateError([原失败,清理失败])；只有清理失败时直接抛清理错误，未吞掉失败或转为成功。没有新增signal handler、任意profile输入、重试或资源操作。

独立精确f18的新增Node测试 **3 PASS / 0 FAIL / 0 SKIP / 64.147ms / native0**：null context remove0；close错误原对象传播且remove0；close成功严格先closed、后仅删除给定profile与固定options。另用精确helper和同一catch/finally控制流构造不使用page/browser fixture的Playwright纯用例，刻意令正文与close各抛不同合成原因：实际JSON report为failed、native1，并分别保留AggregateError、正文原因与close原因三条错误。这个native1是预期失败证据保留探针，不是作者live测试失败；没有启动浏览器或服务。

所有临时纯测试目录已清理，未改实现/产品代码。实际headful启动、Chrome原生200%、API/PG/UI行为及profile关闭事实仍待ROOT新owned窗口；ROOT方法探针不代签本spec。后续QA应把最终spec及新运行依赖lifecycle.profile.mjs一并纳入精确source/blob绑定；本回执没有审查或自动更新browserMode pins，也不授权旧pin接受新文件。
