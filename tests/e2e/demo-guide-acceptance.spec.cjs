/* 三幕演示引导：真实模型一次性验收脚本（5090 端运行）。
 *
 * 用法：LIVE_BASE_URL=http://127.0.0.1:8795 npm run test:demo-guide
 * 可选：HOME_SCREENSHOT_DIR=docs/assets/screenshots  全部通过后才把首页三图写入该目录。
 *
 * 规则：
 * - 每个真实任务只提交一次。任何一步失败立即停止，保存证据，不重试、不补跑。
 * - 引导按钮只填入和定位；脚本统计全部写请求，引导点击后的写请求必须为 0。
 * - 第三幕发布作品新版本不可撤销，所以每次都要用新的空数据库运行；前置检查会拦下已发布过的数据库。
 * - 第二幕换成“青少年学生”，第三幕由手艺人发布作品新版本；另有一次“按要求生成讲解词”并核验。
 * - 文字需求阻断检查使用页面默认条件，只替换“这场体验，您有什么想法？”这一个输入框，并保存实际请求体。
 */
const { chromium } = require('playwright');
const { browserOptions } = require('../../scripts/browser-options.cjs');
const { smallChinese } = require('./legibility.cjs');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');

const root = path.resolve(__dirname, '../..');
const base = (process.env.LIVE_BASE_URL || 'http://127.0.0.1:8780').replace(/\/$/, '');
const output = path.join(root, 'artifacts', 'demo-guide-acceptance');
const homeTarget = process.env.HOME_SCREENSHOT_DIR ? path.resolve(root, process.env.HOME_SCREENSHOT_DIR) : null;
fs.mkdirSync(output, { recursive: true });

const result = { at: new Date().toISOString(), base, steps: [], runs: {}, writes: [], scriptErrors: [], firstFailure: null, passed: false };
const RUN_TIMEOUT = 10 * 60 * 1000;
const ENGLISH = '需要安排英语讲解';
const NEGATION = '不需要翻译，按现有安排。';

function step(name, detail = {}) { result.steps.push({ name, at: new Date().toISOString(), ...detail }); console.log('✓', name); }
function save() { fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(result, null, 2)); }
async function getJson(page, url) { const r = await page.request.get(base + url); assert(r.ok(), `${url} → ${r.status()}`); return r.json(); }

async function waitRun(page, id) {
  const started = Date.now();
  for (;;) {
    const run = await getJson(page, `/api/runs/${encodeURIComponent(id)}`);
    if (!['running', 'queued'].includes(run.status) && run.execution_finished !== false) {
      fs.writeFileSync(path.join(output, `run-${id}.json`), JSON.stringify(run, null, 2));
      result.runs[id] = { status: run.status, model_calls: run.model_calls, elapsed_seconds: run.elapsed_seconds, parent_id: run.parent_id || null, error: run.error || null };
      await page.waitForFunction(() => !document.querySelector('#auditBtn').disabled && !document.querySelector('#runPlan').disabled, null, { timeout: 60000 });
      await page.waitForTimeout(600);
      return run;
    }
    if (Date.now() - started > RUN_TIMEOUT) throw Error(`任务 ${id} 超过 ${RUN_TIMEOUT / 1000} 秒仍未结束`);
    await page.waitForTimeout(1000);
  }
}

// One operator click that must create exactly one task. Returns the created run id.
async function operatorSubmit(page, selector, endpointTest, label) {
  const before = result.writes.length;
  const response = page.waitForResponse(r => endpointTest(new URL(r.url()).pathname) && r.request().method() === 'POST', { timeout: 60000 });
  await page.locator(selector).click();
  const created = await (await response).json();
  assert(created.id, `${label}：服务端没有返回任务号`);
  await page.waitForTimeout(300);
  const added = result.writes.slice(before).filter(w => w.method === 'POST');
  assert.equal(added.length, 1, `${label}：操作者一次点击应只产生 1 个提交，实际 ${added.length}`);
  return created.id;
}

async function noWritesAfter(page, action, label) {
  const before = result.writes.length;
  await action();
  await page.waitForTimeout(1500);
  const added = result.writes.slice(before);
  assert.equal(added.length, 0, `${label}：引导按钮不得发起写请求，实际 ${JSON.stringify(added)}`);
}

