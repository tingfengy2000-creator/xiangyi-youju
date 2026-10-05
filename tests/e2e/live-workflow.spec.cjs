/* Small, real browser acceptance run. No request interception or canned API results.
 * LIVE_BASE_URL defaults to http://127.0.0.1:8780.
 * LIVE_RUN_ID loads an existing real run in explicitly labelled historical mode.
 * Without LIVE_RUN_ID, submits the editable text to the actual local model once.
 * LIVE_EXPECT_MODEL_ERROR=1 verifies a real unavailable-model failure instead.
 * LIVE_CASES_ONLY_FROM=<confirmed-run-id> continues two additional real UI scenarios:
 * budget revision, then material withdrawal and re-verification. Original screenshots stay intact.
 * LIVE_EXPORT_PREVIEW_ONLY=1 reopens the two final exported HTML files and refreshes screenshots,
 * without accessing the API or starting model inference.
 */
const { chromium } = require('playwright');
const { browserOptions } = require('../../scripts/browser-options.cjs');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const assert = require('assert/strict');

const root = path.resolve(__dirname, '../..');
const output = path.join(root, 'artifacts', 'live-browser-check');
const base = process.env.LIVE_BASE_URL || 'http://127.0.0.1:8780';
const replayId = process.env.LIVE_RUN_ID;
fs.mkdirSync(output, { recursive: true });
const errors = [];
const checks = [];
const externalResourceRequests = [];
const defaultDraft = '蔚县剪纸以阳刻为主，阴刻为辅。蔚县剪纸善于多色点染。工坊每天开放并且无需预约。';
async function waitForToast(page) {
  await page.waitForFunction(() => !document.querySelector('#toast')?.classList.contains('show'));
}

