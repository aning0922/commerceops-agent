# 24caa60 最小集成修复独立增量审查

2026-11-04（台北）。结论：`ACCEPTED_TARGETED_PACKAGING_AND_DOCUMENT_FIX / BOTH_REPORTED_P2_CLOSED`。关闭原累计main审查的两项具体P2；未新增业务验收结论，不表示完整镜像构建、Hosted或生产通过，不授权merge。

固定修复：`24caa606a046c6456774f0f81af3136b0207fd9f`，tree `cfb0ada4af1c41987cf48cabde9260152c9aa1de`；直接parent `41c34e2b54f5410172fa609cc3519fe05df3bbaa`。完整增量恰为四文件、13新增/1删除行：Dockerfile及专属dockerignore各新增一行，README替换一行，M1指南顶部增加十行。业务、迁移、schema、检查逻辑及锁不变；提交信息含[skip ci]。

## P2-1：打包缺schema关闭

Dockerfile新增将docs/contracts/p6-daily-read-v1.schema.json复制到/app/docs/contracts同名路径；专属ignore新增该精确路径放行。原父目录放行、原frontend COPY、原检查链及npm build均保留；未通过跳过检查规避缺文件。

授权原件目录：/Users/aipuli/.codex/worktrees/commerceops-v41-archive-main/commerceops-agent/.audit/v41-archive/docker-copy-check 。receipt.json SHA256独立核为 `f4d416ce4025b8aa91a9bd5b7dd80aaec7b362f0fbb29b24f579fa55c6cf3158`，记录UTC2026-11-04T14:20:48.856346+00:00、准备来源41c34e2。回执早于修复commit，未假称当时运行已绑定未来24c SHA；本轮逐字节对冻结24c补足相关输入对应关系。

before.log SHA256 `75d837a8323d33ae49f3ca6d4ed203f6cdf584d4faa3b1caa7a5fbe4a4236647`，回执native1。实际日志显示旧三份检查先通过，随后sync-m3-read-schema.mjs:5对before布局缺失文件抛ENOENT，Node版本行v24.21.0。after.log SHA256 `1cdfef2dbf7cec92bd5f41356c314b96a9bb5643dd064175bce41d98990ff1e1`，回执native0，实际日志含完整npm run check:read-schema七段链与各段成功结果，未跳过M3。

独立读取两布局中各198个实际前端文件，全部字节等于24c Git对象；每份布局三/四个contracts文件也逐项等于24c及回执hash，目录中恰为登记集合，before新增文件确实不存在。两布局均无backend目录，不依赖完整仓库中额外backend文件补足检查。新增schema SHA256为 `fe108320d164496558f73fbbe0698c9c9ae9800182db82d03fce51da5a12954c`。以上独立只读比对native0。

证据限定：before/after为确定性Docker COPY路径模拟，不是实际Docker image层；198文件是检查所用布局，不冒称完整frontend镜像或npm build输入。原native退出依据receipt，输出依据已核日志。所交receipt/log未独立记录可执行文件路径与二进制hash，因此只确认日志显示Node v24.21.0，不额外签历史工具binary pin。此限制不影响精确文件遗漏及修复闭合判断。未重跑npm、Docker或服务。完整Docker build仍NOT_RUN，无需为关闭该确定缺文件问题追加完整构建。

## P2-2：旧部署指令适用范围关闭

README第191行现明确“历史M1”、仅适用完整SHA `8ad436595794ef83f3a99bc80bd9ad4948b7117e` 的0018环境，并警示当前源码不可直接照搬stock PG及旧迁移预期。M1指南新增首节限定全部下方历史命令/回执，明确当前migrate到head且stock PG缺vector会失败，并给出M3与V41当前入口。

历史SHA对应tree独立核为 `ea86b637190ec0ec42da771638a6c72b2853e82b`，与指南原有已验记录相同；未重新签历史运行或把0018改写成0025。原正文及失败/UNKNOWN历史保留。当前README第154–171行受控V41复现与第196行M3 override说明继续适用，旧M1链接不再被呈现为当前head直接装配。此处关闭的是文档误导，不表示当前stock PG支持新迁移。

## 原审查与后续边界

原REVIEW.md未修改，独立复核仍SHA256 `744c30d899a01e6ea3fcf06ca20f51b55062cda6edbd7d0c866820f229a4141a`。其main→accepted完整跨度、祖先/无冲突、API/权限/单Worker、来源复用、M2仅0018备份限制及未验项继续保留；本报告仅关闭两项已指出P2。两处打包配置变化意味着最终归档HEAD不再严格docs-only，应准确记为“文档加两处已审打包修复，业务与受测schema不变”。

当前本独审无未闭合已报告P1/P2，可继续授权的PR归档；不代表获得合main授权、required checks通过或新Hosted结果。最终HEAD保留skip marker及实际PR/Actions回执由Root核；后续merge仍须用户确认及必要检查授权。不要求重复Full/PG/runtime。

本轮仅git对象、指定公开安全原件与模拟布局字节读取；未编辑原报告或受测源码，未启动运行资源、网络或CI，未commit/push。独立报告供Root按既有敏感预检后归档，不覆盖原发现与修复链。
