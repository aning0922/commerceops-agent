'use client';

import {useRef, type ReactNode} from 'react';
import {modules, resolveV41Route} from '../../lib/v41-routes';
import styles from './shell.module.css';

const icons = ['◫', '✧', '▤', '◇', '▧', '▣', '◈', '◎', '▱', '◉', '↻', '▥', '✓', '⚙'];
function Navigation({pathname, close}: {pathname:string; close?:()=>void}) {
  const active = resolveV41Route(pathname)?.module?.id;
  return <nav aria-label="业务导航" className={styles.navigation}>
    <span className={styles.navLabel}>工作空间</span>
    {modules.map((item, index)=><a key={item.id} href={item.href} onClick={close}
      aria-current={active === item.id ? 'page' : undefined} className={styles.navItem}>
      <span className={styles.icon} aria-hidden="true">{icons[index]}</span><span>{item.name}</span>
      {item.kind === 'category' && <span className={styles.soon}>规划</span>}
    </a>)}
  </nav>;
}
export function Shell({pathname, children}:{pathname:string; children:ReactNode}) {
  const menu = useRef<HTMLDialogElement>(null), assistant = useRef<HTMLDialogElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null), assistantButton = useRef<HTMLButtonElement>(null);
  const route = resolveV41Route(pathname);
  return <div className={styles.shell}>
    <aside className={styles.sidebar}>
      <a className={styles.brand} href="/v4"><span className={styles.brandMark}>C</span><span>CommerceOps<small>运营协作工作台</small></span></a>
      <div className={styles.workspace}><span className={styles.workspaceDot}/><span>演示工作空间<small>合成数据 · 隔离环境</small></span></div>
      <Navigation pathname={pathname}/>
      <div className={styles.sideFooter}>V4 演示 <span>·</span> 权限以服务端为准</div>
    </aside>
    <div className={styles.content}>
      <header className={styles.header}>
        <button className={styles.menuTrigger} ref={menuButton} type="button" aria-label="打开业务导航" onClick={()=>menu.current?.showModal()}>☰</button>
        <div className={styles.breadcrumb}><span>工作空间</span><span aria-hidden="true">/</span><strong>{route?.title ?? '演示'}</strong></div>
        <div className={styles.headerActions}><span className={styles.demoBadge}><span/>合成演示</span><button ref={assistantButton} className={styles.assistantTrigger} type="button" onClick={()=>assistant.current?.showModal()}>✧ <span>智能助手</span></button></div>
      </header>
      {children}
    </div>
    <dialog ref={menu} className={styles.menuDialog} onClose={()=>menuButton.current?.focus()} aria-label="业务导航菜单">
      <div className={styles.dialogHead}><strong>业务导航</strong><button type="button" onClick={()=>menu.current?.close()} aria-label="关闭业务导航">×</button></div>
      <Navigation pathname={pathname} close={()=>menu.current?.close()}/>
    </dialog>
    <dialog ref={assistant} className={styles.assistantDialog} onClose={()=>assistantButton.current?.focus()} aria-labelledby="v41-assistant-title">
      <div className={styles.dialogHead}><div><span className={styles.assistantIcon}>✧</span><strong id="v41-assistant-title">智能助手</strong></div><button type="button" onClick={()=>assistant.current?.close()} aria-label="关闭智能助手">×</button></div>
      <div className={styles.assistantBody}><span className={styles.label}>COPILOT</span><h2>在工作中获取帮助</h2><p>未来可在这里查看当前工作上下文与只读快捷入口。</p><div className={styles.disabledState}><strong>模型未启用</strong><p>此阶段尚未连接模型或工具。真实上下文接线后将在此显示。</p></div><p className={styles.helper}>演示数据仅供本地体验，不会发送至外部服务。</p></div>
    </dialog>
  </div>;
}
