'use client';
import {useState} from 'react';
import styles from './business-pending.module.css';
import {validV41Tag} from '../../lib/v41-tags.mjs';

export function TagControls({tags,enabled,busy,onSave}:{tags:string[];enabled:boolean;busy:boolean;onSave:(tags:string[])=>void}) {
  const [editing,setEditing]=useState(false),[text,setText]=useState(tags.join(', '));
  const values=text.split(',').map(value=>value.trim()).filter(Boolean);
  const valid=values.length<=8 && values.every(validV41Tag) && new Set(values).size===values.length;
  if(!editing)return <button type="button" disabled={!enabled||busy} onClick={()=>setEditing(true)}>编辑标签</button>;
  return <form onSubmit={event=>{event.preventDefault();if(valid&&enabled&&!busy)onSave(values);}}>
    <label>标签（逗号分隔，最多 8 项）<input value={text} onChange={event=>setText(event.target.value)} disabled={busy}/></label>
    <p>将保存：{values.length?values.join('、'):'无标签'}</p>
    {!valid&&<p role="status">标签须为可打印字符、不重复且每项不超过 24 字。</p>}
    <div className={styles.writeActions}><button type="button" onClick={()=>{setText(tags.join(', '));setEditing(false);}} disabled={busy}>取消</button><button type="submit" disabled={!valid||!enabled||busy}>确认保存</button></div>
  </form>;
}
export function FulfillmentControls({enabled,busy,onConfirm}:{enabled:boolean;busy:boolean;onConfirm:()=>void}) {
  const [confirm,setConfirm]=useState(false);
  if(!confirm)return <button type="button" disabled={!enabled||busy} onClick={()=>setConfirm(true)}>标记演示已履约</button>;
  return <div><p>仅修改当前演示订单状态，不代表真实物流，也不会更改库存。</p><div className={styles.writeActions}><button type="button" onClick={()=>setConfirm(false)} disabled={busy}>取消</button><button type="button" disabled={!enabled||busy} onClick={onConfirm}>确认演示履约</button></div></div>;
}
