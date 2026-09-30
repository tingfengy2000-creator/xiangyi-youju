const { chromium } = require('playwright');
const { pathToFileURL } = require('url');
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const diagrams = path.join(root, 'docs', 'diagrams');
const options = { headless: true };
if (process.env.BROWSER_CHANNEL) options.channel = process.env.BROWSER_CHANNEL;
(async()=>{
  const browser = await chromium.launch(options);
  const page = await browser.newPage();
  for(const name of ['system-architecture','agent-workflow']) {
    const file=path.join(diagrams, name+'.svg');
    const svg=fs.readFileSync(file, 'utf8');
    const height=Number(svg.match(/height="(\d+)"/)[1]);
    await page.setViewportSize({width:1600,height});
    await page.setContent('<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">'+svg+'</body></html>');
    await page.screenshot({path:path.join(diagrams,name+'.png'),fullPage:false,animations:'disabled'});
  }
  await page.setViewportSize({width:1440,height:900});
  await page.goto(pathToFileURL(path.join(root,'frontend/prototype/index.html')).href);
  await page.screenshot({path:path.join(root,'docs/assets/screenshots/home-hero.png'),fullPage:false,animations:'disabled'});
  await browser.close();
  console.log('Rendered both diagrams and homepage viewport.');
})().catch(err=>{console.error(err);process.exit(1);});
