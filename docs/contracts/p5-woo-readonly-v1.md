# Phase5 首批 Woo 只读 A/B 输入合同

唯一首批授权为 [Issue49](https://github.com/aning0922/commerceops-agent/issues/49)。基线e7cf790；A负责适配/采集与对账，B负责隔离真实Woo测试店及合成样本。本合同不接通业务Worker/Graph，不代表完整M2验收。

## A 接收的配置与命令

A实现 `python -m scripts.woo_readonly_probe --config CONFIG --expected EXPECTED --output OUTPUT`。
三个路径均由操作者显式提供；配置和输出仅放本次新私有目录，不读旧env/私配。

CONFIG为UTF-8 JSON，字段如下：

```json
{
  "base_url": "https://127.0.0.1:18443",
  "consumer_key_file": "/k",
  "consumer_secret_file": "/s",
  "ca_file": "/ca",
  "shop_id": "woo-local",
  "timezone": "Asia/Shanghai",
  "currency": "CNY",
  "window": {"start": "2026-10-18T16:00:00Z", "end": "2026-10-25T16:00:00Z"},
  "per_page": 2,
  "max_pages": 100,
  "max_requests": 1000,
  "timeout_seconds": 10,
  "max_elapsed_seconds": 180,
  "max_response_bytes": 2097152,
  "max_retries": 0
}
```

示例`/k`、`/s`、`/ca`为路径占位符，实际必须替换成本批新私有目录内的绝对文件路径。
示例Window由B按冻结业务时钟选择并与EXPECTED一致；半开UTC窗口，Asia/Shanghai/CNY不变。
base_url仅HTTPS原点（可显式端口），A固定追加`/wp-json/wc/v3`；不接受userinfo/query/fragment。
consumer文件独立、非符号链接、当前用户所有、0600，父私有目录0700；内容只在HTTPX Basic Auth中使用。
CA仅此项目显式路径，始终校验TLS、不安装全局CA、不改hosts/代理；HTTPX关闭环境代理及自动重定向。
仅GET产品/变体/订单/订单退款；忽略Link发起地址，分页仅构造同源固定路径和无认证query。
默认无重试，可配置最多1次有界重试；所有调用共同受请求数、响应字节和单次采集墙钟上限约束。

## B 交给 A 的已提交样本

B独占`tests/fixtures/woocommerce-local/`。提交合成种子manifest与固定业务时钟；实际seed后另产出新私有EXPECTED，保留平台生成ID到合成标签的映射。不得通过复制A实际输出生成预期。
EXPECTED为JSON，顶层：`schema_version="woo-local-expectations-v1"`、`fixture_version`、`shop_id`、`timezone`、`currency`、`business_now`、`window`、`expected`。
`expected`恰含`products`、`order_lines`、`refunds`、`inventories`四个数组，均使用原commerce-v1 DTO完整JSON投影：

- 所有行排除`schema_version`、`source`；inventory另排除动态`observed_at`、`source_version`。
- 平台ID用规范十进制字符串；product.variant_id不存在为null。sku_key及stock_pool_key沿既有`commerce_values`编码，SKU文本不作身份。
- 金额为Decimal规范串（去无意义尾零，如`10.50`→`10.5`，禁止float），时间为UTC `Z`。数组行序不作业务身份；Refund.lines按原line_id排序。
- variable父仅展开实际变体；自身管理库存变体用自身ID为pool，继承父库存变体共享父pool且`pool_allocation="unresolved"`。不对每变体重复制造库存分配。
- 库存null/未管理明确unknown，未知在途始终null/unknown及原因，不伪造0；stock_semantics保持`adapter_available_already_adjusted`。
- 固定unknown原因：未管理库存`STOCK_NOT_MANAGED`，管理但数量null为`STOCK_QUANTITY_UNKNOWN`；在途`WOOCOMMERCE_INBOUND_UNAVAILABLE`；纯金额退款`AMOUNT_ONLY_REFUND`，有行但数量未知为`REFUND_QUANTITY_UNAVAILABLE`。restocked一律null，除非本批另有明确API证据合同。
- OrderLine保留全部原状态，由既有规则决定需求口径；创建时间按`[start,end)`筛选，金额为行total未税/total_tax分列。
- Refund只读取窗口内订单cohort的全部退款（可在窗口外发生），金额归一正数；关联原订单行，不能把退款行自身ID当原line_id。纯金额退款数量未知，restocked缺乏可靠API证明为null，不凭数量推断回库。

B至少覆盖简单商品、独立库存变体/共享父库存、零/null库存、空SKU、订单有效/排除状态、日界线、部分退款/纯金额退款及per_page=2多页。平台拒绝的非法数据与故障由A明确Fake反例覆盖，不能SQL伪造。

## A 输出与通过条件

OUTPUT为新建0600 JSON：来源`woocommerce_test`、开始/结束UTC、`consistency="observational"`、Window、归一四数组、各端点请求计数、完整性/安全错误码、逐组expected匹配结果。成功exit0须四组完整且逐行精确相等；采集错误/缺页/变化/容量或对账差异exit1，配置/预期无效exit2。不输出凭据、认证header、原响应、异常正文或客户字段。

cursor绑定端点、规范查询（Window/订单cohort）、origin/shop、page_size和当前采集代际，不能跨实例/端点/查询复用；它只作内部游标，不携密钥、不作为认证。
分页核`X-WP-Total/TotalPages`、稳定ID/排序、重复及缺页；有界重读比较观测变化，不声称原子快照。错误区分401认证、403权限、TLS、连接、超时、429、5xx、非法JSON/字段与容量/来源变化，任何失败不得转成假空或complete=true。HTTPX复用已锁依赖，不新增SDK。

A/B普通commit后才互相消费；B经审成果由A正常merge。首批实际Woo对账、独审与精确CI仍pending；Root集中释放push/PR/CI，A不自动main merge。所有旧M1资源/失败/HOLD保留，不重做旧Gate。
