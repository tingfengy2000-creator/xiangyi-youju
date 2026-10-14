/* 宣传片素材采集：在 5090 上用真实本地模型跑一遍三幕，录下高清静帧与短视频片段。
 *
 * 用法：LIVE_BASE_URL=http://127.0.0.1:8795 npm run film:capture
 * 输出：artifacts/film-footage/：静帧为 2 倍图；整段操作录成一个 1920×1080 的 webm（take.webm），
 *       manifest.json 的 marks 记下每个节拍在视频里的秒数，剪辑时按秒切段；另有每次运行的原始 JSON。
 *
 * 规则与 test:demo-guide 相同：每个真实任务只提交一次；任何一步失败立即停止，不重试；
 * 第三幕发布作品新版本不可撤销，每次采集都要用新的空数据库。本脚本只采集画面，不判定验收；验收以 test:demo-guide 为准。
 * 采集用“投屏大字”模式、关闭三幕引导条，由脚本模拟操作者操作：第二幕切换体验对象，第三幕发布作品新版本，
 * 另外采集“按要求生成讲解词”并核验一次，以及“需要安排英语讲解”被拦下。
 */
const { chromium } = require('playwright');
const { browserOptions } = require('./browser-options.cjs');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');

const root = path.resolve(__dirname, '..');
const base = (process.env.LIVE_BASE_URL || 'http://127.0.0.1:8780').replace(/\/$/, '');
const output = path.join(root, 'artifacts', 'film-footage');
fs.rmSync(output, { recursive: true, force: true });
fs.mkdirSync(output, { recursive: true });

const manifest = { at: new Date().toISOString(), base, purpose: '宣传片素材：真实本地运行画面', viewport: '1920x1080', stillScale: 2, stills: [], marks: [], runs: {}, missing: [], firstFailure: null, passed: false };
const NOTE = '讲清楚工艺特色，留出观察和提问的时间。';
const RUN_TIMEOUT = 10 * 60 * 1000;
const save = () => fs.writeFileSync(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2));
async function getJson(page, url) { const r = await page.request.get(base + url); assert(r.ok(), `${url} → ${r.status()}`); return r.json(); }

async function still(page, name, what, note) {
  const file = `${name}.png`;
  try {
    if (what) {
      const el = page.locator(what).first();
      if (!(await el.count()) || !(await el.isVisible())) { manifest.missing.push({ name, selector: what }); return; }
      await el.scrollIntoViewIfNeeded();
      await page.waitForTimeout(400);
      await el.screenshot({ path: path.join(output, file), animations: 'disabled' });
    } else {
      await page.screenshot({ path: path.join(output, file), animations: 'disabled' });
    }
    manifest.stills.push({ file, selector: what || 'viewport', note });
    console.log('□', file);
  } catch (e) { manifest.missing.push({ name, selector: what, error: String(e).split('\n')[0] }); }
}

async function waitRun(page, id) {
  const started = Date.now();
  for (;;) {
    const run = await getJson(page, `/api/runs/${encodeURIComponent(id)}`);
    if (!['running', 'queued'].includes(run.status) && run.execution_finished !== false) {
      fs.writeFileSync(path.join(output, `run-${id}.json`), JSON.stringify(run, null, 2));
      manifest.runs[id] = { status: run.status, model_calls: run.model_calls, elapsed_seconds: run.elapsed_seconds, parent_id: run.parent_id || null, comparison: run.comparison ? { before: run.comparison.before, after: run.comparison.after } : null, plan: run.plan ? { id: run.plan.id, craft_minutes: run.plan.craft_minutes, duration_minutes: run.plan.duration_minutes, total_cents: run.plan.total_cents, local_service_cents: run.plan.local_service_cents, material_cents: run.plan.material_cents, operations_cents: run.plan.operations_cents } : null, error: run.error || null };
      await page.waitForFunction(() => !document.querySelector('#auditBtn').disabled && !document.querySelector('#runPlan').disabled, null, { timeout: 60000 });
      await page.waitForTimeout(1200);
      return run;
    }
    if (Date.now() - started > RUN_TIMEOUT) throw Error(`任务 ${id} 超时`);
    await page.waitForTimeout(1000);
  }
}
async function submit(page, selector, endpoint) {
  const response = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === endpoint, { timeout: 60000 });
  await page.locator(selector).click();
  const created = await (await response).json();
  assert(created.id, '没有返回任务号');
  return created.id;
}

