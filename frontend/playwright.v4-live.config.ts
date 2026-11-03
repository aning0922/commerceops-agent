import {defineConfig} from '@playwright/test';
const web=process.env.V4_WEB_ORIGIN;
const evidence=process.env.V4_EVIDENCE_DIR;
if(!web||!process.env.V4_API_ORIGIN||!evidence) throw new Error('V4_WEB_ORIGIN, V4_API_ORIGIN and V4_EVIDENCE_DIR are required');
export default defineConfig({testDir:'./v4-tests',testMatch:'lifecycle.live.ts',outputDir:evidence,retries:0,workers:1,timeout:120000,use:{baseURL:web,trace:'off',video:'off',screenshot:'off',reducedMotion:'reduce'}});
