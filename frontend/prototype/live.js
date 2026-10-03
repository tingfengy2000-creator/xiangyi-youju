/* Live adapter: server results are the only source of verification and plan data.
 * file:// deliberately keeps the separately labelled, original preset prototype.
 */
(() => {
  'use strict';
  if (location.protocol === 'file:') return;
  const q = s => document.querySelector(s);
  const all = s => [...document.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = cents => '¥' + (Number(cents || 0) / 100).toLocaleString('zh-CN', {maximumFractionDigits:2});
  const statusNames = {running:'本地任务正在执行',queued:'任务等待执行',awaiting_review:'核验完成，等待人工确认',needs_confirmation:'文字与表单有冲突，等待您选择',needs_input:'条件需要调整或补充',model_error:'本地模型调用失败',failed:'任务执行失败',invalidated:'资料或素材已变化，结果失效',confirmed:'已人工确认，可导出'};
  const claimNames = {supported:'来源支持',contradicted:'与来源矛盾',conflicting:'资料存在分歧',insufficient:'信息不足'};
  const terminal = new Set(['awaiting_review','needs_confirmation','needs_input','model_error','failed','invalidated','confirmed']);
  const samples = {
    external:'金山区人民政府公告写明，2026年8月8日13:30—14:00开展非遗现场教学，14:00—15:30开展手作体验，地点为金山区非遗保护中心。公告称剪纸作为金山区级非遗项目，又称刻纸，是一种镂空艺术；活动公开招募15人、免费、面向6—15岁亲子家庭。',
    confusion:'蔚县剪纸以阳刻为主，阴刻为辅。蔚县剪纸善于多色点染。工坊每天开放并且无需预约。',
    missing:'剪纸以阴刻为主，阳刻为辅。这次体验将介绍地方剪纸的工艺特色。',
    unsupported:'本次蔚县剪纸体验由当地大师亲授，参加一次就能完全掌握传统工艺。工坊每天开放并且无需预约。'
  };
  let mode = 'connecting', current = null, busy = false, dirty = false, replay = false;
  let selected = 'deep', health = null, catalog = null, eventSource = null, pollTimer = null;
  let activeCaseId = null;
  let watching = null, watchGeneration = 0, activeAction = false;
  let lastImpact = null;
  let previewAudience = 'visitor';
  let manuallySelected = false;
  const invalidatedRuns = new Set();
  const healthCheckedFor = new Set();
  const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = 'live.css'; document.head.append(style);
  document.body.classList.add('pending-runtime');
  q('.prototype').innerHTML = '<b>连接本地服务</b><span>·</span><span>正在检查真实运行环境，不播放预设结果</span>';
  q('#planStatus').innerHTML = '<strong>尚未连接真实业务服务</strong><small>请等待环境检查</small>';
  const originalActions = new Set(['caseSelect','draft','auditBtn','people','budget','minutes','capacity','reuse','conflictBtn','resetPlan','exportPlan']);
  // Capture prevents the original preset listeners from running in HTTP live mode.
  for (const name of ['click','input','change']) document.addEventListener(name, event => {
    if (mode === 'preset') return;
    const target = event.target.closest('button,input,select,textarea');
    if (!target || (!originalActions.has(target.id) && !target.hasAttribute('data-scheme'))) return;
    event.stopImmediatePropagation();
    if (name === 'click' && target.tagName === 'BUTTON') event.preventDefault();
    if (mode === 'live') handleOriginal(event, target);
  }, true);
  function notify(text) { if (typeof window.toast === 'function') window.toast(text); }
  function urlSafe(url) { try { const u = new URL(url); return ['http:','https:'].includes(u.protocol) ? u.href : '#'; } catch { return '#'; } }
  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {...options, signal:controller.signal, headers:{'Content-Type':'application/json', ...(options.headers || {})}});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data.error || ('HTTP ' + response.status)));
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('本地服务响应超时。未使用预设结果替代。');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  function errorMessage(error) { return error instanceof Error ? error.message : typeof error === 'object' ? JSON.stringify(error) : String(error); }
  function acceptRun(run) {
    // Invalidation is permanent for this run ID. Late network responses cannot undo it.
    if(run.status === 'invalidated')invalidatedRuns.add(run.id);
    if(invalidatedRuns.has(run.id)){run.status='invalidated';run.approval=null;}
    current=run;
  }
  function executionPending(run) { return run.execution_finished === false || !terminal.has(run.status); }
  function setBanner() {
    if (!q('#runtimeState')) return;
    const label = replay ? '历史回放' : current ? '真实本地运行' : '真实本地服务';
    const text = dirty?'输入已变化，等待重新执行':replay&&current?.status==='confirmed'?'已保存确认记录 · 仅回放':current ? statusNames[current.status] || current.status : health?.model_ready ? '模型已就绪，等待输入' : '模型未就绪，运行将如实记录失败';
    q('#runtimeState').textContent = label + ' · ' + text;
    q('#runtimeDetail').textContent = current ? `任务 ${current.id.slice(0,8)} · ${current.model_calls ?? 0} 次模型调用 · ${Number(current.elapsed_seconds || 0).toFixed(1)} 秒${dirty ? ' · 输入已改动，需重新执行' : ''}` : `${health?.model || '本地模型'} · 经营参数为演示测算`;
    q('#runtimeDetail').title = current ? '完整任务编号：'+current.id : '';
    q('#runtimeBar').dataset.tone = ['model_error','failed','invalidated'].includes(current?.status) ? 'error' : 'normal';
    const engine = health?.model_ready ? 'Qwen 本地引擎已就绪' : '本地模型尚未就绪';
    q('.prototype').innerHTML = `<b>${esc(label)}</b><span>·</span><span>${esc(engine)} · 经营数据为演示配置${replay ? ' · 当前显示已保存结果' : ''}</span>`;
  }
  function setupLive() {
    mode = 'live'; document.body.classList.remove('pending-runtime'); document.body.classList.add('live-runtime');
    q('.prototype').insertAdjacentHTML('afterend', `<div class="runtime-bar" id="runtimeBar"><div><strong id="runtimeState"></strong><details class="runtime-information"><summary>查看运行信息</summary><div class="runtime-detail" id="runtimeDetail"></div></details></div><div class="runtime-tools"><button class="text-link" id="presentationMode" aria-pressed="false">投屏大字</button><select id="historySelect" aria-label="查看真实历史记录"><option value="">历史记录 · 选择后仅回放</option></select><button class="text-link" id="refreshHealth">检查环境 ↗</button></div></div>`);
    q('#studio .page-header .chip').textContent = '真实输入 · 逐句关联证据';
    q('#studio .step-strip').innerHTML = '<span>01 理解地域</span>→<span>02 逐句查证</span>→<span>03 编排体验</span>→<span>04 人工确认</span>';
    q('#caseSelect').previousElementSibling.innerHTML = '加载一个展示输入 <span>仅填入文案，不生成结果</span>';
    q('#caseSelect').innerHTML = '<option value="external">公开活动案例 · 金山区剪纸小夜灯</option><option value="confusion">地域事实纠错 · 工艺主次混淆</option><option value="missing">地域待明确 · 检查适用范围</option><option value="unsupported">经营承诺 · 区分资料与运营</option>';
    q('#draft').readOnly = false; q('#draft').maxLength = 1800; q('#draft').value = samples.confusion;
    q('#draft').previousElementSibling.innerHTML = '待核验文案 <span>可现场修改，重新运行后生效</span>';
    q('#draft').previousElementSibling.insertAdjacentHTML('beforebegin', `<div class="form-pair"><label for="region">讲解地域<input id="region" value="河北省蔚县" maxlength="80"></label><label for="project">非遗项目<input id="project" value="剪纸" maxlength="50"></label></div>`);
    q('#draft').insertAdjacentHTML('beforebegin', `<section class="public-case-banner" id="publicCaseBanner"><div class="eyebrow">PUBLIC CASE · 公开活动案例</div><h3>金山区剪纸小夜灯 · 公告重建</h3><p>把一则政府活动公告转成可核验的体验方案。公告事实、团队演示配置和当前可预约状态分开标记。</p><div class="public-case-facts"><span>2026-08-08 · 13:30—15:30</span><span>现场教学30′ + 手作90′</span><span>公告招募15人 · 免费</span></div><label class="case-assumption"><input type="checkbox" id="caseAssumptionCheck" checked><span>确认采用团队演示配置继续重建（8人、1位教师、1间场地、演示报价）；这不代表历史活动可预约。</span></label><a class="case-source-link" href="https://www.shanghai.gov.cn/nw17239/20260806/ab8799763c384e7eb1b254cebf1e0cf5.html" target="_blank" rel="noopener noreferrer">查看金山区人民政府原始公告 ↗</a></section>`);
    q('#draft').insertAdjacentHTML('afterend', `<label class="field-label" for="requestNote" style="margin-top:18px">这场体验，您有什么想法？ <span>与表单冲突时请您决定</span></label><textarea id="requestNote" maxlength="1000">为初次了解剪纸的游客安排文化讲解与入门手作。讲述清楚工艺特色，留出观察和提问的时间。</textarea><div class="form-pair"><label for="preferredPlan">套餐偏好<select id="preferredPlan"><option value="deep">优先深体验</option><option value="light">优先轻体验</option></select></label><label for="startTime">开始时间<input id="startTime" type="time" value="09:30"></label></div>`);
    q('#auditBtn').innerHTML = '核验并编排体验 <span class="arrow">→</span>';
    q('#auditBtn').nextElementSibling.textContent = '模型负责理解和表达；程序核对预算、日程与资源。每条结论保留原文和出处，无法证实的内容不会被当作错误。';
    q('#auditBadge').textContent = '等待真实运行';
    q('#auditEmpty p').textContent = '填写文案与需求，运行后在这里逐句比较原文、建议表达和来源证据。';
    q('#auditResult').innerHTML = ''; q('#auditResult').hidden = true; q('#auditEmpty').hidden = false;
    q('#studio .trace').innerHTML = '<details class="execution-details"><summary><span>查看真实执行记录</span><small id="eventHint">尚无运行记录</small></summary><p class="small-note">以下为服务端实际事件，不展示模型内部思维，不模拟执行进度。</p><ol class="event-list" id="eventList"></ol></details>';
    q('#studio .work-grid').insertAdjacentHTML('beforebegin','<div class="runtime-warning" id="runWarning" role="alert" hidden></div>');
    q('.controls .switch-row').insertAdjacentHTML('beforebegin', `<div class="resource-grid"><label for="teachers">手作教师（人）<input id="teachers" type="number" min="0" max="8" value="1"></label><label for="rooms">可用场地（间）<input id="rooms" type="number" min="0" max="8" value="1"></label></div>`);
    q('#conflictBtn').textContent = '填入「超容量且资源不足」';
    q('#conflictBtn').insertAdjacentHTML('beforebegin','<div class="live-actions"><button class="text-link" id="budgetCase">填入「人均预算改为 ¥110」</button></div>');
    q('#conflictBtn').insertAdjacentHTML('afterend','<button class="button" id="runPlan">按当前条件重新编排 <span class="arrow">→</span></button>');
    q('.controls .assumption').textContent = '演示经营配置与文化资料分别存储。报价读取服务端；人数、教师、场地和容量不得由模型擅自增加。单组接待，不假设并行扩容。';
    q('.scheme-help').textContent = '运行后显示服务端计算的候选方案；选择可行方案并人工确认，才可导出。';
    q('#routeCards').insertAdjacentHTML('afterend','<div class="guide-cards" id="guideCards"></div>');
    q('#planner .banner').outerHTML = `<section class="approval-box"><div class="eyebrow">READY TO SHARE</div><h3>把一场体验，交到游客手中。</h3><p>先预览，再确认。游客版简洁易读，组织者版保留日程、账目与来源。演示数据不代表真实报价或经营许可。</p><div class="edition-grid"><article class="edition-card"><span class="edition-number">01</span><h4>游客版</h4><p>文化讲解 · 体验日程 · 参与须知</p><div><button class="text-link" id="previewVisitor" disabled>打开精美预览 ↗</button><button class="text-link" id="exportVisitor" disabled>下载 HTML ↓</button></div></article><article class="edition-card"><span class="edition-number">02</span><h4>组织者版</h4><p>完整账目 · 接待资源 · 核验与授权记录</p><div><button class="text-link" id="previewOrganizer" disabled>打开完整预览 ↗</button><button class="text-link" id="exportOrganizer" disabled>下载 HTML ↓</button></div></article></div><label class="approval-check"><input type="checkbox" id="approvalCheck"><span>我已核对本次讲解与选中方案，知悉演示经营数据及素材使用边界。</span></label><div class="export-actions"><button class="button" id="approveRun" disabled>确认当前方案 ✓</button></div><div class="approval-state" id="approvalState">完成真实运行后可预览；确认后才能下载。</div></section><section class="material-panel"><h3>文化使用边界 · 变化可追溯</h3><p>这个示例改变本项目原创视觉素材的可用状态，展示受影响关系。不是对传统文化或社区权利的授权声明。</p><div id="materialList"></div><div class="impact-trail" id="impactTrail">尚未发生素材使用状态变更。</div><button class="text-link" id="refreshRun" disabled>依据最新资料重新核验 ↗</button></section>`;
    q('#ledgerFormula').textContent = '报价均为演示测算；本地服务报酬为毛收入，不等于净利润。未包含交通、住宿和税费。';
    q('.ledger-foot').insertAdjacentHTML('beforebegin','<table class="ledger-table" id="ledgerTable"><thead><tr><th>项目</th><th>服务角色</th><th>金额</th></tr></thead><tbody></tbody></table>');
    q('#historySelect').addEventListener('change', async event => { if (event.target.value) await loadHistory(event.target.value); });
    q('#refreshHealth').addEventListener('click', refreshEnvironment);
    for (const id of ['region','project','requestNote','preferredPlan','startTime','teachers','rooms','caseAssumptionCheck']) q('#'+id).addEventListener('input', markDirty);
    q('#caseAssumptionCheck').addEventListener('change', markDirty);
    q('#budgetCase').addEventListener('click', () => { q('#budget').value = 110; markDirty(); notify('已填入人均 ¥110。点击重新编排，获得真实修订结果。'); });
    q('#runPlan').addEventListener('click', submit);
    q('#approvalCheck').addEventListener('change', updateActions);
    q('#approveRun').addEventListener('click', approve);
    q('#exportVisitor').addEventListener('click', () => exportBundle('visitor'));
    q('#exportOrganizer').addEventListener('click', () => exportBundle('organizer'));
    q('#previewVisitor').addEventListener('click', () => previewBundle('visitor'));
    q('#previewOrganizer').addEventListener('click', () => previewBundle('organizer'));
    q('#refreshRun').addEventListener('click', refreshRun);
    setupPresentation();
    clearPlan(); renderMaterials(); setBanner(); updateValues(); updateActions(); loadHistoryList();
    if(!health.model_ready)showWarning('业务服务已连接，但本地模型尚未就绪。请启动 Ollama 并准备模型。此时运行会保留真实失败记录，不会使用预设案例替代。');
  }
  function setupPresentation() {
    q('#presentationMode').addEventListener('click', () => {
      const enabled=document.body.classList.toggle('presentation-mode');
      q('#presentationMode').setAttribute('aria-pressed',String(enabled));
      q('#presentationMode').textContent=enabled?'退出投屏大字':'投屏大字';
    });
    q('#requestNote').insertAdjacentHTML('afterend','<div class="note-examples"><span>试着提出：</span><button class="text-link" id="familyNote">亲子互动，不安排茶歇 ↗</button></div>');
    q('#familyNote').addEventListener('click',()=>{q('#requestNote').value='安排亲子互动，不安排茶歇，手作至少40分钟；讲解浅显易懂，留一个观察任务。';markDirty();notify('只填入了文字需求。运行后若与表单不同，将由您确认。');});
    q('.controls .panel-body').insertAdjacentHTML('afterbegin',`<div class="control full"><label for="planningMode">编排方式</label><select id="planningMode" class="select"><option value="modules">按需求组合活动模块</option><option value="packages">经典轻 / 深体验套餐</option></select></div><div class="resource-grid experience-fields"><label for="audience">参与客群<select id="audience"><option value="general">普通游客</option><option value="family">亲子家庭</option></select></label><label for="teaPreference">茶歇安排<select id="teaPreference"><option value="any">灵活安排</option><option value="include">需要茶歇</option><option value="exclude">不含茶歇</option></select></label><label class="wide-field" for="minCraftMinutes">手作至少（分钟）<input id="minCraftMinutes" type="number" min="0" max="180" step="1" value="0"><small>0 表示不额外设定最低时长</small></label></div>`);
    for(const id of ['planningMode','audience','teaPreference','minCraftMinutes'])q('#'+id).addEventListener('input',()=>{syncPlanningMode();markDirty();});
    syncPlanningMode();
    q('#runWarning').insertAdjacentHTML('afterend','<section class="requirement-conflicts" id="requirementConflictStudio" hidden></section>');
    q('#planner .plan-grid').insertAdjacentHTML('beforebegin','<section class="requirement-conflicts" id="requirementConflictPlanner" hidden></section>');
    q('.scheme-choices').insertAdjacentHTML('beforebegin','<section class="plan-comparison" id="planComparison" hidden></section>');
    q('.scheme-choices').setAttribute('aria-label','比较已校验的体验候选');
    q('#planComparison').insertAdjacentHTML('beforebegin','<div class="effective-conditions" id="effectiveConditions" hidden></div>');
    q('#guideCards').insertAdjacentHTML('beforebegin','<section class="teaching-panel" id="teachingPanel" hidden></section>');
    const table=q('#ledgerTable'); const ledgerDetails=document.createElement('details'); ledgerDetails.className='ledger-details';ledgerDetails.innerHTML='<summary>查看每笔服务报酬与成本</summary>';table.before(ledgerDetails);ledgerDetails.append(table);
    const cost=q('#costDetails'); const calculation=document.createElement('details');calculation.className='calculation-details';calculation.innerHTML='<summary>计算口径与经营假设</summary>';cost.before(calculation);calculation.append(cost);
    document.body.insertAdjacentHTML('beforeend',`<dialog class="bundle-preview" id="bundlePreview"><div class="preview-toolbar"><div><span class="eyebrow">EXPERIENCE BOOKLET</span><h2 id="previewTitle">体验包预览</h2></div><div class="preview-switch"><button data-preview-audience="visitor">游客版</button><button data-preview-audience="organizer">组织者版</button></div><button class="preview-close" id="closePreview" aria-label="关闭预览">×</button></div><div class="preview-notice" id="previewNotice"></div><iframe id="previewFrame" title="体验包真实内容预览" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe><div class="preview-footer"><span id="previewFootnote"></span><button class="button" id="previewDownload" disabled>下载当前版本 ↓</button></div></dialog>`);
    q('#closePreview').addEventListener('click',closePreview);
    q('#bundlePreview').addEventListener('click',event=>{if(event.target===q('#bundlePreview'))closePreview();});
    q('#bundlePreview').addEventListener('close',()=>{q('#previewFrame').srcdoc='';});
    all('[data-preview-audience]').forEach(button=>button.addEventListener('click',()=>previewBundle(button.dataset.previewAudience)));
    q('#previewDownload').addEventListener('click',()=>exportBundle(previewAudience));
    document.addEventListener('click',event=>{
      const resolve=event.target.closest('[data-resolve-requirements]');if(resolve){resolveRequirements(resolve.dataset.resolveRequirements);return;}
      const source=event.target.closest('[data-reveal-claim]');if(source){window.page('studio');const row=document.getElementById('claim-'+source.dataset.revealClaim);if(row){const evidence=row.querySelector('details');if(evidence)evidence.open=true;row.scrollIntoView({block:'start',behavior:'smooth'});}}
    });
  }
  function syncPlanningMode(){q('#preferredPlan').closest('label').hidden=q('#planningMode').value!=='packages';}
  function setInputValue(id,value){
    const input=q('#'+id);
    if(input.type==='range'){
      input.min=Math.min(Number(input.min),Number(value));input.max=Math.max(Number(input.max),Number(value));input.step=id==='budget'?'0.01':'1';
      const ticks=input.parentElement.querySelector('.range-ticks');if(ticks){const prefix=id==='budget'?'¥':'';const suffix=['people','capacity'].includes(id)?' 人':id==='minutes'?' 分钟':'';ticks.children[0].textContent=prefix+input.min+suffix;ticks.children[1].textContent=prefix+input.max+suffix;}
    }
    input.value=value;
  }
  function closePreview(){if(q('#bundlePreview')?.open)q('#bundlePreview').close();}
  function renderRequirementConflicts(){
    const show=current?.status==='needs_confirmation'&&(current.requirement_conflicts||[]).length>0;
    for(const panel of all('.requirement-conflicts')){
      panel.hidden=!show;if(!show)continue;
      panel.innerHTML=`<div class="eyebrow">YOUR CHOICE MATTERS</div><h2>您写下的想法，与表单有一点不同。</h2><p>先确认采用哪组条件，再继续编排。系统不会替您改人数、预算或活动要求。</p><div class="conflict-rows">${current.requirement_conflicts.map(item=>`<div class="conflict-row"><strong>${esc(item.label||item.field)}</strong><span><small>表单条件</small>${esc(conflictValue(item.field,item.form_value))}</span><span><small>文字需求</small>${esc(conflictValue(item.field,item.note_value))}</span><p>${esc(item.reason)}</p></div>`).join('')}</div><div class="conflict-actions"><button class="button secondary" data-resolve-requirements="form" ${busy||activeAction||dirty?'disabled':''}>按表单条件继续</button><button class="button" data-resolve-requirements="note" ${busy||activeAction||dirty?'disabled':''}>采纳文字里的条件 →</button></div><small>${dirty?'输入已变化，请先重新分析需求。':'采纳文字时，只更新上方明确列出的条件；教师、场地与报价保持锁定。'}</small>`;
    }
  }
  function conflictValue(field,value){const labels={general:'普通游客',family:'亲子家庭',any:'灵活安排',include:'需要茶歇',exclude:'不含茶歇'};if(labels[value])return labels[value];return String(value)+(field==='budget_per_person'?' 元 / 人':['available_minutes','min_craft_minutes'].includes(field)?' 分钟':field==='people'?' 人':'');}
  async function resolveRequirements(resolution){
    if(busy||activeAction||dirty||current?.status!=='needs_confirmation')return;
    if(resolution==='form'){await submit('form');return;}
    const fields={people:['people',1,100],budget_per_person:['budget',0,10000],available_minutes:['minutes',1,720],min_craft_minutes:['minCraftMinutes',0,180],audience:['audience','general','family'],tea_preference:['teaPreference','any','include','exclude']};
    const updates=[];
    for(const conflict of current.requirement_conflicts||[]){const rule=fields[conflict.field];if(!rule){showWarning('有无法直接写入表单的冲突，请手动核对。');return;}let value=conflict.note_value;if(typeof rule[1]==='number'){value=Number(value);if(!Number.isFinite(value)||value<rule[1]||value>rule[2]||(conflict.field!=='budget_per_person'&&!Number.isInteger(value))){showWarning('文字中的数值超出允许范围，请手动修正后重新运行。');return;}}else if(!rule.slice(1).includes(value)){showWarning('文字条件不能直接映射到表单，请手动选择。');return;}updates.push([rule[0],value]);}
    updates.forEach(([id,value])=>setInputValue(id,value));updateValues();await submit('ask');
  }
  function handleOriginal(event, target) {
    if (event.type === 'click' && target.tagName === 'BUTTON') {
      if (target.id === 'auditBtn') submit();
      if (target.id === 'resetPlan') { for (const [id,value] of Object.entries({people:8,budget:160,minutes:150,capacity:12,teachers:1,rooms:1})) q('#'+id).value = value; q('#reuse').checked = true; q('#preferredPlan').value = 'deep'; markDirty(); }
      if (target.id === 'conflictBtn') { q('#people').value = 16; q('#capacity').value = 8; q('#teachers').value = 1; q('#rooms').value = 1; markDirty(); notify('已填入 16 人、单组 8 人、1 位教师与 1 间场地。重新运行后查看真实冲突。'); }
      if (target.dataset.scheme && current?.planning) { selected = target.dataset.scheme;manuallySelected=true;closePreview();q('#approvalCheck').checked = false; renderPlan(); updateActions(); }
    }
    if (event.type === 'change' && target.id === 'caseSelect') { applyCasePreset(target.value); markDirty(); }
    if (event.type === 'input') markDirty();
  }
  function applyCasePreset(value) {
    activeCaseId = value === 'external' ? 'jinshan-paper-light' : null;
    q('#draft').value = samples[value] || samples.confusion;
    if (value === 'external') {
      q('#region').value='上海市金山区'; q('#project').value='剪纸'; q('#people').value=8; q('#budget').value=220; q('#minutes').value=120; q('#capacity').value=8; q('#teachers').value=1; q('#rooms').value=1; q('#startTime').value='13:30'; q('#preferredPlan').value='deep'; q('#planningMode').value='modules'; q('#audience').value='family'; q('#teaPreference').value='exclude'; q('#minCraftMinutes').value=90; q('#requestNote').value='按公告重建一场8人亲子体验：保留现场教学30分钟和手作90分钟，不安排茶歇；如果人数改为6人仍保持流程。公告条件、团队演示资源和当前可预约状态请分开标记。'; q('#caseAssumptionCheck').checked=true;
    } else {
      q('#region').value = value === 'missing' ? '' : '河北省蔚县'; q('#project').value='剪纸'; q('#caseAssumptionCheck').checked=false;
    }
    syncPlanningMode(); updateValues();
    notify(value === 'external' ? '已载入公开活动案例。运行前请确认演示配置边界。' : '已载入展示输入。');
  }
  function updateValues() { for (const [id,suffix] of [['people',' 人'],['minutes',' 分钟'],['capacity',' 人']]) q('#'+id+'Value').textContent = q('#'+id).value + suffix; q('#budgetValue').textContent = '¥' + q('#budget').value; }
  function requestData(resolution='ask') {
    const data={case_id:activeCaseId,demo_assumptions_confirmed:activeCaseId==='jinshan-paper-light' && q('#caseAssumptionCheck').checked,text:q('#draft').value.trim(),requirements:{region:q('#region').value.trim(),project:q('#project').value.trim(),people:Number(q('#people').value),budget_per_person:Number(q('#budget').value),available_minutes:Number(q('#minutes').value),preferred_plan:q('#preferredPlan').value,start_time:q('#startTime').value,note:q('#requestNote').value.trim(),planning_mode:q('#planningMode').value,audience:q('#audience').value,tea_preference:q('#teaPreference').value,min_craft_minutes:Number(q('#minCraftMinutes').value),teaching_enabled:true},operating_overrides:{capacity:Number(q('#capacity').value),teachers:Number(q('#teachers').value),rooms:Number(q('#rooms').value),reuse:q('#reuse').checked},constraint_resolution:resolution};
    const previous=current?.plan?current.id:current?.previous_run_id;if(previous)data.previous_run_id=previous;
    return data;
  }
  function markDirty() { updateValues(); closePreview(); if (current || busy) { dirty = true; q('#approvalCheck').checked = false; showWarning('输入或经营条件已改变。当前结果属于上一次运行，需重新编排后再确认与导出。'); if(current) renderPlan(); } renderRequirementConflicts();updateActions(); setBanner(); }
  function showWarning(text) { q('#runWarning').hidden = !text; q('#runWarning').textContent = text || ''; }
  function clearPlan() {
    q('#planStatus').className = 'plan-status'; q('#planStatus').innerHTML = '<strong>等待真实编排</strong><small>不会预先填入模型结果</small>';
    q('#routeCards').innerHTML = '<div class="empty-plan">文化、时间与资源准备妥当后，日程将在这里展开。</div>';
    for (const id of ['totalCost','localRevenue','localShare','legendLocal','legendMaterial','legendOperations']) q('#'+id).textContent = '—';
    for (const id of ['barLocal','barMaterial','barOperations']) q('#'+id).style.width = '0%';
    q('#constraints').innerHTML = ''; q('#costDetails').textContent = ''; q('#ledgerTable tbody').innerHTML = ''; q('#guideCards').innerHTML = '';
    q('.scheme-choices').innerHTML='<div class="empty-plan">从真实接待资源中组合候选，运行后比较时间、费用与手作内容。</div>';
    if(q('#planComparison'))q('#planComparison').hidden=true;if(q('#teachingPanel'))q('#teachingPanel').hidden=true;if(q('#effectiveConditions'))q('#effectiveConditions').hidden=true;
  }
  async function submit(resolution='ask') {
    if (busy || activeAction) return;
    if(typeof resolution!=='string')resolution='ask';
    const body = requestData(resolution); if (!body.text) { showWarning('请先填写待核验文案。'); return; }
    busy = true; replay = false; dirty = false; current = null; lastImpact = null;manuallySelected=false;selected='';
    closePreview();renderRequirementConflicts();
    stopWatch(); showWarning(''); clearPlan(); q('#auditResult').innerHTML = ''; q('#auditResult').hidden = true; q('#auditEmpty').hidden = false;
    q('#auditEmpty p').textContent = '请求已发送。下方执行记录来自真实服务端事件，模型失败时会保留失败原因。'; q('#auditBadge').textContent = '等待模型结果';
    q('#eventList').innerHTML = ''; q('#approvalCheck').checked = false; q('#impactTrail').textContent = '尚未发生素材使用状态变更。'; updateActions();
    try { const result = await api('/api/runs',{method:'POST',body:JSON.stringify(body)}); current = {id:result.id,status:result.status || 'running',events:[],claims:[],model_calls:0}; setBanner(); await startWatch(result.id); }
    catch (error) { busy = false; current = null; showWarning('任务未成功提交：' + errorMessage(error)); q('#auditBadge').textContent = '服务故障'; updateActions(); setBanner(); }
  }
  function stopWatch() { watching = null; watchGeneration++; if (eventSource) eventSource.close(); eventSource = null; clearTimeout(pollTimer); }
  async function startWatch(id) {
    stopWatch(); watching = id; const generation = watchGeneration;
    if (typeof EventSource !== 'undefined') {
      eventSource = new EventSource(`/api/runs/${encodeURIComponent(id)}/events`);
      eventSource.addEventListener('progress', event => { if (watching !== id || generation !== watchGeneration) return; try { const item = JSON.parse(event.data); if (current?.id === id) { current.events = current.events || []; if (!current.events.some(e => e.seq === item.seq)) current.events.push(item); if(item.stage==='invalidated'){invalidatedRuns.add(id);current.status='invalidated';current.approval=null;q('#approvalCheck').checked=false;renderRun();}else renderEvents(); } } catch {} });
      eventSource.addEventListener('done', () => { if(watching === id && generation === watchGeneration) pull(); });
      eventSource.onerror = () => { /* HTTP polling below recovers actual stored events, never simulated events. */ };
    }
    let failures = 0;
    async function pull() {
      if (watching !== id || generation !== watchGeneration) return;
      clearTimeout(pollTimer);
      try {
        const run = await api('/api/runs/'+encodeURIComponent(id)); if(watching !== id || generation !== watchGeneration) return;
        failures = 0; acceptRun(run); busy = executionPending(current); renderRun();
        if (!busy) {
          if(!healthCheckedFor.has(id)){
            healthCheckedFor.add(id);
            try{const latestHealth=await api('/api/health');if(current?.id===id){health=latestHealth;setBanner();}}catch{ /* Keep the saved failure; never retry inference here. */ }
          }
          if(watching!==id||generation!==watchGeneration)return;
          stopWatch(); await loadHistoryList(); return;
        }
      } catch(error) {
        if(watching!==id||generation!==watchGeneration)return;
        failures++; showWarning('读取真实执行状态失败：' + errorMessage(error) + '。现有结果不代表新请求已完成。');
        if (failures >= 3) { stopWatch(); busy = false; updateActions(); return; }
      }
      if(watching === id) pollTimer = setTimeout(pull, 2000);
    }
    await pull();
  }
  function renderEvents() {
    const events = [...(current?.events || [])].sort((a,b) => a.seq - b.seq);
    q('#eventHint').textContent = replay ? '已保存的真实执行记录 · 历史回放' : `${events.length} 条真实事件`;
    q('#eventList').innerHTML = events.map(event => { const date = new Date(event.at); const time = Number.isNaN(date.valueOf()) ? String(event.at || '').slice(-8) : date.toLocaleTimeString('zh-CN',{hour12:false}); return `<li><time>${esc(time)}</time><span>${esc(event.message)}</span></li>`; }).join('');
    const stage = [...events].reverse().find(event => event.stage !== 'model_call')?.stage;
    const index = ['awaiting_review','confirmed'].includes(current?.status) ? 3 : ['model_error','failed','needs_input','needs_confirmation','invalidated'].includes(current?.status) ? -1 : ['cards_ready','planned','revision','chosen','validated','teaching_ready'].includes(stage) ? 2 : ['understood','retrieved','audited'].includes(stage) ? 1 : events.length ? 0 : -1;
    all('#studio .step-strip span').forEach((item,i) => item.classList.toggle('current',i === index));
  }
  function highlightRevision(original,revised){
    if(original===revised)return[esc(original),esc(revised)];
    const before=Array.from(original),after=Array.from(revised);let start=0,end=0;
    while(start<before.length&&start<after.length&&before[start]===after[start])start++;
    while(end<before.length-start&&end<after.length-start&&before[before.length-1-end]===after[after.length-1-end])end++;
    const render=(letters,className)=>esc(letters.slice(0,start).join(''))+'<mark class="'+className+'">'+esc(letters.slice(start,letters.length-end).join(''))+'</mark>'+esc(end?letters.slice(-end).join(''):'');
    return[render(before,'diff-removed'),render(after,'diff-added')];
  }
  function renderClaims() {
    const claims = current?.claims || [];
    const audited = claim => Array.isArray(claim.evidence_ids);
    const evidenceFor = claim => {
      if(!audited(claim))return claim.evidence || [];
      const cited = new Set([...(claim.evidence_ids || []),...(claim.corrected_evidence_ids || [])]);
      return (claim.evidence || []).filter(item => cited.has(item.id || item.source_id));
    };
    const completed = claims.filter(audited).length;
    q('#auditBadge').textContent = claims.length ? `${completed} / ${claims.length} 项已判定` : statusNames[current?.status] || '等待真实运行';
    q('#auditEmpty').hidden = claims.length > 0; q('#auditResult').hidden = !claims.length;
    if (!claims.length) { if (current?.error) q('#auditEmpty p').textContent = errorMessage(current.error); return; }
    const sourceCount = new Set(claims.filter(audited).flatMap(c => evidenceFor(c).map(e => e.id || e.source_id))).size;
    const insufficient = claims.filter(c => audited(c) && c.status === 'insufficient').length;
    q('#auditResult').innerHTML = `<div class="result-summary"><strong>${claims.length} 项陈述 · ${sourceCount} 条定位证据</strong><span>${insufficient ? `${insufficient} 项信息不足 · ` : ''}${completed < claims.length ? `${claims.length-completed} 项尚待判定 · ` : ''}每个修改，都能回到出处。</span></div>` + claims.map((claim,index) => {
      const checked = audited(claim);
      const kindLabel = {cultural_fact:'文化事实',public_activity_fact:'公开活动事实 · 历史条件',operating_promise:'经营承诺 · 待另核',user_requirement:'用户需求 · 核对条件'}[claim.kind] || '文化事实';
      const label = checked ? claimNames[claim.status] || claim.status : '等待逐句判定';
      const revised = !checked ? '尚未形成核验结论，暂不改写。' : claim.kind==='operating_promise' ? '经营承诺另行核实；未落实的授课、营业或预约安排，不进入游客版。' : claim.kind==='user_requirement' ? '作为活动需求核对；与表单一致或经您确认后参与编排，不作为文化事实讲述。' : ['insufficient','conflicting'].includes(claim.status) ? '保留原文待核，不进入游客讲解；补充资料或核清分歧后再处理。' : claim.suggested_text || (claim.status === 'supported' ? claim.text : '暂未形成有来源的修订，请人工核对。');
      const correction = claim.corrected_status === 'supported' ? ' 修订表达已再次获得来源支持。' : claim.corrected_status ? ' 修订表达尚未获得充分支持，不进入游客讲解。' : '';
      const evidenceHtml = evidenceFor(claim).map((evidence,evidenceIndex) => `<details class="evidence-block" ${checked&&claim.status==='contradicted'&&evidenceIndex===0?'open':''}><summary>${checked ? '' : '检索候选 · '}${esc(evidence.title || evidence.source_id)} <span>${esc(evidence.region || '地域待核对')}</span></summary><blockquote>${esc(evidence.quote)}</blockquote><div class="evidence-meta"><b>原文位置</b><p>${esc(evidence.locator || '来源记录内定位')}</p><a href="${esc(urlSafe(evidence.url))}" target="_blank" rel="noopener noreferrer">到原始资料核对 ↗</a><details class="source-provenance"><summary>引用时间与使用说明</summary><p>记录编号：${esc(evidence.id || evidence.source_id)}<br>采集时间：${esc(evidence.accessed_at || '见来源清单')}<br>${esc(evidence.use_note || '按来源使用边界引用')}</p></details></div></details>`).join('');
      const changed=checked&&claim.status==='contradicted'&&!!claim.suggested_text;
      const [originalHtml,revisedHtml]=changed?highlightRevision(claim.text,revised):[esc(claim.text),esc(revised)];
      const evidenceNote=claim.kind==='operating_promise'?'文化资料不能证明本次接待承诺，需另核经营安排与授权。':claim.kind==='user_requirement'?'用户需求不是待证明的文化事实，实际条件以本次确认与程序校验为准。':'当前没有被引用的定位证据。未检索到不等于事实错误。';
      return `<article class="claim-item ${changed?'has-correction':''}" id="claim-${esc(claim.id)}"><div class="claim-head"><span class="claim-number">${esc(kindLabel)} · ${String(index+1).padStart(2,'0')}</span><span class="claim-status ${esc(checked ? claim.status : 'insufficient')}">${esc(label)}</span></div><div class="claim-comparison"><div class="claim-version before"><label>原文</label><p>${originalHtml}</p></div><div class="claim-version after"><label>${changed?'有据修订':claim.status==='supported'&&checked?'核对后保留':'处理建议'}</label><p>${revisedHtml}</p></div></div><p class="claim-reason">${esc(claim.reason || '陈述已保存，尚未完成证据判定。')}${esc(correction)}</p>${evidenceHtml || `<div class="evidence-empty">${esc(evidenceNote)}</div>`}</article>`;
    }).join('');
  }
  function candidates() { return current?.planning?.candidates || []; }
  function chosen() { return candidates().find(plan => plan.id === selected) || null; }
  function constraintRefusal() { return current?.status==='needs_input'&&!!current?.blocking_conflicts?.length&&!candidates().some(plan=>plan.feasible); }
  function teachingReady() { return !(current?.requirements?.teaching_enabled || current?.requirements?.planning_mode==='modules') || current?.teaching?.check?.passed===true; }
  function previewReady() { return !!current&&!dirty&&!busy&&!activeAction&&['awaiting_review','confirmed'].includes(current.status)&&!!chosen()?.feasible&&teachingReady(); }
  function downloadReady() { return previewReady()&&!replay&&current.status==='confirmed'&&current.approval?.plan_id===selected; }
  function renderComparison() {
    const comparison=current?.comparison,panel=q('#planComparison');panel.hidden=!comparison?.before||!comparison?.after;if(panel.hidden)return;
    const craftChange=Number.isFinite(comparison.before.craft_minutes)&&Number.isFinite(comparison.after.craft_minutes)?`<div class="comparison-focus"><span>手作时间</span><strong><b data-craft-before>${esc(comparison.before.craft_minutes)}</b><i>→</i><b data-craft-after>${esc(comparison.after.craft_minutes)}</b><small>分钟</small></strong><p>总时长与手作时长分别复算，金额与必要教学时间来自经营配置。</p></div>`:'';
    panel.innerHTML=`<div class="eyebrow">WHAT CHANGED</div><h3>改一句话，方案真变化。</h3>${craftChange}<div class="comparison-versions"><div><small>上一次方案</small><strong>${esc(comparison.before.title)}</strong><span>${money(comparison.before.total_cents)} · 全程 ${esc(comparison.before.duration_minutes)} 分钟</span></div><span class="comparison-arrow">→</span><div><small>${current.approval?'本次已确认方案':'本次程序推荐'}</small><strong>${esc(comparison.after.title)}</strong><span>${money(comparison.after.total_cents)} · 全程 ${esc(comparison.after.duration_minutes)} 分钟</span></div></div><ul>${(comparison.changes||[]).map(change=>`<li>${esc(change)}</li>`).join('')}</ul><small>${dirty||current.status==='invalidated'?'输入或关联资料已变化，以下保留上次比较记录；重新执行后再确认。':'此比较对应本次程序推荐或已确认的方案；切换其他候选后，确认时会重新记录比较。'}</small>`;
  }
  function renderTeaching() {
    const teaching=current?.teaching,panel=q('#teachingPanel');panel.hidden=!teaching;if(!teaching)return;
    const refs=item=>(item.claim_ids||[]).map((id,i)=>`<button class="text-link" data-reveal-claim="${esc(id)}">依据 ${i+1} ↗</button>`).join('');
    panel.innerHTML=`<div class="teaching-heading"><div><div class="eyebrow">CULTURE, MADE APPROACHABLE</div><h3>${teaching.audience==='family'?'让孩子看见剪纸里的巧思。':'让一段讲解，有据，也有趣。'}</h3></div><span class="claim-status ${teaching.check?.passed?'supported':'insufficient'}">${teaching.check?.passed?'讲解引用已校验':'教学内容待核对'}</span></div><div class="teaching-script">${(teaching.short_script||[]).map((item,i)=>`<article><span>${String(i+1).padStart(2,'0')}</span><div><p>${esc(item.text)}</p><div class="teaching-refs">${refs(item)}</div></div></article>`).join('')}</div><div class="teaching-tasks">${[['观察任务',teaching.observation_task],['互动提问',teaching.interaction_question]].filter(([,item])=>item).map(([label,item])=>`<article><span>${label}</span><p>${esc(item.text)}</p>${refs(item)}</article>`).join('')}</div><p class="teaching-label">${esc(teaching.creative_label||'观察任务与互动提问属于教学创意，不作为新增文化事实。')}</p>`;
    if(dirty||current.status==='invalidated'){
      const previous=panel.innerHTML.replace('讲解引用已校验','上次运行的核验记录');
      panel.innerHTML=`<div class="teaching-expired"><strong>${current.status==='invalidated'?'旧版教学包已失效':'输入已变化，教学包等待重编'}</strong><p>以下仅为历史内容，不能用于当前讲解、预览或导出。重新核验后将按最新资料与素材使用边界生成。</p></div><details class="guide-details"><summary>仅查看上一次教学内容</summary>${previous}</details>`;
    }
  }
  function renderPlan() {
    if (!candidates().length) { clearPlan(); if(['needs_input','needs_confirmation'].includes(current?.status)) {q('#planStatus').className='plan-status error';q('#planStatus').innerHTML=`<strong>${current.status==='needs_confirmation'?'先确认您的真实需求':'需要补充条件'}</strong><small>未生成可执行方案</small>`;} if(['model_error','failed'].includes(current?.status)){q('#planStatus').className='plan-status error';q('#planStatus').innerHTML='<strong>本次运行失败，未生成方案</strong><small>'+esc(errorMessage(current.error||'请检查本地模型服务后重新运行'))+'</small>';} return; }
    if (!candidates().some(plan => plan.id === selected)) selected = current.plan?.id || candidates()[0].id;
    q('.scheme-choices').innerHTML=candidates().map((plan,index)=>`<button class="scheme-option ${selected===plan.id?'active':''}" data-scheme="${esc(plan.id)}" aria-pressed="${selected===plan.id}" ${busy||activeAction?'disabled':''}><div class="candidate-topline"><span class="scheme-state ${plan.feasible?'':'bad'}">${plan.feasible?'条件可行':'存在约束冲突'}</span><small>${current.approval?.plan_id===plan.id?'已确认':current.plan?.id===plan.id?'程序推荐':'候选 '+String(index+1).padStart(2,'0')}</small></div><strong>${esc(plan.title)} · ${plan.duration_minutes} 分钟</strong><span class="scheme-price">人均 ${money(plan.per_person_cents)} <small> / 总额 ${money(plan.total_cents)}</small></span><span class="module-tags">${(plan.schedule||[]).map(item=>`<span>${esc(item.title)}</span>`).join('')}</span><small class="scheme-income">${typeof plan.craft_minutes==='number'?'手作 '+plan.craft_minutes+' 分钟 · ':''}本地服务毛收入 ${money(plan.local_service_cents)}</small>${!plan.feasible?`<span class="candidate-conflict">${esc((plan.conflicts||[]).map(item=>item.message).join('；'))}</span>`:''}</button>`).join('');
    renderComparison();renderTeaching();
    const effective=current.effective_requirements||current.requirements||{};
    q('#effectiveConditions').hidden=false;q('#effectiveConditions').innerHTML=`<span>本次采用</span><b>${effective.audience==='family'?'亲子家庭':'普通游客'}</b><b>${esc(conflictValue('tea_preference',effective.tea_preference||'any'))}</b>${effective.min_craft_minutes?`<b>手作至少 ${esc(effective.min_craft_minutes)} 分钟</b>`:''}${effective.constraints?.maximize_craft?'<b>尽量多留手作时间</b>':''}<b>全程最多 ${esc(effective.available_minutes)} 分钟</b><small>手作最低时长与全程上限分别校验</small>`;
    const plan = chosen(); if(!plan) return;
    q('.scheme-help').textContent = current.choice_explanation ? '排序依据：'+current.choice_explanation+' 您仍可比较并选择其他已校验候选。' : '运行后显示服务端计算的候选方案；选择可行方案并人工确认，才可导出。';
    const outdated = dirty || current.status === 'invalidated';
    const refused=constraintRefusal();
    const incomplete = ['model_error','failed','needs_input'].includes(current.status);
    const statusLabel = outdated ? '结果已过期，需重新执行' : refused ? '条件已核算，当前无法接待' : current.status==='needs_input' ? '内容或条件仍需核对，暂不交付' : incomplete ? '本次运行失败，候选不可交付' : busy ? '候选已计算，等待最终校验' : plan.feasible ? '✓ 程序校验可行' : '! 当前条件不可行';
    const statusDetail = outdated ? '此处保留上次结果供比较，禁止确认与导出' : incomplete ? errorMessage(current.error || '需补充信息后重新执行') : (plan.conflicts || []).map(c => c.message).join('；') || '日程、预算、容量与资源已校验 · 演示配置';
    q('#planStatus').className = 'plan-status'+(!plan.feasible || outdated || incomplete ? ' error' : '')+(refused?' constraint-refusal':'');
    q('#planStatus').innerHTML = refused&&!outdated?`<strong>${esc(statusLabel)}</strong><ul>${current.blocking_conflicts.map(item=>`<li>${esc(item.message)}</li>`).join('')}</ul><small>请落实所缺资源或明确调整条件后重新编排。以下仅为冲突候选，不能确认或导出。</small>`:`<strong>${esc(statusLabel)} · ${esc(plan.title)}</strong><small>${esc(statusDetail)}</small>`;
    const resourceLabel = id => id.replace(/^room-(\d+)$/, '演示场地 $1').replace(/^teacher-(\d+)$/, '手作教师 $1');
    q('#routeCards').innerHTML = (plan.schedule || []).map((item,index) => `<article class="route-card"><div class="step">0${index+1}</div><div class="time">${esc(item.start)}</div><h3>${esc(item.title)}</h3><p>${esc(item.description || item.description_text || '使用本次核验后的讲解与活动内容。')}</p><small>${esc(item.start)}—${esc(item.end)} · ${item.minutes} 分钟<br>资源：${esc((item.resource_ids || []).map(resourceLabel).join('、') || '未指定')}</small></article>`).join('');
    q('#guideCards').innerHTML = `<details class="guide-details" ${current.teaching?'':'open'}><summary>查看已核验的讲解卡与素材关联</summary>${(current.cards || []).map(card => `<article class="guide-card${card.usable ? '' : ' unusable'}"><h4>${esc(card.title)}${card.usable ? '' : ' · 待补证 / 不用于游客版'}</h4><p>${esc(card.text)}</p><details><summary>关联记录</summary><small>讲解卡 ${esc(card.id)} · 关联陈述 ${esc((card.claim_ids || []).join('、'))}<br>来源 ${esc((card.source_ids || []).join('、') || '当前无来源支持')} · 素材 ${esc((card.material_ids || []).join('、') || '不使用视觉素材')}</small></details></article>`).join('')}</details>`;
    const total = plan.total_cents || 1; const share = plan.local_service_cents / total * 100;
    q('#totalCost').textContent = money(plan.total_cents); q('#localRevenue').textContent = money(plan.local_service_cents); q('#localShare').innerHTML = `${share.toFixed(1)}<em>%</em>`;
    q('#barLocal').style.width=share+'%'; q('#barMaterial').style.width=plan.material_cents/total*100+'%'; q('#barOperations').style.width=plan.operations_cents/total*100+'%';
    q('#legendLocal').textContent='本地服务 '+money(plan.local_service_cents);q('#legendMaterial').textContent='材料与耗材 '+money(plan.material_cents);q('#legendOperations').textContent='组织成本 '+money(plan.operations_cents);
    q('#ledgerTable tbody').innerHTML=(plan.ledger || []).map(item=>`<tr><td>${esc(item.label)}</td><td>${esc(item.payee || '演示角色')}</td><td>${money(item.cents)}</td></tr>`).join('');
    q('#constraints').innerHTML = (plan.conflicts || []).length ? plan.conflicts.map(item=>`<span class="bad">! ${esc(item.message)}</span>`).join('') : '<span>✓ 预算边界</span><span>✓ 总时长</span><span>✓ 接待容量与资源</span><span>✓ 使用边界</span>';
    q('#costDetails').textContent = `演示账目：本地服务 ${money(plan.local_service_cents)} ＋ 材料 ${money(plan.material_cents)} ＋ 组织成本 ${money(plan.operations_cents)} ＝ ${money(plan.total_cents)}。纸材 ${plan.paper_units} 份，为演示用量，不是实测环保成果。单场地顺序接待，不包含跨地点交通。`;
  }
  function renderRun() {
    if (!current) return;
    if(!manuallySelected&&current.plan?.id)selected=current.plan.id;
    if (current.plan?.id && !busy && !candidates().some(plan=>plan.id===selected && plan.feasible)) selected=current.plan.id;
    if (current.status === 'invalidated')closePreview();
    if (current.status==='needs_confirmation')showWarning('需求分析已完成，等待您明确采用哪组条件。');
    else if (current.status==='needs_input')showWarning((constraintRefusal()?'接待校验结论：':'待核对事项：')+errorMessage(current.error));
    else if (current.error) showWarning('真实运行未完成：'+errorMessage(current.error));
    else if(current.status==='invalidated') showWarning('关联资料或素材使用状态已变化。此结果已失效，重新核验后才可确认与导出。');
    else if(!dirty) showWarning('');
    renderEvents();renderClaims();renderPlan();renderRequirementConflicts();renderImpact();setBanner();updateActions();
  }
  function updateActions() {
    if(mode!=='live')return;
    q('#auditBtn').disabled=busy||activeAction;q('#runPlan').disabled=busy||activeAction;
    q('#auditBtn').innerHTML=busy?'正在执行本地任务…':'核验并编排体验 <span class="arrow">→</span>';
    q('#runPlan').textContent=busy?'正在执行本地任务…':'按当前条件重新编排 →';
    const previewable=previewReady(),valid=previewable&&!replay,confirmed=downloadReady();
    q('#approveRun').disabled=!valid||!q('#approvalCheck').checked||confirmed;
    q('#exportVisitor').disabled=!confirmed;q('#exportOrganizer').disabled=!confirmed;
    q('#previewVisitor').disabled=!previewable;q('#previewOrganizer').disabled=!previewable;q('#previewDownload').disabled=!confirmed;
    all('[data-preview-audience]').forEach(button=>button.disabled=activeAction||busy);
    all('[data-resolve-requirements]').forEach(button=>button.disabled=activeAction||busy||dirty);
    q('#refreshRun').disabled=!current||busy||activeAction;
    q('#approvalState').textContent=replay?'当前为历史回放，可查看仍有效的体验包；依据最新资料重新核验后再确认和下载。':dirty?'条件已改变，旧结果不能确认或导出。':confirmed?'当前方案已确认；下载时仍会检查来源和素材状态。':current?.status==='invalidated'?'关联状态变化，本次确认已失效。':current?.status==='needs_confirmation'?'请先选择采用表单还是文字里的条件。':current?.status==='needs_input'?'请先补充信息或调整冲突条件。':!teachingReady()?'教学内容尚未通过引用校验，不能确认或交付。':valid?'先打开双版预览，核对后勾选并确认当前方案。':'完成真实核验与编排后可人工确认。';
    q('#historySelect').disabled=busy||activeAction;
    all('[data-scheme]').forEach(button=>button.disabled=busy||activeAction);
    all('[data-material-id]').forEach(button=>button.disabled=busy||activeAction);
  }
  async function previewBundle(audience) {
    if(!previewReady()||!['visitor','organizer'].includes(audience))return;
    const id=current.id,planId=selected;previewAudience=audience;activeAction=true;updateActions();
    const dialog=q('#bundlePreview'),controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),20000);
    q('#previewTitle').textContent=audience==='visitor'?'游客版 · 这一程，纸上相逢':'组织者版 · 让每个环节有据可依';
    q('#previewNotice').textContent='正在读取服务端校验后的真实体验包…';q('#previewFrame').srcdoc='';
    q('#previewFootnote').textContent='预览不会自动确认或下载。';
    all('[data-preview-audience]').forEach(button=>button.classList.toggle('active',button.dataset.previewAudience===audience));
    if(!dialog.open)dialog.showModal();
    try{
      const response=await fetch(`/api/runs/${encodeURIComponent(id)}/export?preview=true&audience=${audience}&plan_id=${encodeURIComponent(planId)}`,{signal:controller.signal});
      if(!response.ok){const detail=await response.json().catch(()=>({}));throw new Error(detail.detail||'体验包预览未通过校验');}
      const html=await response.text();if(current?.id!==id||selected!==planId||dirty||current.status==='invalidated'||!dialog.open)return;
      q('#previewFrame').srcdoc=html;
      const confirmed=current.status==='confirmed'&&current.approval?.plan_id===planId;
      q('#previewNotice').textContent=(replay?'历史回放 · ':'')+(confirmed?'当前方案已有确认记录；此窗口为审阅预览':'草稿预览 · 尚未人工确认')+' · '+chosen().title+' · '+money(chosen().total_cents)+' / '+chosen().duration_minutes+' 分钟';
      q('#previewFootnote').textContent=replay?'当前为历史回放，重新核验后才能确认和下载。':confirmed?'此窗口统一展示审阅预览稿；下载将取得已有确认记录的正式版本。':'请核对内容；关闭预览后勾选并人工确认，才可下载。';
    }catch(error){q('#previewNotice').textContent='预览未完成：'+(error.name==='AbortError'?'本地服务响应超时。':errorMessage(error));showWarning(q('#previewNotice').textContent);try{acceptRun(await api('/api/runs/'+encodeURIComponent(id)));renderRun();}catch{}}
    finally{clearTimeout(timeout);activeAction=false;updateActions();}
  }
  async function approve() {
    if(q('#approveRun').disabled)return;activeAction=true;updateActions();
    try { const result=await api(`/api/runs/${encodeURIComponent(current.id)}/approve`,{method:'POST',body:JSON.stringify({plan_id:selected,confirmed:true})}); acceptRun(result.id?result:await api('/api/runs/'+encodeURIComponent(current.id))); renderRun();notify('已保存人工确认。可导出游客版与组织者版体验包。'); }
    catch(error){q('#approvalCheck').checked=false;try{acceptRun(await api('/api/runs/'+encodeURIComponent(current.id)));renderRun();}catch{}showWarning('确认未完成：'+errorMessage(error));}finally{activeAction=false;updateActions();}
  }
  async function exportBundle(audience) {
    if(!downloadReady())return;
    const id=current.id;activeAction=true;updateActions();
    try { const response=await fetch(`/api/runs/${encodeURIComponent(id)}/export?audience=${audience}`);if(!response.ok){const detail=await response.json().catch(()=>({}));throw new Error(detail.detail||'导出校验失败');} const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`xiangyi-youju-${audience}-${id.slice(0,8)}.html`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify(audience==='visitor'?'游客版体验包已生成。':'组织者版体验包已生成，保留依据、账目与核验记录。'); }
    catch(error){showWarning('导出未完成：'+errorMessage(error));try{acceptRun(await api('/api/runs/'+encodeURIComponent(id)));renderRun();}catch{}}finally{activeAction=false;updateActions();}
  }
  async function loadHistoryList(){try{const list=await api('/api/runs');q('#historySelect').innerHTML='<option value="">历史记录 · 选择后仅回放</option>'+(list.runs||[]).slice(0,30).map(run=>`<option value="${esc(run.id)}">${esc(statusNames[run.status]||run.status)} · ${esc((run.text||'').slice(0,18))}</option>`).join('');}catch{ /* History availability does not fabricate a result or block current input. */ }}
  function restoreInputs(run) {
    activeCaseId=run.case_id||null; q('#caseSelect').value=activeCaseId?'external':'confusion'; q('#caseAssumptionCheck').checked=!!run.demo_assumptions_confirmed; q('#draft').value=run.text||'';const req=run.requirements||{};
    for(const [id,key] of Object.entries({region:'region',project:'project',people:'people',budget:'budget_per_person',minutes:'available_minutes',requestNote:'note',startTime:'start_time',preferredPlan:'preferred_plan'}))if(req[key]!==undefined)setInputValue(id,req[key]);
    for(const [id,value] of Object.entries({planningMode:req.planning_mode||'packages',audience:req.audience||'general',teaPreference:req.tea_preference||'any',minCraftMinutes:req.min_craft_minutes||0}))setInputValue(id,value);
    syncPlanningMode();
    const profile={...(run.profile||{}),...(run.operating_overrides||{})};
    for(const id of ['capacity','teachers','rooms'])if(typeof profile[id]==='number')setInputValue(id,profile[id]);
    if(typeof profile.reuse==='boolean')q('#reuse').checked=profile.reuse;updateValues();
  }
  async function loadHistory(id) {
    if(busy)return;activeAction=true;updateActions();
    try {closePreview();stopWatch();acceptRun(await api('/api/runs/'+encodeURIComponent(id)));replay=true;dirty=false;lastImpact=null;restoreInputs(current);selected=current.plan?.id||current.requirements?.preferred_plan||'deep';q('#approvalCheck').checked=false;renderRun();window.page('studio');}
    catch(error){showWarning('读取历史记录失败：'+errorMessage(error));}finally{activeAction=false;updateActions();}
  }
  function renderMaterials() {
    const materials=catalog?.materials||[];
    q('#materialList').innerHTML=materials.map(material=>`<div class="material-action"><div class="material-name">${esc(material.title||material.id)}<small>${material.usage_status==='available'?'当前可用':'当前不可用'} · 版本 ${esc(material.version||1)}</small></div><button data-material-id="${esc(material.id)}" data-state="${material.usage_status==='available'?'withdrawn':'available'}">${material.usage_status==='available'?'撤回使用':'恢复可用'}</button></div>`).join('')||'<p class="small-note">尚无素材目录。</p>';
    all('[data-material-id]').forEach(button=>button.addEventListener('click',()=>changeMaterial(button.dataset.materialId,button.dataset.state)));
  }
  function renderImpact() {
    const raw=current?.affected?.length ? current.affected : lastImpact;
    const affected=Array.isArray(raw)?raw:(raw?.affected_runs || (raw ? [raw] : []));
    if(!affected.length){if(lastImpact)q('#impactTrail').textContent='使用状态已更新；服务端未找到需要失效的已保存内容。';return;}
    q('#impactTrail').innerHTML='<strong>已定位受影响的关联内容</strong>'+affected.map(item=>`<p>来源 / 素材：<code>${esc(item.record_id||item.source_id||item.material_id||lastImpact?.record?.id||'使用状态变更')}</code><br>陈述：${esc((item.claim_ids||[]).join('、')||(item.kind==='materials'?'文本事实不受此素材变更影响':'当前尚未关联具体陈述'))}<br>讲解卡：${esc((item.card_ids||[]).join('、')||'见关联记录')} → 体验方案：${esc((item.plan_ids||[]).join('、')||'关联方案需重验')}<br>运行记录：<code>${esc(item.id||item.run_id||current?.id)}</code></p>`).join('');
  }
  async function changeMaterial(id,state) {
    if(activeAction||busy)return;closePreview();activeAction=true;updateActions();
    try {const result=await api('/api/materials/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({usage_status:state})});lastImpact=result;catalog=await api('/api/catalog');renderMaterials();if(current)acceptRun(await api('/api/runs/'+encodeURIComponent(current.id)));q('#approvalCheck').checked=false;renderRun();renderImpact();notify('素材使用状态已更新；关联结果由服务端重新标记。');}
    catch(error){showWarning('素材状态未更新：'+errorMessage(error));}finally{activeAction=false;updateActions();}
  }
  async function refreshRun() {
    if(!current||busy||activeAction)return;
    closePreview();
    if(dirty){await submit();return;}
    activeAction=true;updateActions();
    try {const result=await api(`/api/runs/${encodeURIComponent(current.id)}/refresh`,{method:'POST',body:'{}'});current={id:result.id,status:result.status||'running',events:[],claims:[]};replay=false;dirty=false;busy=true;manuallySelected=false;selected='';q('#approvalCheck').checked=false;clearPlan();await startWatch(result.id);}
    catch(error){showWarning('重新核验未启动：'+errorMessage(error));}finally{activeAction=false;updateActions();}
  }
  async function refreshEnvironment(){try{health=await api('/api/health');setBanner();notify(health.model_ready?'本地模型已就绪。':'服务可达，但模型尚未就绪。可运行以记录真实失败。');}catch(error){showWarning('本地服务无法连接：'+errorMessage(error));}}
  async function initialize() {
    try {health=await api('/api/health');if(health.mode!=='live')throw new Error('该地址未提供真实业务 API');catalog=await api('/api/catalog');setupLive();}
    catch(error){mode='unavailable';q('.prototype').innerHTML='<b>本地服务未连接</b><span>·</span><span>不能进行真实核验</span>';q('#planStatus').innerHTML='<strong>真实业务服务不可用</strong><small>请按 README 启动服务</small>';q('#auditEmpty p').textContent='当前没有可连接的业务 API。页面不会把预设案例当作真实运行结果。';q('#auditBtn').disabled=true;q('#exportPlan').disabled=true;q('.prototype').insertAdjacentHTML('afterend',`<div class="runtime-bar"><div><strong>请先启动本地服务</strong><div class="runtime-detail">${esc(errorMessage(error))}</div></div><button class="text-link" id="choosePreset">明确进入预设案例模式 ↗</button></div>`);q('#choosePreset').addEventListener('click',()=>{mode='preset';document.body.classList.remove('pending-runtime');q('#auditBtn').disabled=false;q('#exportPlan').disabled=false;q('.runtime-bar').remove();q('.prototype').innerHTML='<b>预设案例模式</b><span>·</span><span>无模型调用 · 仅查看原型设计与本地演示测算</span>';window.resetAudit();window.calculate();});}
  }
  initialize();
})();
