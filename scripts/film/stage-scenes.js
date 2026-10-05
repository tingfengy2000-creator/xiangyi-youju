'use strict';
/* 《一刀之差》镜 5–21。真实界面镜头只对静帧/录屏做推拉、裁切、虚化周边和加框，不改动画面上的任何文字与数字。 */

/* ---------- 通用：纸面背景、静帧、录屏 ---------- */
function paperBg(root, tex = TEX.rice, extra = '') {
  const bg = h('div', { class: 'layer' }, root);
  bg.style.cssText = `background:url(${tex}) center/cover;${extra}`;
  return bg;
}

/* 以“源图像素”为坐标的镜头：cam = [cx, cy, k]，k = 屏幕像素 / 源图像素 */
function viewport(root) {
  const wrap = h('div', { class: 'abs' }, root);
  wrap.style.cssText = 'left:0;top:0;transform-origin:0 0;';
  return {
    wrap,
    set(cam) {
      const [cx, cy, k] = cam;
      wrap.style.transform = `translate(${(960 - cx * k).toFixed(2)}px,${(540 - cy * k).toFixed(2)}px) scale(${k.toFixed(5)})`;
    },
  };
}
function stillImg(parent, file, w, hgt, x = 0, y = 0, shadow = true) {
  const img = h('img', { class: 'abs' }, parent);
  img.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${hgt}px;${shadow ? 'box-shadow:0 18px 50px rgba(20,30,25,.28),0 2px 6px rgba(20,30,25,.18);' : ''}`;
  setSrc(img, P.footage + file);
  return img;
}
/* 叠加层：与静帧同一坐标系的 SVG（高亮框、刀线） */
function overlay(parent, w, hgt, x = 0, y = 0) {
  const o = s('svg', { width: w, height: hgt, viewBox: `0 0 ${w} ${hgt}`, class: 'abs' }, parent);
  o.style.cssText = `left:${x}px;top:${y}px;overflow:visible;`;
  return o;
}
/* 画框：沿矩形周长逐步描出 */
function frameBox(o, x, y, w, hgt, color = C.red, width = 3) {
  const r = s('rect', { x, y, width: w, height: hgt, rx: 6, fill: 'none', stroke: color, 'stroke-width': width }, o);
  const per = 2 * (w + hgt);
  return {
    node: r,
    set(p, alpha = 1) {
      r.setAttribute('stroke-dasharray', `${(per * clamp(p)).toFixed(1)} ${per + 10}`);
      r.setAttribute('opacity', (p > 0 ? alpha : 0).toFixed(3));
    },
  };
}
/* 录屏帧：源 25 fps，按源时间取帧 */
function clipFrame(img, srcT) {
  let idx = Math.max(0, Math.round(srcT * 25));
  while ((P.badFrames || []).includes(idx)) idx -= 1;   // 坏帧用前一帧代替
  setSrc(img, `${P.clips}f${String(idx).padStart(5, '0')}.jpg`);
}
/* 分段映射：segs = [[l0, l1, s0, s1], ...] 把镜头内时间换成源时间 */
function remap(l, segs) {
  for (const [l0, l1, s0, s1] of segs) if (l <= l1) return lerp(s0, s1, clamp((l - l0) / (l1 - l0)));
  const last = segs[segs.length - 1];
  return last[3];
}
/* 焦点以外轻微压暗、虚化 */
function focusLayer(root) {
  const blur = h('div', { class: 'layer' }, root);
  const dim = h('div', { class: 'layer' }, root);
  return {
    set(x, y, rx, ry, a) {
      const m = `radial-gradient(ellipse ${rx}px ${ry}px at ${x}px ${y}px, transparent 55%, black 100%)`;
      blur.style.backdropFilter = `blur(${(2.0 * a).toFixed(2)}px)`;
      blur.style.webkitMaskImage = m; blur.style.maskImage = m;
      dim.style.background = `radial-gradient(ellipse ${rx * 1.15}px ${ry * 1.15}px at ${x}px ${y}px, rgba(20,30,25,0) 50%, rgba(20,30,25,${(0.32 * a).toFixed(3)}) 100%)`;
    },
  };
}
const cue = (key, fallback) => (T.cues && T.cues[key] != null ? T.cues[key] : fallback);

/* 宋体文字逐字出现 */
function typeLine(parent, text, css) {
  const box = h('div', { class: 'abs serif' }, parent);
  box.style.cssText = css;
  const spans = [...text].map(ch => h('span', {}, box, ch));
  return {
    box, spans,
    set(t0, per, t, fade = 0.35) {
      spans.forEach((sp, i) => {
        const a = prog(t, t0 + i * per, t0 + i * per + fade, E.sine);
        sp.style.opacity = a.toFixed(3);
        sp.style.filter = a < 1 ? `blur(${((1 - a) * 3).toFixed(2)}px)` : 'none';
      });
    },
  };
}

/* 品牌朱印（同首页 Logo 字形：朱红底、米白宋体、四字两行、微倾） */
function seal(parent, size) {
  const d = h('div', { class: 'abs serif' }, parent);
  const fs = size * 0.36;
  d.style.cssText = `width:${size}px;height:${size * 1.09}px;background:${C.red};color:#fff5e5;border-radius:${size * 0.08}px;
    display:grid;place-items:center;font-size:${fs}px;line-height:1.15;letter-spacing:${fs * 0.17}px;padding-left:${fs * 0.17}px;
    box-shadow:0 ${size * 0.05}px ${size * 0.14}px rgba(0,0,0,.28);text-align:center;font-weight:600;`;
  d.innerHTML = '乡艺<br>有据';
  const tex = h('div', { class: 'layer' }, d);
  tex.style.cssText = `background:url(${TEX.red}) center/cover;mix-blend-mode:multiply;opacity:.55;border-radius:inherit;`;
  return d;
}

/* =====================================================================
 * 镜 5–6：一句讲反的话，被复制到处都是（示意动画，虚构通用卡片）
 * ===================================================================== */
function sceneCards() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root, TEX.cream);
  const world = h('div', { class: 'abs' }, root);
  world.style.cssText = 'left:0;top:0;width:1920px;height:1080px;transform-origin:0 0;';
  const SENT = '蔚县剪纸以阳刻为主';
  const sentence = (fs, color = C.ink) => {
    const wrap = h('div', { class: 'serif' });
    wrap.style.cssText = `font-size:${fs}px;letter-spacing:${fs * 0.08}px;color:${color};white-space:nowrap;`;
    [...SENT].forEach(ch => {
      const sp = h('span', {}, wrap, ch);
      if (ch === '阳') { sp.className = 'yang'; sp.style.color = C.red; sp.style.fontWeight = '700'; }
    });
    return wrap;
  };
  const bars = (parent, n, w, color = 'rgba(34,57,50,.14)') => {
    for (let i = 0; i < n; i++) {
      const b = h('div', {}, parent);
      b.style.cssText = `height:10px;border-radius:5px;background:${color};margin-top:14px;width:${w * (0.55 + 0.4 * ((i * 37) % 10) / 10)}px;`;
    }
  };
  // 中央：讲解词草稿，光标逐字打出
  const draft = h('div', { class: 'abs' }, world);
  draft.style.cssText = `left:560px;top:380px;width:800px;height:300px;background:url(${TEX.rice}) center/cover;border-radius:6px;
    box-shadow:0 20px 60px rgba(30,40,35,.22);padding:46px 56px;`;
  const dl = h('div', { class: 'sans' }, draft, '讲解词 · 草稿');
  dl.style.cssText = 'font-size:22px;letter-spacing:4px;color:#74796b;';
  const typed = h('div', { class: 'serif' }, draft);
  typed.style.cssText = 'margin-top:34px;font-size:64px;letter-spacing:6px;color:#223932;white-space:nowrap;';
  const typedSpans = [...SENT].map(ch => {
    const sp = h('span', {}, typed, ch);
    if (ch === '阳') { sp.className = 'yang'; sp.style.color = C.red; sp.style.fontWeight = '700'; }
    return sp;
  });
  const caret = h('span', {}, typed, '');
  caret.style.cssText = 'display:inline-block;width:4px;height:62px;background:#223932;vertical-align:-8px;margin-left:4px;';
  // 四周的通用卡片：导览牌、手机屏、手册页、讲解卡
  const r = rng(41);
  const cards = [];
  const kinds = ['sign', 'phone', 'page', 'card'];
  const spots = [];
  for (let gy = -1; gy <= 3; gy++) for (let gx = -1; gx <= 5; gx++) {
    const x = 120 + gx * 380 + (gy % 2) * 130 + (r() - .5) * 90, y = 40 + gy * 330 + (r() - .5) * 70;
    if (x > 420 && x < 1380 && y > 300 && y < 720) continue;
    spots.push([x, y]);
  }
  spots.forEach(([x, y], i) => {
    const kind = kinds[(i * 7 + 3) % 4];
    const c = h('div', { class: 'abs' }, world);
    const rot = (r() - .5) * 7;
    let w = 300, hh = 210;
    if (kind === 'sign') {
      w = 330; hh = 200;
      c.style.cssText = `background:${C.ink};border-radius:4px;padding:30px 30px;box-shadow:0 16px 40px rgba(20,30,25,.3);`;
      const t = h('div', { class: 'sans' }, c, '导览'); t.style.cssText = 'font-size:18px;letter-spacing:5px;color:rgba(246,243,235,.6);';
      const s1 = sentence(30, '#f6f3eb'); s1.style.marginTop = '20px'; c.appendChild(s1);
      bars(c, 2, 220, 'rgba(246,243,235,.18)');
      const leg = h('div', { class: 'abs' }, c); leg.style.cssText = 'left:46%;top:100%;width:16px;height:60px;background:#1a2c26;';
    } else if (kind === 'phone') {
      w = 190; hh = 360;
      c.style.cssText = `background:#1d2b26;border-radius:30px;padding:16px;box-shadow:0 16px 40px rgba(20,30,25,.3);`;
      const scr = h('div', {}, c); scr.style.cssText = `height:328px;border-radius:20px;background:url(${TEX.rice}) center/cover;padding:46px 14px;`;
      bars(scr, 2, 110);
      const bub = h('div', {}, scr); bub.style.cssText = 'margin-top:22px;background:#e6ece1;border-radius:12px;padding:12px 10px;';
      const s1 = sentence(18); s1.style.whiteSpace = 'normal'; s1.style.lineHeight = '1.6'; bub.appendChild(s1);
      bars(scr, 3, 120);
    } else if (kind === 'page') {
      w = 280; hh = 360;
      c.style.cssText = `background:url(${TEX.rice}) center/cover;border-radius:3px;padding:34px 30px;box-shadow:0 16px 40px rgba(20,30,25,.22);`;
      const t = h('div', {}, c); t.style.cssText = 'width:120px;height:14px;background:rgba(185,70,51,.5);border-radius:7px;';
      bars(c, 2, 200);
      const s1 = sentence(26); s1.style.marginTop = '24px'; s1.style.whiteSpace = 'normal'; s1.style.lineHeight = '1.6'; c.appendChild(s1);
      bars(c, 4, 210);
    } else {
      w = 300; hh = 170;
      c.style.cssText = `background:#fffdf8;border-radius:6px;padding:28px 28px;box-shadow:0 14px 34px rgba(20,30,25,.2);border-top:6px solid ${C.green};`;
      const s1 = sentence(28); c.appendChild(s1);
      bars(c, 3, 220);
    }
    c.style.left = `${x}px`; c.style.top = `${y}px`; c.style.width = `${w}px`;
    c.style.transformOrigin = '50% 50%';
    const d = Math.hypot(x + w / 2 - 960, y + hh / 2 - 540);
    cards.push({ c, rot, d, x, y });
  });
  cards.sort((a, b) => a.d - b.d);
  const dark = h('div', { class: 'layer' }, root);
  dark.style.background = '#0b120f';

  function update(t) {
    const s5 = shot(5), s6 = shot(6), l = t - s5.start;
    const typeStart = 0.35, per = 0.24;
    typedSpans.forEach((sp, i) => { sp.style.visibility = l >= typeStart + i * per ? 'visible' : 'hidden'; });
    const typedAll = l >= typeStart + SENT.length * per;
    caret.style.opacity = (!typedAll || Math.floor(l * 2.2) % 2 === 0) && l < 3.6 ? '1' : '0';
    const n = cards.length;
    cards.forEach((cd, i) => {
      const a = 2.7 + 4.6 * (i / n);
      const p = prog(l, a, a + 0.7, E.out);
      cd.c.style.opacity = p.toFixed(3);
      cd.c.style.transform = `translate(${((960 - cd.x - 150) * (1 - p) * 0.35).toFixed(1)}px,${((540 - cd.y - 120) * (1 - p) * 0.35).toFixed(1)}px) rotate(${(cd.rot * p).toFixed(2)}deg) scale(${(0.82 + 0.18 * p).toFixed(3)})`;
    });
    // 摄影机：从草稿后拉，看见铺满的卡片
    const cam = kf(l, [[0, [960, 540, 1.45]], [2.6, [960, 540, 1.34]], [8.5, [960, 540, 0.86]], [s6.end - s5.start, [960, 540, 0.8]]], E.inOut);
    world.style.transform = `translate(960px,540px) scale(${cam[2].toFixed(4)}) translate(-960px,-540px)`;
    // “如果这一刀讲反了”：所有“阳”字一起泛红，其余退淡
    const hot = prog(t, cue('VO-04#3', s5.start + 6.5) - 0.2, cue('VO-04#3', s5.start + 6.5) + 0.8, E.sine);
    root.querySelectorAll('.yang').forEach(sp => { sp.style.textShadow = hot > 0 ? `0 0 ${(14 * hot).toFixed(1)}px rgba(185,70,51,${(0.55 * hot).toFixed(2)})` : 'none'; });
    world.style.filter = `saturate(${(1 - 0.35 * hot).toFixed(3)})`;
    // 镜 6：画面渐暗，音乐停一拍
    setOpacity(dark, 0.58 * prog(t, s6.start, s6.end - 0.2, E.sine));
  }
  return { id: 'cards', root, from: 5, to: 6, update };
}

