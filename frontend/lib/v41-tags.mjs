// Match the reviewed Python printable-character rule; server and SQL remain authoritative.
export function hasV41NonPrintable(value){return typeof value!=='string'||/[\p{C}\p{Z}]/u.test(value.replaceAll(' ',''));}
export function validV41Tag(value){
 return typeof value==='string' && value.length>0 && value.length<=24 && value.trim()===value && !hasV41NonPrintable(value);
}