async function evidence(page, name) {
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true, animations: 'disabled' });
  const dom = await page.evaluate(() => [...document.querySelectorAll('.demo-guide')].map(bar => ({ id: bar.id, hidden: bar.hidden, steps: [...bar.querySelectorAll('.demo-step')].map(s => ({ step: s.dataset.demoStep, done: s.classList.contains('done'), active: s.classList.contains('active'), check: s.querySelector('.demo-check')?.textContent })), hint: bar.querySelector('.demo-hint')?.textContent })));
  fs.writeFileSync(path.join(output, `${name}-guide.json`), JSON.stringify(dom, null, 2));
  return dom;
}

async function doneText(page, bar, index) {
  const el = page.locator(`#${bar} .demo-step[data-demo-step="${index}"]`);
  return { done: await el.evaluate(e => e.classList.contains('done')), text: await el.locator('.demo-check').textContent() };
}

(async () => {
  const browser = await chromium.launch(browserOptions('msedge'));
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1, acceptDownloads: true });
  const page = await context.newPage();
  page.on('pageerror', e => result.scriptErrors.push(String(e)));
  page.on('request', r => {
    const u = new URL(r.url());
    if (r.method() !== 'GET' && u.pathname.startsWith('/api/')) result.writes.push({ at: new Date().toISOString(), method: r.method(), path: u.pathname, body: r.postData() || null });
  });
  try {
    // 0. Preconditions: no model calls.
    const health = await getJson(page, '/api/health');
    assert.equal(health.status, 'ready', '模型服务未就绪：' + JSON.stringify(health));
    assert.equal(health.model_ready, true);
    const catalog = await getJson(page, '/api/catalog');
    const notAvailable = (catalog.materials || []).filter(m => m.usage_status !== 'available').map(m => m.id);
    assert.deepEqual(notAvailable, [], '开始前有素材不是可用状态，请先在页面上恢复后再运行：' + notAvailable.join(','));
    const published = (catalog.materials || []).filter(m => (m.edition || 1) > 1).map(m => m.id);
    assert.deepEqual(published, [], '作品已发布过新版本，请换用新的空数据库再运行：' + published.join(','));
    const running = (await getJson(page, '/api/runs')).filter?.(r => ['running', 'queued'].includes(r.status)) || [];
    assert.equal(running.length, 0, '开始前仍有运行中的任务');
    step('前置条件：模型就绪，素材全部可用、作品均为第 1 版，无运行中任务', { model: health.model });

    // 1. Home: silent first paint, then still screenshots.
    await page.goto(base + '/');
    await page.waitForSelector('#runtimeState', { timeout: 30000 });
    await page.waitForTimeout(500);
    assert.equal(await page.locator('#toast.show').count(), 0, '首次载入弹出了提示条');
    await page.waitForTimeout(3500);
    assert.equal(await page.locator('#toast.show').count(), 0, '首次载入后 4 秒内出现提示条');
    await page.locator('#home .hero').screenshot({ path: path.join(output, 'home-hero.png'), animations: 'disabled' });
    await page.screenshot({ path: path.join(output, 'home-desktop.png'), fullPage: true, animations: 'disabled' });
    step('首页：首次载入无提示条；已截取静止画面（桌面）');

    // 2. Act one.
    await page.locator('[data-page="studio"]').first().click();
    assert(await page.locator('#demoGuideStudio').isHidden(), '三幕演示应默认关闭');
    await page.locator('#demoGuideToggle').click();
    assert((await page.locator('#demoGuideStudio').textContent()).includes('演示引导 · 结果以真实运行为准'));
    await noWritesAfter(page, () => page.locator('#demoGuideStudio [data-demo-fill="0"]').click(), '第一幕填入');
    assert.equal(await page.locator('#caseSelect').inputValue(), 'confusion');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'auditBtn');
    const act1 = await operatorSubmit(page, '#auditBtn', p => p === '/api/runs', '第一幕');
    const run1 = await waitRun(page, act1);
    assert.equal(run1.status, 'awaiting_review', '第一幕状态：' + run1.status + ' ' + (run1.error || ''));
    const first = (run1.claims || [])[0];
    assert.equal(first?.status, 'contradicted', '第一句应判为与来源矛盾');
    assert((first.suggested_text || first.revised_text || JSON.stringify(first)).includes('阴刻为主'), '修订应为阴刻为主');
    const c1 = await doneText(page, 'demoGuideStudio', 0);
    assert(c1.done && c1.text.includes(act1.slice(0, 8)), '第一幕 ✓ 未按真实运行出现：' + c1.text);
    await evidence(page, 'act-1');
    step('第一幕：阳刻为主判为矛盾，修订为阴刻为主；✓ 出现', { run_id: act1, check: c1.text });

    // 3. Act two: same heritage, a different audience.
    await noWritesAfter(page, () => page.locator('#demoGuideStudio [data-demo-fill="1"]').click(), '第二幕填入');
    assert.equal(await page.locator('#audience').inputValue(), 'student');
    assert.equal(await page.locator('#planningMode').inputValue(), 'modules');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'runPlan');
    const act2 = await operatorSubmit(page, '#runPlan', p => p === '/api/runs', '第二幕');
    const run2 = await waitRun(page, act2);
    assert.equal(run2.status, 'awaiting_review', '第二幕状态：' + run2.status + ' ' + (run2.error || ''));
    const cmp = run2.comparison || {};
    assert(cmp.before && cmp.after && JSON.stringify(cmp.before.module_ids) !== JSON.stringify(cmp.after.module_ids), '换成青少年学生后活动组合应改变：' + JSON.stringify(cmp));
    assert.equal((run2.effective_requirements || run2.requirements).audience, 'student');
    assert.equal(run2.teaching?.audience, 'student', '教学内容应面向青少年学生');
    assert.equal(run2.teaching?.check?.passed, true, '面向学生的教学内容应通过逐项扫描：' + JSON.stringify(run2.teaching?.check?.issues || []));
    const c2 = await doneText(page, 'demoGuidePlanner', 1);
    assert(c2.done && c2.text.includes('青少年学生') && c2.text.includes(`${cmp.before.craft_minutes} → ${cmp.after.craft_minutes}`) && c2.text.includes(act2.slice(0, 8)), '第二幕 ✓ 与对比不一致：' + c2.text);
    await evidence(page, 'act-2');
    step('第二幕：换成青少年学生后活动组合和讲解一起调整，✓ 与方案对比一致', { run_id: act2, comparison: { before: cmp.before, after: cmp.after }, teaching_script: (run2.teaching?.short_script || []).map(item => item.text), check: c2.text });

    // 4. Act three: a craftsperson publishes a new edition; the handbook follows.
    await noWritesAfter(page, () => page.locator('#demoGuidePlanner [data-demo-fill="2"]').click(), '第三幕定位');
    const target = page.locator('#materialList [data-publish-id].demo-target');
    assert.equal(await target.count(), 1, '应高亮且只高亮一个“发布新版本”按钮');
    const workId = await target.getAttribute('data-publish-id');
    const publishResponse = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === `/api/materials/${workId}/publish`);
    await target.click();
    const publishResult = await (await publishResponse).json();
    assert.equal(publishResult.record?.edition, 2, '作品应进入第 2 版');
    await page.waitForFunction(() => document.querySelector('#refreshRun')?.classList.contains('demo-target'), null, { timeout: 30000 });
    const old = await getJson(page, `/api/runs/${act2}`);
    assert.equal(old.status, 'invalidated', '作品上新后，引用旧版本的运行应待更新，实际 ' + old.status);
    assert(await page.locator('#approveRun').isDisabled(), '待更新时确认应禁用');
    assert(await page.locator('#exportVisitor').isDisabled() && await page.locator('#exportOrganizer').isDisabled(), '待更新时导出应禁用');
    const pending = await doneText(page, 'demoGuidePlanner', 2);
    assert(!pending.done, '重新核验前第三幕不应 ✓');
    const act3 = await operatorSubmit(page, '#refreshRun', p => p === `/api/runs/${act2}/refresh`, '第三幕');
    const run3 = await waitRun(page, act3);
    assert.equal(run3.status, 'awaiting_review', '第三幕状态：' + run3.status + ' ' + (run3.error || ''));
    assert.equal(run3.parent_id, act2, '新运行应以待更新的运行为 parent');
    const newWork = (run3.materials_snapshot || []).find(item => item.id === workId);
    assert(newWork && newWork.edition === 2, '新运行应使用作品第 2 版');
    const preview = await page.request.get(`${base}/api/runs/${act3}/export?audience=visitor&preview=true`);
    assert(preview.ok(), '游客版预览失败：' + preview.status());
    const visitorHtml = await preview.text();
    fs.writeFileSync(path.join(output, 'act-3-visitor-preview.html'), visitorHtml);
    assert(visitorHtml.includes('手艺人作品') && visitorHtml.includes(newWork.title), '游客版应含手艺人作品栏与新版作品');
    const c3 = await doneText(page, 'demoGuidePlanner', 2);
    assert(c3.done && c3.text.includes(act3.slice(0, 8)), '第三幕 ✓ 未按真实运行出现：' + c3.text);
    await evidence(page, 'act-3');
    step('第三幕：作品发布第 2 版后旧手册待更新、确认与导出禁用；重新核验后 ✓ 出现，游客版换上新作品', { run_id: act3, parent_id: run3.parent_id, work: workId, title: newWork.title, check: c3.text });

    // 5. Legibility matrix with real results on screen (no model calls).
    const matrix = [];
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      for (const presentation of [false, true]) {
        if (await page.evaluate(() => document.body.classList.contains('presentation-mode')) !== presentation) await page.locator('#presentationMode').click();
        for (const guide of [true, false]) {
          if ((await page.locator('#demoGuideToggle').getAttribute('aria-pressed') === 'true') !== guide) await page.locator('#demoGuideToggle').click();
          for (const id of ['home', 'studio', 'planner']) {
            await page.locator(`[data-page="${id}"]`).first().click();
            await page.waitForTimeout(250);
            const overflow = await page.evaluate(() => document.body.scrollWidth - innerWidth);
            const tiny = await smallChinese(page);
            matrix.push({ width, presentation, guide, page: id, overflow, smallChinese: tiny });
            assert(overflow <= 0, `${width}/${id}/投屏${presentation ? '开' : '关'}/引导${guide ? '开' : '关'} 横向溢出 ${overflow}px`);
            assert.equal(tiny.length, 0, `${width}/${id}/投屏${presentation ? '开' : '关'}/引导${guide ? '开' : '关'} 中文小于12px：${JSON.stringify(tiny)}`);
          }
        }
      }
      if (await page.evaluate(() => document.body.classList.contains('presentation-mode'))) await page.locator('#presentationMode').click();
    }
    fs.writeFileSync(path.join(output, 'legibility-matrix.json'), JSON.stringify(matrix, null, 2));
    step('可读性矩阵：2 宽度 × 投屏开/关 × 引导开/关 × 3 页，共 24 组，无横向溢出，中文不小于 12px');

    // 6. Draft generation from a simple requirement, then one real audit of that draft.
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(base + '/');
    await page.waitForSelector('#runtimeState');
    await page.locator('[data-page="studio"]').first().click();
    // 重新载入后文字需求恢复为默认句，其中的“游客”可能被模型读成普通游客，与学生冲突；
    // 先换成与三幕引导相同的中性需求（370f7db 宣传片采集第二幕首次失败即此原因）。
    await page.locator('#requestNote').fill('讲清楚工艺特色，留出观察和提问的时间。');
    await page.locator('#draftAudience').selectOption('student');
    await page.locator('#draftMinutes').selectOption('5');
    const draftResponse = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/drafts', { timeout: 200000 });
    await page.locator('#generateDraft').click();
    const draft = await (await draftResponse).json();
    fs.writeFileSync(path.join(output, 'draft.json'), JSON.stringify(draft, null, 2));
    assert.equal(draft.origin, 'local_model', '应由本地模型生成草稿，实际：' + draft.origin + ' ' + (draft.model_error || ''));
    assert.equal(await page.locator('#draft').inputValue(), draft.text);
    const draftRun = await operatorSubmit(page, '#auditBtn', p => p === '/api/runs', '草稿核验');
    const runDraft = await waitRun(page, draftRun);
    const statuses = (runDraft.claims || []).map(claim => claim.status);
    assert(!statuses.includes('contradicted'), '生成的草稿不应含与来源矛盾的句子：' + JSON.stringify(statuses));
    assert(statuses.filter(status => status === 'supported').length >= 2, '生成的草稿至少应有两句获来源支持：' + JSON.stringify(statuses));
    step('按要求生成讲解词：本地模型为青少年学生写成草稿，逐句核验无矛盾', { draft_model_calls: draft.model_calls, text: draft.text, run_id: draftRun, status: runDraft.status, claim_statuses: statuses });

    // 7. Note blockers with untouched defaults: reload, replace only the note field.
    for (const [label, note, expectBlock] of [['英语讲解阻断', ENGLISH, true], ['不误伤', NEGATION, false]]) {
      await page.goto(base + '/');
      await page.waitForSelector('#runtimeState');
      await page.locator('[data-page="studio"]').first().click();
      await page.locator('#requestNote').fill(note);
      const sent = page.waitForRequest(r => r.method() === 'POST' && new URL(r.url()).pathname === '/api/runs');
      const id = await operatorSubmit(page, '#auditBtn', p => p === '/api/runs', label);
      const body = JSON.parse((await sent).postData());
      fs.writeFileSync(path.join(output, `note-${expectBlock ? 'english' : 'negation'}-request.json`), JSON.stringify(body, null, 2));
      assert.equal(body.requirements.note, note, '请求体中的文字需求必须只有给定短句');
      assert.equal(body.requirements.planning_mode, 'modules');
      assert.equal(body.requirements.tea_preference, 'any');
      const run = await waitRun(page, id);
      if (expectBlock) {
        assert.equal(run.status, 'needs_input', `${label}：状态应为 needs_input，实际 ${run.status}`);
        assert(String(run.error || '').startsWith('文字需求存在矛盾或超出当前模块能力，请先澄清'), `${label}：错误信息不符：${run.error}`);
        assert(!run.plan, `${label}：不应生成方案`);
        const flagged = (run.note_issue_review || []).some(i => i.category === 'needs_clarification') || (run.program_note_blockers || []).length > 0;
        assert(flagged, `${label}：记录中看不到拦截来源`);
      } else {
        assert.equal(run.status, 'awaiting_review', `${label}：状态应为 awaiting_review，实际 ${run.status} ${run.error || ''}`);
        assert(!(run.program_note_blockers || []).length, `${label}：不应出现 program_note_blockers`);
      }
      step(`${label}：默认条件 + 只填“${note}”`, { run_id: id, status: run.status, error: run.error || null, note_issue_review: run.note_issue_review || null, program_note_blockers: run.program_note_blockers || null });
    }

    // 8. Mobile home screenshot, then publish the three home images only after everything passed.
    await page.goto(base + '/');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(4000);
    assert.equal(await page.locator('#toast.show').count(), 0);
    await page.screenshot({ path: path.join(output, 'home-mobile.png'), fullPage: true, animations: 'disabled' });
    assert.deepEqual(result.scriptErrors, [], '页面脚本错误：' + result.scriptErrors.join('\n'));
    if (homeTarget) {
      for (const name of ['home-hero.png', 'home-desktop.png', 'home-mobile.png']) fs.copyFileSync(path.join(output, name), path.join(homeTarget, name));
      step('首页三图已写入 ' + path.relative(root, homeTarget));
    }
    result.passed = true;
  } catch (error) {
    result.firstFailure = { message: String(error && error.stack || error), at: new Date().toISOString(), lastStep: result.steps.at(-1)?.name || null };
    try { await evidence(page, 'failure'); } catch {}
    console.error('✗ 首次失败：', error.message || error);
    process.exitCode = 1;
  } finally {
    const posts = result.writes.filter(w => w.method === 'POST').length;
    result.summary = { real_runs_submitted: posts, model_calls: Object.values(result.runs).reduce((n, r) => n + (r.model_calls || 0), 0) };
    save();
    await browser.close();
    console.log(JSON.stringify({ passed: result.passed, runs: result.runs, summary: result.summary, firstFailure: result.firstFailure?.message?.split('\n')[0] || null }, null, 2));
  }
})();