/* =====================================================================
 * 镜 7：朱印“乡艺有据”落下
 * ===================================================================== */
function sceneTitle() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root, TEX.riceDark);
  const sh = h('div', { class: 'abs' }, root);
  sh.style.cssText = 'left:860px;top:250px;width:200px;height:218px;border-radius:16px;background:rgba(0,0,0,.45);filter:blur(18px);';
  const sl = seal(root, 200);
  sl.style.left = '860px'; sl.style.top = '240px';
  const ring = h('div', { class: 'abs' }, root);
  ring.style.cssText = 'left:960px;top:349px;width:0;height:0;border-radius:50%;border:2px solid rgba(246,243,235,.5);';
  const l1 = typeLine(root, '每一句讲解有出处，', 'left:0;right:0;top:560px;text-align:center;font-size:58px;letter-spacing:14px;color:#f6f3eb;');
  const l2 = typeLine(root, '每一分钱有去处。', 'left:0;right:0;top:660px;text-align:center;font-size:58px;letter-spacing:14px;color:#f6f3eb;');
  const rule = h('div', { class: 'abs' }, root);
  rule.style.cssText = `left:930px;top:520px;width:60px;height:2px;background:${C.red};`;
  function update(t) {
    const s7 = shot(7), l = t - s7.start;
    const drop = prog(l, 0.55, 1.05, E.in2);
    const settle = prog(l, 1.05, 1.5, E.out);
    const sc = l < 1.05 ? lerp(1.9, 1.0, drop) : 1.0 + 0.03 * Math.sin(settle * Math.PI) * (1 - settle);
    sl.style.opacity = prog(l, 0.45, 0.8, E.sine).toFixed(3);
    sl.style.transform = `rotate(-3deg) scale(${sc.toFixed(4)})`;
    sh.style.opacity = (0.9 * drop).toFixed(3);
    sh.style.transform = `scale(${lerp(1.6, 1.0, drop).toFixed(3)})`;
    const rp = prog(l, 1.05, 2.2, E.out);
    const rr = 120 + 260 * rp;
    ring.style.width = ring.style.height = `${rr * 2}px`;
    ring.style.left = `${960 - rr}px`; ring.style.top = `${349 - rr}px`;
    ring.style.opacity = (rp > 0 ? 0.5 * (1 - rp) : 0).toFixed(3);
    const c2 = cue('VO-05#2', s7.start + 3.0);
    l1.set(c2 - 0.1, 0.2, t);
    l2.set(c2 + 1.95, 0.2, t);
    rule.style.opacity = prog(t, c2 - 0.6, c2, E.sine).toFixed(3);
    const k = 1 + 0.025 * prog(l, 0, s7.end - s7.start, E.lin);
    root.style.transform = `scale(${k.toFixed(4)})`;
  }
  return { id: 'title', root, from: 7, to: 7, update };
}

