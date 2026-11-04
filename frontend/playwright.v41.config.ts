import {defineConfig} from '@playwright/test';

if (!process.env.V41_WEB_ORIGIN) throw new Error('Explicit owned V41 Web origin required');
export default defineConfig({
  testDir:'./v41-tests', testMatch:'*.spec.ts', workers:1, retries:0,
  use:{baseURL:process.env.V41_WEB_ORIGIN, trace:'off', video:'off', screenshot:'off'},
});
