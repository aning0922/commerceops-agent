# V4-0 本地阶段交付

本阶段以 M3 已验业务源码为起点，在独立集成分支 `codex/v4-control-20261103` 实施。V40-01/02 复用已批准基线与四份合同；V40-03/04/05 完成服务端演示身份、双店联合种子、重置和欢迎体验。原 A 阶段 NOT_STARTED 是历史记录。

## 实现与文件归属

- BACKEND：新增 0024 迁移及十张演示表、复合来源约束、窄数据库权限；`application/v4_demo` 定义合同与 seed 规格，`infrastructure/v4_demo_*` 管理身份、种子和事务。`v4_demo_http.py` 提供真实接口，原 API 工厂注册路由。
- WEB：`frontend/app/v4/[[...path]]` 提供 `/v4`、`/v4/demo`、`/v4/settings/demo`；真实服务端上下文、双店摘要、角色切换、二次确认重置、退出、移动导航、键盘焦点和失效清屏。
- QA：新 owned API/PG/Web 验收入口、严格 DTO 检查、固定场景、原生浏览器缩放及清理回执。原有 PG 验收仅更新当前 head 精确 schema 预期，历史迁移检查保留。
- SECURITY_SCAN：新公开材料导致的精确假阳性来源绑定及同 blob 合并副本核验；保留全部规则、目录/index/完整历史扫描、原历史例外和拒绝负例。
- ROOT/REVIEW：冻结合同、每次源码与资源窗口、独立审查、安全回执和交付说明。完整实际文件列表见 `FILE_MAP.json`。

## 行为与边界

每位访客由服务端建立独立演示 tenant、身份及两家合成店铺；三种 persona 的授权由服务器和数据库校验，切换后重新核验。会话是固定 30 分钟绝对到期；切角色与重置不延长期限，原键去重、只读 UNKNOWN 核对、CSRF/Origin、店铺范围和撤权/登出失效保留。重置在事务内清理当前租户覆盖数据、重建固定 seed、旋转 epoch/generation，其他访客不受影响。固定 seed 含两店联合异常；无真实商业数据。

首次欢迎和六个场景卡明确标注真实状态，后续场景仍在规划，14 模块/66 页面/99 功能不是本阶段完成范围。保留 M3 单 Worker，Harness 未合入。没有模型、embedding、飞书实际发送或 Woo 写入。

## 实际验收

| 验收 | 实际结果与受测来源 | 回执 |
|---|---|---|
| PG 组件 | 23 项，分源原生检查 | SCHEMA_SIX_461 / IDENTITY_FOURTEEN_3606 / ROLLBACK_TWO_1C35 / DB_CAP_761 |
| UI fixture | 35 PASS，13.208 秒，合成响应 | UI_FIXTURE_363_FULL.json |
| 真实 HTTP | 11 类成功：F1 两项、R2 五项、R3 四项 | HTTP_FINAL_MATRIX.json |
| 固定 30 分钟 TTL | DB UTC 自然跨到期，原创建/期限不变，到期拒绝 | TTL_F1.json |
| 真实浏览器 | R3 固定生命周期 1 PASS、0 skip/flaky/retry；8.181 秒；1440/1280/390 与原生 200% | BROWSER_R3.json |
| 对应旧业务 Web | F1 read/write/items=7/10/7，共 24 PASS；N01 六项 PASS | LEGACY_WEB24.safe.json / N01_SIX.safe.json |
| 完整工程 | cbd 原 scripts.check native0，1389.861 秒；4316 offline PASS / 748 deselected / 4 warnings；M3 无 server46/46，前端类型、NPM/95包Python审计通过 | ENGINEERING_CBD.json |
| 完整 PostgreSQL | R2 existing568 + phase3177 =745，零交集；严格配对native0；G1三/G2六；两线清理0 | FINAL_GATES.json |

工程检查含公开依赖漏洞查询的网络访问；没有真实业务 provider 调用。历史原生秘密扫描有 1555 条已审分类、blocking0，扫描包装器及完整工程退出0；不宣称原生没有命中。工程 Markdown204 是受测 cbd 时点，后增交付文档另跑检查与扫描。四项既有 deprecation warning 保留。

独立核收包括 HTTP11、R3 视觉、legacy24/N01、四合同与源复用，以及完整工程实际原件。PG 完整配对及最终阶段独审已核收；后增文档由冻结提交的独立文档 Gate 回执记录。

不同来源的回执各自绑定 SHA/tree。代码复用依据后端与产品 UI 子树、PG 测试/工具链/锁文件的实际 byte identity；不把旧源码的结果改写成最终源码运行结果。先前失败与 UNKNOWN 原件保留，新 case、新窗口的后续通过单列。

## 运行与审查

复现入口为 `LOCAL_RUN.md`；自动验证会在结束后关闭服务，现无常驻演示地址。截图保留于对应 R3 browser 原件目录，并以原始哈希核验；200% 使用真实 Chrome 缩放和五个重叠视口，无拼图或 CSS 放大。手动浏览步骤经过源码核对，尚未单独作为手动整链验收。

新测试卷按各案回执保留；容器、网络、注册宿主进程、端口的实际清理按安全回执验收。完整 PG canonical helper 使用其原 scoped 清理方式。失败原件、受测源码、导出图片均未覆盖。旧 M3、Harness 及原始工作树保持原样。

## 已知限制与后续

- 本地原生 arm64 Docker/PG 与合成 API/Web，不代表 Hosted、amd64、3865U 远端或生产验收。
- M3 daily/inquiry/copy 三条独立浏览器整链未运行；对应旧业务使用完整 PG、离线与 legacy Web/N01 回归证明，证据层级分开。
- 外部真实模型、embedding、飞书、Woo 写和生产：NOT_RUN；无新付费依赖。
- owner 物理保留期 GC 未单独原生验收；本阶段 reset 数据清除和回滚已实际验收。无生产自动清理部署。
- 实际模型 token 费用无法从工具精确计量，记 UNKNOWN；角色、模型和推理强度使用记录保留。
- V4-1 NOT_STARTED。下一阶段仅提供任务卡接单建议，须新阶段授权。

## 交付来源与耗时

完整 PG 实际执行来源 R2，existing 1947.5 秒、phase3 1684.853 秒，原配对 0.085 秒；与候选不同的两处扫描 fingerprint 如实分列。完整工程实际执行来源 cbd；之后只整合文档。全阶段墙钟由 ROOT_LEDGER 的起始 UTC 与最终文档 Gate 的结束 UTC 分账，Agent 有效工时及实际模型费用未计量，保持 UNKNOWN，不虚填预算净余。

## 合同与文件清单

四份核心合同、OpenAPI 与 seed manifest 保持已批准内容。权限 CSV 仅做 LF 导入：当前 649 字节，历史 CRLF 656 字节，七个换行；逐行内容相同，两种 SHA256 及原件位置见 `../../IMPORT_NORMALIZATION.json`。旧冻结清单的 CRLF hash 继续保留，不拿它充当当前 LF 文件的 bytes hash。

文件责任清单见 `FILE_MAP.json`；源代码实际受测来源与后增事实文档分开，后增文档不触发重做已通过的业务 PG。最终阶段独审见 `../../review/FINAL_LOCAL_STAGE_CF9.md`；本阶段本地实施和必要运行 Gate 已接受。最终文档 Gate 由冻结提交下 `.audit/v4-0/final-document-gate-<source7>/receipt.json` 独立记录，包含源码前后不变、完整扫描、文档和文件清单核对。
