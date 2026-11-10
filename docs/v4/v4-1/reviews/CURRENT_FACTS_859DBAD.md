# V41 currentFacts 请求与 UI 关联独审

日期：2026-11-04（台北）。结论：`ACCEPT_SOURCE_AND_BOUNDED_PURE_COMPONENTS_BROWSER_NOT_RUN`；精确两路径候选无实质 P1/P2，可供 Root 普通集成。本回执不签正式browser或r8，不改写r7失败。

source `859dbad0764ce280f244f539880fd97024274b4b` / tree `c9eebeab0e99cb236c9f969a3e4a6c99937cb605`，精确父 `2140fe22a97850a1c312393198b78a0225ff3b9a`。diff仅 `frontend/v41-e2e/shell.live.spec.ts` 与新增 `frontend/v41-tests/current-facts-correlation.test.mjs`，201+/13-。二者SHA256分别为 `82424a643eef2e598b47785f3ac2f504c35c8346e880dd9030cebeeb5926b063`、`3aada45672bba7a7554ca08015b43fefc9ab78c7bde342b01160b2dd87e30be5`。

## 核对结果

- click前安装request/requestfailed监听并arm，只收原API的GET/read-context/mainFrame请求；按Request对象去重，不以URL替代对象。完整query entries比较保留重复/额外参数拒绝。直接Request.response后回核response.request对象；response构造后才检查已填充的timing.startTime，未知值拒绝，原生start早于arm排除。没有以request事件初始timing=0误判已开始请求。
- 每个收录请求有独立bounded任务，依次核finished=null、HTTP200、精确no-store、JSON、严格Ajv、原五身份字段及shop；query不符立即保留fatal，后续验证成功不会清除。requestfailed和各任务异常都保留失败。任何后来的有效响应不能把已捕获失败改成成功。原代码没有新增POST、重新click、请求重发、取消传输、时间仿真或关闭产品timer。
- UI按完整“数据读取于 + read_at”标记匹配唯一validated响应；没有first/latest/max时间启发式。多个完整UI标记或多个有效响应共享显示timestamp均拒绝。poll要求匹配且已捕获任务全部done；关闭admission后仍全await捕获任务，再读取UI并进行原heading可见与完整文本exact断言。窗口之后的新请求不扩充此次关联集合；结论仅对应这次最终UI观察，不声称页面以后不再刷新。
- 共用原5秒deadline，响应/finished/json/UI操作均受该绝对预算约束。任务自己catch并在finally标done；Promise.race持有底层拒绝处理，超时后不重试或abort传输。外层finally停止收录、关闭probe、等待已捕获任务、移除两监听后写独占safe序号trace；trace只含安全状态、时间、序号及read_at，不输出cookie/header/body。trace写失败也不会转为成功。
- 只读本机PW1.64的invokePollMatcher/pollAgainstDeadline实现：probe的await在matcher重试catch之外，probe抛出的fatal/歧义会向外传播，非普通matcher失败重试吞掉。此为已安装依赖源码核对，未调用浏览器。
- 原offline、hidden、includeHidden DOM清除/cookie、五身份字段与creation key的GET恢复、create1、零额外POST、Native及lateACK代码在本差分中不变；原fixture/父进程/config/business/product/锁不变。

## 独立纯验证

从精确Git对象提取两文件到新review-owned目录 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/v41-859-review-k2sp2x3j`，未读作者WIP/private auth。使用既有Node运行原16项helper组件测试，16/16通过、native0、约128ms；执行的是标记区内精确helper，使用EventEmitter及Fake Request/Response，没有Playwright资源启动。

另在该临时树新增4项review边界检查，仍提取原helper：poll完成瞬间新收录的延迟503被全量drain并拒绝；bounded超时后底层response Promise迟到reject没有unhandledRejection且监听已移除；重复及额外query参数均fatal；多个完整UI标记拒绝。4/4通过、native0、约143ms。临时复核脚本 `frontend/v41-tests/current-facts-review-boundaries.test.mjs` SHA256 `c7ed26ec49d5b323c0c3f8fba0c430b5378a88f0afda644c9fd5c72eb1810057`。两次Node stripTypeScriptTypes实验性提示原样保留；没有修改候选测试或业务源码。

作者全TS/两原标题collect成功及首轮Fake noStore错误修正是Root转交记录，本轮未重跑TS/collect，不以摘要替代原始开发失败日志。r7 business PASS、handshake/CFT native0与Shell失败/Node1分账保持；r7具体旧Request因无lineage仍UNKNOWN，不能把已证刷新竞争机制指定为唯一timer根因。新的实际关联、offline/hidden/Native与最终清理仍等待精确新案运行回执。

本轮无浏览器、服务、PG、Docker、build、网络、Full或CI运行；仅新增本审查文档，指定changed-file/index预检通过后普通提交，不push。
