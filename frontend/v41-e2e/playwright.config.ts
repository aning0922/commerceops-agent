import {defineConfig} from '@playwright/test';
import {realpathSync, statSync} from 'node:fs';
import {resolve} from 'node:path';

import {readBrowserCase} from './browser-subjects';
const c=readBrowserCase();
const executablePath=process.env.V41_CHROMIUM_EXECUTABLE;
if(!executablePath||resolve(executablePath)!==executablePath||realpathSync(executablePath)!==executablePath||!statSync(executablePath).isFile())throw new Error('Root pinned browser executable required');
process.umask(0o077);
export default defineConfig({
  testDir:'.',testMatch:['shell.live.spec.ts','business.live.spec.ts'],timeout:240000,workers:1,retries:0,forbidOnly:true,
  use:{launchOptions:{executablePath},baseURL:`http://127.0.0.1:${c.web_port}`,trace:'off',video:'off',screenshot:'off',reducedMotion:'reduce'},
});
