'use strict';
/* 《一刀之差》确定性渲染舞台：filmInit(payload) 建场景，filmSeek(t) 把画面设到第 t 秒。
 * 所有动画都由 t 计算，不使用 CSS 动画或计时器，同一个 t 永远得到同一帧。 */

const W = 1920, H = 1080;
const C = { paper: '#f6f3eb', ink: '#223932', red: '#b94633', cream: '#eee9dd', green: '#476852', deep: '#16241f' };
let T = null;            // 时间线（shots、subtitles、transitions）
let P = null;            // 素材路径等
const scenes = [];
let frameIndex = 0;

/* ---------- 数学与缓动 ---------- */
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, k) => a + (b - a) * k;
const E = {
  lin: k => k,
  inOut: k => (k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
  sine: k => -(Math.cos(Math.PI * k) - 1) / 2,
  out: k => 1 - Math.pow(1 - k, 3),
  outQuint: k => 1 - Math.pow(1 - k, 5),
  in: k => k * k * k,
  in2: k => k * k,
};
const prog = (t, a, b, e = E.inOut) => e(clamp((t - a) / (b - a)));
function rng(seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let x = Math.imul(seed ^ seed >>> 15, 1 | seed);
    x = x + Math.imul(x ^ x >>> 7, 61 | x) ^ x;
    return ((x ^ x >>> 14) >>> 0) / 4294967296;
  };
}
/* 关键帧：[[t, v], ...]，v 可以是数或数组，段内按 easing 插值 */
function kf(t, frames, e = E.inOut) {
  if (t <= frames[0][0]) return frames[0][1];
  for (let i = 1; i < frames.length; i++) {
    const [t1, v1] = frames[i];
    if (t <= t1) {
      const [t0, v0] = frames[i - 1];
      const k = e((t - t0) / (t1 - t0 || 1));
      return Array.isArray(v0) ? v0.map((x, j) => lerp(x, v1[j], k)) : lerp(v0, v1, k);
    }
  }
  return frames[frames.length - 1][1];
}

/* ---------- DOM 工具 ---------- */
const NS = 'http://www.w3.org/2000/svg';
function h(tag, attrs = {}, parent = null, text = null) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'style') Object.assign(node.style, v); else node.setAttribute(k, v);
  }
  if (text != null) node.textContent = text;
  if (parent) parent.appendChild(node);
  return node;
}
function s(tag, attrs = {}, parent = null) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}
function setOpacity(node, o) { node.style.opacity = o.toFixed(4); node.style.visibility = o <= 0.001 ? 'hidden' : 'visible'; }

