# V4 browser_lifecycle固定363来源的2c4专项审查

日期：2026-11-04（Asia/Taipei）。**结论：ACCEPT_PREPARED_BROWSER_DRIVER_363，0 P1 / 0 P2。** 只接受已审363 spec的固定browser mode组件，不签整个2c4组合资源准入；6ca owned API密码文件P2仍独立待修，新693原生200%段不在pins内且尚未接受。

candidate `2c4a4a64aac91c283df70b67b371909e98612392` / tree `8c3ee8eee38386de66657da057347f4aace0e40c`。本次同时读该提交实际browser_lifecycle、测试与owned_driver调用/结果路径，不能只据机械pin改动签未读的wrapper。未读WIP，未启动Node/browser或资源。

## 来源与命令边界

固定WEB_SOURCE为36319b458a304311d01e3f05afc356568424a59a，四PINS对应live config、lifecycle.live.ts、lifecycle.waiter.mjs及v4-schema.json。独立git show/rev-parse核四文件实际Git blob与PINS逐一相同；不是仅信WEB_SOURCE注释。

verify_source要求工作文件存在、末级非symlink、resolve后仍在ROOT内，按完整bytes计算Git blob hash，且git rev-parse HEAD:path必须同pin。由Case.validate在资源启动前执行，browser wrapper入口再执行；Case本身另核干净HEAD/tree及ROOT实际source。文件变动、缺失、已审原363未合入、helper/schema更改均不能通过；未来693不能因标题同名被旧pin放行。验证没有从CLI/env接任意source/spec/command，也没有任意ancestor回退。

command固定ROOT本地Node、锁定Playwright CLI、专用config、lifecycle.live.ts、转义后的完整单标题grep、workers1/retries0/forbid-only/json reporter。原fixture glob和旧*.live.spec.ts不被选择。固定config无自启服务，实际API/Web由ROOT owned driver先启动；ROOT仍须提供与全树source一致的工具链/依赖和镜像，四pin不是整个产品/依赖验收替代物。

wrapper只接受--case固定形状，验证scenario=browser_lifecycle；设置umask077，新建独占700 case/browser目录，向Node只传本机工具PATH/HOME、当前case的canonical loopback API/Web origin、独占evidence目录和telemetry关闭，没有owner DB环境或凭据值。用execve替换已受supervisor管理的probe进程，不用shell或任意caller argv。

## 报告与清理路径

driver先等待真实probe native退出，非0或watchdog错误不进入成功路径。native0后读取本case probe.raw.log JSON，validate_report要求errors为空、stats四项精确整数expected1/unexpected0/flaky0/skipped0；递归只准一个固定title且ok=true、一个expectedStatus=passed test、一个passed result且retry0。空集合、多测例、skip、flaky、错误标题及重试均不能冒签成功。未知/损坏JSON抛错，保留FAILED_OR_UNKNOWN，不自动重跑。

只有这些检查通过且工作预算仍在，才记录browser_live selected1/passed1/skipped0/retries0；随后仍须完整writers停止、API与owner oneoff停止、最终PG facts和project清理。最终browser状态是EXECUTED_PENDING_REVIEW或NOT_ACCEPTED，不是正式acceptance；Full/Hosted仍NOT_RUN。

父对外回执只输出状态/计数/证据定位，不打印完整Playwright报告。probe原始输出由supervisor新建600文件保留；已pin的363 spec关闭trace/video/自动失败截图且未打印bearer/CSRF，响应断言仅输出规定字段/布尔或合成页面信息。该结构不是对任意未来spec的无秘密保证，未来源码必须再审再pin。outputDir是新建空browser目录，不能用已有case凭据/PG回执目录替代。

## 独立验证与范围

精确2c4快照定向 **12 PASS / 0.21s / native0**，覆盖source缺失/bytes变化、固定command、单report/skip/failure/flaky/retry/标题/重复结果拒绝；另独立核四pin的真实363源对象。未执行实际browser、截图、HTTP/PG或监听服务，无真实GUI200%行为。临时测试目录已清理。

ROOT应先处理owned API 6ca独立P2，再将相应已审组件与363产品普通集成、绑定新资源/UTC后运行。将来原生200%修复源码接受后，QA需另交新的准确spec/helper pin更新；本次不接受任意未来hash、不扩命令、不预签200%。当前已审HTTP/TTL/browser准备结论分别分账。
