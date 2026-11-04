export type BatchTarget={readonly id:string;readonly version:number};
export type BatchCounts={success:number;rejected:number;pending:number;unsent:number};
export type BatchOutcome={status:'success';revision:string}|{status:'rejected'|'unknown'|'cancelled'};
export function batchTargets(items:readonly {product_id?:string;version?:number}[],ids:string[],tags:string[]):readonly BatchTarget[]|null;
export function applyBatchTags(targets:readonly BatchTarget[],revision:string,active:()=>boolean,execute:(target:BatchTarget,revision:string,dispatch:()=>void)=>Promise<BatchOutcome>,publish:(counts:BatchCounts)=>void):Promise<BatchCounts>;
export function matchesBatchRead(data:unknown,target:BatchTarget,revision:string):boolean;
export function matchesBatchTags(actual:unknown,expected:readonly string[]):boolean;