/* =====================================================================
 * 镜 8：待核验文案，推向“阳刻为主”
 * ===================================================================== */
function sceneDraft() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const vp = viewport(root);
  const frame = h('img', { class: 'abs' }, vp.wrap);
  frame.style.cssText = 'left:0;top:0;width:1920px;height:1080px;';
  clipFrame(frame, 10.0);
  // s05 是录屏 10 秒处文案框的 2 倍图，与录屏帧位置对齐（模板匹配：x=319, y=288）
  const still = stillImg(vp.wrap, 's05-studio-before.png', 450, 156, 319, 288, false);
  const o = overlay(vp.wrap, 450, 156, 319, 288);
  const box = frameBox(o, 92, 21, 69, 30, C.red, 1.6);
  const focus = focusLayer(root);
  function update(t) {
    const s8 = shot(8), l = t - s8.start, d = s8.end - s8.start;
    const cam = kf(l, [[0, [960, 520, 1.0]], [d * 0.55, [500, 340, 2.6]], [d, [446, 323, 3.5]]], E.inOut);
    vp.set(cam);
    const sharp = prog(l, 0.6, 2.2, E.sine);
    frame.style.filter = `blur(${(2.4 * sharp).toFixed(2)}px)`;
    still.style.opacity = sharp.toFixed(3);
    still.style.boxShadow = `0 ${(10 * sharp).toFixed(1)}px ${(30 * sharp).toFixed(1)}px rgba(20,30,25,${(0.25 * sharp).toFixed(2)})`;
    box.set(prog(l, d - 2.6, d - 1.4, E.inOut), 0.95);
    focus.set(960, 540, 900, 520, prog(l, 1, 4, E.sine));
  }
  return { id: 'draft', root, from: 8, to: 8, update };
}

/* =====================================================================
 * 镜 9：点击核验 → 等待（剪短为 1 秒）→ 结果出现
 * ===================================================================== */
function sceneVerifyClip() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const vp = viewport(root);
  const img = h('img', { class: 'abs' }, vp.wrap);
  img.style.cssText = 'left:0;top:0;width:1920px;height:1080px;';
  const pulse = h('div', { class: 'abs' }, vp.wrap);
  pulse.style.cssText = 'left:408px;top:768px;width:0;height:0;border-radius:50%;border:3px solid rgba(185,70,51,.8);';
  function update(t) {
    const s9 = shot(9), l = t - s9.start, d = s9.end - s9.start;
    const m = P.manifest.marks.reduce((a, x) => (a[x.name] = x.sec, a), {});
    const click = m['act1-click'], result = m['act1-result'];
    // 真实速度 1.5 秒 → 等待段 1 秒 → 结果出现后真实速度
    const segs = [[0, 1.5, click - 0.9, click + 0.6], [1.5, 2.5, click + 0.6, result - 0.2], [2.5, d, result - 0.2, result - 0.2 + (d - 2.5)]];
    clipFrame(img, remap(l, segs));
    vp.set(kf(l, [[0, [930, 560, 1.22]], [d, [1000, 470, 1.36]]], E.inOut));
    const pp = prog(l, 0.9 - 0.02, 1.5, E.out);
    const rr = 60 * pp;
    pulse.style.width = pulse.style.height = `${rr * 2}px`;
    pulse.style.left = `${408 - rr}px`; pulse.style.top = `${768 - rr}px`;
    pulse.style.opacity = (pp > 0 && pp < 1 ? 1 - pp : 0).toFixed(3);
  }
  return { id: 'verify', root, from: 9, to: 9, update };
}

/* =====================================================================
 * 镜 10：首句“与来源矛盾”；刀线划开“阳”，看修订里的“阴”；出处卡滑入
 * ===================================================================== */
