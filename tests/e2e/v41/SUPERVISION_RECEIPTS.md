# 监督异常边界增量

对应独审 `00bb3d47abd1cb658aa76bba581000761f8ce719` 的 P2-Q01：原 foundation 的 ps identity
异常和注册写入失败可能越过 finally，原 HOLD 结论继续保留；本修复必须精确 SHA 复审。

Popen 成功后的 identity、注册和 wait 全部纳入 finally。探测/注册失败按安全 stage/type/errno
记录，仍通过自建且未 reap 的 direct-child handle terminate/kill/wait；不向身份未核的 group
发信号。直接子进程的真实 native exit 与 group 盘点结果分开；group/后代未知不能填已清理。

逐登记项捕获 parse/ps/timeout/signal 异常，UNKNOWN 残余和安全 observation 留存，不阻断其余
登记项。组长已退出而后代仍存活时，不因原 leader birth 记录就强杀当前未知 group。
外层即使 inventory 再抛异常也写实际 worker exit、UNKNOWN 残余和回执；worker0/检查通过
不覆盖清理未知。`requested_outer_exit` 是随后请求给 SystemExit 的值，实际 outer CLI native
仍由调用方 wait 观察，不能把该字段冒称外层已退出。

新增测试的错误来自真实短子进程非零/超时、真实注册路径冲突、实际 group leader 退出，
包括未核 group 不 signal、子进程 reap 和外层实际 worker0 后异常仍落盘。故障注入只在
单测边界；固定 recipes 不接受任意命令或运行时替换，不支持服务和业务执行。
这些是本机进程模拟，不签 importer 2秒解析预算、PG advisory slot 生命周期或 V41 StageGate。
