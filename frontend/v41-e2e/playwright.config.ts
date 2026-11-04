import {defineConfig} from '@playwright/test';
import {readFileSync, realpathSync, statSync} from 'node:fs';
import {dirname, resolve} from 'node:path';

const supplied=process.env.V41_CASE_FILE;
if(!supplied||resolve(supplied)!==supplied||realpathSync(supplied)!==supplied)throw new Error('New canonical Root case required');
const info=statSync(supplied),parent=statSync(dirname(supplied));
if((info.mode&0o777)!==0o600||(parent.mode&0o777)!==0o700||info.uid!==process.getuid?.())throw new Error('Owner private case required');
const c=JSON.parse(readFileSync(supplied,'utf8'));
if(c.scenario!=='shell_navigation'||!/^[a-f0-9]{40}$/.test(c.source_sha)||!/^[a-f0-9]{40}$/.test(c.source_tree)||!/^v41qa_[a-z0-9_]{8,32}$/.test(c.project)||c.uid!==process.getuid?.()||c.directory!==dirname(supplied))throw new Error('Fixed Shell case required');
const start=Date.parse(c.starts_at),end=Date.parse(c.deadline),parentEnd=Date.parse(c.parent_deadline);
if(![start,end,parentEnd].every(Number.isFinite)||Date.now()<start||end-Date.now()<=180000||end>parentEnd||end-start>1800000)throw new Error('Active Root window required');
for(const p of [c.api_port,c.web_port])if(!Number.isInteger(p)||p<1024||p>65535)throw new Error('Explicit loopback ports required');
if(c.api_port===c.web_port)throw new Error('Distinct ports required');
process.umask(0o077);
export default defineConfig({
  testDir:'.',testMatch:'shell.live.spec.ts',timeout:120000,workers:1,retries:0,forbidOnly:true,
  use:{baseURL:`http://127.0.0.1:${c.web_port}`,trace:'off',video:'off',screenshot:'off',reducedMotion:'reduce'},
});
