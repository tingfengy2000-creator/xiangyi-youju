const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'artifacts', 'test-results');
fs.mkdirSync(output, { recursive: true });
const { browserOptions } = require('../../scripts/browser-options.cjs');
const { smallChinese } = require('./legibility.cjs');
const options = browserOptions();
(async()=>{
 const browser=await chromium.launch(options);
 const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const file = pathToFileURL(path.join(root, 'frontend/prototype/index.html')).href;
 await page.goto(file);
 await page.screenshot({path:path.join(output,'home-desktop.png'),fullPage:true,animations:'disabled'});
 const results=[];
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:width===390?844:1100});
  for(const id of ['home','studio','planner']){
   await page.locator(`[data-page="${id}"]`).click();
   const overflow=await page.evaluate(()=>({body:document.body.scrollWidth,viewport:innerWidth}));
   results.push({width,page:id,...overflow});
   if(overflow.body>width)throw Error('Horizontal overflow: '+JSON.stringify(results.at(-1)));
   const tiny=await smallChinese(page);
   if(tiny.length)throw Error(`Chinese text below 12px at ${width}/${id}: `+JSON.stringify(tiny));
   if(id==='studio'){
    for(const value of ['confusion','missing','unsupported']){
     await page.locator('#caseSelect').selectOption(value);await page.locator('#auditBtn').click();
     if(!await page.locator('#auditResult').isVisible())throw Error('Missing audit result');
    }
    await page.locator('#caseSelect').selectOption('confusion');await page.locator('#auditBtn').click();
   }
   if(id==='planner'){
    await page.locator('#resetPlan').click();
    if(!await page.locator('#totalCost').textContent().then(t=>t.includes('1,080')))throw Error('Default total failed');
    if(await page.locator('.scheme-state').allTextContents().then(ts=>ts.some(t=>t!=='条件可行')))throw Error('Both default plans should be feasible');
    await page.locator('[data-scheme="light"]').click();
    if(!await page.locator('#totalCost').textContent().then(t=>t.includes('784')))throw Error('Light total failed');
    if(!await page.locator('#localRevenue').textContent().then(t=>t.includes('520')))throw Error('Light local income failed');
    if(!await page.locator('#legendMaterial').textContent().then(t=>t.includes('144')))throw Error('Light material total failed');
    if(!await page.locator('#legendOperations').textContent().then(t=>t.includes('120')))throw Error('Light organization total failed');
    if(JSON.stringify(await page.locator('#routeCards .time').allTextContents())!==JSON.stringify(['09:30','09:50','10:40']))throw Error('Light actual schedule failed');
    const downloadPromise=page.waitForEvent('download');await page.locator('#exportPlan').click();
    const exported=JSON.parse(fs.readFileSync(await (await downloadPromise).path(),'utf8'));
    if(exported.总计!==784||exported.方案!=='轻体验'||!exported.授权状态.includes('未取得')&&!exported.授权状态.includes('不代表已取得'))throw Error('Export provenance/data failed');
    await page.locator('#budget').fill('100');await page.locator('#budget').dispatchEvent('input');
    await page.locator('#minutes').fill('90');await page.locator('#minutes').dispatchEvent('input');
    if(!await page.locator('#planStatus').textContent().then(t=>t.includes('✓ 当前条件可行')))throw Error('Light should fit 90 minutes and 100 budget');
    await page.locator('[data-scheme="deep"]').click();
    if(!await page.locator('#planStatus').textContent().then(t=>t.includes('人均费用超出预算')&&t.includes('可用时长不足')))throw Error('Deep should fail while light feasible');
    await page.locator('#resetPlan').click();
    await page.locator('#people').fill('12');await page.locator('#people').dispatchEvent('input');
    if(!await page.locator('#totalCost').textContent().then(t=>t.includes('1,340')))throw Error('Dynamic total failed');
    if(!await page.locator('#localRevenue').textContent().then(t=>t.includes('960')))throw Error('Dynamic village income failed');
    if(!await page.locator('#localShare').textContent().then(t=>t.includes('71.6')))throw Error('Dynamic share failed');
    await page.locator('#budget').fill('60');await page.locator('#budget').dispatchEvent('input');
    if(!await page.locator('#planStatus').textContent().then(t=>t.includes('预算')))throw Error('Budget constraint failed');
    await page.locator('#budget').fill('200');await page.locator('#budget').dispatchEvent('input');
    if(!await page.locator('#planStatus').textContent().then(t=>t.includes('✓ 当前条件可行')))throw Error('Budget recovery failed');
    await page.locator('#reuse').uncheck();
    if(!await page.locator('#totalCost').textContent().then(t=>t.includes('1,412')))throw Error('Reuse material arithmetic failed');
    if(!await page.locator('#planStatus').textContent().then(t=>t.includes('可复用')))throw Error('Reuse constraint failed');
    await page.locator('#conflictBtn').click();
    if(!await page.locator('#planStatus').textContent().then(t=>t.includes('不可行')))throw Error('Conflict check failed');
    await page.locator('#resetPlan').click();
   }
   await page.locator('#toast').evaluate(el=>el.classList.remove('show'));
   const prefix = id;
   await page.screenshot({path:path.join(output,prefix+(width===390?'-mobile':'-desktop')+'.png'),fullPage:true,animations:'disabled'});
  }
 }
 await page.setViewportSize({width:1440,height:1100});
 await page.locator('[data-scheme="light"]').click();
 await page.screenshot({path:path.join(output,'planner-comparison.png'),fullPage:true,animations:'disabled'});
 await page.locator('#conflictBtn').click();
 await page.locator('#toast').evaluate(el=>el.classList.remove('show'));
 await page.screenshot({path:path.join(output,'planner-conflict.png'),fullPage:true,animations:'disabled'});
 fs.writeFileSync(path.join(output,'verification.json'),JSON.stringify({checks:results,scriptErrors:errors,interactions:'3 audit cases; navigation; group size, total, village income, percentage; budget failure and recovery; reusable material cost and constraint; infeasibility and reset; 2 plans both default feasible; light actual schedule/amounts; light feasible under 90min/100yuan while deep infeasible; JSON export values and authorization notice verified'},null,2));
 await browser.close();console.log(JSON.stringify({checks:results,scriptErrors:errors}));
 if(errors.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