async function additionalScenarios(page, context, previousId) {
  const runIds = [];
  let restoreNeeded = false;
  async function waitForCreated(action, endpoint) {
    const responsePromise = page.waitForResponse(response => response.url().endsWith(endpoint) && response.request().method() === 'POST');
    await action();
    const response = await responsePromise;
    assert(response.ok(), '创建真实任务失败：' + await response.text());
    const result = await response.json();
    runIds.push(result.id);
    await page.waitForFunction(() => !document.querySelector('#auditBtn').disabled, null, { timeout: 600000 });
    const run = await (await page.request.get(`${base}/api/runs/${result.id}`)).json();
    fs.writeFileSync(path.join(output, `scenario-${runIds.length}-run.json`), JSON.stringify(run, null, 2));
    assert.equal(run.mode, 'live');
    assert.equal(run.status, 'awaiting_review', JSON.stringify(run.error));
    assert((run.model_calls || 0) > 0);
    assert(await page.locator('#runtimeState').textContent().then(text => text.includes('真实本地运行') && !text.includes('历史回放')));
    return run;
  }
  async function confirm() {
    await page.locator('#approvalCheck').check();
    await page.locator('#approveRun').click();
    await page.waitForFunction(() => !document.querySelector('#exportVisitor').disabled && !document.querySelector('#exportOrganizer').disabled, null, { timeout: 30000 });
  }
  async function downloadAndInspect(audience, prefix, expectArtwork) {
    const downloaded = page.waitForEvent('download');
    await page.locator('#export' + audience).click();
    const download = await downloaded;
    const filepath = path.join(output, `${prefix}-${audience.toLowerCase()}.html`);
    await download.saveAs(filepath);
    const html = fs.readFileSync(filepath, 'utf8');
    assert(html.includes('轻体验') && html.includes(audience === 'Visitor' ? '¥98.00' : '¥784.00'), '导出须使用已确认的轻体验账目（游客展示人均费用，组织者展示总额）');
    assert.equal(html.includes('data:image/svg+xml'), expectArtwork, '原创素材的实际渲染必须遵循当前运行的使用状态');
    const preview = await context.newPage();
    preview.on('pageerror', error => errors.push(`${prefix}: ${String(error)}`));
    try {
      await preview.goto(pathToFileURL(filepath).href);
      for (const width of [1440, 390]) {
        await preview.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
        assert(await preview.evaluate(() => document.body.scrollWidth <= innerWidth));
        await preview.screenshot({ path: path.join(output, `${prefix}-${audience.toLowerCase()}-${width === 390 ? 'mobile' : 'desktop'}.png`), fullPage: true, animations: 'disabled' });
      }
    } finally { await preview.close(); }
  }
  try {
    await page.locator('#historySelect').selectOption(previousId);
    await page.waitForFunction(() => document.querySelector('#runtimeState')?.textContent.includes('历史回放'));
    await page.locator('[data-page="studio"]').click();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await waitForToast(page);
    await page.screenshot({ path: path.join(output, 'studio-viewport-history.png'), animations: 'disabled' });
    await page.locator('[data-page="planner"]').click();
    await page.locator('#budgetCase').click();
    assert.equal(await page.locator('#budget').inputValue(), '110');
    assert(await page.locator('#approveRun').isDisabled());
    assert(await page.locator('#exportVisitor').isDisabled());
    const budgetRun = await waitForCreated(() => page.locator('#runPlan').click(), '/api/runs');
    assert.equal(budgetRun.requirements.budget_per_person, 110);
    assert.equal(budgetRun.plan.id, 'light');
    assert.equal(budgetRun.plan.total_cents, 78400);
    assert.equal(budgetRun.plan.duration_minutes, 90);
    assert.equal(budgetRun.planning.candidates.find(plan => plan.id === 'deep').feasible, false);
    assert(budgetRun.revision_count > 0);
    assert.equal(await page.locator('[data-scheme="light"]').getAttribute('aria-pressed'), 'true');
    checks.push('UI将预算改为110元后真实重新运行，深体验超预算，修订为784元/90分钟轻体验');
    await page.locator('[data-page="studio"]').click();
    await waitForToast(page);
    await page.screenshot({ path: path.join(output, 'studio-viewport-live.png'), animations: 'disabled' });
    if (await page.locator('.evidence-block').count()) await page.locator('.evidence-block').first().evaluate(element => element.open = true);
    await page.screenshot({ path: path.join(output, 'studio-evidence-viewport-live.png'), animations: 'disabled' });
    await page.locator('[data-page="planner"]').click();
    await page.screenshot({ path: path.join(output, 'budget-110-planner-desktop.png'), fullPage: true, animations: 'disabled' });
    await confirm();
    await downloadAndInspect('Visitor', 'budget-110', true);
    const withdrawalResponse = page.waitForResponse(response => response.url().endsWith('/api/materials/mat-paper-garden') && response.request().method() === 'PATCH');
    await page.locator('[data-material-id="mat-paper-garden"][data-state="withdrawn"]').click();
    assert((await withdrawalResponse).ok());
    restoreNeeded = true;
    await page.waitForFunction(() => document.querySelector('#runtimeState')?.textContent.includes('结果失效'));
    assert(await page.locator('#approveRun').isDisabled());
    assert(await page.locator('#exportVisitor').isDisabled());
    assert(await page.locator('#exportOrganizer').isDisabled());
    assert((await page.request.get(`${base}/api/runs/${budgetRun.id}/export?audience=visitor`)).status() === 409);
    assert((await page.request.get(`${base}/api/runs/${budgetRun.id}/export?audience=organizer`)).status() === 409);
    assert(await page.locator('#impactTrail').textContent().then(text => text.includes('mat-paper-garden') && text.includes('card-')));
    await waitForToast(page);
    await page.locator('#impactTrail').screenshot({ path: path.join(output, 'material-impact.png') });
    await page.screenshot({ path: path.join(output, 'material-invalidated-desktop.png'), fullPage: true, animations: 'disabled' });
    checks.push('UI撤回素材后当前结果失效；两版导出入口禁用，后端两版均409，影响链包含素材/卡片/方案');
    const refreshed = await waitForCreated(() => page.locator('#refreshRun').click(), `/api/runs/${budgetRun.id}/refresh`);
    assert.equal(refreshed.parent_id, budgetRun.id);
    assert.equal(refreshed.requirements.budget_per_person, 110);
    assert.equal(refreshed.plan.total_cents, 78400);
    assert(refreshed.cards.every(card => !(card.material_ids || []).includes('mat-paper-garden')));
    await confirm();
    const approved = await (await page.request.get(`${base}/api/runs/${refreshed.id}`)).json();
    assert.equal(approved.status, 'confirmed');
    fs.writeFileSync(path.join(output, 'material-refreshed-approved-run.json'), JSON.stringify(approved, null, 2));
    await downloadAndInspect('Visitor', 'material-refreshed', false);
    await downloadAndInspect('Organizer', 'material-refreshed', false);
    checks.push('UI依据撤回状态重新核验并确认；两版真实导出均移除已撤回图案，保留有效文本与轻体验账目');
    await page.locator('[data-material-id="mat-paper-garden"][data-state="available"]').click();
    await page.waitForSelector('[data-material-id="mat-paper-garden"][data-state="withdrawn"]');
    const catalog = await (await page.request.get(`${base}/api/catalog`)).json();
    assert.equal(catalog.materials.find(material => material.id === 'mat-paper-garden').usage_status, 'available');
    restoreNeeded = false;
    checks.push('完成后通过UI恢复素材available；全部真实历史记录保留');
    return runIds;
  } finally {
    if (restoreNeeded) {
      // A failed assertion must not leave the shared demonstration catalog withdrawn.
      const restored = await page.request.patch(`${base}/api/materials/mat-paper-garden`, { data: { usage_status: 'available' } });
      assert(restored.ok(), '验收退出时恢复演示素材失败');
    }
  }
}