function sceneAudit() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const vp = viewport(root);
  // s07 为 2 倍图（1614×2898），以源像素为坐标
  const still = stillImg(vp.wrap, 's07-audit-result.png', 1614, 2898);
  const o = overlay(vp.wrap, 1614, 2898);
  const knife = s('line', { x1: 300, y1: 505, x2: 300, y2: 505, stroke: C.red, 'stroke-width': 5, 'stroke-linecap': 'round' }, o);
  const glow = s('circle', { r: 16, fill: '#fff1d6', opacity: 0 }, o); glow.setAttribute('style', 'filter:blur(5px)');
  const yinBox = frameBox(o, 1084, 432, 68, 70, C.green, 4);
  const badge = frameBox(o, 1396, 238, 170, 66, C.red, 3);
  // 出处卡 s08：从下方像纸片一样滑入，停在右侧
  const card = h('div', { class: 'abs' }, root);
  card.style.cssText = 'left:1000px;top:350px;width:820px;height:344px;';
  const ci = h('img', { class: 'abs' }, card);
  ci.style.cssText = 'left:0;top:0;width:820px;height:344px;box-shadow:0 26px 70px rgba(20,30,25,.35),0 3px 8px rgba(20,30,25,.2);';
  setSrc(ci, P.footage + 's08-evidence.png');
  const co = overlay(card, 1502, 630);
  co.style.transformOrigin = '0 0'; co.style.transform = `scale(${820 / 1502})`;
  const q1 = frameBox(co, 50, 165, 480, 100, C.green, 5);
  const q2 = frameBox(co, 20, 305, 760, 110, C.green, 5);
  function update(t) {
    const s10 = shot(10), l = t - s10.start, d = s10.end - s10.start;
    const slide = prog(l, 6.6, 7.8, E.out);
    vp.set(kf(l, [
      [0, [800, 470, 1.18]], [2.2, [470, 470, 1.7]], [3.4, [470, 470, 1.75]],
      [5.2, [1060, 470, 1.6]], [6.4, [1060, 470, 1.6]], [7.8, [600, 520, 1.0]], [d, [610, 520, 1.03]],
    ], E.inOut));
    // 刀线：斜着划过“阳”（322–380, 442–493）
    const kc = prog(l, 2.6, 3.05, E.outQuint);
    const x1 = 300, y1 = 505, x2 = 402, y2 = 428;
    knife.setAttribute('x2', lerp(x1, x2, kc).toFixed(1)); knife.setAttribute('y2', lerp(y1, y2, kc).toFixed(1));
    knife.setAttribute('opacity', (kc > 0 ? 0.92 : 0).toFixed(2));
    glow.setAttribute('cx', lerp(x1, x2, kc).toFixed(1)); glow.setAttribute('cy', lerp(y1, y2, kc).toFixed(1));
    glow.setAttribute('opacity', (kc > 0 && kc < 1 ? 0.95 : 0).toFixed(2));
    badge.set(prog(l, 0.8, 1.8, E.inOut), 0.9 * (1 - prog(l, 6.2, 6.8, E.sine)));
    yinBox.set(prog(l, 4.9, 5.7, E.inOut), 1 - prog(l, 7.0, 7.6, E.sine));
    card.style.opacity = slide.toFixed(3);
    card.style.transform = `translateY(${(380 * (1 - slide)).toFixed(1)}px) rotate(${(2.5 * (1 - slide)).toFixed(2)}deg)`;
    const c4 = cue('VO-07#4', s10.start + 10);
    q1.set(prog(t, cue('VO-07#3', s10.start + 8) - 0.2, cue('VO-07#3', s10.start + 8) + 0.6, E.inOut), 0.9);
    q2.set(prog(t, c4 + 0.2, c4 + 1.1, E.inOut), 0.9);
  }
  return { id: 'audit', root, from: 10, to: 10, update };
}

/* =====================================================================
 * 镜 11：横移扫过三句结论，停在“信息不足”
 * ===================================================================== */
function sceneSweep() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const a = h('div', { class: 'layer' }, root);
  const va = viewport(a);
  stillImg(va.wrap, 's06-studio-viewport.png', 3840, 2160, 0, 0, false);
  const oa = overlay(va.wrap, 3840, 2160);
  const b1 = frameBox(oa, 3022, 236, 176, 66, C.red, 5);
  const b2 = frameBox(oa, 3046, 1482, 152, 66, C.green, 5);
  const b = h('div', { class: 'layer' }, root);
  paperBg(b);
  const vb = viewport(b);
  stillImg(vb.wrap, 's07-audit-result.png', 1614, 2898);
  const ob = overlay(vb.wrap, 1614, 2898);
  const b3 = frameBox(ob, 1420, 2164, 146, 66, C.ink, 4);
  const line3 = frameBox(ob, 70, 2330, 640, 120, C.ink, 3);
  const focus = focusLayer(root);
  function update(t) {
    const s11 = shot(11), l = t - s11.start, d = s11.end - s11.start;
    va.set(kf(l, [[0, [1450, 720, 0.76]], [3.2, [2620, 640, 0.76]], [5.0, [2620, 1250, 0.78]]], E.inOut));
    b1.set(prog(l, 1.6, 2.6, E.inOut), 0.9);
    b2.set(prog(l, 3.9, 4.8, E.inOut), 0.9);
    const x = prog(l, 4.8, 5.6, E.sine);
    setOpacity(b, x);
    vb.set(kf(l, [[4.8, [820, 1800, 0.95]], [7.5, [820, 2330, 1.05]], [d, [800, 2360, 1.12]]], E.inOut));
    b3.set(prog(l, 6.6, 7.6, E.inOut), 0.95);
    line3.set(prog(t, cue('VO-08#3', s11.start + 7.5), cue('VO-08#3', s11.start + 7.5) + 1.0, E.inOut), 0.8);
    focus.set(960, 520, 1000, 560, 0.8);
  }
  return { id: 'sweep', root, from: 11, to: 11, update };
}

/* =====================================================================
 * 镜 12：真实打字，原速
 * ===================================================================== */
function sceneTyping() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const vp = viewport(root);
  const img = h('img', { class: 'abs' }, vp.wrap);
  img.style.cssText = 'left:0;top:0;width:1920px;height:1080px;';
  const focus = focusLayer(root);
  function update(t) {
    const s12 = shot(12), l = t - s12.start, d = s12.end - s12.start;
    const m = P.manifest.marks.reduce((a, x) => (a[x.name] = x.sec, a), {});
    // 原速：从开始打字前 0.8 秒播到收尾，打字段 33.5–39.0 秒不变速
    clipFrame(img, m['act2-typing'] - 0.5 + l);
    vp.set(kf(l, [[0, [560, 470, 1.85]], [d, [545, 505, 2.05]]], E.inOut));
    focus.set(960, 600, 860, 360, 0.9);
  }
  return { id: 'typing', root, from: 12, to: 12, update };
}

/* =====================================================================
 * 镜 13：纸条重排（长度严格按真实分钟数，数据来自运行 66f40b93）
 * ===================================================================== */
