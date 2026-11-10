# V41 browser subject writer 接口独立审查

日期：2026-11-04（台北）。source `95deb3943d53f444bb63e48b5245deb3d19ea3fe`，tree `ca466a7ee27d36f727c3820ba555877d175a7412`，parent `7358880dfb82c72da899d02f133d0ff3462f0042`。增量仅 `frontend/v41-e2e/browser-subjects.ts` 与 `tests/e2e/v41/test_browser_subjects.py`；未读WIP。

结论：ACCEPT_LOCAL_BROWSER_WRITER_INTERFACE，在本地文件写入/异常传播的接口范围未发现P1/P2。可窄合入该两文件；不据此签实际浏览器先记后发、业务请求/服务端提交或终态消费已接通。

文件和意图：readBrowserCase核本UID、0700规范case目录、0600有界普通case文件、固定shell scenario/source/tree/project、UTC活动窗口和180秒余量、两独立本机端口。writer使用固定shell/business路径、wx独占新建；追加使用O_NOFOLLOW，fstat要求原inode/device、普通文件、本UID/0600、512KB和1000事件上限。初建和每次追加均同步fsync，部分write循环补全，异常不吞掉，追加fd在finally关闭。业务ATTEMPT_STARTED必须携带原POST witness，核四固定路由、scope/shop/key/counters、字段白名单及有限JSON/64KB；不会自动生成替代key、ACK或重试。

证据边界：request_body_sha256是排序JSON键后的本地body字节SHA，记录同时保留method/path/body。它没有声明服务端payload_digest、canonical_request或receipt证明；ACK/READBACK状态只是调用方提供的观察值。该writer不是DTO完整业务验证器，也不是事务结果裁判。原headers/cookies等顶层材料不在允许的witness/body字段中。四路由和允许字段与Root590已审HTTP/DTO接口相符。

独立验证：精确archive内使用已准备Node二进制，只运行本地组件。新增pytest节点1 passed，0.33s，nativeexit0，覆盖原body、缺intent、非法字段/路由/scope拒绝、UNKNOWN、重复创建、权限改变和symlink拒绝。另以实际Node加载同一未改writer，注入fsyncSync异常：调用方continuation标记保持false，异常确实传播；已经写入的原ATTEMPT_STARTED/key字节保留，没有ACK/payload_digest或HTTP调用，实验nativeexit0。未把文件可读等同于服务端执行。

明确限制：目前fsync的是文件，没有fsync父目录；这里只接受进程级同步写入及异常传播，不声明新journal目录项的整机断电/重启恢复保证。fsync失败后已写字节不等于已持久成功，调用方必须停止该路径，不能吞错后发送。实际浏览器接线须在请求发送前调用且等待同步返回，原JSONL的最终聚合/只读事实消费另验；本片未修改或证明这些消费者。writer本身也不是独立Root运行授权，仍受外层新case/window与已审driver控制。

无真实浏览器、HTTP、owner动作、SQL、Docker、服务、Full/CI或远端写入；只使用新临时合成文件，未读取真实凭据。Root590组合与未来真实case并未由该组件测试验收。
