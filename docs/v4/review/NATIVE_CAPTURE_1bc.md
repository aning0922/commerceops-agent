# 原生截图 1bcd87a 主控独立增量审查

结论：ACCEPT_PREPARED_CAPTURE_ONLY_DELTA；仅接受取证实现，实际新浏览器视觉 Gate 待运行。审查人为 ROOT，未参与该文件本次作者修改。

候选 1bcd87a03c1c734208e846723724f7bafc8e1974，parent6e98399fb485d7a852d0e4c92923af0ef005782c，仅修改 frontend/v4-tests/lifecycle.live.ts。ROOT 已逐行读取42行 helper 与三个替换点，并实际逆还 helper/调用，结果与 parent 文件字节完全相等。全部原业务 POST、身份/回执/计数、单标题、超时/零重试及 profile 关闭守卫保持原样。

CDP 捕获使用真实原生窗口表面，未改 CSS/viewport/device metrics/zoom，也未拼接、后处理图像。设置页和模态框只记当前视口；会话页按实际滚动位置分段，双 RAF 后拍摄，原生 PNG 尺寸核对 DPR，文档尺寸变化、重复位置、空档和32段不足均失败。覆盖回执只有尺寸、滚动位置，不记录 cookie、CSRF 或请求。finally 恢复会话原滚动并 detach CDP；外层原 profile 清理仍执行。

作者完整 TypeScript 检查及 live1/fixture35 静态收集通过，早期隔离依赖不完整的检查失败保留。本次 ROOT 只做源增量和逆还字节核对，不重跑服务、不代签新截图。方法研究在公开 data 页有效，不能代签真实 UI。

后续 QA 需精确更新原固定 spec pin，并在新 owned 同源 API/PG/Web 中运行原单一测试；必须独立读取 PNG 和覆盖回执。原 F1 已通过功能、截图裁切限制及新的取证运行按各自 source 分列。
