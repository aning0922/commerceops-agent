import {resolveV41Route} from '../../lib/v41-routes';
import styles from './business-pending.module.css';

export type DashboardData = {
  snapshot:{data_revision:string;read_at:string;source:{data_mode:string;fixture_version:string;baseline_snapshot_at:string}};
  period:{from_date:string;to_date:string;timezone:string};
  metrics:{metric:string;value:string|null;known_value:string;currency:string|null;completeness:string;reason_codes:string[]}[];
  trend:{day:string;metrics:{metric:string;value:string|null;currency:string|null;completeness:string}[]}[];
  insights:{rule:string;analysis_mode:string;rule_version:string;reason:string|null;threshold_units:number|null}[];
  model_mode:'not_used';
};
export type CatalogData={snapshot:{source:{data_mode:string;fixture_version:string;baseline_snapshot_at:string};read_at:string};items:CatalogItem[];total:number;next_cursor:string|null};
export type CatalogItem={product_id?:string;order_id?:string;title?:string;tags?:string[];skus?:{sku_id:string;label:string;price:string;currency:string;available_units:number|null}[];created_at?:string;paid_at?:string|null;payment_status?:string;demo_fulfillment?:string;source:{data_mode:string}};
type CatalogProps={data:CatalogData|null;state:'idle'|'loading'|'error';enabled:boolean;scopeToken:string;previous:boolean;onSearch:(q:string)=>void;onNext:()=>void;onPrevious:()=>void};
const metricLabels:Record<string,string>={paid_order_amount:'已支付金额',paid_order_count:'已支付订单',created_order_count:'订单创建数',refund_event_amount:'退款事件金额'};

