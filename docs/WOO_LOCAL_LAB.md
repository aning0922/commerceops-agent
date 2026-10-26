# Phase5 首批：本地 Woo 合成测试店

本工具只服务 [Issue49](https://github.com/aning0922/commerceops-agent/issues/49) 的真实本地 Woo 只读适配与最小对账。它不接业务 PG、审批、Worker/Graph、飞书或模型，也不代表完整 M2。原 M1 资产、凭据与卷保持。

## 固定来源与运行结构

[版本清单](../infrastructure/woo-lab/versions.json)记录来源与摘要：WordPress7.1.3/PHP8.3 Apache官方镜像、WooCommerce11.2.1插件、WP-CLI2.12.0、MariaDB11.4.13、Nginx1.30.6。基础镜像用registry index digest固定；插件和CLI的官方下载使用SHA256校验。PHP/Apache实际补丁号与本机镜像ID在本次私有验证记录中回读，不用软件大版本代替实际来源。官方来源为[WordPress要求](https://wordpress.org/about/requirements/)、[Woo插件版本](https://wordpress.org/plugins/woocommerce/)、[Docker官方WordPress定义](https://github.com/docker-library/official-images/blob/master/library/wordpress)。

独立[Compose](../compose.woo-lab.yml)只有database、wordpress、tls三个服务，最大内存约1.85GiB、CPU额度3.5核，不合入原根Compose。WP/DB只连internal网络；TLS代理另接本项目入口网络，主机仅绑定127.0.0.1高位端口。代理初始化只在自身网络命名空间删除默认路由，随后降到UID101；启动前核CapEff/CapPrm/CapInh/CapAmb为0及NoNewPrivs=1。不使用privileged、host网络、docker.sock、主机iptables或全局CA；cap bounding set与实际能力分别记录，不把用户名当降权证明。

初次准备只读核Docker已有子网与主机路由，按实际两个/28核具体占用；每次启动再核。macOS缩写路由先规范化。只有由多个公网目标路由共同证明的VPN全流量捕获组、且严格包含完整RFC1918块的路由，才单列broad_capture_overlap；私网块本身、更具体私网、直连、Docker及未知路由仍硬排除。当前两个/28未发现具体占用，但仍处于VPN广域捕获覆盖内，不称完全无重叠。不得清理旧网络来腾地址。端口只是准备时选出的空闲端口，之后占用会失败并收尾，不接管旧监听。入口网络、路由和真实loopback监听以runtime-boundary记录核收。本机Desktop设置未报告完整VM CIDR；内置DNS只观测到IPv6主机/网关地址，IPv4 A查询不可用。该未知保留，不能宣称完整VM网段已排除。

## 私有准备与有界命令

从本次checkout根目录执行，需Docker/Compose、Python3.12、OpenSSL及仓库uv工具链。脚本使用POSIX权限和flock；macOS/Linux主机路由检查分别用netstat/ip。首次构建需要下载公开镜像/插件，不是断网安装包。

```sh
uv sync --frozen
python -m scripts.woo_lab prepare
# 用上一条返回的新绝对目录替换下例；不是从旧项目复制配置。
python -m scripts.woo_lab build --directory /absolute/checkout/runtime/woolab-xxxxxxxxxxxx
python -m scripts.woo_lab verify --directory /absolute/checkout/runtime/woolab-xxxxxxxxxxxx --seconds 600
```

prepare独占新runtime目录0700；文件0600，凭据不进命令参数、聊天、Git或CI。独立CA仅供本项目客户端通过ca_file信任。initial.json保存后台初始化管理员及受限reader账号；runtime-auth.json及独立consumer_key/consumer_secret保存Woo生成的read权限key。运行用户只具备产品/订单读取及报告读取能力，不具备edit_products/manage_options/manage_woocommerce。不要打印这些文件。

build仅构建/拉取固定镜像且有命令超时。verify启动后核运行边界、合法初始化和种子、实际REST校验，再重跑种子比较原平台ID/对象数及结果；最终只down本项目并保卷。失败保存独立私有日志，仍进入自有清理；bootstrap、seed及显式key轮换命令的成功、失败stdout/stderr均不写日志，只留固定诊断、原生退出码、长度和摘要，超时不保留异常正文或链；清理失败会明确报错。数据库不公开端口。超时/中断不能当成功。

后台体验采用有界前台命令，输出仅URL和文件路径：

```sh
python -m scripts.woo_lab serve --directory /absolute/checkout/runtime/woolab-xxxxxxxxxxxx --seconds 900
```

该命令最多使用声明窗口，预留90秒收尾；Ctrl-C/SIGTERM也进入本项目清理。后台凭据只在本地initial.json取得。浏览器会提示专用CA未被全局信任；API仍必须显式ca_file并验证TLS，不使用verify=false。本批已实际通过专用CA验证并读取HTTPS登录页；浏览器人工登录体验尚未验收。需要单独收尾时用相同目录的stop命令；不加-v，不手工清理未知容器/卷。

## 合成样本与独立预期

[种子定义](../tests/fixtures/woocommerce-local/seed.json)冻结业务时钟、Asia/Shanghai/CNY及半开窗口。平台观测时间仍为实际UTC，不伪造跨请求原子快照。样本包括：5个简单商品（正常12、零0、负-3/可延期、未管理null、空SKU），2个variable父及4个变体（独立7/0与共享父15）；10订单覆盖7种标准状态、日界线前1秒/起点/终点；3退款包含部分数量、全额数量、纯金额。负库存必须由实际Woo CRUD支持才记通过，拒绝的非法数据另记Fake。

所有对象使用明确logical标记，由WC_Product/WC_Order/wc_create_refund生成真实ID；不用SQL造业务行、非法状态或重复SKU。退款refund_payment=false、restock_items=false；首次种子完成后用合法商品CRUD设置最终库存，完整重跑不重置库存。只读模型中的restocked仍为null，因为该REST接口没有可靠回库证明。

[预期生成器](../scripts/woo_lab/expectations.py)只用版本化合成定义和Woo生成ID映射，不导入adapter、不读取A的OUTPUT。variable父不作为独立SKU；共享父库存标unresolved，未知库存与在途保留null/原因；退款关联原order line ID，纯金额不伪造数量0。退款cohort按窗口内订单选取，不按退款日期裁剪。金额用Decimal规范串。

配置/预期按已提交A合同84287eaf及ba3e7d6补充生成，放同一私有目录：probe-config.private.json、expected.private.json。per_page2、max_pages32、max_requests256、无重试、采集180秒，全部只读。最终probe由A消费冻结B提交后执行：

```sh
python -m scripts.woo_readonly_probe --config CONFIG --expected EXPECTED --output OUTPUT
```

A工具必须用其已提交实现运行，不能复制A实际输出生成EXPECTED。四组应为products、order_lines、refunds、inventories；具体实际通过计数与异常以私有原件和下方验证记录为准。

## 运行态边界与证据

MU guard拒绝wp_mail、WordPress外部HTTP、Webhook delivery和支付网关，关闭自动更新、WP cron及Action Scheduler异步/队列触发。实际safety.php会执行受控邮件/HTTP/外部TCP拒绝及网关/任务检查；静态开关不代签运行态无外发。没有真实收件人、支付信息或生产数据。IPv4/IPv6默认路由、业务外部HTTP/TCP和任务开关分别核验；Docker内置DNS/宿主网关仍存在，不宣称任意协议绝对零外发。

runtime-boundary.safe.json记录实际容器网络、loopback端口、默认路由、UID/cap/NNP和镜像ID；runtime-safety.safe.json记录实际受控拒绝。verification/reseed记录真实REST与幂等结果，allocation记录路由/子网前置，cleanup记录容器/网络0、监听关闭及保留卷。含平台ID的原件、配置、CA和凭据均只在新私有目录，不作为公开附件。

## 本批真实验证与交付边界

2026-10-26 09:22 UTC，本批新店实际完整verify通过，两次REST校验之间重跑种子：顶层商品7、变体4、订单10、退款3；平台ID映射相同，无额外对象。订单状态、金额、创建/支付/完成时间、商品/变体关联、退款原line关联及日期均与版本化种子核对。API新key的POST/PUT/DELETE实际401，除Woo随机related_ids外商品完整读回不变；raw前后快照保留。独立EXPECTED为9 products、8 order_lines、3 refunds、9 inventories；这只是预期计数，A最终adapter probe尚待冻结集成实跑。

实际专用CA验证成功、不信任CA被拒，HTTPS登录页200。Nginx进程UID101，CapEff/Prm/Inh/Amb为0、NoNewPrivs=1；CapBnd非零单列，不声称所有cap集合清零。WP/DB仅internal，入口只映射127.0.0.1，TLS没有IPv4/IPv6默认路由。邮件/外部WordPress HTTP/外部TCP受控拒绝、支付网关为空、Webhook/cron/异步队列禁用均有实际检查。退出后容器0、网络0、监听关闭，两个本批数据卷保留。

开发期发现seed原始stdout曾复制本批新API key到7个0700目录内的0600通用私有日志；尚未提交/推送。已抑制敏感命令输出，并撤销两个本批新店的旧key、换发read key：两店旧key GET均401，新key GET均200，POST/PUT/DELETE均401。较早失败店仅短启动作凭据处置，不计业务通过。先期7个日志整份替换而非按值保留，原hash和说明保留，已删除的非敏感部分不能恢复；随后按已知秘密值盘点新私有目录，其他管理员/reader/DB/TLS秘密未见额外副本。原始非敏感平台证据、失败类别及命令摘要仍保留。显式轮换脚本不会被seed/verify/serve自动调用；旧key已撤销但新输出丢失时，重跑会因旧pair不再匹配而拒绝，不盲目再发key。

离线边界测试11项通过，含权限/路径/已有资源保护、失败清理、重定向、路由分类、独立预期以及敏感命令成功/非零/超时日志抑制；Ruff和mypy通过。独审、A最终adapter probe、CI、main、完整M2与生产均未以本报告代签。

开发期原失败包括tmpfs内联列表、Nginx只读目录/非root stderr、WP-CLI登记表作用域、仅internal网络无host映射、Docker默认地址池耗尽、nullable IPAM、BusyBox路由过滤、降权前chmod顺序、严格VPN路由阻断、共享库存原验证器误解及related_ids随机变化；原失败和自有清理证据保留。历史Docker info运行数7与ps/stats实际0的差异保留，未停止任何未知实例。

冻结前敏感扫描仍有两项公开合成标记误报待共享scanner owner精确审核：seed.php中的Woo meta_key标记及seed.json中的partial_refund逻辑ID；本批没有修改或放宽共享扫描规则，不将已知值零泄漏扫描等同完整gitleaks通过。


## bbb候选独审后的绝对截止修复

bbb独审确认凭据日志P1可关闭；7份原日志非敏感字节不可恢复的限制继续保留。独审另发现P2：原urllib的idle timeout不能限制持续慢流，总截止后仍可能返回成功并延迟清理。后续局部修复复用已审A提交58e76a2的WooDeadlineTransport，不修改该传输实现或生产adapter的方法名单。API成功/错误响应、HTTPS登录页和不受信任CA检查均使用每次connect/TLS/write/read重新计算剩余时间的传输；原始响应限制2MiB，登录页512KiB，无自动重试或重定向。

run以原声明时长为绝对终点，工作阶段提前90秒停止；子命令及主机路由检查夹取当前阶段剩余时间，清理仍使用原总截止，不因进入finally延长窗口。收到完整响应、JSON解析结束、verifier返回及原生命令退出后再次核截止，晚到结果不能记录PASS。子命令未能在截止内完成或清理失败会保留失败记录，不签资源已回收。

本次lab测试共21项通过，Ruff/mypy及112份Markdown检查通过。定向证据使用native socketpair与Fake TLS握手：200/401各覆盖慢流、末尾阻塞、慢响应头，均在截止中止且finally清理入口执行；另核晚到完整响应、晚到verifier PASS及清理原生退出拒绝。未为该项重开Woo服务；bbb的真实平台/种子/权限/网络实证按未变代码复用，本次传输的故障注入不冒充新真实Woo/TLS成功。
