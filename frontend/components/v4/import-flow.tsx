'use client';
import {useEffect,useRef,useState} from 'react';
import {validMapping,digestImportFile,matchesImportSelection} from '../../lib/v41-import.mjs';
import styles from './business-pending.module.css';

export type ImportJob={import_job_id:string;version:number;parent_job_id:string|null;job_digest:string;data_revision:string;parser_version:'v41-parser-1';import_schema_version:'v41-import-1';expires_at:string};
export type ImportMapping={sku:string;title:string;price:string;currency:string;tags:string|null};
export type ImportPreview={job:ImportJob;state:'DISCOVERED'|'READY'|'INVALID'|'SUPERSEDED'|'COMMITTED';file_digest:string;mapping:ImportMapping|null;headers:string[];sample:{row:number;cells:string[]}[];row_count:number;issue_count:number;issues:{row:number;column:string|null;code:string}[];confirmable:boolean};
export function ImportFlow({enabled,identityActive,busy,preview,hasReference,canConfirm,onDiscover,onMap,onRead,onConfirm,onDiscard}:{enabled:boolean;identityActive:boolean;busy:boolean;preview:ImportPreview|null;hasReference:boolean;canConfirm:boolean;onDiscover:(file:File)=>void;onMap:(file:File,mapping:ImportMapping)=>void;onRead:()=>void;onConfirm:()=>void;onDiscard:()=>void}) {
  const [file,setFile]=useState<File|null>(null),[mapping,setMapping]=useState<ImportMapping>({sku:'',title:'',price:'',currency:'',tags:null}),[confirm,setConfirm]=useState(false),[discardConfirm,setDiscardConfirm]=useState(false);
  const previousJob=useRef<string|null>(null),fileSequence=useRef(0);
  const [fileDigest,setFileDigest]=useState<string|null>(null);
  useEffect(()=>{const sequence=++fileSequence.current;setFileDigest(null);if(file)void digestImportFile(file).then(value=>{if(fileSequence.current===sequence)setFileDigest(value);}).catch(()=>{});return ()=>{fileSequence.current++;};},[file]);
  useEffect(()=>{if(!identityActive){setFile(null);setMapping({sku:'',title:'',price:'',currency:'',tags:null});setConfirm(false);setDiscardConfirm(false);previousJob.current=null;}},[identityActive]);
  useEffect(()=>{if(preview && preview.job.import_job_id!==previousJob.current){if(preview.mapping)setMapping(preview.mapping);setConfirm(false);previousJob.current=preview.job.import_job_id;}},[preview]);
  const selectionMatches=!!preview&&matchesImportSelection(preview,mapping,file,fileDigest);
  const fieldLabels={sku:'SKU',title:'商品名称',price:'价格',currency:'币种',tags:'标签（可选）'};
  return <div>
    <div className={styles.note}><strong>导入演示商品</strong><span>先预览和校验，再明确确认；不会写入真实店铺。</span></div>
    <article className={styles.panel}><div className={styles.panelHead}><div><h3>选择文件</h3><p>CSV 或 XLSX，最大 2 MiB；内容仍由服务端校验。</p></div></div>
      <label className={styles.fileInput}>文件<input type="file" accept=".csv,.xlsx" disabled={!enabled||busy} onChange={event=>{fileSequence.current++;setFileDigest(null);setConfirm(false);setFile(event.target.files?.[0]??null);}}/></label>
      <div className={styles.actions}><button type="button" disabled={!enabled||busy||!file||hasReference} onClick={()=>file&&onDiscover(file)}>上传并预览</button>{hasReference&&<button type="button" disabled={!enabled||busy} onClick={onRead}>读取已保存预览</button>}</div>
      {hasReference&&!preview&&<p className={styles.source}>已有预览引用。先读取当前预览；如需修改映射，请重新选择同一文件。</p>}
      {hasReference&&(!discardConfirm?<button type="button" disabled={!enabled||busy} onClick={()=>setDiscardConfirm(true)}>放弃本地预览引用</button>:<div><p>仅删除本地引用，不会取消服务器上的预览或撤销已提交的导入。</p><div className={styles.writeActions}><button type="button" disabled={busy} onClick={()=>setDiscardConfirm(false)}>取消</button><button type="button" disabled={!enabled||busy} onClick={()=>{onDiscard();setDiscardConfirm(false);}}>确认放弃本地引用</button></div></div>)}
    </article>
    {preview&&<article className={styles.panel}><div className={styles.panelHead}><div><h3>预览与字段映射</h3><p>状态 {preview.state} · {preview.row_count} 行 · {preview.issue_count} 个问题 · 截止 {preview.job.expires_at}</p></div></div>
      <div className={styles.mapping}>{(Object.keys(fieldLabels) as (keyof ImportMapping)[]).map(key=><label key={key}>{fieldLabels[key]}<select value={mapping[key]??''} disabled={!enabled||busy||preview.state==='COMMITTED'||preview.state==='SUPERSEDED'} onChange={event=>{setConfirm(false);setMapping(current=>({...current,[key]:event.target.value||null}));}}><option value="">请选择</option>{preview.headers.map(header=><option key={header} value={header}>{header}</option>)}</select></label>)}</div>
      {file&&<button type="button" disabled={!enabled||busy||!validMapping(mapping,preview.headers)||preview.state==='COMMITTED'||preview.state==='SUPERSEDED'} onClick={()=>onMap(file,mapping)}>确认映射并重新预览</button>}
      <h4>安全样本</h4><div className={styles.tableScroll}><table><thead><tr><th>行</th>{preview.headers.map(header=><th key={header}>{header}</th>)}</tr></thead><tbody>{preview.sample.map(sample=><tr key={sample.row}><td>{sample.row}</td>{sample.cells.map((cell,index)=><td key={index}>{cell}</td>)}</tr>)}</tbody></table></div>
      {preview.state==='COMMITTED'&&<p>已读取确认后的作业状态。<a href="/v4/products">查看商品列表</a></p>}
      <h4>质量问题</h4>{preview.issues.length?<ul>{preview.issues.map((issue,index)=><li key={`${issue.row}-${index}`}>第 {issue.row} 行 · {issue.column??'整行'} · {issue.code}</li>)}</ul>:<p>当前预览没有返回问题明细。</p>}
      {preview.confirmable&&!selectionMatches&&<p role="status">当前文件或映射与已保存预览不一致，请使用相同文件重新预览。</p>}
      {preview.confirmable&&selectionMatches&&!file&&<p>当前未选择本地文件；确认将使用已保存的预览。</p>}
      {!confirm?<button type="button" disabled={!enabled||busy||!preview.confirmable||!canConfirm||!selectionMatches} onClick={()=>setConfirm(true)}>{canConfirm?'准备确认导入':'需要有效预览与当前数据版本'}</button>:<div><p>确认将本次有效预览原子导入当前演示店铺；失败不应留下部分商品。</p><div className={styles.writeActions}><button type="button" disabled={busy} onClick={()=>setConfirm(false)}>取消</button><button type="button" disabled={!enabled||busy||!preview.confirmable||!canConfirm||!selectionMatches} onClick={onConfirm}>确认导入</button></div></div>}
    </article>}
  </div>;
}