function sceneStrips() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const D = P.plan;
  const X0 = 300, PX = 13.2;            // 1 分钟 = 13.2 像素
  const Y = 560;
  const colors = { story: C.green, craft: C.red, ext: '#9c3a2a', tea: C.cream };
  const kindOf = id => (id.includes('story') ? 'story' : id === 'craft-extension' ? 'ext' : id === 'tea' ? 'tea' : 'craft');
  const axis = h('div', { class: 'abs' }, root);
  axis.style.cssText = `left:${X0}px;top:${Y + 118}px;width:${PX * 100}px;height:2px;background:rgba(34,57,50,.35);`;
  const ticks = [];
  for (let m = 0; m <= 100; m += 10) {
    const tk = h('div', { class: 'abs sans' }, root, String(m));
    tk.style.cssText = `left:${X0 + m * PX - 30}px;width:60px;top:${Y + 130}px;text-align:center;font-size:20px;color:rgba(34,57,50,.55);`;
    const ln = h('div', { class: 'abs' }, root);
    ln.style.cssText = `left:${X0 + m * PX}px;top:${Y + 110}px;width:2px;height:10px;background:rgba(34,57,50,.35);`;
    ticks.push(tk, ln);
  }
  const unit = h('div', { class: 'abs sans' }, root, '分钟');
  unit.style.cssText = `left:${X0 + 100 * PX + 30}px;top:${Y + 128}px;font-size:20px;color:rgba(34,57,50,.55);letter-spacing:2px;`;
  const strip = (title, minutes, kind) => {
    const d = h('div', { class: 'abs' }, root);
    const col = colors[kind];
    d.style.cssText = `top:${Y}px;height:96px;border-radius:3px;overflow:hidden;
      box-shadow:0 10px 24px rgba(30,30,20,.22), 0 2px 3px rgba(30,30,20,.2);`;
    const fill = h('div', { class: 'layer' }, d);
    fill.style.cssText = `background:${col};`;
    const tex = h('div', { class: 'layer' }, d);
    tex.style.cssText = `background:url(${kind === 'tea' ? TEX.cream : TEX.red}) center/cover;mix-blend-mode:${kind === 'tea' ? 'normal' : 'multiply'};opacity:${kind === 'tea' ? 1 : .35};`;
    if (kind === 'ext') {
      const hatch = h('div', { class: 'layer' }, d);
      hatch.style.cssText = 'background:repeating-linear-gradient(135deg, rgba(255,240,225,.13) 0 6px, transparent 6px 16px);';
    }
    const txt = h('div', { class: 'abs sans' }, d);
    txt.style.cssText = `left:18px;top:16px;right:10px;font-size:26px;letter-spacing:2px;white-space:nowrap;color:${kind === 'tea' ? C.ink : '#fbf3e6'};`;
    const tt = h('div', {}, txt, title);
    const mm = h('div', {}, txt, `${minutes} 分钟`);
    mm.style.cssText = 'font-size:22px;opacity:.85;margin-top:4px;';
    if (kind === 'tea') d.style.border = '2px dashed rgba(34,57,50,.45)';
    return { d, tt, mm, minutes };
  };
  const before = D.before.schedule.map(x => strip(x.title, x.minutes, kindOf(x.id)));
  const after = D.after.schedule.map(x => strip(x.title, x.minutes, kindOf(x.id)));
  const tea = strip(D.tea.title, D.tea.minutes, 'tea');
  const teaNote = h('div', { class: 'abs sans' }, root, '可选模块');
  teaNote.style.cssText = 'font-size:20px;letter-spacing:3px;color:rgba(34,57,50,.6);';
  const head = h('div', { class: 'abs sans' }, root);
  head.style.cssText = `left:${X0}px;top:${Y - 66}px;font-size:24px;letter-spacing:4px;color:rgba(34,57,50,.75);`;
  // 中央大字：手作 50 → 80 分钟，数字翻牌
  const big = h('div', { class: 'abs' }, root);
  big.style.cssText = 'left:0;right:0;top:150px;text-align:center;color:#223932;white-space:nowrap;';
  const lab = h('span', { class: 'sans' }, big, '手作 ');
  lab.style.cssText = 'font-size:44px;letter-spacing:8px;vertical-align:28px;color:#476852;';
  const from = h('span', { class: 'serif' }, big, String(D.before.craft));
  from.style.cssText = 'font-size:150px;font-weight:500;color:#476852;';
  const arrow = h('span', { class: 'serif' }, big, ' → ');
  arrow.style.cssText = 'font-size:80px;vertical-align:30px;color:rgba(34,57,50,.5);';
  const flipBox = h('span', {}, big);
  flipBox.style.cssText = 'display:inline-block;position:relative;width:200px;height:150px;vertical-align:-22px;perspective:600px;';
  const digitA = h('span', { class: 'abs serif' }, flipBox, String(D.before.craft));
  const digitB = h('span', { class: 'abs serif' }, flipBox, String(D.after.craft));
  [digitA, digitB].forEach(dg => { dg.style.cssText += 'left:0;top:-38px;width:200px;text-align:center;font-size:150px;font-weight:500;color:#b94633;backface-visibility:hidden;transform-origin:50% 60%;'; });
  const unitBig = h('span', { class: 'sans' }, big, ' 分钟');
  unitBig.style.cssText = 'font-size:44px;letter-spacing:6px;vertical-align:28px;color:#476852;';
  const reqNote = h('div', { class: 'abs serif' }, root, `“${D.note}”`);
  reqNote.style.cssText = 'left:0;right:0;top:400px;text-align:center;font-size:34px;letter-spacing:6px;color:rgba(34,57,50,.8);';
  function place(list, x0, op = 1, y = Y) {
    let x = x0;
    list.forEach(st => {
      st.d.style.left = `${x}px`; st.d.style.width = `${st.minutes * PX}px`; st.d.style.top = `${y}px`;
      st.d.style.opacity = op.toFixed(3); x += st.minutes * PX;
    });
  }
  function update(t) {
    const s13 = shot(13), l = t - s13.start, d = s13.end - s13.start;
    const cTea = cue('VO-10#2', s13.start + 3.6), cCraft = cue('VO-10#3', s13.start + 5.5);
    const morph = prog(t, cCraft, cCraft + 1.6, E.inOut);
    setOpacity(big, prog(l, 0.2, 1.0, E.sine));
    setOpacity(reqNote, prog(l, 0.5, 1.3, E.sine) * (1 - prog(t, cCraft - 0.5, cCraft, E.sine)));
    // 修改前：讲解 20 + 基础手作 50
    place(before, X0, 1 - prog(t, cCraft + 0.6, cCraft + 1.2, E.sine));
    before.forEach((st, i) => { if (i === 1) st.d.style.width = `${lerp(st.minutes, st.minutes, 0) * PX}px`; });
    // 修改后：讲解 20 + 深度手作 60 + 延伸 20；手作纸条从 50 延长到 60，延伸练习从右侧滑入
    let x = X0;
    after.forEach((st, i) => {
      const grow = i === 1 ? prog(t, cCraft, cCraft + 1.2, E.inOut) : 1;
      const w = i === 1 ? lerp(D.before.schedule[1].minutes, st.minutes, grow) : st.minutes;
      st.d.style.left = `${x}px`; st.d.style.width = `${w * PX}px`; st.d.style.top = `${Y}px`;
      let op = prog(t, cCraft + 0.4, cCraft + 1.0, E.sine);
      if (i === 2) {
        const sl = prog(t, cCraft + 0.9, cCraft + 1.9, E.out);
        st.d.style.left = `${x + 240 * (1 - sl)}px`; op = sl;
      }
      st.d.style.opacity = op.toFixed(3);
      x += w * PX;
    });
    // 茶歇：作为可选模块停在时间轴右上方，需求“不要茶歇”后被提起移走
    const lift = prog(t, cTea - 0.2, cTea + 1.3, E.inOut);
    const tx = X0 + 100 * PX - D.tea.minutes * PX, ty = Y - 190;
    tea.d.style.left = `${tx + 420 * lift}px`; tea.d.style.top = `${ty - 140 * lift}px`; tea.d.style.width = `${D.tea.minutes * PX}px`;
    tea.d.style.transform = `rotate(${(8 * lift).toFixed(2)}deg)`;
    tea.d.style.opacity = (prog(l, 0.8, 1.5, E.sine) * (1 - prog(t, cTea + 0.6, cTea + 1.3, E.sine))).toFixed(3);
    teaNote.style.left = `${tx}px`; teaNote.style.top = `${ty - 36}px`;
    teaNote.style.opacity = (prog(l, 0.8, 1.5, E.sine) * (1 - lift)).toFixed(3);
    head.textContent = morph < 0.5 ? `上一次方案 · 全程 ${D.before.total} 分钟` : `本次程序推荐 · 全程 ${D.after.total} 分钟`;
    head.style.opacity = (morph < 0.5 ? 1 - morph * 2 : morph * 2 - 1).toFixed(3);
    // 翻牌
    const fl = prog(t, cCraft + 0.3, cCraft + 1.0, E.inOut);
    // 翻牌前只显示“手作 50 分钟”；翻牌时左侧“50 →”淡入，定格为“50 → 80”
    const showFrom = prog(t, cCraft + 0.3, cCraft + 1.0, E.sine);
    from.style.opacity = arrow.style.opacity = showFrom.toFixed(3);
    from.style.fontSize = `${(150 * showFrom).toFixed(1)}px`;
    arrow.style.fontSize = `${(80 * showFrom).toFixed(1)}px`;
    digitA.style.transform = `rotateX(${(fl * 180).toFixed(1)}deg)`;
    digitB.style.transform = `rotateX(${(fl * 180 - 180).toFixed(1)}deg)`;
    const k = 1 + 0.03 * prog(l, 0, d, E.lin);
    root.style.transform = `scale(${k.toFixed(4)})`;
  }
  return { id: 'strips', root, from: 13, to: 13, update };
}

