# V41 next-env唯一生成声明窄修审查

日期：2026-11-04（台北）。source `1794fc7d5e87f252ad16fa54c5594a6c704ef3ac`，tree `afa8c1cb6023e333ccb9f7e04a2d62d8df9ce9d0`，parent `2db8f33863eda411cf0474f73e6657e39865f756`。仅source_seal.py、test_source_seal.py及owned_driver唯一比较caller。

结论：ACCEPT_EXACT_NEXT_ENV_SEAL_PATCH，未见P1/P2。Root可按该三文件精确patch窄cherry-pick；不准把1794整个父链当作已接受，187浏览器PGID清理P2仍HOLD。2db的窄配方接受也不解除该父问题。

独立核模板确为7行296bytes，SHA256 `0f70629890b72a0a82e91972cc032c04b658b26c265373cb711cf576bfbf8fcc`；唯一frontend/next-env.d.ts，内容包含固定两个next引用和两个.next/dev/types声明路径。不是按后缀/目录或文件名无条件跳过。实际打开使用O_NOFOLLOW/O_NONBLOCK，根与frontend父目录canonical，fstat普通文件/本UID/600或644/精确长度，读回原bytes及hash双核。symlink、异内容、额外声明、错误权限/UID或其他untracked路径不被例外接纳。

每次snapshot记录ABSENT或PRESENT_CANONICAL的实际hash/UID/mode/bytes。matches_source严格要求唯一generated key与规范record，其他所有字段完全相等；仅允许ABSENT→规范PRESENT和完全同态。PRESENT→ABSENT、既有600↔644、head/tree/tracked/tool变化均拒绝。tracked文件原Git blob/执行位、staged diff、其他新输入和既有source/tool规则不改，owned_driver唯一调用点在保存after快照后使用此窄比较。

独立验证：精确1794 QA archive，使用已审Root590 backend作为明确依赖；test_source_seal及test_owned_driver共8 passed，3.18s，nativeexit0。另纯函数九格状态矩阵实际为ABSENT行[true,true,true]、PRESENT600行[false,true,false]、PRESENT644行[false,false,true]，模板长度/行数/hash同时通过，nativeexit0。无生产源码修改或资源运行。

Root报告旧r2 owner三动作/HTTPprobe0及terminalseal失败、freshsnapshot定位单列保留；本轮未重读或改动r2现场，不把新的源码判据追溯应用来重签旧案。后续实际source比较效果仍待Root新冻结组合/新案。无Docker、PG、API/Web、浏览器、SDK、Full/CI或远端写入。
