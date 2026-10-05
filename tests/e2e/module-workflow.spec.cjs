/* Real module/teaching UI acceptance. API/model responses are never mocked.
 * BROWSER_CHANNEL=msedge node tests/e2e/module-workflow.spec.cjs
 * LIVE_BASE_URL defaults to http://127.0.0.1:8780.
 * MODULE_REPLAY_ID=<existing-id> performs read-only visual checks, without inference.
 * MODULE_EXPORT_PREVIEW_ONLY=1 captures the existing final HTML exports without API calls.
 * The normal path creates five bounded real tasks: initial, needs-confirmation,
 * adopted note, withdrawn-material refresh, and impossible resources.
 */
const { chromium } = require('playwright');
const { browserOptions } = require('../../scripts/browser-options.cjs');
const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const root = path.resolve(__dirname, '../..');
const checkName = process.env.MODULE_CHECK_NAME || '';
assert(!checkName || /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(checkName), 'MODULE_CHECK_NAME 使用小写英文、数字和连字符');
const output = path.join(root, 'artifacts', 'module-browser-check', checkName);
const base = process.env.LIVE_BASE_URL || 'http://127.0.0.1:8780';
const checks = [], errors = [], externalResourceRequests = [], runs = [];
fs.mkdirSync(output, { recursive: true });
const save = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2));
const waitToast = page => page.waitForFunction(() => {
  const toast = document.querySelector('#toast');
  return !toast || (!toast.classList.contains('show') && Number(getComputedStyle(toast).opacity) === 0);
});