/* =====================================================================
 * 镜 14：方案对比推近“50 → 80”，账目三类依次亮起（金额为演示测算）
 * ===================================================================== */
function sceneLedger() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const a = h('div', { class: 'layer' }, root);
  const va = viewport(a);
  stillImg(va.wrap, 's12-comparison.png', 2008, 1004);
  const oa = overlay(va.wrap, 2008, 1004);
  const nb = frameBox(oa, 190, 178, 375, 110, C.red, 3);
  const b = h('div', { class: 'layer' }, root);
  b.style.background = C.ink;
  const vb = viewport(b);
  stillImg(vb.wrap, 's13-ledger.png', 1916, 852, 0, 0, false);
  const ob = overlay(vb.wrap, 1916, 852);
  const rowY = [226, 300, 374, 448, 520, 594, 668, 742, 816];
  const groups = [[0, 2, 6], [3, 4, 7], [1, 5, 8]];
  const shades = rowY.map(y => s('rect', { x: -10, y: y - 37, width: 1936, height: 74, fill: '#0f1a16', opacity: 0 }, ob));
  const bars = rowY.map(y => s('rect', { x: -14, y: y - 30, width: 6, height: 60, fill: C.red, opacity: 0 }, ob));
  // 三类合计来自运行记录的整数分（manifest.json 中 plan 字段），换算成元显示
  const pl = P.plan.plan;
  const chipsWrap = h('div', { class: 'abs' }, b);
  chipsWrap.style.cssText = 'left:0;right:0;top:100px;display:flex;justify-content:center;gap:26px;';
  const chip = (label, cents) => {
    const c = h('div', { class: 'sans' }, chipsWrap);
    c.style.cssText = `padding:12px 26px;border-radius:3px;background:rgba(246,243,235,.08);border:1.5px solid rgba(246,243,235,.25);color:#f6f3eb;font-size:28px;letter-spacing:3px;`;
    c.innerHTML = `${label} <b style="font-weight:500;color:#f3c9b9;margin-left:8px">${cents / 100} 元</b>`;
    return c;
  };
  const chips = [chip('本地服务报酬', pl.local_service_cents), chip('材料工具', pl.material_cents), chip('活动组织', pl.operations_cents)];
  const total = chip('合计', pl.total_cents);
  function update(t) {
    const s14 = shot(14), l = t - s14.start, d = s14.end - s14.start;
    va.set(kf(l, [[0, [1004, 520, 0.92]], [3.6, [378, 236, 2.1]], [4.6, [378, 236, 2.15]]], E.inOut));
    nb.set(prog(l, 2.6, 3.6, E.inOut), 0.9);
    const x = prog(l, 4.2, 4.9, E.sine);
    setOpacity(b, x);
    vb.set(kf(l, [[4.2, [958, 418, 0.84]], [d, [958, 420, 0.86]]], E.inOut));
    const c2 = cue('VO-11#2', s14.start + 4.8), c3 = cue('VO-11#3', s14.start + 7.5);
    const on = [prog(t, c2, c2 + 0.5), prog(t, c2 + 1.1, c2 + 1.6), prog(t, c2 + 2.2, c2 + 2.7)];
    const back = prog(t, c3, c3 + 0.6);   // 说到“付给本地讲解和手作老师”时回到第一类
    const anyOn = Math.max(...on);
    rowY.forEach((_, r) => {
      const g = groups.findIndex(gr => gr.includes(r));
      let lit = on[g];
      if (back > 0) lit = g === 0 ? 1 : lerp(on[g], 0.35, back);
      shades[r].setAttribute('opacity', (0.55 * anyOn * (1 - lit)).toFixed(3));
      bars[r].setAttribute('opacity', (lit * (g === 0 ? 1 : 0.7) * (back > 0 && g !== 0 ? 1 - back : 1)).toFixed(3));
    });
    chips.forEach((c, i) => setOpacity(c, on[i] * (back > 0 && i !== 0 ? lerp(1, 0.45, back) : 1)));
    setOpacity(total, prog(t, c2 + 3.0, c2 + 3.6) * (1 - back * 0.55));
  }
  return { id: 'ledger', root, from: 14, to: 14, update };
}

/* =====================================================================
 * 镜 15：需要安排英语讲解 → 停下请人澄清
 * ===================================================================== */
function sceneStop() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const vp = viewport(root);
  const img = h('img', { class: 'abs' }, vp.wrap);
  img.style.cssText = 'left:0;top:0;width:1920px;height:1080px;';
  // s23 是警示条的 2 倍图，录屏 102 秒处约在 (298, 432)
  const warn = stillImg(vp.wrap, 's23-stop-warning.png', 1328, 48, 296, 422, false);
  const o = overlay(vp.wrap, 1328, 48, 296, 422);
  const box = frameBox(o, -8, -8, 1344, 64, C.red, 2);
  const focus = focusLayer(root);
  function update(t) {
    const s15 = shot(15), l = t - s15.start, d = s15.end - s15.start;
    const m = P.manifest.marks.reduce((a, x) => (a[x.name] = x.sec, a), {});
    const click = m['stop-click'], result = m['stop-result'];
    const segs = [[0, 2.6, click - 2.4, click + 0.2], [2.6, 3.6, click + 0.2, result - 0.1], [3.6, d, result - 0.1, result - 0.1 + Math.min(d - 3.6, 3.3)]];
    clipFrame(img, remap(l, segs));
    vp.set(kf(l, [[0, [640, 760, 1.5]], [2.6, [700, 740, 1.5]], [3.8, [960, 520, 1.25]], [6.0, [960, 446, 1.45]], [d, [800, 446, 2.0]]], E.inOut));
    const st = prog(l, 5.4, 6.4, E.sine);
    warn.style.opacity = st.toFixed(3);
    box.set(prog(l, 6.4, 7.4, E.inOut), 0.9);
    img.style.filter = `blur(${(2.2 * st).toFixed(2)}px) brightness(${(1 - 0.06 * st).toFixed(3)})`;
    focus.set(960, 540, 980, 420, 0.6 + 0.4 * st);
  }
  return { id: 'stop', root, from: 15, to: 15, update };
}

/* =====================================================================
 * 镜 16：作品卡从手册里抽走（示意动画）
 * ===================================================================== */
