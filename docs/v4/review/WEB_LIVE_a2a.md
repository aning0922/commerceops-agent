# V4真实浏览器spec a2a专项审查

日期：2026-11-04（Asia/Taipei）。**结论：P2_REQUIRED_CHANGES，0 P1 / 2 P2；暂不签该live spec准备接受。** 两项是测试隔离及响应等待的接线问题，不把未运行的真实GUI/200%/Full列为本包缺陷。

candidate `a2a7873ca7453fc2c86ffdc1b8cd57063b66f5b3` / tree `44f3e3b8cf9675f46199e034456364bc303dd8cd`，从已审WEB63a经bcdbcf4→788eeb3→a2a，累计只新增`frontend/playwright.v4-live.config.ts`和`frontend/v4-tests/lifecycle.live.spec.ts`。只读该精确链与已审前端实际poll逻辑，不读WIP。ROOT实际delta2/cleanup结果保持独立，不代签本浏览器用例。

## LIVE-01 [P2] 新live文件被原UI_FIXTURE配置同时收集

位置：新文件`lifecycle.live.spec.ts:8`与原`playwright.v4.config.ts:2`的testMatch='*.spec.ts'。

新文件名仍匹配原fixture glob。独立在精确a2a前端测试快照，仅运行Playwright --list（无浏览器/网络）复现：原配置不设V4_API_ORIGIN时native1、0tests，报新live文件第8行Invalid URL；补live env后原配置native0却收34tests/2files，其中含LIVE标题。原33项UI_FIXTURE因此被无意混入要求实际API并会真实创建tenant的用例；是否最终能连接真实服务不能由fixture命令名称保证。

最小修正：让新增live文件不匹配原fixture glob，例如改为独立`.live.ts`文件并更新专用config的精确testMatch；或ROOT明确允许后给原配置增加精确testIgnore。不要用skip缺env或默认真实API来掩盖混收。补两种--list回归：原配置无live env仍只收原33项，新专用配置只收这一项，且两集合无交集。影响旧fixture收集/执行隔离，不能归因于后端未启动。

## LIVE-02 [P2] persona/reset读回等待器会接到控制前的在途轮询

位置：`lifecycle.live.spec.ts:13` response helper；switchPersona内updated promise及resetCurrent promise。

helper对GET /session只筛origin/path/method/HTTP成功，等待器在点击控制前注册；页面已知active后每5秒轮询current。若控制前的poll仍在途，其200可能在新POST和真正读回之前到达，updated/resetCurrent就会先解析旧persona/旧generation，随后断言新target失败。前端本身通过seq丢弃旧响应，并不阻止浏览器产生该网络response事件。因此真实后端/页面都正确时此用例仍可假失败。这里为精确源码时序反例，未声称实际浏览器已发生一次竞态。

最小修正：控制读回listener在点击前注册，但必须过滤到同creation key/tenant及本次预期persona、精确epoch/generation的当前响应（完整schema继续核验）；或实现等效的操作关联捕获。不要关页面poll、mock响应、sleep固定延迟或开重试来绕开。补纯等待器/受控事件序列验证：旧在途200先到不能消费新控制读回，正确新context随后到才完成。影响persona/reset阶段的live稳定性，不要求改后端或UI实现。

## 正向范围：确为live路径，但尚未运行

用例只有一个固定标题`LIVE: isolated demo lifecycle and browser layout`；无route.fulfill、route.abort、fetch替身、mock transport、手工cookie认证注入或storageState导入。通过页面点击真实创建/切persona/reset/logout；response过滤配置API origin并用原冻结v4-schema全部Envelope严格Ajv校验，不把HTTP200本身当语义成功。

创建核请求key/回执/creation key、初始operator双店及代际；两店summary核请求shop、header代际、响应shop/context及UI计数文字。persona核旧期望代际、原key、回执、同tenant/org、principal变化、epoch不变/generation+1、目标persona/店铺数量和读回context；restricted_admin reset要求同principal、epoch/generation各+1且仍无店；再切回operator。logout核key/代际、UI清屏和cookie移除。实际数据库次数/回执event持久化不由本浏览器spec独立核验，仍须QA PG observer证据。

创建cookie断言仅目标API的commerceops_v4_demo唯一、HttpOnly/Lax/Path=/api/v4，HTTPS时要求Secure。无trace/video/自动失败截图、无敏感storage导出；显式截图是匿名欢迎页。当前没有独立浏览器storage凭据检查、跨tenant/跨tab/迟到渲染或真实网络ACK丢等新增分支，不能据这一个生命周期用例宣称全部Web边界已验。

布局只在匿名欢迎页1440/1280/390×900下核button可见及scrollWidth==innerWidth，检查prefers-reduced-motion媒体匹配并各存一张截图。之后生命周期只在1440进行；不能把三张欢迎页截图说成登录态/各role/弹窗的三尺寸视觉验收。Enter开dialog、Escape关dialog和返回reset焦点有明确断言；Tab之后只核dialog文字，未验证完整焦点循环/陷阱。实际200%桌面浏览器GUI未尝试，保持独立未验；没有用CSS scale或viewport变小伪造200%。

## 配置及运行边界

专用config要求三项显式env、workers1/retries0/timeout120秒、reducedMotion=reduce；不自启服务。ROOT运行时须绑定已审整合source、实际API/Web同一新owned窗口、独占新evidence目录和外层绝对截止。Playwright outputDir指向该目录，会管理其测试输出，不能把已有case私配/PG回执目录直接当可清空的outputDir；本spec本身不是资源owner或清理driver。此为输入范围说明，不另申请运行或扩展TTL。

独立仅collect：新live config **1 test / native0**；原fixture无env **native1/Invalid URL**；原fixture有live env **34 tests/2files/native0且混收live**。使用精确源码与现有锁定node_modules读取依赖，临时目录/cache均在Reviewer .audit并已清理。未启动浏览器、访问URL、截图、操作真实cookie、连接PG或启动服务。本轮没有重新跑typecheck，作者pure/type/collect1仍按原准备事实分列。

请作者在新增文件/config范围内优先修隔离及等待关联，普通提交精确SHA；原33fixture和新单live分开收集后再复审。当前driver8196已另签11HTTP准备组件，不等于此live spec已接受，也不等待不存在的TTL/browserMode来覆盖本次问题。