(async () => {
  const browser = await chromium.launch(browserOptions('msedge'));
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' });
  await context.route(/^https?:\/\//, async route => {
    const url = new URL(route.request().url());
    if (['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) return route.continue();
    externalResourceRequests.push({ url: url.href, resourceType: route.request().resourceType() });
    return route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(String(error)));
  let restoreMaterial = false, result = {};
  const getRun = async id => (await page.request.get(`${base}/api/runs/${id}`)).json();
  async function execute(action, name, expected, endpoint = '/api/runs') {
    const created = page.waitForResponse(response => response.url().endsWith(endpoint) && response.request().method() === 'POST');
    await action();
    const response = await created;
    assert(response.ok(), await response.text());
    const { id } = await response.json();
    runs.push({ id, scenario: name });
    await page.waitForFunction(() => !document.querySelector('#auditBtn').disabled, null, { timeout: 600000 });
    const run = await getRun(id);
    save(`${name}-run.json`, run);
    assert.equal(run.mode, 'live');
    assert.equal(run.status, expected, JSON.stringify(run.error || run.status));
    assert(run.model_calls > 0 && run.model_calls <= 8);
    assert((await page.locator('#runtimeState').textContent()).includes('真实本地运行'));
    return run;
  }
  async function approve() {
    await page.locator('#approvalCheck').check();
    await page.locator('#approveRun').click();
    await page.waitForFunction(() => !document.querySelector('#exportVisitor').disabled, null, { timeout: 30000 });
    await waitToast(page);
  }
  async function capturePages(prefix) {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      for (const id of ['home', 'studio', 'planner']) {
        await page.locator(`[data-page="${id}"]`).click();
        await waitToast(page);
        assert(await page.evaluate(() => document.body.scrollWidth <= innerWidth), `${prefix}/${id}/${width} overflow`);
        await page.screenshot({ path: path.join(output, `${prefix}-${id}-${width}.png`), fullPage: true, animations: 'disabled' });
        if (width === 1440) await page.screenshot({ path: path.join(output, `${prefix}-${id}-viewport.png`), animations: 'disabled' });
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    checks.push(`${prefix}: real three-page rendering at 1440/390, no horizontal overflow`);
  }
  async function previewBoth(prefix, draft) {
    await page.locator('[data-page="planner"]').click();
    for (const audience of ['visitor', 'organizer']) {
      await page.locator(audience === 'visitor' ? '#previewVisitor' : '#previewOrganizer').click();
      await page.waitForFunction(() => document.querySelector('#previewFrame').srcdoc.includes('乡艺有据') && !document.querySelector('#auditBtn').disabled);
      await page.waitForFunction(() => document.querySelector('#previewFrame').contentDocument?.body?.textContent.includes('乡艺有据'));
      const html = await page.locator('#previewFrame').getAttribute('srcdoc');
      assert(html.includes('乡艺有据'));
      if (draft) {
        assert((await page.locator('#previewNotice').textContent()).includes('草稿'));
        assert(await page.locator('#previewDownload').isDisabled());
      }
      assert(!await page.locator('#previewFrame').getAttribute('sandbox').then(value => value.split(' ').includes('allow-scripts')));
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
        const frame = page.frameLocator('#previewFrame');
        await frame.locator('body').waitFor();
        assert(await frame.locator('body').evaluate(element => element.scrollWidth <= window.innerWidth), `${prefix}/${audience}/${width} iframe overflow`);
        await page.screenshot({ path: path.join(output, `${prefix}-${audience}-preview-${width}.png`), animations: 'disabled' });
      }
      await page.locator('#closePreview').click();
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
    checks.push(`${prefix}: server-rendered visitor/organizer previews at desktop/mobile, draft gating checked`);
  }
  async function downloadBoth(run, prefix, artwork) {
    for (const audience of ['Visitor', 'Organizer']) {
      const promise = page.waitForEvent('download');
      await page.locator('#export' + audience).click();
      const downloaded = await promise;
      const file = path.join(output, `${prefix}-${audience.toLowerCase()}.html`);
      await downloaded.saveAs(file);
      const html = fs.readFileSync(file, 'utf8');
      assert(html.includes(run.plan.title));
      assert.equal(html.includes('data:image/svg+xml'), artwork);
      if (audience === 'Visitor') assert(!html.includes('工坊每天开放并且无需预约'));
      const bundle = await context.newPage();
      bundle.on('pageerror', error => errors.push(String(error)));
      await bundle.goto(pathToFileURL(file).href);
      for (const width of [1440, 390]) {
        await bundle.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
        assert(await bundle.evaluate(() => document.body.scrollWidth <= innerWidth));
        await bundle.screenshot({ path: path.join(output, `${prefix}-${audience.toLowerCase()}-${width}.png`), fullPage: true, animations: 'disabled' });
        await bundle.screenshot({ path: path.join(output, `${prefix}-${audience.toLowerCase()}-${width}-viewport.png`), animations: 'disabled' });
      }
      await bundle.close();
    }
    checks.push(`${prefix}: both actual downloads match the confirmed plan and material state`);
  }
  try {
    if (process.env.MODULE_EXPORT_PREVIEW_ONLY === '1') {
      for (const audience of ['visitor', 'organizer']) {
        const filename = path.join(output, `material-refreshed-${audience}.html`);
        await page.goto(pathToFileURL(filename).href);
        for (const width of [1440, 390]) {
          await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
          assert(await page.evaluate(() => document.body.scrollWidth <= innerWidth));
          await page.screenshot({ path: path.join(output, `material-refreshed-${audience}-${width}-viewport.png`), animations: 'disabled' });
        }
      }
      assert.equal(errors.length, 0, errors.join('\n'));
      assert.equal(externalResourceRequests.length, 0, JSON.stringify(externalResourceRequests));
      result = { mode: 'existing-real-html-preview-only', passed: true };
      checks.push('Existing actual final exports: visitor/organizer 1440x1000 and 390x844 viewport screenshots; no API/model calls');
      return;
    }
    await page.goto(base);
    await page.waitForSelector('#runtimeState');
    if (process.env.MODULE_REPLAY_ID) {
      await page.locator('#historySelect').selectOption(process.env.MODULE_REPLAY_ID);
      await page.waitForFunction(() => document.querySelector('#runtimeState').textContent.includes('历史回放'));
      assert(await page.locator('#approveRun').isDisabled());
      assert(await page.locator('#exportVisitor').isDisabled());
      await capturePages('history');
      if (await page.locator('#previewVisitor').isEnabled()) await previewBoth('history', false);
      result = { mode: 'read-only-real-history', runId: process.env.MODULE_REPLAY_ID };
    } else {
      assert.equal((await (await page.request.get(`${base}/api/health`)).json()).model_ready, true);
      assert.equal(await page.locator('#planningMode').inputValue(), 'modules');
      // The comparison baseline explicitly requests tea. Neutral preferences need not
      // return a 50-minute craft+tea option among the six diverse candidates.
      await page.locator('[data-page="planner"]').click();
      await page.locator('#teaPreference').selectOption('include');
      await page.locator('[data-page="studio"]').click();
      const baseline = await execute(() => page.locator('#auditBtn').click(), '01-default', 'awaiting_review');
      assert(baseline.teaching.check.passed);
      assert(baseline.planning.candidates.length > 2);
      assert(baseline.claims.some(claim => claim.status === 'contradicted' && claim.corrected_status === 'supported'));
      assert(baseline.claims.some(claim => claim.kind === 'operating_promise' && claim.status === 'insufficient'));
      assert((await page.locator('#auditResult').textContent()).includes('文化事实'));
      assert((await page.locator('#auditResult').textContent()).includes('经营承诺 · 待另核'));
      await capturePages('default');
      await page.locator('[data-page="studio"]').click();
      await page.locator('#presentationMode').click();
      await page.screenshot({ path: path.join(output, 'studio-projection-viewport.png'), animations: 'disabled' });
      await page.locator('#presentationMode').click();
      await page.locator('[data-page="planner"]').click();
      const initial = baseline.planning.candidates.find(plan => plan.feasible && plan.craft_minutes === 50 && plan.module_ids.includes('tea'));
      assert(initial, '需要真实可行的50分钟手作+茶歇候选作为人工选择基线');
      await page.locator(`[data-scheme="${initial.id}"]`).click();
      await previewBoth('draft', true);
      assert.equal((await getRun(baseline.id)).approval, null, '预览不能暗中确认');
      await approve();
      const initialApproved = await getRun(baseline.id);
      save('01-default-approved.json', initialApproved);
      assert.equal(initialApproved.plan.id, initial.id);
      checks.push('Default genuine module choices/teaching; user chose feasible 50-minute craft + tea; preview did not approve');

      await page.locator('#budgetCase').click();
      await page.locator('[data-page="studio"]').click();
      await page.locator('#requestNote').fill('安排亲子互动，不安排茶歇，手作至少40分钟，多留手作时间；讲解浅显易懂。');
      const conflict = await execute(() => page.locator('#auditBtn').click(), '02-note-conflict', 'needs_confirmation');
      assert.equal(conflict.previous_run_id, baseline.id);
      assert(conflict.requirement_conflicts.some(item => item.field === 'audience'));
      assert(!conflict.plan);
      assert(await page.locator('#approveRun').isDisabled());
      assert(await page.locator('#previewVisitor').isDisabled());
      await page.locator('#requirementConflictStudio').screenshot({ path: path.join(output, 'note-conflict.png') });
      const revised = await execute(() => page.locator('#requirementConflictStudio [data-resolve-requirements="note"]').click(), '03-note-adopted', 'awaiting_review');
      assert.equal(revised.previous_run_id, baseline.id, '冲突任务不能覆盖最近有方案的比较基线');
      assert.equal(revised.effective_requirements.audience, 'family');
      assert.equal(revised.effective_requirements.budget_per_person, 110);
      assert.equal(revised.effective_requirements.tea_preference, 'exclude');
      assert.equal(revised.effective_requirements.constraints.maximize_craft, true);
      assert(revised.plan.craft_minutes >= 40 && revised.plan.per_person_cents <= 11000);
      assert(!revised.plan.module_ids.includes('tea'));
      assert.equal(revised.plan.craft_minutes, Math.max(...revised.planning.candidates.filter(plan => plan.feasible).map(plan => plan.craft_minutes)));
      const ranked = revised.planning.candidates.filter(plan => plan.feasible).sort((a,b) => b.craft_minutes-a.craft_minutes || a.total_cents-b.total_cents || a.duration_minutes-b.duration_minutes || a.id.localeCompare(b.id));
      assert.equal(revised.plan.id, ranked[0].id, '明确偏好由程序排序，同手作时选择较低总价，再比较总时长');
      assert.equal(revised.selection_method, 'deterministic_preference_ranking');
      assert.equal(revised.comparison.before.craft_minutes, 50);
      assert(revised.comparison.after.craft_minutes > 50);
      assert(revised.teaching.check.passed && revised.teaching.audience === 'family');
      assert(revised.teaching.short_script.every(item => item.claim_ids.length && item.source_ids.length));
      await capturePages('family-revised');
      await page.locator('[data-page="planner"]').click();
      assert((await page.locator('#planComparison').textContent()).includes('改一句话，方案真变化'));
      assert.equal(await page.locator('[data-craft-before]').textContent(), String(revised.comparison.before.craft_minutes));
      assert.equal(await page.locator('[data-craft-after]').textContent(), String(revised.comparison.after.craft_minutes));
      assert((await page.locator('#effectiveConditions').textContent()).includes('手作最低时长与全程上限分别校验'));
      await page.locator('#planComparison').screenshot({ path: path.join(output, 'comparison.png') });
      await page.evaluate(() => window.scrollTo(0, document.querySelector('#planComparison').getBoundingClientRect().top + window.scrollY - 30));
      await page.screenshot({ path: path.join(output, 'comparison-with-candidates.png'), animations: 'disabled' });
      await page.locator('#teachingPanel').screenshot({ path: path.join(output, 'family-teaching.png') });
      await page.locator('#teachingPanel [data-reveal-claim]').first().click();
      assert(await page.locator('#studio').evaluate(element => element.classList.contains('active')));
      await previewBoth('family-draft', true);
      await approve();
      const revisedApproved = await getRun(revised.id);
      save('03-note-adopted-approved.json', revisedApproved);
      await downloadBoth(revisedApproved, 'family-confirmed', true);
      checks.push('UI note conflict explicitly adopted; budget110/no-tea/maximize-craft/family constraints change actual modules, teaching and comparison');

      await page.locator('[data-material-id="mat-paper-garden"][data-state="withdrawn"]').click();
      restoreMaterial = true;
      await page.waitForFunction(() => document.querySelector('#runtimeState').textContent.includes('结果失效'));
      for (const id of ['previewVisitor', 'previewOrganizer', 'exportVisitor', 'exportOrganizer', 'approveRun']) assert(await page.locator('#' + id).isDisabled());
      for (const audience of ['visitor', 'organizer']) {
        assert.equal((await page.request.get(`${base}/api/runs/${revised.id}/export?audience=${audience}`)).status(), 409);
        assert.equal((await page.request.get(`${base}/api/runs/${revised.id}/export?preview=true&audience=${audience}`)).status(), 409);
      }
      await page.waitForFunction(() => !document.querySelector('#auditBtn').disabled);
      await waitToast(page);
      await page.locator('#impactTrail').screenshot({ path: path.join(output, 'withdrawal-impact.png') });
      const refreshed = await execute(() => page.locator('#refreshRun').click(), '04-material-refresh', 'awaiting_review', `/api/runs/${revised.id}/refresh`);
      assert(refreshed.cards.every(card => !card.material_ids.includes('mat-paper-garden')));
      await previewBoth('withdrawn-draft', true);
      await approve();
      const refreshedApproved = await getRun(refreshed.id);
      save('04-material-refreshed-approved.json', refreshedApproved);
      await downloadBoth(refreshedApproved, 'material-refreshed', false);
      await page.locator('[data-material-id="mat-paper-garden"][data-state="available"]').click();
      await page.waitForSelector('[data-material-id="mat-paper-garden"][data-state="withdrawn"]');
      restoreMaterial = false;
      assert.equal((await getRun(refreshed.id)).status, 'confirmed', '恢复素材不得使不依赖该素材的新包失效');
      for (const audience of ['visitor', 'organizer']) assert.equal((await page.request.get(`${base}/api/runs/${refreshed.id}/export?audience=${audience}`)).status(), 200);
      checks.push('Actual material withdrawal invalidates both preview/download; UI refresh preserves teaching and removes SVG in both exports; restored material');

      await page.locator('#conflictBtn').click();
      const impossible = await execute(() => page.locator('#runPlan').click(), '05-resources-impossible', 'needs_input');
      assert(!impossible.plan);
      assert.equal(impossible.requirements.people, 16);
      assert(impossible.planning.candidates.every(plan => !plan.feasible));
      assert(impossible.blocking_conflicts.some(item => item.code === 'capacity_exceeded'));
      assert(impossible.blocking_conflicts.some(item => item.code === 'teacher_capacity_exceeded'));
      const refusalText = await page.locator('#planStatus').textContent();
      assert(refusalText.includes('条件已核算，当前无法接待'));
      assert(refusalText.includes('人数16超过单组容量8'));
      assert(refusalText.includes('需至少2位教师') && refusalText.includes('现有1位'));
      assert(!refusalText.includes('运行未完成') && !refusalText.includes('运行失败'));
      for (const id of ['approveRun', 'previewVisitor', 'previewOrganizer', 'exportVisitor', 'exportOrganizer']) assert(await page.locator('#' + id).isDisabled());
      assert.equal((await page.request.get(`${base}/api/runs/${impossible.id}/export?audience=visitor`)).status(), 409);
      await waitToast(page);
      await page.screenshot({ path: path.join(output, 'resources-impossible-viewport.png'), animations: 'disabled' });
      checks.push('Actual 16 people/8 capacity/one teacher/one room fails closed; no fabricated parallel reception or export');
      result = { mode: 'real-module-ui-workflow', approvedFinalRunId: refreshed.id, impossibleRunId: impossible.id };
    }
    assert.equal(errors.length, 0, errors.join('\n'));
    assert.equal(externalResourceRequests.length, 0, JSON.stringify(externalResourceRequests));
    checks.push('Opened browser pages/packages request no external HTTP resources; local API was never mocked; not a whole-machine offline test');
    result.passed = true;
  } catch (error) {
    result.error = String(error);
    result.passed = false;
    throw error;
  } finally {
    if (restoreMaterial) {
      const response = await page.request.patch(`${base}/api/materials/mat-paper-garden`, { data: { usage_status: 'available' } });
      result.materialRestoredAfterFailure = response.ok();
    }
    const report = { at: new Date().toISOString(), base, output, ...result, runs, checks, scriptErrors: errors, externalResourceRequests };
    save(process.env.MODULE_EXPORT_PREVIEW_ONLY === '1' ? 'export-preview-verification.json' : process.env.MODULE_REPLAY_ID ? 'history-verification.json' : 'verification.json', report);
    console.log(JSON.stringify(report, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