function sceneWithdrawCard() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root, TEX.cream);
  const book = h('div', { class: 'abs' }, root);
  book.style.cssText = 'left:310px;top:150px;width:1300px;height:760px;';
  const page = (x) => {
    const p = h('div', { class: 'abs' }, book);
    p.style.cssText = `left:${x}px;top:0;width:650px;height:760px;background:url(${TEX.rice}) center/cover;box-shadow:0 24px 60px rgba(30,30,20,.22);`;
    return p;
  };
  const left = page(0), right = page(650);
  const gutter = h('div', { class: 'abs' }, book);
  gutter.style.cssText = 'left:610px;top:0;width:80px;height:760px;background:linear-gradient(90deg,transparent,rgba(60,50,30,.16) 50%,transparent);';
  const ttl = h('div', { class: 'abs serif' }, left, '游客手册');
  ttl.style.cssText = 'left:70px;top:70px;font-size:40px;letter-spacing:10px;color:#223932;';
  for (let i = 0; i < 9; i++) {
    const b = h('div', { class: 'abs' }, left);
    b.style.cssText = `left:70px;top:${170 + i * 56}px;height:12px;border-radius:6px;background:rgba(34,57,50,.13);width:${360 + ((i * 53) % 140)}px;`;
  }
  // 右页：作品卡空位与作品卡
  const slot = h('div', { class: 'abs' }, right);
  slot.style.cssText = 'left:110px;top:90px;width:430px;height:480px;border:2px dashed rgba(34,57,50,.35);border-radius:4px;';
  for (let i = 0; i < 3; i++) {
    const b = h('div', { class: 'abs' }, right);
    b.style.cssText = `left:110px;top:${615 + i * 40}px;height:12px;border-radius:6px;background:rgba(34,57,50,.13);width:${300 + i * 40}px;`;
  }
  const card = h('div', { class: 'abs' }, right);
  card.style.cssText = `left:110px;top:90px;width:430px;height:480px;background:#fffdf8;box-shadow:0 14px 36px rgba(30,30,20,.25);overflow:hidden;`;
  const art = h('div', { class: 'abs' }, card);
  art.style.cssText = 'left:-205px;top:-150px;width:836px;height:836px;';
  const yin = makeCut('yin', art);
  const tagEl = h('div', { class: 'abs sans' }, card, '署名 · 使用范围');
  tagEl.style.cssText = `right:0;bottom:0;background:${C.ink};color:#f6f3eb;font-size:22px;letter-spacing:3px;padding:10px 16px;`;
  const hole = h('div', { class: 'abs sans' }, right, '');
  function update(t) {
    const s16 = shot(16), l = t - s16.start, d = s16.end - s16.start;
    const out = prog(t, cue('VO-13#1', s16.start + 1.3) + 0.6, cue('VO-13#1', s16.start + 1.3) + 2.6, E.inOut);
    card.style.transform = `translate(${(160 * out).toFixed(1)}px,${(-760 * out).toFixed(1)}px) rotate(${(-6 * out).toFixed(2)}deg)`;
    card.style.boxShadow = `0 ${(14 + 40 * out).toFixed(0)}px ${(36 + 50 * out).toFixed(0)}px rgba(30,30,20,${(0.25 - 0.1 * out).toFixed(2)})`;
    const k = 1.04 - 0.04 * prog(l, 0, d, E.lin);
    book.style.transform = `scale(${k.toFixed(4)})`;
  }
  return { id: 'withdraw-card', root, from: 16, to: 16, update, init() { finishCut(yin); } };
}

/* =====================================================================
 * 镜 17：点击“撤回使用”，旧确认失效；朱印“已失效”为示意叠加
 * ===================================================================== */
function sceneInvalidate() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const vp = viewport(root);
  const img = h('img', { class: 'abs' }, vp.wrap);
  img.style.cssText = 'left:0;top:0;width:1920px;height:1080px;';
  const stamp = h('div', { class: 'abs serif' }, vp.wrap, '已失效');
  stamp.style.cssText = `left:560px;top:360px;width:330px;height:130px;border:7px solid ${C.red};color:${C.red};border-radius:10px;
    font-size:74px;letter-spacing:14px;padding-left:14px;display:grid;place-items:center;font-weight:700;background:rgba(246,243,235,.12);
    mix-blend-mode:multiply;`;
  const stampTex = h('div', { class: 'layer' }, stamp);
  stampTex.style.cssText = `background:url(${TEX.rice}) center/cover;mix-blend-mode:screen;opacity:.45;`;
  const pulse = h('div', { class: 'abs' }, vp.wrap);
  pulse.style.cssText = 'border-radius:50%;border:3px solid rgba(185,70,51,.8);';
  function update(t) {
    const s17 = shot(17), l = t - s17.start, d = s17.end - s17.start;
    const m = P.manifest.marks.reduce((a, x) => (a[x.name] = x.sec, a), {});
    const w = m['act3-withdraw'], inv = m['act3-invalidated'];
    // 真实速度：撤回点击前 0.6 秒起，播到旧确认失效后停住
    const src = Math.min(w - 0.6 + l, inv + 0.4);
    clipFrame(img, src);
    vp.set(kf(l, [[0, [1180, 760, 1.28]], [2.2, [1180, 760, 1.32]], [3.6, [940, 560, 1.3]], [d, [920, 540, 1.36]]], E.inOut));
    const pp = prog(l, 0.6, 1.3, E.out);
    const rr = 50 * pp;
    pulse.style.width = pulse.style.height = `${rr * 2}px`;
    pulse.style.left = `${1566 - rr}px`; pulse.style.top = `${838 - rr}px`;
    pulse.style.opacity = (pp > 0 && pp < 1 ? 1 - pp : 0).toFixed(3);
    // 印章在“旧手册立刻作废”说完后落下，不压住旁白
    const sAt = cue('VO-14#end', s17.start + 4.0) + 0.05;
    const drop = prog(t, sAt, sAt + 0.32, E.in2);
    stamp.style.opacity = (drop > 0 ? 0.9 : 0).toFixed(3);
    stamp.style.transform = `rotate(-8deg) scale(${lerp(1.8, 1.0, drop).toFixed(3)})`;
  }
  return { id: 'invalidate', root, from: 17, to: 17, update };
}

/* =====================================================================
 * 镜 18：定位受影响内容 → 新版游客手册
 * ===================================================================== */
function sceneRenew() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const a = h('div', { class: 'layer' }, root);
  const va = viewport(a);
  // s17 只取上部 250 像素（下沿有一条提示浮层）
  const clipBox = h('div', { class: 'abs' }, va.wrap);
  clipBox.style.cssText = 'left:0;top:0;width:1920px;height:250px;overflow:hidden;box-shadow:0 18px 50px rgba(20,30,25,.25);';
  const si = h('img', { class: 'abs' }, clipBox);
  si.style.cssText = 'left:0;top:0;width:1920px;height:284px;';
  setSrc(si, P.footage + 's17-impact.png');
  const oa = overlay(va.wrap, 1920, 250);
  const fb = frameBox(oa, -6, 88, 330, 50, C.red, 3);
  const fb2 = frameBox(oa, -6, 186, 980, 52, C.red, 3);
  const b = h('div', { class: 'layer' }, root);
  const vb = viewport(b);
  stillImg(vb.wrap, 's20-preview-visitor.png', 3840, 2160, 0, 0, false);
  function update(t) {
    const s18 = shot(18), l = t - s18.start, d = s18.end - s18.start;
    // 左缘对齐源图左缘（cx = 960 / k - 20），不裁掉行首文字
    va.set(kf(l, [[0, [650, 140, 1.45]], [3.8, [573, 150, 1.62]]], E.inOut));
    fb.set(prog(l, 0.8, 1.6, E.inOut), 0.9);
    fb2.set(prog(l, 1.8, 2.8, E.inOut), 0.9);
    const x = prog(l, 3.6, 4.4, E.sine);
    setOpacity(b, x);
    vb.set(kf(l, [[3.6, [1920, 1080, 0.5]], [d, [1920, 1000, 0.6]]], E.inOut));
  }
  return { id: 'renew', root, from: 18, to: 18, update };
}