function PageHeader({eyebrow,title,description,status="数据服务待接入"}:{eyebrow:string;title:string;description:string;status?:string}) {
  return <header className={styles.pageHeader}><div><p className={styles.eyebrow}>{eyebrow}</p><h2>{title}</h2><p className={styles.subheading}>{description}</p></div><span className={styles.pendingBadge}><span/>{status}</span></header>;
}
function PendingMessage({title,children}:{title:string;children:React.ReactNode}) {
  return <div className={styles.empty} role="status"><span className={styles.emptyIcon} aria-hidden="true">◇</span><strong>{title}</strong><p>{children}</p></div>;
}
function DashboardPending({data,state}:{data:DashboardData|null;state:'idle'|'loading'|'error'}) {
  const metrics=['已支付金额','已支付订单','订单创建数','退款事件金额'];
  return <section className={styles.workspace} aria-labelledby="dashboard-title">
    <div id="dashboard-title"><PageHeader eyebrow="OVERVIEW · 经营总览" title="经营驾驶舱" status={data?'合成数据':state==='loading'?'正在读取':state==='error'?'数据暂不可用':'请选择授权店铺'} description="在同一店铺和时间范围内查看经营表现与后续行动。"/></div>
    <div className={styles.toolbar}><div><strong>经营概览</strong><p>{data?`${data.period.from_date} 至 ${data.period.to_date}（结束日期不含） · ${data.period.timezone}`:state==='error'?'暂时无法读取经营数据，请检查服务和当前授权。':'选择授权店铺后读取经营指标。'}</p></div><label>时间范围 <select disabled defaultValue="pending"><option value="pending">等待数据接入</option></select></label></div>
    <div className={styles.metrics}>{metrics.map((label)=>{const metric=data?.metrics.find(item=>metricLabels[item.metric]===label);return <article className={styles.metric} key={label}><div className={styles.metricTop}><span>{label}</span><span aria-hidden="true">↗</span></div><strong aria-label={metric?.value==null?'数值未知':undefined}>{metric?.value??'—'}</strong><small>{metric ? `${metric.currency??''} ${metric.completeness==='COMPLETE'?'完整':`已知小计 ${metric.known_value} · 不完整：${metric.reason_codes.join('、')}`}` : '暂无已验证数据'}</small></article>;})}</div>
    <div className={styles.dashboardGrid}><article className={styles.panel}><div className={styles.panelHead}><div><h3>经营趋势</h3><p>按店铺时区查看所选期间的指标变化</p></div><span className={styles.muted}>{data?'已核验响应':'待接入'}</span></div>{data && data.trend.length ? <div className={styles.tableScroll}><table><thead><tr><th>日期</th><th>指标</th><th>数值</th></tr></thead><tbody>{data.trend.flatMap(day=>day.metrics.map(metric=><tr key={`${day.day}-${metric.metric}`}><td>{day.day}</td><td>{metricLabels[metric.metric]??metric.metric}</td><td>{metric.value??'未知'} {metric.currency??''}</td></tr>))}</tbody></table></div> : <PendingMessage title={state==='loading'?'正在读取趋势':'暂无已验证的趋势数据'}>数据可用后显示对应日期和来源。</PendingMessage>}</article>
      <article className={styles.panel}><div className={styles.panelHead}><div><h3>规则洞察</h3><p>基于已授权数据的规则提示</p></div><span className={styles.muted}>非模型生成</span></div>{data && data.insights.length ? <ul>{data.insights.map((insight,index)=><li key={`${insight.rule}-${index}`}>{insight.rule} · {insight.reason??'规则触发'} · {insight.rule_version}{insight.threshold_units!=null?` · 阈值 ${insight.threshold_units}`:''}</li>)}</ul> : <PendingMessage title="暂无已验证的规则结果">规则结果可用后显示依据。</PendingMessage>}</article></div>
    <div className={styles.dashboardGrid}><article className={styles.panel}><div className={styles.panelHead}><div><h3>异常关注</h3><p>识别需要进一步核对的经营信息</p></div></div><PendingMessage title="异常数据尚未接入">当前没有可验证的异常数据。</PendingMessage></article><article className={styles.panel}><div className={styles.panelHead}><div><h3>运营待办</h3><p>聚焦已授权的工作事项</p></div></div><PendingMessage title="待办数据尚未接入">当前没有可验证的待办数据。</PendingMessage></article></div>
    <p className={styles.source}>{data?`来源 ${data.snapshot.source.data_mode} · 种子 ${data.snapshot.source.fixture_version} · 基线快照 ${data.snapshot.source.baseline_snapshot_at} · 读取时间 ${data.snapshot.read_at}`:'来源与快照将在读取成功后显示。'} 演示数据不代表实时外部同步。</p>
  </section>;
}
function CatalogPending({kind,detail,title,view,catalog}:{kind:'product'|'order';detail:boolean;title:string;view:string;catalog:CatalogProps}) {
  const products=kind==='product', data=catalog.data;
  const columns=products?['商品','SKU / 规格','标签','来源']:['订单','创建时间','支付状态','演示履约','来源'];
  return <section className={styles.workspace} aria-label={products?'商品中心':'订单中心'}>
    <PageHeader eyebrow={products?'CATALOG · 商品管理':'ORDERS · 订单管理'} title={title} status={data?'合成数据':catalog.state==='loading'?'正在读取':catalog.state==='error'?'数据暂不可用':'请选择授权店铺'} description={products?'按授权店铺查找商品，并查看规格、标签与来源。':'按授权店铺查看订单、关联商品与演示履约状态。'}/>
    <div className={styles.note}><strong>当前为演示界面</strong><span>{data?'数据仅代表当前授权店铺与本次查询快照，不代表真实外部同步。':'当前没有已验证的商品或订单数据。'}</span></div>
    {detail?<article className={styles.panel}><div className={styles.panelHead}><div><h3>{products?'商品信息':'订单信息'}</h3><p>详情仅在服务端核验对象与店铺权限后显示</p></div></div><PendingMessage title="详情服务尚未接入">请等待业务接口接入后查看授权详情。</PendingMessage></article>:
    <article className={styles.panel}><div className={styles.catalogHead}><div><h3>{products?'商品列表':'订单列表'}</h3><p>{view==='SKU规格'?'SKU 展示范围为本次加载的商品页':view==='分类标签'?'标签展示范围为本次加载的商品页；分类树来源未提供':'列表、筛选和分页使用服务端授权结果'}</p></div><div className={styles.actions}><button type="button" disabled>导出 CSV</button>{products&&<button type="button" disabled>导入商品</button>}</div></div>
      <form key={`${kind}:${catalog.scopeToken}`} className={styles.filters} onSubmit={event=>{event.preventDefault();const form=new FormData(event.currentTarget);catalog.onSearch(String(form.get('q')??'').trim());}}><label>{products?'搜索商品':'搜索订单'}<input name="q" maxLength={80} disabled={!catalog.enabled} placeholder={products?'商品名称或 SKU':'订单信息'} /></label><button type="submit" disabled={!catalog.enabled}>筛选</button></form>
      <div className={styles.tableScroll}><table><thead><tr>{columns.map(label=><th scope="col" key={label}>{label}</th>)}</tr></thead>{data&&<tbody>{data.items.map(item=><tr key={item.product_id??item.order_id}>{products?<><td><a href={`/v4/products/${item.product_id}`}>{item.title}</a></td><td>{item.skus?.map(sku=><div key={sku.sku_id}>{sku.label} · {sku.currency} {sku.price} · 库存 {sku.available_units??'未知'}</div>)}</td><td>{item.tags?.join('、')||'无标签'}</td><td>{item.source.data_mode==='demo_upload'?'演示导入':'合成基线'}</td></>:<><td><a href={`/v4/orders/${item.order_id}`}>查看订单</a></td><td>{item.created_at}</td><td>{item.payment_status==='payment_timestamp_unknown'?'支付时间未知':'已记录'}</td><td>{item.demo_fulfillment==='demo_fulfilled'?'演示已履约':'演示未履约'}</td><td>{item.source.data_mode==='demo_upload'?'演示导入':'合成基线'}</td></>}</tr>)}</tbody>}</table></div>
      {!data?<PendingMessage title={catalog.state==='loading'?'正在读取':catalog.state==='error'?'无法读取当前查询':products?'请选择授权店铺':'请选择授权店铺'}>{catalog.state==='error'?'请检查服务及当前授权，重新核对后再查询。':'选择店铺后显示同源查询结果。'}</PendingMessage>:data.items.length===0?<PendingMessage title="当前筛选没有结果">请调整筛选条件后重试。</PendingMessage>:null}
      <div className={styles.pagination}><span>{data?`当前查询共 ${data.total} 项 · 本页 ${data.items.length} 项`:'分页信息将在读取成功后显示'}</span><button type="button" disabled={!catalog.enabled||catalog.state==='loading'||!catalog.previous} onClick={catalog.onPrevious}>上一页</button><button type="button" disabled={!catalog.enabled||catalog.state==='loading'||!data?.next_cursor} onClick={catalog.onNext}>下一页</button></div>
      {data&&<p className={styles.source}>来源 {data.snapshot.source.data_mode} · 基线快照 {data.snapshot.source.baseline_snapshot_at} · 读取 {data.snapshot.read_at}</p>}
    </article>}
  </section>;
}
function ImportPending() {
  return <section className={styles.workspace} aria-label="商品导入">
    <PageHeader eyebrow="IMPORT · 数据导入" title="导入商品" description="上传文件后，先预览与映射字段，再确认导入当前演示店铺。"/>
    <div className={styles.note}><strong>导入服务待接入</strong><span>当前不能上传或提交文件，不会创建任何商品。</span></div>
    <article className={styles.panel}><div className={styles.panelHead}><div><h3>导入步骤</h3><p>服务接入后将提供服务端预览和质量校验</p></div></div>
      <ol className={styles.steps}><li><strong>选择文件</strong><span>CSV 或 XLSX；格式与大小限制由服务端校验</span></li><li><strong>预览与映射</strong><span>核对表头、字段映射和质量问题</span></li><li><strong>确认导入</strong><span>确认后查看结果并核对当前店铺商品</span></li></ol>
      <button className={styles.unavailableButton} type="button" disabled>选择文件</button>
    </article>
  </section>;
}
export function BusinessPending({pathname,dashboard,dashboardState,catalog}:{pathname:string;dashboard:DashboardData|null;dashboardState:'idle'|'loading'|'error';catalog:CatalogProps}) {
  const route=resolveV41Route(pathname);
  if (!route || route.auxiliary || !route.module) return null;
  if (route.module.id==='01') return <DashboardPending data={pathname==='/v4/dashboard'?dashboard:null} state={pathname==='/v4/dashboard'?dashboardState:'idle'}/>;
  if (pathname==='/v4/products/import') return <ImportPending/>;
  if (route.module.id==='04' || route.module.id==='05') {
    return <CatalogPending kind={route.module.id==='04'?'product':'order'} title={route.title} view={route.title} catalog={catalog} detail={route.title==='商品详情'||route.title==='订单详情'}/>;
  }
  return null;
}
