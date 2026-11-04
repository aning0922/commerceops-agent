# 659 六锚点候选事实（待独立审查）

日期：2026-11-04（台北）。状态：**CANDIDATE_ONLY / ONE_BLOCKING_REMAINS**。Root 仅批准形成精确审查提交；本页不代表合入、push、Full 工程或安全 Gate 通过。page 第 11 行位置绑定尚未获准，未加入本候选。

## 来源与原始失败

Root 已核首次 allrefs 扫描实际 native 1：dir/index 零命中；Git 1,759 条为 1,745 已分类和 14 blocking。14 条均位于 `65959a543abab123614da2ee6c9722e24c9c6386`；该对象 tree 为 `145b970b9d9bfa2e67dfd8f815b4f99e48c4bf1c`，有三个父提交，呈 stash 形态，并非已推 `fcd8477c2d709afe82f7a678844b59dcdb07f511` 的祖先。旧失败、stash 和所有 refs 均保留。

Root/Astra 后续另准对该单提交完整 diff 取证，使用原派生 history config、redact100 和原完整 diff flags。实际原生报告 native 1，包含全部 51 条，未筛选覆盖原件；其中 37 条本来已分类，14 条原阻断。原报告 SHA256 为 `0473ad95c444abdd899b282c049fa19cfb388651399842185fc5937914aa13ea`。不是 51 条新增阻断，也不能将原生退出改写为 0。

## 本候选仅六个完整 blob 锚点

修改仅为 vendor 常量中的六个 anchor 及相应生成 JSON；另附本事实页。五个文档 blob 指向已核 `fa96764cf2b8e3ab9adbb579b764f600a7d17e60`，page blob 指向已审 `f949781fa0b9958fedeaf3303c4cf6cefdef8322`。不枚举 659 为允许的 merge SHA，不增加 author 批准、目录例外或 copy-only 位置绑定。

| 路径 | 精确完整 blob | 本次文档分类覆盖 |
| --- | --- | --- |
| docs/v4/baseline/API_EVENTS_CONTRACT.md | c0375ea6f87ca3c6c77fdc1ebcb91c258916b7b0 | 第 14 行 |
| docs/v4/baseline/evidence/A_EXECUTION_RECEIPT.json | 6f557ffb294209637a0293f5b310d3477edb6435 | 第 5 行 |
| docs/v4/baseline/evidence/CONTRACT_REVIEW_CANDIDATE_HASHES.json | 992581f35dec4fa94b1dc2fdb5ac79a4211909b6 | 第 5、9 行 |
| docs/v4/baseline/reviews/M3_API_INVENTORY.json | 4120a447bf26812585d40ea81fc156cfdfa7400a | 第 42、64、86、108、130、152、18512 行 |
| docs/v4/baseline/v4-public-openapi.json | 58ad090b39b70954065b9613b53a8fe65f19e193 | 第 99、251 行 |
| frontend/app/v4/[[...path]]/page.tsx | 6fe538b6de6f6532a8198476a0ca8a2dd9ca05ee | 第 11 行仍 blocking |

anchors 从 34 到 40。原 222 条规则、45 条 native 历史 allowlists、96 条目录例外、152 条精确历史和 7 条 copy 绑定保持不变；`.gitleaks.toml` 与 `scripts/scan_secrets.py` 字节不变，其余 provenance 字段逐项相等。

## 有限分类与反例

同一完整 51 条原生 finding 在本候选下为 **50 reviewed merge-copy / 1 blocking**：原 37 条保持，新增分类 13 条文档命中；page11 唯一阻断。测试不重新运行全历史扫描，也不把原 native1 当作分类 wrapper0。

有限反例分别为：51 条的 dir/index 共 102 个拒绝；九字段乘 51 共 459 个拒绝；50 条可分类项的新 blob 及源 span 篡改各 50 个拒绝；找到实际单父来源的 41 项均拒绝作为 merge-copy。九字段包括 rule、path、commit、起止行、起止列、Match 和 fingerprint。没有将非单父来源虚报为已验单父负例。

全部原件在 GATES 树 `.audit/v4-1/gates-prep/659-native-sso7w33d/`：native.json、capture.json、candidate-classification.json、candidate-check-receipt.json、check_candidate.py 与原日志。首次私有检查脚本直接路径启动因缺 root sys.path 而失败，未执行断言；失败日志保留，使用正确 runpy.run_path launcher 后有限检查通过。未启动任何 Docker、PG、API、浏览器或网络请求。

page11 的独立提案为该目录 page11-copy-only-proposal.json，SHA256 `581df5fc0799d1c477518f905564ebb6a2904372b37d51182ec3f405c005cf82`。新 native 为第 11 行、列 43–116，完整 span 与旧批准第 9 行相同；原位置守卫继续拒绝新行。本候选没有采用该提案，也不做行号容差。Astra 需另裁定 stash 语义与精确位置绑定；如另获准仍须验证单父/dir/index拒绝且不增加 author 批准。

提交前仅核生成一致性、算法/规则字节不变、Ruff/mypy、文档与显式三文件 current/index 原生预检。Root 不合入或推送该未闭合候选；Full 继续 HOLD，任何后续完整扫描须新准入。
