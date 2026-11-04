# Native 强制清理P2修复独立复审

2026-11-04（台北）。结论：`SOURCE_FIX_ACCEPTED / PRIOR_P2_CLOSED`。冻结提交 `651cac313a242ebf1ad29cacc40f29d2d660d959`，直接parent为原审查 `315ee23948a4643ef2a007afc85f1c05a1a799c2`，tree `181d058ed7f7ace2b07732409f81f74400b42446`。唯一变更 `tests/e2e/v41/native_zoom.cjs`，+32/-1；独立核文件SHA-256为 `3d71c7695b946a1714d98c1a92cfe7af7c3cd4fec9b3cae05ca91820414f15dd`。关闭[原审查](NATIVE_315ee239.md)的唯一P2，原失败反例与历史HOLD保留。

新增 `markForcedStop` 在信号之前设置forced、保存事件、将状态置为FAILED_OR_UNKNOWN，并保留已有failure或设置NATIVE_FORCED_PROFILE_STOP。原PID/birth/UID准入通过后，intent记录bound/observed身份、信号及原因；使用wx/0600新文件写入并fsync，关闭成功后才调用原信号操作，再写SIGNAL_SENT或ALREADY_EXITED结果。intent写入失败不会继续发信号；其他信号错误仍沿既有失败路径处理。后续残留清零及source/tool复核可以记录cleanup.confirmed=true，但不会清除failure，最终仍抛出失败，不会返回采集成功。

复用原反例，以精确最终源码finally片段和新增helper原文、同一组模拟进程/时钟依赖作前后对比。315版本在模拟SIGTERM后仍为failure=null和CAPTURED_PENDING；651版本为forced=true、NATIVE_FORCED_PROFILE_STOP、FAILED_OR_UNKNOWN，同时cleanup.confirmed=true。独立断言实际模拟调用顺序为intent-open → intent-write → intent-fsync → intent-close → signal → result-write。该验证没有真实进程信号或文件持久化故障注入，不声称验证掉电耐久性；私有复现为Reviewer `.audit/v4-1/native-651-review/cleanup-repro.cjs`。

固定Node v24.21.0执行syntax check exit0，self-test原14项加forced分支1项共15项通过。复审未扩大矩阵；与13b086e→315ee239组合阅读，未发现本次差分引入的新P1/P2。公开调用接口、Root材料绑定、同Shell cookies/context/currentShopId、只读路由、native factor证据、profile前缀与e20父完整组清理约束均未改动，原审查的这些源码结论继续适用。完整PGID清理仍由父层证明，不能用模块PID清理替代。

本次仅接受公开模块源码修复，供Root后续集成；QA最终caller及组合Main独审另行进行。实际profile、浏览器、Native 200%、截图、服务与整链清理均NOT_RUN；视觉验收PENDING_REVIEW、browser native exit NOT_EXPOSED的边界不变。不签实际运行成功、Full、阶段完成或新资源窗口。
