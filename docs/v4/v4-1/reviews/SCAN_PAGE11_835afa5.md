# V41 page11 copy-only 最终代码独审

日期：2026-11-04（台北）。source `835afa54dfa7d9b708f47112bd0c7b1974369e06`，tree `9f7e4cc18e712e74c448a0b6d7c41f7fe1b20a6d`，parent `4d6f20005bd8fbc4f65a385b510e7f9a4f259f73`。

结论：ACCEPT_FINAL_METADATA_CANDIDATE。可供 Root 普通合入后，对最终冻结 source 另开新 Full 扫描；本结论不是 Full 通过，不替代 Root 的扫描准入。

完整读取两文件各12行增量，唯一变化为已准入提案581df5fc对应的第8条copy-only绑定：f949页面第11行、43至116列、精确Match/span。原7条逐项保持；vendor去除该常量后的AST与parent完全相等，生成JSON所有其他键逐项相等；vendor的40anchors和8bindings与JSON一致。原算法与.gitleaks配置字节相同，222规则、45原native历史、96目录例外、152作者历史及40anchors不增。没有659提交白名单或位置容差。

独立从精确835afa5载入vendor和分类函数，只重放既有native.json原件；报告SHA256仍为 `0473ad95c444abdd899b282c049fa19cfb388651399842185fc5937914aa13ea`。51条全部classified、blocking0，且全部不命中作者历史批准。独立负例：dir/index102、九字段459、错误whole-blob51、修改源span51、实际单父42，全部拒绝；最后一类包含f949作者提交本身。多父/整blob/完整位置/Match/span守卫保留。

未执行新的gitleaks或历史扫描，未修改原件、refs、候选或远端。此前659的native exit1、37+14旧分类与六anchor阶段50+1保持，当前51+0属于对已有原件的纯分类结果，不回填旧失败。最终source新Full结果只能由后续新回执给出。