/* ---------- 程序生成纹理 ---------- */
function canvas(w, hgt) { const c = document.createElement('canvas'); c.width = w; c.height = hgt; return c; }
function hexRgb(hex) { const n = parseInt(hex.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }

/* 宣纸：底色 + 大尺度云状起伏 + 细噪声 + 纤维线 */
function fiberTexture(w, hgt, base, seed, opts = {}) {
  const r = rng(seed);
  const c = canvas(w, hgt); const g = c.getContext('2d');
  g.fillStyle = base; g.fillRect(0, 0, w, hgt);
  const cloud = opts.cloud ?? 0.05;
  for (let i = 0; i < 90; i++) {
    const x = r() * w, y = r() * hgt, rad = 80 + r() * 380;
    const grd = g.createRadialGradient(x, y, 0, x, y, rad);
    const light = r() > .5;
    grd.addColorStop(0, light ? `rgba(255,255,250,${cloud * r()})` : `rgba(60,40,20,${cloud * .6 * r()})`);
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd; g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  }
  const img = g.getImageData(0, 0, w, hgt); const d = img.data; const amp = opts.noise ?? 7;
  for (let i = 0; i < d.length; i += 4) {
    const n = (r() - .5) * amp;
    d[i] = clamp(d[i] + n, 0, 255); d[i + 1] = clamp(d[i + 1] + n, 0, 255); d[i + 2] = clamp(d[i + 2] + n, 0, 255);
  }
  g.putImageData(img, 0, 0);
  const fibers = opts.fibers ?? Math.round(w * hgt / 900);
  const fl = opts.fiberLight ?? 'rgba(255,252,240,', fd = opts.fiberDark ?? 'rgba(90,70,45,';
  for (let i = 0; i < fibers; i++) {
    const x = r() * w, y = r() * hgt, len = (opts.fiberLen ?? 40) * (0.4 + r() * 1.6), ang = r() * Math.PI * 2;
    const bend = (r() - .5) * len * .8;
    g.beginPath(); g.moveTo(x, y);
    g.quadraticCurveTo(x + Math.cos(ang) * len / 2 - Math.sin(ang) * bend, y + Math.sin(ang) * len / 2 + Math.cos(ang) * bend,
      x + Math.cos(ang) * len, y + Math.sin(ang) * len);
    const light = r() > .42;
    g.strokeStyle = (light ? fl : fd) + (0.04 + r() * (light ? .16 : .08)) + ')';
    g.lineWidth = (opts.fiberWidth ?? 1) * (0.35 + r() * 1.1);
    g.stroke();
  }
  return c;
}
let TEX = {};
function buildTextures() {
  TEX.rice = fiberTexture(2400, 1500, C.paper, 11, { cloud: .06, noise: 6, fiberLen: 46 }).toDataURL('image/jpeg', .93);
  TEX.riceDark = fiberTexture(1200, 800, C.ink, 13, { cloud: .07, noise: 5, fiberLen: 40, fiberLight: 'rgba(120,150,130,', fiberDark: 'rgba(0,0,0,' }).toDataURL('image/jpeg', .93);
  TEX.red = fiberTexture(1600, 1600, C.red, 17, { cloud: .05, noise: 9, fiberLen: 30, fiberLight: 'rgba(235,150,120,', fiberDark: 'rgba(70,10,5,' }).toDataURL('image/jpeg', .94);
  TEX.redMacro = fiberTexture(1920, 1080, '#a83d2b', 19, { cloud: .08, noise: 14, fiberLen: 150, fiberWidth: 2.6, fibers: 3200, fiberLight: 'rgba(240,160,130,', fiberDark: 'rgba(50,5,0,' }).toDataURL('image/jpeg', .94);
  TEX.cream = fiberTexture(1200, 900, C.cream, 23, { cloud: .05, noise: 6, fiberLen: 36 }).toDataURL('image/jpeg', .93);
  // 颗粒：8 张噪声轮换
  TEX.grain = [];
  const r = rng(29);
  for (let k = 0; k < 8; k++) {
    const c = canvas(640, 360); const g = c.getContext('2d'); const img = g.createImageData(640, 360);
    for (let i = 0; i < img.data.length; i += 4) { const v = r() * 255; img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255; }
    g.putImageData(img, 0, 0); TEX.grain.push(c);
  }
}

/* ---------- 时间线工具 ---------- */
const shot = n => T.shots.find(x => x.n === n);
const local = (n, t) => t - shot(n).start;

/* ---------- 图片等待 ---------- */
const waits = [];
function setSrc(img, src) {
  if (img.dataset.src === src) return;
  img.dataset.src = src; img.src = src;
  waits.push(img.decode().catch(() => {}));
}

/* =====================================================================
 * 原创纹样 paper-garden.svg：拆成线描（阳刻）与刻线（阴刻）
 * ===================================================================== */
let GARDEN = null;   // [{tag, attrs, transform, width, closed}]
function parseGarden(text) {
  const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
  const root = doc.documentElement;
  const defs = {};
  root.querySelectorAll('defs > g').forEach(g => { defs[g.id] = [...g.children]; });
  const out = [];
  function emit(node, transform) {
    const tag = node.tagName;
    if (tag === 'use') {
      const id = node.getAttribute('href').slice(1);
      const tr = [transform, node.getAttribute('transform') || ''].join(' ').trim();
      defs[id].forEach(child => emit(child, tr));
    } else if (tag === 'g') {
      const tr = [transform, node.getAttribute('transform') || ''].join(' ').trim();
      [...node.children].forEach(child => emit(child, tr));
    } else if (tag === 'path' || tag === 'circle') {
      const attrs = {};
      for (const a of ['d', 'cx', 'cy', 'r']) if (node.hasAttribute(a)) attrs[a] = node.getAttribute(a);
      const filled = node.getAttribute('fill') && node.getAttribute('fill') !== 'none';
      const sw = parseFloat(node.getAttribute('stroke-width') || '0');
      const dash = node.getAttribute('stroke-dasharray');
      const closed = tag === 'circle' || /Z\s*$/i.test(attrs.d || '');
      out.push({ tag, attrs, transform, width: filled ? 5 : Math.max(sw, 4.6), dash, closed, filled });
    }
  }
  [...root.children].forEach(n => { if (n.tagName !== 'defs') emit(n, ''); });
  return out;
}

/* 一张剪纸：mode = 'yang'（只留线条）| 'yin'（红面刻去线条）| 'carve'（阳刻的刻制过程） */
let uid = 0;
function makeCut(mode, parent, size = 760) {
  const id = `cut${uid++}`;
  const svg = s('svg', { viewBox: '-40 -40 880 880', width: size * 1.1, height: size * 1.1, class: 'cut' }, parent);
  svg.style.overflow = 'visible';
  const defs = s('defs', {}, svg);
  const pat = s('pattern', { id: `${id}tex`, patternUnits: 'userSpaceOnUse', width: 800, height: 800 }, defs);
  s('image', { href: TEX.red, width: 800, height: 800 }, pat);
  const f = s('filter', { id: `${id}sh`, x: '-20%', y: '-20%', width: '140%', height: '140%' }, defs);
  s('feDropShadow', { dx: 3.2, dy: 4.5, stdDeviation: 3.2, 'flood-color': '#2a1a10', 'flood-opacity': .36 }, f);
  // 线描
  const lines = s('g', { id: `${id}lines`, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, defs);
  const items = [];
  GARDEN.forEach((g, i) => {
    const node = s(g.tag, { ...g.attrs, transform: g.transform, 'stroke-width': g.width }, lines);
    if (g.dash) node.setAttribute('stroke-dasharray', g.dash);
    items.push({ ...g, node, i });
  });
  const res = { svg, id, items, mode };
  if (mode === 'yin') {
    // 阴刻：红纸上把线条刻掉。闭合线条留几处细小的连接点（剪纸的“断口”），整张纸才不会掉出中间部分
    const cut = s('g', { fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, defs);
    cut.id = `${id}cutlines`;
    GARDEN.forEach(g => {
      const node = s(g.tag, { ...g.attrs, transform: g.transform, 'stroke-width': g.width * 0.92 }, cut);
      if (g.dash) node.setAttribute('stroke-dasharray', g.dash);
      else if (g.closed) node.dataset.bridge = '1';   // 长度在挂载后计算
    });
    const m = s('mask', { id: `${id}m`, maskUnits: 'userSpaceOnUse', x: -40, y: -40, width: 880, height: 880 }, defs);
    s('rect', { x: -40, y: -40, width: 880, height: 880, fill: 'white' }, m);
    s('use', { href: `#${id}cutlines`, stroke: 'black' }, m);
    const g = s('g', { filter: `url(#${id}sh)` }, svg);
    s('circle', { cx: 400, cy: 400, r: 372, fill: `url(#${id}tex)`, mask: `url(#${id}m)` }, g);
    res.cutGroup = cut;
  } else if (mode === 'yang') {
    const g = s('g', { filter: `url(#${id}sh)` }, svg);
    s('use', { href: `#${id}lines`, stroke: `url(#${id}tex)` }, g);
  } else {
    // 刻制过程：宽刀路逐段“刻出”线描，未刻部分仍是整张红纸
    const carve = s('g', { fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, defs);
    carve.id = `${id}carve`;
    items.forEach(it => {
      it.carve = s(it.tag, { ...it.attrs, transform: it.transform, 'stroke-width': it.tag === 'circle' && +it.attrs.r > 300 ? 46 : 36 }, carve);
    });
    const mr = s('mask', { id: `${id}mr`, maskUnits: 'userSpaceOnUse', x: -40, y: -40, width: 880, height: 880 }, defs);
    s('rect', { x: -40, y: -40, width: 880, height: 880, fill: 'black' }, mr);
    s('use', { href: `#${id}carve`, stroke: 'white' }, mr);
    const mu = s('mask', { id: `${id}mu`, maskUnits: 'userSpaceOnUse', x: -40, y: -40, width: 880, height: 880 }, defs);
    s('rect', { x: -40, y: -40, width: 880, height: 880, fill: 'white' }, mu);
    s('use', { href: `#${id}carve`, stroke: 'black' }, mu);
    const g = s('g', { filter: `url(#${id}sh)` }, svg);
    res.uncut = s('circle', { cx: 400, cy: 400, r: 372, fill: `url(#${id}tex)`, mask: `url(#${id}mu)` }, g);
    const yg = s('g', { mask: `url(#${id}mr)` }, g);
    s('use', { href: `#${id}lines`, stroke: `url(#${id}tex)` }, yg);
    // 刀光：一段亮的尾迹 + 刀尖
    res.trail = s('g', {}, svg);
    res.knife = s('g', {}, svg);
    const rg = s('radialGradient', { id: `${id}glow` }, defs);
    s('stop', { offset: '0', 'stop-color': '#fff8ea', 'stop-opacity': .95 }, rg);
    s('stop', { offset: '.35', 'stop-color': '#ffd9a8', 'stop-opacity': .45 }, rg);
    s('stop', { offset: '1', 'stop-color': '#ffb070', 'stop-opacity': 0 }, rg);
    s('circle', { r: 26, fill: `url(#${id}glow)` }, res.knife);
    res.blade = s('path', { d: 'M-15 0 L9 -1.4 L13 0 L9 1.4 Z', fill: '#fffaf0' }, res.knife);
    s('circle', { r: 2.6, fill: '#ffffff' }, res.knife);
  }
  return res;
}

/* 挂载后补全：路径长度、阴刻的连接点 */
function finishCut(cut) {
  if (cut.mode === 'yin') {
    cut.cutGroup.querySelectorAll('[data-bridge]').forEach(node => {
      const len = node.getTotalLength();
      const n = Math.max(2, Math.round(len / 260));
      const gap = 5.5, seg = len / n - gap;
      node.setAttribute('stroke-dasharray', `${seg.toFixed(2)} ${gap}`);
      node.setAttribute('stroke-dashoffset', (seg * 0.37).toFixed(2));
    });
  }
  if (cut.mode === 'carve') {
    cut.items.forEach(it => {
      it.len = it.carve.getTotalLength();
      const m = it.carve.transform.baseVal.consolidate();
      it.matrix = m ? m.matrix : cut.svg.createSVGMatrix();
      it.carve.setAttribute('stroke-dasharray', `0 ${it.len + 1}`);
    });
  }
}

/* 刻制进度：p∈[0,1]，沿路径从起点刻到 p 处 */
function carveTo(it, p) {
  it.carve.style.display = p <= 0 ? 'none' : 'inline';
  const l = it.len * clamp(p);
  it.carve.setAttribute('stroke-dasharray', `${l.toFixed(2)} ${(it.len + 2).toFixed(2)}`);
  it.progress = p;
}
function pointOn(it, p) {
  const pt = it.carve.getPointAtLength(it.len * clamp(p));
  const pt2 = it.carve.getPointAtLength(Math.min(it.len, it.len * clamp(p) + 2));
  const a = new DOMPoint(pt.x, pt.y).matrixTransform(it.matrix);
  const b = new DOMPoint(pt2.x, pt2.y).matrixTransform(it.matrix);
  return { x: a.x, y: a.y, ang: Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI };
}

/* =====================================================================
 * 场景：序 · 一刀之差（镜 1–4）
 * ===================================================================== */
function scenePaper() {
  const root = h('div', { class: 'scene' }, document.getElementById('scenes'));
  root.style.background = '#0b120f';
  const world = h('div', { class: 'abs' }, root);
  world.style.cssText = 'left:0;top:0;width:1920px;height:1080px;transform-origin:0 0;';
  const backing = h('div', { class: 'abs' }, world);
  backing.style.cssText = `left:-240px;top:-210px;width:2400px;height:1500px;background:url(${TEX.rice}) center/cover;`;
  // 两张剪纸：主图（刻制→翻面），以及分屏时左侧的阳刻
  const flipper = h('div', { class: 'abs' }, world);
  flipper.style.cssText = 'left:960px;top:540px;width:0;height:0;perspective:2600px;';
  const card = h('div', { class: 'abs' }, flipper);
  card.style.cssText = 'left:-418px;top:-418px;width:836px;height:836px;transform-style:preserve-3d;';
  const front = h('div', { class: 'abs' }, card);
  front.style.cssText = 'inset:0;backface-visibility:hidden;';
  const back = h('div', { class: 'abs' }, card);
  back.style.cssText = 'inset:0;backface-visibility:hidden;transform:rotateY(180deg);';
  const edge = h('div', { class: 'abs' }, card);   // 翻到侧面时看到的红纸厚度
  edge.style.cssText = 'left:415px;top:46px;width:6px;height:744px;border-radius:3px;transform:rotateY(90deg);background:linear-gradient(180deg,#7d2b1f,#c4543f 30%,#a33b2b 70%,#7d2b1f);';
  const carve = makeCut('carve', front);
  const yin = makeCut('yin', back);
  const leftWrap = h('div', { class: 'abs' }, world);
  leftWrap.style.cssText = 'left:542px;top:122px;width:836px;height:836px;';
  const yangCopy = makeCut('yang', leftWrap);
  // 光：镜 1 的全黑与侧光，镜 2 开灯
  const dark = h('div', { class: 'layer' }, root);
  // 镜 1：黑暗中浮现的红纸边缘，侧光照出纤维
  const macro = h('div', { class: 'layer' }, root);
  macro.style.background = '#090e0c';
  const macroImg = h('div', { class: 'abs' }, macro);
  macroImg.style.cssText = `left:520px;top:-560px;width:2700px;height:2700px;border-radius:50%;transform-origin:1150px 1050px;
    background:url(${TEX.redMacro}) 0 0/1920px 1080px repeat;
    box-shadow:-26px 34px 70px rgba(0,0,0,.75), inset 5px -3px 0 rgba(255,196,160,.22), inset 14px -8px 26px rgba(255,170,130,.10);`;
  const macroLight = h('div', { class: 'layer' }, macro);
  macroLight.style.background = 'linear-gradient(118deg, rgba(255,222,180,.16) 0%, rgba(255,200,150,.05) 30%, rgba(0,0,0,.18) 58%, rgba(0,0,0,.72) 100%)';
  const macroBlack = h('div', { class: 'layer' }, macro);
  macroBlack.style.background = '#060908';
  const macroCap = h('div', { class: 'abs serif' }, root, '同一张红纸。');
  macroCap.style.cssText = 'left:0;right:0;top:640px;text-align:center;font-size:56px;letter-spacing:22px;color:#f6efe2;font-weight:500;text-shadow:0 2px 18px rgba(0,0,0,.5);';
  // 文字层
  const label = (txt, small, x, y) => {
    const box = h('div', { class: 'abs' }, world);
    box.style.cssText = `left:${x - 300}px;top:${y}px;width:600px;text-align:center;`;
    const big = h('div', { class: 'serif' }, box, txt);
    big.style.cssText = 'font-size:58px;letter-spacing:18px;color:#223932;font-weight:600;padding-left:18px;';
    const sm = h('div', { class: 'sans' }, box, small);
    sm.style.cssText = 'margin-top:14px;font-size:28px;letter-spacing:8px;color:#476852;padding-left:8px;';
    return box;
  };
  const vLabel = (txt, small) => {
    const box = h('div', { class: 'abs' }, root);
    box.style.cssText = 'left:1452px;top:330px;height:420px;display:flex;gap:26px;flex-direction:row-reverse;align-items:flex-start;';
    const big = h('div', { class: 'serif' }, box, txt);
    big.style.cssText = 'writing-mode:vertical-rl;font-size:68px;letter-spacing:26px;color:#223932;font-weight:600;';
    const sm = h('div', { class: 'sans' }, box, small);
    sm.style.cssText = 'writing-mode:vertical-rl;font-size:28px;letter-spacing:10px;color:#476852;margin-top:12px;';
    const seal = h('div', {}, box);
    seal.style.cssText = 'width:14px;height:14px;background:#b94633;margin-top:4px;';
    return box;
  };
  const vYang = vLabel('阳刻', '刀留下线条');
  const vYin = vLabel('阴刻', '刀刻去线条');
  const lYang = label('阳刻', '刀留下线条', 530, 712);
  const lYin = label('阴刻', '刀刻去线条', 1390, 712);
  const src = (txt, x) => {
    const d = h('div', { class: 'abs serif' }, world, txt);
    d.style.cssText = `left:${x - 400}px;width:800px;top:842px;text-align:center;font-size:34px;letter-spacing:6px;color:#223932;`;
    return d;
  };
  const sYang = src('丰宁满族剪纸 · 以阳刻为主', 530);
  const sYin = src('蔚县剪纸 · 以阴刻为主', 1390);
  sYang.innerHTML = '丰宁满族剪纸 · 以<b style="color:#b94633;font-weight:600">阳刻</b>为主';
  sYin.innerHTML = '蔚县剪纸 · 以<b style="color:#b94633;font-weight:600">阴刻</b>为主';
  const divider = s('svg', { width: 1920, height: 1080, class: 'abs' }, world);
  divider.style.cssText = 'left:0;top:0;';
  const divLine = s('line', { x1: 960, y1: 170, x2: 960, y2: 170, stroke: C.red, 'stroke-width': 3, 'stroke-linecap': 'round' }, divider);
  const divGlow = s('circle', { cx: 960, cy: 170, r: 16, fill: '#fff3dc', opacity: 0 }, divider);
  divGlow.setAttribute('style', 'filter:blur(5px)');
  const shadowFlip = h('div', { class: 'abs' }, world);

  // 刻制顺序：左鸟轮廓先由刀尖带着刻，其余随后分组刻出
  let birdBody = null; const order = [];
  function plan() {
    const its = carve.items;
    const isLeftBird = it => it.transform.includes('') && it.attrs.d && it.attrs.d.startsWith('M204 408') && !it.transform.includes('scale');
    birdBody = its.find(isLeftBird);
    const rest = its.filter(it => it !== birdBody);
    const ring = its.find(it => it.tag === 'circle' && it.attrs.r === '353');
    rest.forEach(it => {
      // 以纹样中心为原点按角度排序，像刀沿着圆周一圈圈走
      const c = it.carve.getBBox();
      const cx = c.x + c.width / 2, cy = c.y + c.height / 2;
      const p = new DOMPoint(cx, cy).matrixTransform(it.matrix);
      const ang = (Math.atan2(p.y - 400, p.x - 400) + Math.PI * 2.5) % (Math.PI * 2);
      const rad = Math.hypot(p.x - 400, p.y - 400);
      it.key = it === ring ? -1 : ang / (Math.PI * 2) * 0.75 + (rad < 120 ? 0.18 : 0);
    });
    rest.sort((a, b) => a.key - b.key);
    rest.forEach((it, k) => order.push(it));
    carve.ring = ring;
  }

  function update(t) {
    const s1 = shot(1), s2 = shot(2), s3 = shot(3), s4 = shot(4);
    if (!birdBody) plan();
    const l2 = t - s2.start, l3 = t - s3.start, l4 = t - s4.start;
    // ---- 镜 1：微距 ----
    const mOp = 1 - prog(t, s2.start - 0.4, s2.start + 0.9, E.sine);
    setOpacity(macro, mOp);
    setOpacity(macroBlack, 1 - prog(t, s1.start + 0.2, s1.start + 2.4, E.sine));
    macroImg.style.transform = `scale(${(1 + 0.09 * prog(t, s1.start, s2.start + 0.9, E.lin)).toFixed(4)}) translateX(${(-24 * prog(t, s1.start, s2.start + 1, E.lin)).toFixed(2)}px)`;
    setOpacity(macroCap, prog(t, s1.start + 1.6, s1.start + 2.8, E.sine) * (1 - prog(t, s2.start - 0.8, s2.start + 0.1, E.sine)));
    macroCap.style.transform = `translateY(${(-8 * prog(t, s1.start + 1.6, s2.start, E.lin)).toFixed(2)}px)`;
    // ---- 摄影机 ----
    // 世界坐标：纹样中心 (960,540)，1 单位 ≈ 0.95 px（viewBox 880 → 836px）
    const u = 836 / 880, ox = 960 - 418 + 40 * u, oy = 540 - 418 + 40 * u;
    const birdC = [ox + 232 * u, oy + 392 * u];
    const cam = kf(t, [
      [s2.start, [birdC[0] + 30, birdC[1] + 6, 2.35]],
      [s2.start + 3.3, [birdC[0] - 10, birdC[1] - 4, 2.15]],
      [s2.start + 6.4, [960, 540, 1.0]],
      [s3.start + 0.2, [960, 540, 1.0]],
      [s3.start + 2.6, [960, 548, 1.06]],
      [s3.start + 3.3, [960, 548, 1.06]],
      [s4.start - 0.2, [960, 540, 1.0]],
      [s4.end, [960, 520, 1.03]],
    ], E.inOut);
    world.style.transform = `translate(960px,540px) scale(${cam[2].toFixed(4)}) translate(${(-cam[0]).toFixed(2)}px,${(-cam[1]).toFixed(2)}px)`;
    // ---- 灯光：从全黑到宣纸上的柔光 ----
    const lightUp = prog(t, s2.start - 0.3, s2.start + 2.2, E.sine);
    dark.style.background = `radial-gradient(ellipse 60% 70% at 46% 46%, rgba(8,12,10,${(0.55 * (1 - lightUp)).toFixed(3)}) 0%, rgba(8,12,10,${(0.25 + 0.75 * (1 - lightUp)).toFixed(3)}) 100%)`;
    dark.style.opacity = (0.35 + 0.65 * (1 - lightUp * 0.8)).toFixed(3);
    // ---- 镜 2：刻制 ----
    // 刀尖沿左鸟轮廓
    const kb = prog(t, s2.start + 0.8, s2.start + 4.0, E.sine);
    carveTo(birdBody, kb);
    // 其余线条：3.4–6.2 秒依次刻出
    const n = order.length;
    order.forEach((it, k) => {
      const a = s2.start + 3.2 + 2.4 * (k / n), d = 0.9;
      carveTo(it, prog(t, a, a + d, E.sine));
    });
    // 外圈：第二把刀光
    let knife = null;
    if (t > s2.start + 0.7 && t < s2.start + 4.05) knife = pointOn(birdBody, kb);
    const ringIt = carve.ring; const ringP = ringIt ? ringIt.progress || 0 : 0;
    if (!knife && ringIt && ringP > 0 && ringP < 1) knife = pointOn(ringIt, ringP);
    if (knife) {
      carve.knife.setAttribute('transform', `translate(${knife.x.toFixed(2)} ${knife.y.toFixed(2)}) rotate(${knife.ang.toFixed(1)})`);
      const flick = 0.85 + 0.15 * Math.sin(t * 37.0) * Math.sin(t * 13.0);
      carve.knife.setAttribute('opacity', flick.toFixed(3));
    } else carve.knife.setAttribute('opacity', 0);
    // 尾迹：刀尖后方 60 单位的亮线
    carve.trail.replaceChildren();
    const trailOf = (it, p, alpha) => {
      if (!(p > 0 && p < 1)) return;
      const end = it.len * p, len = Math.min(70, end);
      const tr = s(it.tag, { ...it.attrs, transform: it.transform, fill: 'none', stroke: '#fff4dc', 'stroke-width': 2.2, 'stroke-linecap': 'round',
        'stroke-dasharray': `0 ${(end - len).toFixed(2)} ${len.toFixed(2)} ${(it.len + 10).toFixed(2)}`, opacity: alpha }, carve.trail);
      tr.style.filter = 'blur(0.6px)';
    };
    trailOf(birdBody, kb, .85);
    order.forEach(it => trailOf(it, it.progress, .35));
    // 剩下的空白纸片抬起移走
    const lift = prog(t, s2.start + 5.6, s2.start + 6.9, E.in2);
    const fallen = prog(t, s2.start + 5.6, s2.start + 7.0, E.inOut);
    carve.uncut.setAttribute('opacity', (1 - fallen).toFixed(3));
    carve.uncut.setAttribute('transform', `translate(${(0).toFixed(2)} ${(-16 * lift).toFixed(2)}) scale(${(1 + 0.025 * lift).toFixed(4)})`);
    carve.uncut.style.transformOrigin = '400px 400px';
    // ---- 镜 2 尾：竖排“阳刻” ----
    setOpacity(vYang, prog(t, s2.start + 6.4, s2.start + 7.4, E.sine) * (1 - prog(t, s3.start + 0.2, s3.start + 0.8, E.sine)));
    // ---- 镜 3：翻面 ----
    const flip = prog(t, s3.start + 0.5, s3.start + 2.7, E.inOut);
    const liftZ = Math.sin(flip * Math.PI);
    card.style.transform = `translateZ(${(90 * liftZ).toFixed(2)}px) rotateY(${(180 * flip).toFixed(2)}deg) rotateX(${(6 * liftZ).toFixed(2)}deg)`;
    setOpacity(vYin, prog(t, s3.start + 2.6, s3.start + 3.3, E.sine) * (1 - prog(t, s3.start + 3.4, s3.start + 3.9, E.sine)));
    // 分屏：阴刻右移，阳刻从左侧淡入
    const split = prog(t, s3.start + 3.4, s4.start - 0.2, E.inOut);
    const sc = lerp(1, 0.62, split);
    flipper.style.transform = `translate(${(430 * split).toFixed(2)}px,${(-100 * split).toFixed(2)}px) scale(${sc.toFixed(4)})`;
    leftWrap.style.transform = `translate(${(-430 - 70 * (1 - split)).toFixed(2)}px,${(-100).toFixed(2)}px) scale(0.62)`;
    leftWrap.style.transformOrigin = '418px 418px';
    setOpacity(leftWrap, prog(t, s3.start + 3.6, s4.start - 0.1, E.sine));
    setOpacity(lYang, prog(t, s3.start + 4.6, s3.start + 5.4, E.sine));
    setOpacity(lYin, prog(t, s3.start + 4.8, s3.start + 5.6, E.sine));
    // ---- 镜 4：出处 ----
    setOpacity(sYang, prog(t, s4.start + 0.5, s4.start + 1.4, E.sine));
    setOpacity(sYin, prog(t, s4.start + 2.6, s4.start + 3.5, E.sine));
    // “一刀之差”：中线一刀
    const cutAt = (T.cues && T.cues.yidao) || (s4.start + 6.6);
    const dl = prog(t, cutAt, cutAt + 0.7, E.outQuint);
    divLine.setAttribute('y2', (170 + 540 * dl).toFixed(2));
    divLine.setAttribute('opacity', (dl > 0 ? 0.9 : 0).toFixed(2));
    divGlow.setAttribute('cy', (170 + 540 * dl).toFixed(2));
    divGlow.setAttribute('opacity', (dl > 0 && dl < 1 ? 0.9 : 0).toFixed(2));
  }
  return { id: 'paper', root, from: 1, to: 4, update, init() { finishCut(carve); finishCut(yin); } };
}

/* =====================================================================
 * 合成：场景显隐、转场、颗粒、角标、字幕
 * ===================================================================== */
const SCENE_BUILDERS = [scenePaper];
const KNIFE_INTO = new Set([7, 8, 12, 16, 19]);   // 段落交界的刀切转场，全片 5 次

function sceneRange(sc) { return [shot(sc.from).start, shot(sc.to).end]; }

function knifeClip(width, angDeg) {
  // 画面减去一条以中心为轴、半宽 width 的斜带：两块多边形拼成一个 clip-path
  const a = angDeg * Math.PI / 180;
  const nx = -Math.sin(a), ny = Math.cos(a);
  const rect = [[-5, -5], [W + 5, -5], [W + 5, H + 5], [-5, H + 5]];
  const half = sign => {
    const out = [];
    const f = p => sign * ((p[0] - W / 2) * nx + (p[1] - H / 2) * ny) - width;
    for (let i = 0; i < rect.length; i++) {
      const p = rect[i], q = rect[(i + 1) % rect.length];
      const fp = f(p), fq = f(q);
      if (fp >= 0) out.push(p);
      if ((fp >= 0) !== (fq >= 0)) { const k = fp / (fp - fq); out.push([lerp(p[0], q[0], k), lerp(p[1], q[1], k)]); }
    }
    return out;
  };
  const A = half(1), B = half(-1);
  if (!A.length && !B.length) return 'polygon(0 0,0 0,0 0)';
  const pts = [...A, A[0] || B[0], ...B, B[0] || A[0], A[0] || B[0]];
  return `polygon(${pts.map(p => `${p[0].toFixed(1)}px ${p[1].toFixed(1)}px`).join(',')})`;
}

function composite(t) {
  const list = scenes.map(sc => ({ sc, r: sceneRange(sc) }));
  const tr = document.getElementById('transition');
  tr.replaceChildren();
  list.forEach(({ sc, r }, i) => {
    const next = list[i + 1], prev = list[i - 1];
    let visible = t >= r[0] - 0.001 && t < r[1];
    let opacity = 1, clip = 'none';
    // 进入：上一场景结束处
    if (prev) {
      const tb = r[0];
      const knife = KNIFE_INTO.has(sc.from);
      if (!knife && t >= tb - 0.35 && t < tb + 0.35) { visible = true; opacity = prog(t, tb - 0.35, tb + 0.35, E.sine); }
    }
    // 离开：刀切或叠化
    if (next) {
      const tb = r[1];
      const knife = KNIFE_INTO.has(next.sc.from);
      if (knife && t >= tb - 0.05 && t < tb + 0.75) {
        visible = true;
        const open = prog(t, tb + 0.05, tb + 0.75, E.in2);
        clip = knifeClip(open * 1250, -13);
        drawKnife(tr, t, tb, open);
      }
      if (knife && t >= tb - 0.55 && t < tb - 0.05) drawKnife(tr, t, tb, 0);
      if (!knife && t >= tb - 0.35 && t < tb + 0.35) visible = true;
    }
    sc.root.style.display = visible ? 'block' : 'none';
    sc.root.style.opacity = opacity.toFixed(4);
    sc.root.style.clipPath = clip;
    sc.root.style.zIndex = visible && clip !== 'none' ? 5 : (i + 1);
    if (visible) sc.update(t);
  });
}

function drawKnife(svg, t, tb, open) {
  // 一道朱红细线划过画面：先划出（tb-0.55→tb-0.05），再随切口张开向两侧退去
  const a = -13 * Math.PI / 180, dx = Math.cos(a), dy = Math.sin(a);
  const L = 1250;
  const draw = prog(t, tb - 0.55, tb - 0.05, E.outQuint);
  const nx = -dy, ny = dx;
  const w = open * 1250;
  const fade = 1 - prog(open, 0.05, 0.55, E.lin);
  if (fade <= 0) return;
  const x0 = W / 2 - dx * L, y0 = H / 2 - dy * L;
  const xe = x0 + dx * 2 * L * draw, ye = y0 + dy * 2 * L * draw;
  [-1, 1].forEach(sg => {
    const ox = nx * w * sg, oy = ny * w * sg;
    s('line', { x1: x0 + ox, y1: y0 + oy, x2: xe + ox, y2: ye + oy, stroke: C.red, 'stroke-width': 3.4, opacity: fade.toFixed(3), 'stroke-linecap': 'round' }, svg);
  });
  if (draw < 1) {
    const g = s('circle', { cx: xe, cy: ye, r: 20, fill: '#fff1d6', opacity: .9 }, svg);
    g.setAttribute('style', 'filter:blur(6px)');
    s('circle', { cx: xe, cy: ye, r: 3, fill: '#ffffff' }, svg);
  }
}

function overlays(t) {
  // 颗粒
  const gc = document.getElementById('grain').getContext('2d');
  gc.drawImage(TEX.grain[Math.floor(frameIndex / 2) % TEX.grain.length], 0, 0);   // 颗粒每 2 帧换一次
  // 角标
  const tag = document.getElementById('tag');
  const sh = T.shots.find(x => t >= x.start && t < x.end) || T.shots[T.shots.length - 1];
  if (sh.tag) {
    tag.textContent = sh.tag; tag.style.display = 'block';
    const a = Math.min(prog(t, sh.start + 0.2, sh.start + 0.7, E.sine), 1 - prog(t, sh.end - 0.35, sh.end, E.sine));
    tag.style.opacity = (0.92 * a).toFixed(3);
  } else tag.style.display = 'none';
  // 左下注记
  const note = document.getElementById('note');
  const nt = (T.notes || []).find(x => t >= x.start && t < x.end);
  if (nt) {
    note.textContent = nt.text; note.style.display = 'block';
    note.style.opacity = Math.min(prog(t, nt.start, nt.start + .3, E.sine), 1 - prog(t, nt.end - .3, nt.end, E.sine)).toFixed(3);
  } else note.style.display = 'none';
  // 字幕
  const sub = document.getElementById('sub');
  // 镜 7 与镜 20 的旁白就是画面上的宋体大字，不再重复烧录字幕条（SRT 仍完整保留）
  const cue = (T.subtitles || []).find(x => t >= x.start && t < x.end && x.burn !== false);
  if (cue) {
    sub.firstChild.textContent = cue.text; sub.style.display = 'block';
    sub.style.opacity = Math.min(prog(t, cue.start, cue.start + .18, E.sine), 1 - prog(t, cue.end - .18, cue.end, E.sine)).toFixed(3);
  } else sub.style.display = 'none';
}

/* ---------- 对外接口 ---------- */
window.filmInit = async function (payload) {
  T = payload.timeline; P = payload;
  GARDEN = parseGarden(payload.garden);
  buildTextures();
  await document.fonts.load('56px "Noto Serif CJK SC"');
  await document.fonts.load('44px "Noto Sans CJK SC"');
  await document.fonts.load('bold 44px "Noto Sans CJK SC"');
  for (const b of SCENE_BUILDERS) {
    const sc = b();
    scenes.push(sc);
  }
  // 挂载后再计算路径长度
  for (const sc of scenes) { sc.root.style.display = 'block'; if (sc.init) await sc.init(); sc.root.style.display = 'none'; }
  await document.fonts.ready;
  return { scenes: scenes.map(x => x.id) };
};

window.filmSeek = async function (t, index) {
  frameIndex = index ?? Math.round(t * 24);
  waits.length = 0;
  composite(t);
  overlays(t);
  await Promise.all(waits);
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  return true;
};
