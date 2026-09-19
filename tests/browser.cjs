// Optional browser smoke test. npm install --no-save playwright, or set PLAYWRIGHT_MODULE.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({headless:true, channel:process.env.PLAYWRIGHT_CHANNEL || 'msedge'});
  const context = await browser.newContext({viewport:{width:1440,height:1080},locale:'en-US'});
  const page = await context.newPage();
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.RADAR_URL || 'http://127.0.0.1:8765';
  const out=path.resolve('work');fs.mkdirSync(out,{recursive:true});
  await page.goto(base); await page.waitForSelector('.card');
  assert((await page.locator('.card').count())>0);
  assert.match(await page.locator('#heading').innerText(),/Worth considering/);
  const quick=page.locator('[data-apply]').first();
  const quickId=await quick.getAttribute('data-apply');
  await quick.click();
  assert.equal(await page.locator('#jobStatus').inputValue(),'Applied');
  await page.reload();await page.waitForSelector('[data-apply]');
  assert.match(await page.locator(`[data-apply="${quickId}"]`).innerText(),/Applied/);
  await page.locator(`[data-apply="${quickId}"]`).click();
  assert.equal(await page.locator('#jobStatus').inputValue(),'New');
  await page.locator('#saveJob').click();
  await page.locator('#jobNotes').fill('Browser regression check — private notes');
  await page.locator('#jobStatus').selectOption('Applied');
  assert.equal(await page.locator('#jobStatus').inputValue(),'Applied');
  const downloadPromise=page.waitForEvent('download');await page.locator('#exportTop').click();
  const download=await downloadPromise; const backup=path.join(out,'browser-progress.json');await download.saveAs(backup);
  const data=JSON.parse(fs.readFileSync(backup));assert(Object.values(data.progress).some(p=>p.status==='Applied'&&p.notes.includes('regression')));
  await page.reload();await page.waitForSelector('.card');
  await page.locator('[data-view="applied"]').click();
  assert.equal(await page.locator('.card').count(),1);
  assert.match(await page.locator('#jobNotes').inputValue(),/regression/);
  await page.locator('[data-view="all"]').click();
  await page.locator('#search').fill('nonexistent-role-72bb63');
  assert.equal(await page.locator('.card').count(),0);
  await page.locator('#clear').click();assert((await page.locator('.card').count())>0);
  await page.locator('[data-view="sources"]').click();assert((await page.locator('.sources tbody tr').count())>=20);
  await page.locator('[data-view="profile"]').click();await page.waitForSelector('#saveProfile');
  assert((await page.locator('[name="enabledSource"]').count())>=20);
  // Validate profile-save integration without changing the user's settings.
  await page.waitForFunction(()=>typeof apiToken==='string');
  await page.locator('#saveProfile').click();
  await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Profile saved'));
  // Never start a live scan in the browser test.
  const rejected=await context.request.post(base+'/api/scan');assert.equal(rejected.status(),403);
  const leak=await context.request.get(base+'/notify_config.py');assert.equal(leak.status(),404);
  await page.locator('[data-view="backup"]').click();
  await page.evaluate(()=>localStorage.removeItem('radar-progress-v2'));
  await page.reload();await page.locator('[data-view="backup"]').click();
  await page.locator('#restoreFile').setInputFiles(backup);
  await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Restored'));
  await page.locator('[data-view="applied"]').click();assert.equal(await page.locator('.card').count(),1);
  // V1 URL-keyed status migration, without touching the user's real browser.
  const one=await page.evaluate(()=>DATA.jobs[0]);
  await page.locator('[data-view="backup"]').click();
  await page.locator('#restoreFile').setInputFiles({name:'legacy.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({version:1,by_url:{[one.url]:'Sent'}}))});
  await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Restored'));
  await page.waitForFunction(id=>JSON.parse(localStorage.getItem('radar-progress-v2')||'{}')[id]?.status==='Applied',one.id);
  await page.locator('[data-view="consider"]').click();
  await page.screenshot({path:path.join(out,'desktop.png'),fullPage:false});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.locator('.card-select').first().click();
  assert(await page.locator('#detail h2').isVisible());
  await page.screenshot({path:path.join(out,'mobile.png'),fullPage:false});
  assert.deepEqual(errors,[]);
  // Browser state lives in a temporary isolated context, never the user's browser.
  await browser.close();console.log('Browser checks passed: desktop/mobile, filters, detail, stages, notes, persistence, export/restore, source health, profile controls, API protection.');
})().catch(e=>{console.error(e);process.exit(1)});