/* =====================================================================
 * 镜 19：一台电脑（示意动画；无耗时实测记录，不放实测行）
 * ===================================================================== */
function sceneLaptop() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const svg = s('svg', { width: 1920, height: 1080, class: 'abs' }, root);
  const g = s('g', { fill: 'none', stroke: C.ink, 'stroke-width': 3.2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, svg);
  const paths = [
    'M330 300 H950 Q966 300 966 316 V690 H314 V316 Q314 300 330 300 Z',
    'M346 332 H934 V664 H346 Z',
    'M250 690 H1030 L1070 742 Q1074 752 1062 752 H218 Q206 752 210 742 Z',
    'M570 720 H710',
  ].map(d => s('path', { d }, g));
  // 屏幕里：一枚小小的阴刻纹样，表示本地运行的就是这套系统
  const scr = h('div', { class: 'abs' }, root);
  scr.style.cssText = 'left:490px;top:348px;width:300px;height:300px;';
  const mini = makeCut('yin', scr, 272);
  const items = ['一台电脑离线运行', '零模型调用费', '人工确认才交付'].map((txt, i) => {
    const row = h('div', { class: 'abs' }, root);
    row.style.cssText = `left:1150px;top:${360 + i * 110}px;display:flex;align-items:center;gap:26px;`;
    const dot = h('div', {}, row); dot.style.cssText = `width:16px;height:16px;background:${C.red};`;
    const tx = h('div', { class: 'serif' }, row, txt); tx.style.cssText = 'font-size:52px;letter-spacing:10px;color:#223932;';
    return row;
  });
  function update(t) {
    const s19 = shot(19), l = t - s19.start, d = s19.end - s19.start;
    paths.forEach((p, i) => {
      const len = p.getTotalLength();
      const k = prog(l, 0.2 + i * 0.35, 1.6 + i * 0.35, E.inOut);
      p.setAttribute('stroke-dasharray', `${(len * k).toFixed(1)} ${len + 5}`);
    });
    setOpacity(scr, prog(l, 1.6, 2.6, E.sine));
    const c2 = cue('VO-16#2', s19.start + 3.5);
    items.forEach((row, i) => {
      const a = [s19.start + 1.2, c2, c2 + 1.6][i];
      const p = prog(t, a, a + 0.7, E.out);
      row.style.opacity = p.toFixed(3); row.style.transform = `translateX(${(30 * (1 - p)).toFixed(1)}px)`;
    });
    const k = 1.06 - 0.06 * prog(l, 0, d, E.inOut);
    root.style.transform = `scale(${k.toFixed(4)})`;
  }
  return { id: 'laptop', root, from: 19, to: 19, update, init() { finishCut(mini); } };
}

/* =====================================================================
 * 镜 20：阴刻纹样在墨绿底上缓缓旋转半圈，金句逐字出现
 * ===================================================================== */
function sceneFinale() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root, TEX.riceDark);
  const holder = h('div', { class: 'abs' }, root);
  holder.style.cssText = 'left:120px;top:122px;width:836px;height:836px;';
  const yin = makeCut('yin', holder, 760);
  const lines = [
    ['AI 正在成为人们', 'VO-17#1'], ['认识一个地方的第一扇窗。', 'VO-17#2'],
    ['我们让它只讲有出处的话，', 'VO-17#3'], ['把拍板权和收益留在乡里。', 'VO-17#4'],
  ].map(([txt, key], i) => ({ key, line: typeLine(root, txt, `left:1060px;top:${300 + i * 118 + (i >= 2 ? 40 : 0)}px;font-size:56px;letter-spacing:8px;color:#f6f3eb;white-space:nowrap;`) }));
  const rule = h('div', { class: 'abs' }, root);
  rule.style.cssText = `left:1062px;top:${300 + 2 * 118 - 12}px;width:70px;height:2px;background:${C.red};`;
  function update(t) {
    const s20 = shot(20), l = t - s20.start, d = s20.end - s20.start;
    holder.style.transform = `rotate(${(180 * prog(l, 0, d + 4.2, E.lin)).toFixed(2)}deg) scale(${(0.98 + 0.03 * prog(l, 0, d, E.sine)).toFixed(4)})`;
    holder.style.opacity = prog(l, 0, 1.2, E.sine).toFixed(3);
    lines.forEach(({ key, line }, i) => {
      const c = cue(key, s20.start + 1 + i * 3);
      const n = line.spans.length;
      const next = lines[i + 1] ? cue(lines[i + 1].key, c + 3) : c + 3.2;
      const per = Math.min(0.23, Math.max(0.12, (next - c - 0.3) / n));
      line.set(c - 0.05, per, t, 0.4);
    });
    rule.style.opacity = prog(t, cue('VO-17#3', s20.start + 7) - 0.6, cue('VO-17#3', s20.start + 7), E.sine).toFixed(3);
  }
  return { id: 'finale', root, from: 20, to: 20, update, init() { finishCut(yin); } };
}

/* =====================================================================
 * 镜 21：片尾
 * ===================================================================== */
function sceneEnd() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  paperBg(root);
  const sl = seal(root, 150);
  sl.style.left = '885px'; sl.style.top = '250px'; sl.style.transform = 'rotate(-3deg)';
  const motto = h('div', { class: 'abs serif' }, root, '一方乡土，万千有据。');
  motto.style.cssText = 'left:0;right:0;top:500px;text-align:center;font-size:56px;letter-spacing:16px;color:#223932;';
  const fine = h('div', { class: 'abs sans' }, root);
  fine.style.cssText = 'left:0;right:0;top:930px;text-align:center;font-size:20px;line-height:1.7;letter-spacing:1px;color:rgba(34,57,50,.72);';
  fine.innerHTML = '系统画面为本地真实运行，等待时间已剪短；动画为示意，纹样为项目原创；价格、报酬、人员与场地为演示配置。<br>资料：中国非物质文化遗产网';
  function update(t) {
    const s21 = shot(21), l = t - s21.start, d = s21.end - s21.start;
    setOpacity(sl, prog(l, 0.1, 0.9, E.sine));
    setOpacity(motto, prog(l, 0.6, 1.6, E.sine));
    setOpacity(fine, prog(l, 1.0, 1.8, E.sine));
    const fadeOut = prog(l, d - 0.7, d, E.sine);
    root.style.filter = `brightness(${(1 - fadeOut).toFixed(3)})`;
  }
  return { id: 'end', root, from: 21, to: 21, update };
}

SCENE_BUILDERS.push(sceneCards, sceneTitle, sceneDraft, sceneVerifyClip, sceneAudit, sceneSweep, sceneTyping,
  sceneStrips, sceneLedger, sceneStop, sceneWithdrawCard, sceneInvalidate, sceneRenew, sceneLaptop, sceneFinale, sceneEnd);
