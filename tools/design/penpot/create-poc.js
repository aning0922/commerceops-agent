// 只通过官方 MCP execute_code 执行。独立测试文件中的原生可编辑元素。
if (penpot.currentFile.id !== "ad74bff8-48e8-8141-8008-c31715c76703") {
  throw new Error("Wrong verification file");
}
if (penpot.currentFile.pages.some(p => p.name === "00 / Tool verification")) {
  throw new Error("POC already exists; inspect before retrying");
}
const page = penpot.currentPage;
page.name = "00 / Tool verification";
const revision = "ux-poc/0.1.1";
const mark = (shape, id) => {
  shape.name = id;
  shape.setSharedPluginData("commerceops-ux", "stable-id", id);
  shape.setSharedPluginData("commerceops-ux", "revision", revision);
  return shape;
};
const text = (parent, id, value, x, y, size = 16, color = "#101828", width = 700) => {
  const t = penpot.createText(value);
  if (!t) throw new Error("Text creation failed");
  mark(t, id);
  parent.appendChild(t);
  t.fontSize = String(size);
  t.fills = [{fillColor: color, fillOpacity: 1}];
  t.resize(width, size * 2.2);
  t.x = x; t.y = y;
  return t;
};
const rect = (parent, id, x, y, w, h, color, radius = 0) => {
  const r = mark(penpot.createRectangle(), id);
  parent.appendChild(r);
  r.resize(w,h); r.x=x; r.y=y;
  r.fills=[{fillColor:color,fillOpacity:1}]; r.borderRadius=radius;
  return r;
};
const board = (id, x, y, w, h, color) => {
  const b = mark(penpot.createBoard(),id);
  b.resize(w,h); b.x=x; b.y=y; b.fills=[{fillColor:color,fillOpacity:1}];
  return b;
};
// 单独原生 Page 保存组件主实例，避免把组件主实例当作业务页面播放。
const componentsPage=penpot.createPage();
componentsPage.name="01 / POC components";
await penpot.openPage(componentsPage);
const main=board("POC-C01 / Primary button",0,0,232,48,"#0F766E");
main.borderRadius=8;
const flex=main.addFlexLayout();
flex.dir="row"; flex.alignItems="center"; flex.justifyContent="center";
flex.horizontalPadding=16; flex.verticalPadding=10; flex.columnGap=8;
const label=penpot.createText("查看分析报告");
if (!label) throw new Error("Button text failed");
main.appendChild(label); label.name="POC-C01-LABEL"; label.fontSize="16";
label.fills=[{fillColor:"#FFFFFF",fillOpacity:1}];
const component=penpot.library.local.createComponent([main]);
await penpot.openPage(page);
const a=board("POC-S01 / 任务中心",0,0,1200,800,"#F7F8FA");
const b=board("POC-S02 / 库存分析报告",1320,0,1200,800,"#F7F8FA");
const modal=board("POC-M01 / 数据口径",2640,0,560,350,"#FFFFFF");
modal.borderRadius=16;
for (const screen of [a,b]) {
  const x=screen.x;
  rect(screen,screen.name+"/sidebar",x,0,210,800,"#101828");
  text(screen,screen.name+"/brand","CommerceOps",x+24,28,23,"#FFFFFF",180);
  text(screen,screen.name+"/nav-tasks","任务中心",x+24,106,16,"#FFFFFF",170);
  text(screen,screen.name+"/nav-approvals","审批与内部补货",x+24,157,16,"#CBD5E1",170);
  text(screen,screen.name+"/nav-trace","Agent 执行轨迹",x+24,208,16,"#CBD5E1",170);
  text(screen,screen.name+"/context","MOCK · 本地工具验证",x+24,723,13,"#CBD5E1",180);
  rect(screen,screen.name+"/header",x+210,0,990,74,"#FFFFFF");
  text(screen,screen.name+"/notice","界面原型 / 模拟数据 / 未连接业务服务",x+242,26,14,"#667085",680);
  text(screen,screen.name+"/role","operator",x+1070,26,14,"#667085",110);
}
text(a,"POC-S01-TITLE","任务中心",242,108,30);
text(a,"POC-S01-DESC","查看分析进度、冻结报告与待处理事项。",242,159,16,"#667085");
rect(a,"POC-S01-SUMMARY",242,219,926,122,"#FFFFFF",12);
text(a,"POC-S01-SUMMARY-LABEL","本次验证",267,242,14,"#667085");
text(a,"POC-S01-SUMMARY-TEXT","一个任务 · 两张界面 · 一个原生弹窗",267,279,24);
rect(a,"POC-S01-TASK-CARD",242,373,926,251,"#FFFFFF",12);
text(a,"POC-S01-TASK-ID","DEMO-TASK-001 · 最近 7 个完整自然日",267,401,16,"#667085");
text(a,"POC-S01-TASK-TITLE","库存风险分析",267,446,24);
text(a,"POC-S01-TASK-STATE","报告可查看 · 审批状态为模拟展示",267,492,16,"#667085");
const nav=mark(component.instance(),"POC-B01 / 查看分析报告");
a.appendChild(nav); nav.x=267; nav.y=551;
text(a,"POC-S01-BOUNDARY","按钮只跳转原型，不创建补货项、不修改真实库存。",242,664,14,"#667085");
text(b,"POC-S02-TITLE","库存分析报告",1562,108,30);
text(b,"POC-S02-WINDOW","模拟数据 · 销量窗口 2026-10-02 至 2026-10-08 · 库存观测 2026-10-09",1562,162,14,"#667085",900);
rect(b,"POC-S02-SOURCE",1562,213,926,106,"#E7F4F1",12);
text(b,"POC-S02-SOURCE-TITLE","确定性计算 · rule v1 · 演示参数 L=3 / R=7 / S=2",1587,237,18,"#0F766E",870);
text(b,"POC-S02-SOURCE-DESC","原始在途未知仍为 null；按 0 估算的草案必须显式确认。",1587,275,14,"#0F766E",870);
rect(b,"POC-S02-TABLE",1562,352,926,197,"#FFFFFF",12);
text(b,"POC-S02-TABLE-HEAD","SKU              日均需求          可用库存          在途          建议件数",1587,375,16,"#667085",875);
rect(b,"POC-S02-DIVIDER",1587,417,875,1,"#E4E7EC");
text(b,"POC-S02-ROW","DEMO-SKU-A          10                   20                  未知              100",1587,440,18,"#101828",875);
text(b,"POC-S02-QUALITY","草案 · 未知在途按 0 估算 · 可能重复补货",1587,496,14,"#9A6700",875);
const overlayBg=rect(b,"POC-B02-BG",1562,582,232,48,"#0F766E",8);
const overlayLabel=text(b,"POC-B02-LABEL","查看数据口径",1590,593,16,"#FFFFFF",188);
const overlayButton=mark(penpot.group([overlayBg,overlayLabel]),"POC-B02 / 查看数据口径");
const backBg=rect(b,"POC-B03-BG",1818,582,232,48,"#E4E7EC",8);
const backLabel=text(b,"POC-B03-LABEL","返回任务中心",1846,593,16,"#344054",188);
const back=mark(penpot.group([backBg,backLabel]),"POC-B03 / 返回任务中心");
text(b,"POC-S02-BOUNDARY","审批与执行为后续 M1 设计；此处仅验证导航和弹窗。",1562,664,14,"#667085",875);
text(modal,"POC-M01-TITLE","数据口径",2672,32,26,"#101828",488);
text(modal,"POC-M01-TEXT1","D = 70 / 7 = 10 件 / 天",2672,89,17,"#344054",488);
text(modal,"POC-M01-TEXT2","T = ceil(10 × (3 + 7 + 2)) = 120",2672,134,17,"#344054",488);
text(modal,"POC-M01-TEXT3","Q = max(0, 120 − 20 − 0) = 100",2672,179,17,"#344054",488);
text(modal,"POC-M01-MOCK","模拟示例 · 关闭弹窗不构成批准或拒绝",2672,224,14,"#667085",488);
const closeBg=rect(modal,"POC-B04-BG",2672,282,232,44,"#0F766E",8);
const closeLabel=text(modal,"POC-B04-LABEL","关闭",2758,293,16,"#FFFFFF",60);
const close=mark(penpot.group([closeBg,closeLabel]),"POC-B04 / 关闭数据口径");
nav.addInteraction("click",{type:"navigate-to",destination:b});
overlayButton.addInteraction("click",{type:"open-overlay",destination:modal,position:"center",closeWhenClickOutside:true,addBackgroundOverlay:true});
back.addInteraction("click",{type:"navigate-to",destination:a});
close.addInteraction("click",{type:"close-overlay",destination:modal});
page.createFlow("POC / A → B → 弹窗",a);
penpot.viewport.zoomIntoView([a,b,modal]);
page.setSharedPluginData("commerceops-ux","revision",revision);
page.setSharedPluginData("commerceops-ux","purpose","tool-verification-only");
return {
  fileId:penpot.currentFile.id,pageId:page.id,componentPageId:componentsPage.id,
  revision,components:[{id:component.id,mainInstance:component.mainInstance().id}],
  screens:[a,b,modal].map(s=>({id:s.id,stableId:s.name,x:s.x,y:s.y,width:s.width,height:s.height})),
  controls:[nav,overlayButton,back,close].map(s=>({id:s.id,stableId:s.name,interactions:s.interactions.map(i=>({trigger:i.trigger,type:i.action.type,destination:i.action.destination?.id}))})),
  validation:penpot.currentFile.validate()
};
