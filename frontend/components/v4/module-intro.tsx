import {resolveV41Route} from '../../lib/v41-routes';
import styles from './module-intro.module.css';

const descriptions:Record<string,{heading:string; detail:string; next:string}> = {
  '01':{heading:'用可信数据看清经营',detail:'在统一来源和店铺范围内查看经营指标、变化趋势与待办。',next:'经营查询接口接入后，将在这里展示指标及来源。'},
  '02':{heading:'让信息更容易被理解',detail:'围绕当前工作上下文查看可用的只读帮助入口。',next:'对话和工具能力将在后续阶段开放。'},
  '03':{heading:'深入理解经营变化',detail:'从销售、商品与退款等角度探索有依据的分析。',next:'完整经营分析将在后续阶段开放。'},
  '04':{heading:'管理商品与规格',detail:'在当前授权店铺中查找商品、查看详情与来源。',next:'商品列表与演示编辑接口尚待接入。'},
  '05':{heading:'掌握订单进展',detail:'按时间与状态查找订单，并核对订单与商品的关联。',next:'订单详情与演示履约接口尚待接入。'},
  '06':{heading:'关注库存与补货',detail:'汇总库存风险、查看补货工作与相关来源。',next:'库存模拟与流水将在后续阶段开放。'},
  '07':{heading:'连接需求与供应',detail:'围绕采购需求、供应商和报价组织后续工作。',next:'采购与到货流程将在后续阶段开放。'},
  '08':{heading:'了解客户与售后',detail:'在授权范围内组织客户信息与售后处理。',next:'客户画像和售后工单将在后续阶段开放。'},
  '09':{heading:'整理服务对话',detail:'围绕模拟会话、订单关联与人工处理组织服务。',next:'客服工作区将在后续阶段开放，不发送真实消息。'},
  '10':{heading:'规划营销活动',detail:'连接活动规划、内部文案与经营反馈。',next:'营销活动将在后续阶段开放，不会真实发布。'},
  '11':{heading:'梳理自动化工作',detail:'集中查看规则、运行历史与通知的规划。',next:'通用自动化将在后续阶段开放。'},
  '12':{heading:'管理可用知识',detail:'围绕资料版本、检索和引用组织知识。',next:'知识管理将在后续阶段开放。'},
  '13':{heading:'处理任务与审批',detail:'集中查看待处理工作、审批和操作记录的规划。',next:'新工作区接线将在后续阶段开放。'},
  '14':{heading:'管理演示环境',detail:'查看当前演示空间的身份与设置。',next:'数据源和其他系统设置将在后续阶段开放。'},
};
export function ModuleIntro({pathname}:{pathname:string}) {
  const route=resolveV41Route(pathname);
  if(!route || route.auxiliary || !route.module)return null;
  const content=descriptions[route.module.id];
  return <section className={styles.section} aria-labelledby="module-intro-title">
    <div className={styles.top}><span className={styles.badge}>{route.module.kind==='business'?'待接入':'规划中'}</span><span className={styles.index}>工作区 / {route.module.id}</span></div>
    <h2 id="module-intro-title">{content.heading}</h2><p>{content.detail}</p>
    {route.title!==route.module.name && <p className={styles.page}>当前入口：{route.title}</p>}
    <div className={styles.status}><span className={styles.dot} aria-hidden="true"/><div><strong>此功能尚未开放</strong><p>{content.next}</p></div></div>
  </section>;
}
