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
