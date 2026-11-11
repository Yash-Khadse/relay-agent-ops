import {test,expect} from '@playwright/test';
test('administrator-issued access code authenticates an assigned identity',async({page})=>{
 test.skip(!process.env.RELAY_TEST_ACCESS_CODE,'Set RELAY_TEST_ACCESS_CODE to a provisioned workspace code.');
 await page.goto('/');await page.getByText('Sign in to your workspace',{exact:true}).click();
 await page.getByLabel('Workspace access code').fill(process.env.RELAY_TEST_ACCESS_CODE!);
 await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Overview',exact:true})).toBeVisible();
 await expect(page.getByLabel('Workspace access code')).not.toBeVisible();
});
test('demo session → workflow → human approval → artifact download',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Try demo workspace'}).click();
 await expect(page.getByRole('heading',{name:'Overview',exact:true})).toBeVisible();
 await page.screenshot({path:'test-results/overview-desktop.png',fullPage:true});
 await page.getByRole('button',{name:'Workflows',exact:true}).click();
 await page.locator('.template-card').first().click();
 await page.getByLabel('Topic',{exact:true}).fill(`Integration research ${Date.now()}`);
 await page.getByRole('button',{name:'Run workflow',exact:true}).click();
 await expect(page.getByText('Execution details',{exact:true})).not.toBeVisible();
 await expect(page.getByRole('button',{name:'Approve',exact:true})).toBeVisible({timeout:60000});
 await page.getByRole('button',{name:'Approve',exact:true}).click();
 await expect(page.locator('.execution-summary .badge')).toHaveText('completed',{timeout:60000});
 const download=page.waitForEvent('download');await page.getByRole('button',{name:/^Download /}).first().click();
 expect((await download).suggestedFilename()).toMatch(/\.md$/);
 await page.screenshot({path:'test-results/completed-execution.png',fullPage:true});
});
test('landing and mobile workspace remain navigable',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 await expect(page.getByRole('heading',{name:'Good work. In good hands.'})).toBeVisible();
 await page.getByText('Sign in to your workspace',{exact:true}).click();
 await expect(page.getByLabel('Workspace access code')).toHaveAttribute('minlength','32');
 await page.screenshot({path:'test-results/landing-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'Try demo workspace'}).click();
 await expect(page.getByRole('heading',{name:'Overview',exact:true})).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 await page.getByRole('button',{name:'Dark',exact:true}).click();
 await expect(page.locator('html')).toHaveAttribute('data-theme','light');
 await page.screenshot({path:'test-results/settings-mobile-light.png',fullPage:true});
});