(async () => {
  const browser = await chromium.launch(browserOptions());
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1, serviceWorkers: 'block' });
  // This checks browser resources only, not whole-machine network isolation.
  // Local API traffic remains real and is never replaced or mocked.
  await context.route(/^https?:\/\//, async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) return route.continue();
    externalResourceRequests.push({ url: request.url(), resourceType: request.resourceType(), at: new Date().toISOString() });
    await route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(String(error)));
  try {
    if (process.env.LIVE_EXPORT_PREVIEW_ONLY === '1') {
      for (const audience of ['visitor', 'organizer']) {
        const filename = `material-refreshed-${audience}.html`;
        const filepath = path.join(output, filename);
        const html = fs.readFileSync(filepath, 'utf8');
        assert(!html.includes('data:image/svg+xml'), '撤回后导出的实际 SVG 必须移除');
        if (audience === 'organizer') assert(html.includes('原句保留（已有来源支持）'), '最新版组织者包须使用准确的支持状态标签');
        await page.goto(pathToFileURL(filepath).href);
        for (const width of [1440, 390]) {
          await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
          assert(await page.evaluate(() => document.body.scrollWidth <= innerWidth), `${audience} ${width}px 导出预览横向溢出`);
          await page.screenshot({ path: path.join(output, `material-refreshed-${audience}-${width === 390 ? 'mobile' : 'desktop'}.png`), fullPage: true, animations: 'disabled' });
          checks.push(`${filename} 最新真实导出 ${width}px 预览通过，无横向溢出`);
        }
      }
      assert.equal(errors.length, 0, errors.join('\n'));
      assert.equal(externalResourceRequests.length, 0, JSON.stringify(externalResourceRequests));
      const result = { at: new Date().toISOString(), mode: 'existing-real-export-preview', scope: '仅重新预览已导出的真实 HTML；未访问业务 API、未启动模型任务', checks, scriptErrors: errors, externalResourceRequests };
      fs.writeFileSync(path.join(output, 'final-exports-verification.json'), JSON.stringify(result, null, 2));
      console.log(JSON.stringify(result, null, 2));
      return;
    }
    await page.goto(base);
    await page.waitForSelector('#runtimeState', { timeout: 30000 });
    assert(await page.locator('#runtimeState').textContent().then(t => t.includes('真实本地')));
    assert.equal(await page.locator('#draft').getAttribute('readonly'), null);
    assert.equal(await page.locator('#toast.show').count(), 0, 'first paint must not show a toast over the home hero');
    if (process.env.LIVE_CASES_ONLY_FROM) {
      const runIds = await additionalScenarios(page, context, process.env.LIVE_CASES_ONLY_FROM);
      assert.equal(errors.length, 0, errors.join('\n'));
      assert.equal(externalResourceRequests.length, 0, JSON.stringify(externalResourceRequests));
      checks.push('增量真实UI场景和双版HTML预览无JS错误、无外部页面资源请求；不是整机断网测试');
      const result = { at: new Date().toISOString(), base, parentRunId: process.env.LIVE_CASES_ONLY_FROM, runIds, mode: 'real-ui-additional-scenarios', checks, scriptErrors: errors, externalResourceRequests };
      fs.writeFileSync(path.join(output, 'ui-scenarios-verification.json'), JSON.stringify(result, null, 2));
      console.log(JSON.stringify(result, null, 2));
      return;
    }
    let runId = replayId;
    if (replayId) {
      await page.locator('#historySelect').selectOption(replayId);
      await page.waitForFunction(() => document.querySelector('#runtimeState')?.textContent.includes('历史回放'));
      assert(await page.locator('#approveRun').isDisabled());
      assert(await page.locator('#exportVisitor').isDisabled());
      checks.push('真实保存记录按历史回放标识，禁止直接确认和导出');
    } else {
      // This suite preserves the fixed-package regression; module UX has its own real acceptance script.
      await page.locator('[data-page="planner"]').click();
      await page.locator('#planningMode').selectOption('packages');
      await page.locator('[data-page="studio"]').click();
      await page.locator('#draft').fill(defaultDraft);
      const created = page.waitForResponse(response => response.url().endsWith('/api/runs') && response.request().method() === 'POST');
      await page.locator('#auditBtn').click();
      const submitted = await (await created).json();
      assert(submitted.id, '服务端须返回真实任务编号');
      runId = submitted.id;
      await page.waitForFunction(() => !document.querySelector('#auditBtn').disabled, null, { timeout: 600000 });
      checks.push('浏览器编辑文案后真实提交并等待本地模型运行');
    }
    const response = await page.request.get(`${base}/api/runs/${encodeURIComponent(runId)}`);
    const run = await response.json();
    fs.writeFileSync(path.join(output, 'run.json'), JSON.stringify(run, null, 2));
    assert.equal(run.mode, 'live');
    if (process.env.LIVE_EXPECT_MODEL_ERROR === '1') {
      assert.equal(run.status, 'model_error');
      assert.equal((run.claims || []).length, 0);
      assert.equal((run.planning?.candidates || []).length, 0);
      assert(await page.locator('#runtimeState').textContent().then(t => t.includes('失败')));
      assert(await page.locator('#approveRun').isDisabled());
      assert(await page.locator('#exportVisitor').isDisabled());
      checks.push('真实模型不可用：保留 model_error，不生成陈述、方案或可导出结果');
      // Three-act guide: it only fills and points. Count writes so a guide button can never submit for the operator.
      const writes = { runs: 0, other: 0 };
      page.on('request', request => {
        if (request.method() === 'GET') return;
        if (request.url().endsWith('/api/runs') && request.method() === 'POST') writes.runs++;
        else if (new URL(request.url()).pathname.startsWith('/api/')) writes.other++;
      });
      await page.locator('[data-page="studio"]').click();
      assert(await page.locator('#demoGuideStudio').isHidden(), '三幕演示默认关闭');
      await page.locator('#demoGuideToggle').click();
      assert.equal(await page.locator('#demoGuideToggle').getAttribute('aria-pressed'), 'true');
      assert(await page.locator('#demoGuideStudio').isVisible());
      assert((await page.locator('#demoGuideStudio').textContent()).includes('演示引导 · 结果以真实运行为准'));
      await page.locator('#draft').fill('临时改动');
      await page.locator('#demoGuideStudio [data-demo-fill="0"]').click();
      assert.equal(await page.locator('#caseSelect').inputValue(), 'confusion');
      assert.equal(await page.locator('#draft').inputValue(), defaultDraft);
      assert.equal(await page.locator('#region').inputValue(), '河北省蔚县');
      assert.equal(await page.locator('#project').inputValue(), '剪纸');
      assert.equal(await page.evaluate(() => document.activeElement?.id), 'auditBtn');
      assert(await page.locator('#auditBtn').evaluate(element => element.classList.contains('demo-target')));
      checks.push('三幕演示第一幕：填入主线案例（蔚县 · 剪纸 · 主线文案），焦点移到「核验并编排体验」并高亮');
      await page.locator('#demoGuideStudio [data-demo-fill="1"]').click();
      assert(await page.locator('#planner').evaluate(element => element.classList.contains('active')));
      assert.equal(await page.locator('#requestNote').inputValue(), '不要茶歇，多留手作时间');
      assert.equal(await page.locator('#planningMode').inputValue(), 'modules');
      assert.equal(await page.evaluate(() => document.activeElement?.id), 'runPlan');
      assert(await page.locator('#runPlan').evaluate(element => element.classList.contains('demo-target')));
      assert(!(await page.locator('#auditBtn').evaluate(element => element.classList.contains('demo-target'))));
      checks.push('三幕演示第二幕：需求框写入“不要茶歇，多留手作时间”，编排方式为按需求组合活动模块，高亮重新编排按钮');
      await page.locator('#demoGuidePlanner [data-demo-fill="2"]').click();
      const withdraw = page.locator('#materialList [data-material-id]').first();
      assert.equal(await withdraw.getAttribute('data-state'), 'withdrawn');
      assert(await withdraw.evaluate(element => element.classList.contains('demo-target') && document.activeElement === element));
      checks.push('三幕演示第三幕：定位并高亮第一条素材的「撤回使用」，不代为点击');
      await page.waitForTimeout(1500);
      assert.deepEqual(writes, { runs: 0, other: 0 }, '引导按钮不得发起提交、确认、导出或素材变更');
      assert.equal(await page.locator('.demo-step.done').count(), 0, '模型不可用时三步都不能显示 ✓');
      checks.push('三步引导按钮点击后 POST /api/runs 次数不变，也没有其他写请求；三步均未显示 ✓');
      await page.locator('[data-page="home"]').click();
      await page.locator('#home .act').nth(1).click();
      assert(await page.locator('#planner').evaluate(element => element.classList.contains('active')));
      assert(await page.locator('#demoGuidePlanner .demo-step[data-demo-step="1"]').evaluate(element => element.classList.contains('active')));
      assert.equal(await page.evaluate(() => document.activeElement?.dataset.demoFill), '1');
      checks.push('首页第二幕卡片在真实 API 模式下打开引导并定位到第二步');
      const submitted = page.waitForResponse(response => response.url().endsWith('/api/runs') && response.request().method() === 'POST');
      await page.locator('#runPlan').click();
      await submitted;
      await page.waitForFunction(() => !document.querySelector('#runPlan').disabled, null, { timeout: 60000 });
      assert.equal(writes.runs, 1, '只有操作者自己点击运行才提交一次');
      assert.equal(await page.locator('.demo-step.done').count(), 0, '真实运行失败后仍不能显示 ✓');
      assert((await page.locator('#demoGuidePlanner .demo-hint').textContent()).includes('不显示 ✓'));
      checks.push('操作者自行点击重新编排后真实失败：仍为 model_error，三步均无 ✓，引导提示失败不替代结果');
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 1100 });
        for (const id of ['home', 'studio', 'planner']) {
          await page.locator(`[data-page="${id}"]`).click();
          assert(await page.evaluate(() => document.body.scrollWidth <= innerWidth), `${width}/${id} 横向溢出`);
          await page.screenshot({ path: path.join(output, `model-error-${id}-${width === 390 ? 'mobile' : 'desktop'}.png`), fullPage: true, animations: 'disabled' });
          checks.push(`${width}px ${id} 真实故障界面无溢出`);
        }
      }
      await page.locator('#historySelect').selectOption(runId);
      await page.waitForFunction(() => document.querySelector('#runtimeState')?.textContent.includes('历史回放'));
      assert(await page.locator('#approveRun').isDisabled());
      assert(await page.locator('#exportVisitor').isDisabled());
      checks.push('真实失败记录可历史回放，确认和导出保持禁用');
      assert.equal(errors.length, 0, errors.join('\n'));
      assert.equal(externalResourceRequests.length, 0, '页面请求了外部 HTTP(S) 资源：' + JSON.stringify(externalResourceRequests));
      checks.push('浏览器页面资源无外部 HTTP(S) 请求；本机 API 正常访问，此项不代表整机断网验收');
      fs.writeFileSync(path.join(output, 'model-error-verification.json'), JSON.stringify({ at: new Date().toISOString(), base, runId, mode: 'real-model-error', checks, scriptErrors: errors, externalResourceRequests }, null, 2));
      console.log(JSON.stringify({ runId, status: run.status, checks, scriptErrors: errors, externalResourceRequests }, null, 2));
      return;
    }
    assert(['awaiting_review', 'confirmed'].includes(run.status), '真实运行未成功：' + JSON.stringify(run.error || run.status));
    assert((run.events || []).length > 0);
    assert((run.model_calls || 0) > 0);
    assert((run.claims || []).length > 0);
    assert(await page.locator('.claim-item').count() === run.claims.length);
    if (run.text === defaultDraft) {
      const technique = run.claims.find(claim => claim.text.includes('阳刻为主'));
      const color = run.claims.find(claim => claim.text.includes('多色点染'));
      const opening = run.claims.find(claim => claim.text.includes('每天开放'));
      assert.equal(technique?.status, 'contradicted', '主次颠倒应与地域来源矛盾');
      assert.equal(technique?.corrected_status, 'supported', '修订表达须被重新核验');
      assert.equal(color?.status, 'supported', '点染技法应有来源支持');
      assert.equal(opening?.status, 'insufficient', '文化资料不能证明实际开门与预约信息');
      checks.push('真实默认案例：技法矛盾并复核修订、点染获支持、营业预约信息不足');
    }
    const plans = run.planning.candidates;
    if (run.requirements.people === 8 && run.requirements.budget_per_person === 160) {
      assert.equal(plans.find(p => p.id === 'light').total_cents, 78400);
      assert.equal(plans.find(p => p.id === 'deep').total_cents, 108000);
      assert(plans.every(p => p.feasible));
      checks.push('真实服务端双方案：轻体验 784 元 / 90 分钟；深体验 1080 元 / 120 分钟');
    }
    if (!replayId) {
      await page.locator('[data-page="planner"]').click();
      await page.locator('#approvalCheck').check();
      await page.locator('#approveRun').click();
      await page.waitForFunction(() => !document.querySelector('#exportVisitor').disabled, null, { timeout: 30000 });
      for (const audience of ['Visitor', 'Organizer']) {
        const downloaded = page.waitForEvent('download');
        await page.locator('#export' + audience).click();
        const download = await downloaded;
        const filepath = path.join(output, audience.toLowerCase() + '-bundle.html');
        await download.saveAs(filepath);
        const html = fs.readFileSync(filepath, 'utf8');
        assert(html.includes('乡艺有据') && html.includes('演示'));
        if (audience === 'Visitor') assert(!html.includes('工坊每天开放并且无需预约'), '游客包不能包含未支持的营业承诺');
        const bundlePage = await context.newPage();
        await bundlePage.setViewportSize({ width: 1440, height: 1100 });
        bundlePage.on('pageerror', error => errors.push(`${audience} bundle: ${String(error)}`));
        try {
          await bundlePage.goto(pathToFileURL(filepath).href);
          for (const width of [1440, 390]) {
            await bundlePage.setViewportSize({ width, height: width === 390 ? 844 : 1100 });
            assert(await bundlePage.evaluate(() => document.body.scrollWidth <= innerWidth), `${audience} ${width}px 体验包横向溢出`);
            await bundlePage.screenshot({ path: path.join(output, `${audience.toLowerCase()}-bundle-${width === 390 ? 'mobile' : 'desktop'}.png`), fullPage: true, animations: 'disabled' });
            checks.push(`${audience === 'Visitor' ? '游客' : '组织者'}版真实导出 HTML ${width}px 无横向溢出`);
          }
        } finally { await bundlePage.close(); }
      }
      checks.push('人工确认后真实下载游客版和组织者版 HTML');
    }
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1100 });
      for (const id of ['home', 'studio', 'planner']) {
        await page.locator(`[data-page="${id}"]`).click();
        await waitForToast(page);
        const overflow = await page.evaluate(() => ({ body: document.body.scrollWidth, viewport: innerWidth }));
        assert(overflow.body <= width, `Horizontal overflow: ${width}/${id}: ${overflow.body}`);
        await page.screenshot({ path: path.join(output, `${id}-${width === 390 ? 'mobile' : 'desktop'}.png`), fullPage: true, animations: 'disabled' });
        checks.push(`${width}px ${id} 无横向溢出`);
      }
    }
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.locator('[data-page="studio"]').click();
    if (await page.locator('.evidence-block').count()) {
      await page.locator('.evidence-block').first().evaluate(element => element.open = true);
      const href = await page.locator('.evidence-block a').first().getAttribute('href');
      assert(href.startsWith('https://'));
      await page.screenshot({ path: path.join(output, 'evidence-desktop.png'), fullPage: true, animations: 'disabled' });
      checks.push('展开真实来源：原文、位置、时间、使用说明与原始链接');
    }
    await page.locator('[data-page="planner"]').click();
    await page.locator('#budget').fill('110');
    await page.locator('#budget').dispatchEvent('input');
    assert(await page.locator('#approveRun').isDisabled());
    assert(await page.locator('#exportVisitor').isDisabled());
    assert(await page.locator('#planStatus').textContent().then(t => t.includes('过期')));
    checks.push('现场修改预算会使旧结果过期，禁止继续确认和导出');
    assert.equal(errors.length, 0, errors.join('\n'));
    assert.equal(externalResourceRequests.length, 0, '页面或体验包请求了外部 HTTP(S) 资源：' + JSON.stringify(externalResourceRequests));
    checks.push((replayId ? '真实历史页面' : '真实页面、游客版与组织者版体验包') + '无外部 HTTP(S) 资源请求；本机 API 正常访问，此项不代表整机断网验收');
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify({ at: new Date().toISOString(), base, runId, mode: replayId ? 'real-history-replay' : 'real-local-inference', checks, scriptErrors: errors, externalResourceRequests }, null, 2));
    console.log(JSON.stringify({ runId, status: run.status, checks, scriptErrors: errors, externalResourceRequests }, null, 2));
  } finally {
    fs.writeFileSync(path.join(output, 'browser-resource-audit.json'), JSON.stringify({
      at: new Date().toISOString(), base,
      scope: '仅检查本次浏览器已打开页面的资源请求，不代表整机断网验收；未替换本机 API 响应',
      policy: '允许 localhost、127.0.0.1、[::1] HTTP(S)；记录并阻止其余 HTTP(S) 页面资源',
      externalResourceRequests
    }, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
