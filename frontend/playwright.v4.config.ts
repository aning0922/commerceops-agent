import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./v4-tests',testMatch:'*.spec.ts',use:{baseURL:process.env.V4_WEB_ORIGIN ?? 'http://127.0.0.1:3000'},workers:1});