let t0 = Date.now();
function mark(name, note) { const sec = Math.round((Date.now() - t0) / 100) / 10; manifest.marks.push({ name, sec, note }); console.log(`⏱ ${sec}s`, name); }
async function pause(page, ms) { await page.waitForTimeout(ms); }

(async () => {
  const browser = await chromium.launch(browserOptions('msedge'));
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2, recordVideo: { dir: output, size: { width: 1920, height: 1080 } } });
  let page = null;
  try {
    const probe = await context.request.get(base + '/api/health');
    const health = await probe.json();
    assert.equal(health.status, 'ready', '模型服务未就绪：' + JSON.stringify(health));
    const catalog = await (await context.request.get(base + '/api/catalog')).json();
    const notAvailable = (catalog.materials || []).filter(m => m.usage_status !== 'available').map(m => m.id);
    assert.deepEqual(notAvailable, [], '开始前有素材不是可用状态：' + notAvailable.join(','));
    const published = (catalog.materials || []).filter(m => (m.edition || 1) > 1).map(m => m.id);
    assert.deepEqual(published, [], '作品已发布过新版本，请换用新的空数据库：' + published.join(','));
    manifest.model = health.model;

    page = await context.newPage();
    t0 = Date.now();
    page.on('pageerror', e => (manifest.scriptErrors ||= []).push(String(e)));

    // Home.
    await page.goto(base + '/');
    await page.waitForSelector('#runtimeState', { timeout: 30000 });
    await pause(page, 800);
    await page.locator('#presentationMode').click();
    await pause(page, 3600);
    mark('home-still', '首页首屏静置');
    await still(page, 's01-home-viewport', null, '首页首屏');
    await still(page, 's02-home-hero', '#home .hero', '首页主视觉');
    await still(page, 's03-home-acts', '#home .acts', '三幕故事条');
    await still(page, 's04-home-meaning', '#home .meaning', '意义带');
    await page.evaluate(() => scrollTo({ top: 0 }));
    await pause(page, 1500);

    // Act one.
    await page.locator('[data-page="studio"]').first().click();
    await page.locator('#caseSelect').selectOption('confusion');
    await pause(page, 1500);
    mark('act1-draft', '工坊页：待核验文案（含“阳刻为主”）');
    await still(page, 's05-studio-before', '#draft', '待核验文案');
    await page.locator('#auditBtn').hover(); await pause(page, 800);
    mark('act1-click', '点击“核验并编排体验”');
    const act1 = await submit(page, '#auditBtn', '/api/runs');
    const run1 = await waitRun(page, act1);
    assert.equal(run1.status, 'awaiting_review', '第一幕：' + run1.status + ' ' + (run1.error || ''));
    mark('act1-result', '核验结果出现（此前为等待段）');
    await page.locator('#auditResult').scrollIntoViewIfNeeded(); await pause(page, 2500);
    await still(page, 's06-studio-viewport', null, '核验结果全屏');
    await still(page, 's07-audit-result', '#auditResult', '逐句核验与修订');
    await still(page, 's08-evidence', '#auditResult .evidence-block', '出处原文卡');

    // Act two: same heritage, a different audience. The operator switches 体验对象 on screen.
    // 文字需求框在工坊页：必须先在工坊页换成与对象无关的中性需求（与三幕引导同一句），
    // 否则默认需求里的“游客”会被模型读成普通游客，与表单上的青少年学生冲突（5090 首次失败，370f7db）。
    await page.locator('#requestNote').fill(NOTE);
    assert.equal(await page.locator('#requestNote').inputValue(), NOTE, '第二幕前文字需求应换成中性需求');
    await page.locator('[data-page="planner"]').first().click();
    await page.locator('#planningMode').selectOption('modules');
    await page.locator('#audience').scrollIntoViewIfNeeded(); await pause(page, 1200);
    await still(page, 's10-audience-before', '#audience', '体验对象：普通游客');
    mark('act2-audience', '体验对象从普通游客换成青少年学生');
    await page.locator('#audience').selectOption('student');
    await page.locator('#audience').dispatchEvent('input');
    await pause(page, 1500);
    await still(page, 's10-audience-after', '#audience', '体验对象：青少年学生');
    await page.locator('#runPlan').scrollIntoViewIfNeeded(); await page.locator('#runPlan').hover(); await pause(page, 800);
    assert.equal(await page.locator('#audience').inputValue(), 'student');
    assert.equal(await page.locator('#planningMode').inputValue(), 'modules');
    assert.equal(await page.locator('#requestNote').inputValue(), NOTE, '提交第二幕前文字需求被改动');
    mark('act2-click', '点击“按当前条件重新编排”');
    const act2 = await submit(page, '#runPlan', '/api/runs');
    const run2 = await waitRun(page, act2);
    assert.equal(run2.status, 'awaiting_review', '第二幕：' + run2.status + ' ' + (run2.error || ''));
    mark('act2-result', '方案对比出现');
    manifest.act2 = { audience: (run2.effective_requirements || run2.requirements).audience, teaching_audience: run2.teaching?.audience,
                      teaching_passed: run2.teaching?.check?.passed, teaching_script: (run2.teaching?.short_script || []).map(item => item.text),
                      observation: run2.teaching?.observation_task?.text, question: run2.teaching?.interaction_question?.text };
    await page.locator('#planComparison').scrollIntoViewIfNeeded(); await pause(page, 3000);
    await still(page, 's11-planner-viewport', null, '编排结果全屏');
    await still(page, 's12-comparison', '#planComparison', '换个对象，方案真变化');
    await page.locator('.ledger-details').first().evaluate(d => { d.open = true; }).catch(() => {});
    await pause(page, 600);
    await still(page, 's13-ledger', '.ledger-details', '账目：本地服务报酬、材料、组织');
    await still(page, 's09-teaching', '#teachingPanel', '面向青少年学生的讲解与提问');
    await still(page, 's14-route', '#routeCards', '日程');

    // Act three: the craftsperson publishes a new edition; the handbook follows.
    await page.locator('#materialList').scrollIntoViewIfNeeded(); await pause(page, 1500);
    await still(page, 's15-works-before', '#materialList', '手艺人作品（第 1 版）');
    const target = page.locator('#materialList [data-publish-id]:not(:disabled)').first();
    const workId = await target.getAttribute('data-publish-id');
    await target.hover(); await pause(page, 1000);
    mark('act3-publish', '点击“发布新版本”');
    const publishWait = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === `/api/materials/${workId}/publish`);
    await target.click();
    const publishResult = await (await publishWait).json();
    assert.equal(publishResult.record?.edition, 2, '作品应进入第 2 版');
    await pause(page, 2500);
    const old = await getJson(page, `/api/runs/${act2}`);
    manifest.invalidated = { run_id: act2, status: old.status, work: workId, title: publishResult.record.title };
    mark('act3-outdated', '旧手册待更新、确认与导出禁用');
    await still(page, 's16-outdated-viewport', null, '作品上新后全屏');
    await still(page, 's17-impact', '#impactTrail', '找出引用旧版本的内容');
    await still(page, 's18-works-after', '#materialList', '手艺人作品（第 2 版）');
    await page.locator('#refreshRun').scrollIntoViewIfNeeded(); await page.locator('#refreshRun').hover(); await pause(page, 800);
    mark('act3-click', '点击“依据最新资料重新核验”');
    const act3 = await submit(page, '#refreshRun', `/api/runs/${act2}/refresh`);
    const run3 = await waitRun(page, act3);
    assert.equal(run3.status, 'awaiting_review', '第三幕：' + run3.status + ' ' + (run3.error || ''));
    mark('act3-result', '重新核验完成');
    await pause(page, 2000);
    await still(page, 's19-refreshed-viewport', null, '重新核验后全屏');

    // Human confirmation, then both editions (preview only; nothing is published).
    await page.locator('#approvalCheck').scrollIntoViewIfNeeded();
    await page.locator('#approvalCheck').check(); await pause(page, 800);
    mark('confirm', '人工确认');
    await page.locator('#approveRun').click();
    await page.waitForFunction(() => !document.querySelector('#exportVisitor').disabled, null, { timeout: 30000 });
    await pause(page, 1500);
    for (const [edition, label] of [['Visitor', '游客版'], ['Organizer', '组织者版']]) {
      await page.locator('#preview' + edition).click();
      await page.waitForSelector('#bundlePreview[open]', { timeout: 30000 });
      await pause(page, 2500);
      mark('preview-' + edition.toLowerCase(), label + '预览');
      await still(page, `s2${edition === 'Visitor' ? 0 : 1}-preview-${edition.toLowerCase()}`, null, label + '预览');
      const frame = page.frameLocator('#previewFrame');
      await frame.locator('body').evaluate(b => b.scrollTo({ top: 600, behavior: 'smooth' })).catch(() => {});
      await pause(page, 2500);
      if (edition === 'Visitor') {
        await frame.locator('h2', { hasText: '手艺人作品' }).scrollIntoViewIfNeeded().catch(() => {});
        await pause(page, 2000);
        mark('preview-works', '游客版：手艺人作品栏（新版作品）');
        await still(page, 's20b-preview-works', null, '游客版手艺人作品栏');
      }
      await page.locator('#closePreview').click(); await pause(page, 800);
    }

    // Write a 讲解词 from a simple requirement, then verify it once.
    await page.locator('[data-page="studio"]').first().click();
    await page.locator('#draftGenerator').scrollIntoViewIfNeeded(); await pause(page, 1200);
    await page.locator('#draftAudience').selectOption('senior'); await pause(page, 800);
    mark('draft-click', '讲给老年人、约 5 分钟：点击“按要求生成讲解词”');
    const draftResponse = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/drafts', { timeout: 200000 });
    await page.locator('#generateDraft').click();
    const draft = await (await draftResponse).json();
    await page.waitForSelector('#draftOrigin:not([hidden])');
    mark('draft-result', '草稿填入，标明来源');
    manifest.draft = { origin: draft.origin, text: draft.text, source_ids: draft.source_ids, model_calls: draft.model_calls, error: draft.model_error || null };
    await pause(page, 2000);
    await still(page, 's24-draft', '#draftGenerator', '按要求生成讲解词');
    await still(page, 's25-draft-text', '#draft', '生成的讲解词草稿');
    await page.locator('#auditBtn').scrollIntoViewIfNeeded(); await page.locator('#auditBtn').hover(); await pause(page, 600);
    mark('draft-audit-click', '草稿送去逐句核验');
    const draftRun = await submit(page, '#auditBtn', '/api/runs');
    const runDraft = await waitRun(page, draftRun);
    mark('draft-audit-result', '草稿逐句核验结果');
    manifest.draft.audit = { run_id: draftRun, status: runDraft.status, claim_statuses: (runDraft.claims || []).map(c => c.status) };
    await page.locator('#auditResult').scrollIntoViewIfNeeded(); await pause(page, 2500);
    await still(page, 's26-draft-audit', '#auditResult', '草稿逐句核验');

    // A request the system must not promise: one more real run, defaults kept, note replaced.
    await page.locator('[data-page="studio"]').first().click();
    await page.locator('#requestNote').scrollIntoViewIfNeeded();
    await page.locator('#requestNote').fill('');
    await page.keyboard.type('需要安排英语讲解', { delay: 140 });
    await pause(page, 800);
    mark('stop-click', '提出未配置服务：需要安排英语讲解');
    const stop = await submit(page, '#auditBtn', '/api/runs');
    const runStop = await waitRun(page, stop);
    mark('stop-result', '系统停下请人澄清');
    manifest.stop = { run_id: stop, status: runStop.status, error: runStop.error || null };
    await still(page, 's22-stop-viewport', null, '停下来请人澄清');
    await still(page, 's23-stop-warning', '#runWarning', '阻断提示');
    await pause(page, 2500);

    mark('end', '采集结束');
    manifest.passed = true;
  } catch (error) {
    manifest.firstFailure = { message: String(error && error.stack || error), at: new Date().toISOString() };
    console.error('✗ 首次失败：', error.message || error);
    process.exitCode = 1;
  } finally {
    const video = page?.video();
    if (page) await page.close();
    if (video) { await video.saveAs(path.join(output, 'take.webm')); await video.delete().catch(() => {}); manifest.video = 'take.webm'; }
    save();
    await context.close(); await browser.close();
    console.log(JSON.stringify({ passed: manifest.passed, stills: manifest.stills.length, marks: manifest.marks.length, missing: manifest.missing, runs: Object.keys(manifest.runs) }, null, 2));
  }
})();
