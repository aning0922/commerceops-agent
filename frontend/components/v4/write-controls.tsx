'use client';
import styles from './business-pending.module.css';
import {validV41Tag,hasV41NonPrintable} from '../../lib/v41-tags.mjs';

export type TagDraft={editing:boolean;text:string};
export function TagControls({tags,enabled,busy,onSave,draft,onDraft}:{tags:string[];enabled:boolean;busy:boolean;onSave:(tags:string[])=>void;draft:TagDraft|null;onDraft:(draft:TagDraft|null)=>void}) {
  const editing=draft?.editing??false,text=draft?.text??tags.join(', ');
  const parts=text.split(','),values=parts.map(value=>value.trim()).filter(Boolean);
  const valid=!parts.some(hasV41NonPrintable) && values.length<=8 && values.every(validV41Tag) && new Set(values).size===values.length;
  if(!editing)return <button type="button" disabled={!enabled||busy} onClick={()=>onDraft({editing:true,text})}>编辑标签</button>;
  return <form onSubmit={event=>{event.preventDefault();if(valid&&enabled&&!busy)onSave(values);}}>
    <label>标签（逗号分隔，最多 8 项）<input value={text} onChange={event=>onDraft({editing:true,text:event.target.value})} disabled={busy}/></label>
    <p>将保存：{values.length?values.join('、'):'无标签'}</p>
    {!valid&&<p role="status">标签须为可打印字符、不重复且每项不超过 24 字。</p>}
    <div className={styles.writeActions}><button type="button" onClick={()=>onDraft(null)} disabled={busy}>取消</button><button type="submit" disabled={!valid||!enabled||busy}>确认保存</button></div>
  </form>;
}
export function FulfillmentControls({enabled,busy,onConfirm,confirm,onConfirmDraft}:{enabled:boolean;busy:boolean;onConfirm:()=>void;confirm:boolean;onConfirmDraft:(value:boolean)=>void}) {
  if(!confirm)return <button type="button" disabled={!enabled||busy} onClick={()=>onConfirmDraft(true)}>标记演示已履约</button>;
  return <div><p>仅修改当前演示订单状态，不代表真实物流，也不会更改库存。</p><div className={styles.writeActions}><button type="button" onClick={()=>onConfirmDraft(false)} disabled={busy}>取消</button><button type="button" disabled={!enabled||busy} onClick={onConfirm}>确认演示履约</button></div></div>;
}
