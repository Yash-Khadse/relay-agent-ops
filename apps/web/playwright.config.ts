import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',timeout:90000,use:{baseURL:process.env.RELAY_WEB_URL||'http://localhost:5173',trace:'retain-on-failure'},webServer:{command:'pnpm dev',url:'http://localhost:5173',reuseExistingServer:true},projects:[{name:'chromium',use:{browserName:'chromium'}}]});
