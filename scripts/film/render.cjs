'use strict';
/* 《一刀之差》渲染入口。
 *
 *   npm run film:render                       全流程：画面 → 配乐音效 → 混音 → 成片（男声、女声两版）
 *   node scripts/film/render.cjs --video      只渲染画面（4 个进程并行，输出 artifacts/film/picture.mp4）
 *   node scripts/film/render.cjs --stills 7.5,12,20   抽帧到 artifacts/film/stills/
 *   node scripts/film/render.cjs --sheet 0,31,1       按区间每 1 秒抽帧并拼联系表
 *   node scripts/film/render.cjs --mux        用已有画面与分轨合成两版成片（MP4 与 SRT）
 *   node scripts/film/render.cjs --webm       由两版 MP4 另导出 WebM
 *
 * 画面由 scripts/film/stage.html 的 filmSeek(t) 逐帧设定，Playwright 截图后经管道交给 ffmpeg。
 */
const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(ROOT, 'artifacts', 'film');
const FPS = 24;
const STAGE = 'file://' + path.join(__dirname, 'stage.html');
const FOOTAGE = path.join(ROOT, 'docs', 'assets', 'film', 'footage');

function arg(name, fallback = null) {
  const i = process.argv.indexOf(name);
  return i < 0 ? fallback : (process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : true);
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts });
  if (r.status !== 0) throw new Error(`${cmd} ${args.join(' ')} 失败`);
}

/* 镜 13 的纸条数据：直接取自 5090 采集运行 66f40b93 的方案对比与候选日程 */
function planData() {
  const manifest = JSON.parse(fs.readFileSync(path.join(FOOTAGE, 'manifest.json'), 'utf8'));
  const runId = Object.keys(manifest.runs).find(id => id.startsWith('66f40b93'));
  const run = JSON.parse(fs.readFileSync(path.join(FOOTAGE, `run-${runId}.json`), 'utf8'));
  const pick = id => run.planning.candidates.find(c => c.id === id);
  const sched = c => c.schedule.map(x => ({ id: x.module_id, title: x.title, minutes: x.minutes }));
  const tea = run.profile.modules.find(m => m.id === 'tea');
  const before = pick(run.comparison.before.id), after = pick(run.comparison.after.id);
  return {
    run: runId, note: run.requirements.note,
    before: { craft: run.comparison.before.craft_minutes, total: run.comparison.before.duration_minutes, schedule: sched(before) },
    after: { craft: run.comparison.after.craft_minutes, total: run.comparison.after.duration_minutes, schedule: sched(after) },
    tea: { title: tea.title, minutes: tea.min_duration_minutes },
    plan: manifest.runs[runId].plan,
  };
}

function payload() {
  const timeline = JSON.parse(fs.readFileSync(path.join(OUT, 'timeline.json'), 'utf8'));
  return {
    plan: planData(),
    timeline,
    garden: fs.readFileSync(path.join(ROOT, 'frontend', 'prototype', 'assets', 'paper-garden.svg'), 'utf8'),
    footage: 'file://' + FOOTAGE + '/',
    clips: 'file://' + path.join(OUT, 'clips') + '/',
    badFrames: fs.existsSync(path.join(OUT, 'clips', 'bad.json')) ? JSON.parse(fs.readFileSync(path.join(OUT, 'clips', 'bad.json'), 'utf8')) : [],
    manifest: JSON.parse(fs.readFileSync(path.join(FOOTAGE, 'manifest.json'), 'utf8')),
  };
}

async function openStage() {
  const options = { args: ['--allow-file-access-from-files', '--disable-web-security', '--font-render-hinting=none'] };
  const exe = process.env.BROWSER_EXECUTABLE || (fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : null);
  if (exe) options.executablePath = exe;
  const browser = await chromium.launch(options);
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on('pageerror', e => console.error('页面错误', e.message));
  page.on('console', m => { if (m.type() === 'error') console.error('控制台', m.text()); });
  await page.goto(STAGE);
  await page.evaluate(p => window.filmInit(p), payload());
  return { browser, page };
}

/* 从 take.webm 抽出需要的片段帧（源 25 fps），按源帧号存 JPEG */
function extractClips() {
  const dir = path.join(OUT, 'clips');
  if (fs.existsSync(path.join(dir, 'done'))) return;
  fs.mkdirSync(dir, { recursive: true });
  run('ffmpeg', ['-v', 'error', '-y', '-i', path.join(FOOTAGE, 'take.webm'), '-vf', 'fps=25', '-q:v', '2',
    '-start_number', '0', path.join(dir, 'f%05d.jpg')]);
  // 采集脚本截静帧的瞬间，录屏里会出现几帧只画出顶部、其余灰色的坏帧；记下来，渲染时用前一帧代替
  run('python3', ['-c', `
import json, glob, numpy as np
from PIL import Image
bad = []
for f in sorted(glob.glob(${JSON.stringify(dir)} + '/f*.jpg')):
    im = np.asarray(Image.open(f).convert('L').resize((96, 54)), dtype=float)
    if (np.abs(im - 128) < 6).mean() > 0.35:
        bad.append(int(f[-9:-4]))
json.dump(bad, open(${JSON.stringify(path.join(dir, 'bad.json'))}, 'w'))
print('录屏坏帧', bad)
`]);
  fs.writeFileSync(path.join(dir, 'done'), 'ok');
}

async function stills(times, dir) {
  extractClips();
  fs.mkdirSync(dir, { recursive: true });
  const { browser, page } = await openStage();
  const files = [];
  for (const t of times) {
    await page.evaluate(([x, i]) => window.filmSeek(x, i), [t, Math.round(t * FPS)]);
    const file = path.join(dir, `t${t.toFixed(2).padStart(7, '0')}.jpg`);
    await page.screenshot({ path: file, type: 'jpeg', quality: 90 });
    files.push(file);
  }
  await browser.close();
  return files;
}

function contactSheet(files, out, cols = 4) {
  // 用 ffmpeg 拼联系表：每格 480×270，下方标注秒数
  const list = files.map(f => ({ f, t: path.basename(f).slice(1, -4) }));
  const rows = Math.ceil(list.length / cols);
  const inputs = []; const filters = [];
  list.forEach((x, i) => {
    inputs.push('-i', x.f);
    filters.push(`[${i}:v]scale=480:270,pad=480:300:0:0:0x16241f,drawtext=fontfile=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc:text='${Number(x.t).toFixed(1)}s':x=8:y=274:fontsize=20:fontcolor=white[v${i}]`);
  });
  const layout = list.map((_, i) => `${(i % cols) * 480}_${Math.floor(i / cols) * 300}`).join('|');
  filters.push(`${list.map((_, i) => `[v${i}]`).join('')}xstack=inputs=${list.length}:layout=${layout}:fill=0x0d1512[out]`);
  run('ffmpeg', ['-v', 'error', '-y', ...inputs, '-filter_complex', filters.join(';'), '-map', '[out]', '-q:v', '3', out]);
  return out;
}

/* 并行渲染：把总帧数切成 N 段，每段一个浏览器，截图经管道交给 ffmpeg 编成中间段 */
async function renderSegment(index, from, to, dir) {
  const { browser, page } = await openStage();
  const file = path.join(dir, `seg${index}.mp4`);
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '12', '-pix_fmt', 'yuv420p', file], { stdio: ['pipe', 'inherit', 'inherit'] });
  const started = Date.now();
  for (let f = from; f < to; f++) {
    const t = f / FPS;
    await page.evaluate(([x, i]) => window.filmSeek(x, i), [t, f]);
    const buf = await page.screenshot({ type: 'jpeg', quality: 95 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if ((f - from) % 120 === 0) console.log(`段 ${index}: ${f - from}/${to - from} 帧，${((Date.now() - started) / 1000).toFixed(0)} 秒`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();
  return file;
}

async function renderVideo() {
  extractClips();
  const timeline = JSON.parse(fs.readFileSync(path.join(OUT, 'timeline.json'), 'utf8'));
  const total = Math.round(timeline.duration * FPS);
  const from = Math.round(Number(arg('--from', 0)) * FPS);
  const to = Math.min(total, Math.round(Number(arg('--to', timeline.duration)) * FPS));
  const workers = Number(arg('--workers', 4));
  const dir = path.join(OUT, 'segments');
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const size = Math.ceil((to - from) / workers);
  const jobs = [];
  for (let k = 0; k < workers; k++) {
    const a = from + k * size, b = Math.min(to, a + size);
    if (a < b) jobs.push(renderSegment(k, a, b, dir));
  }
  const files = await Promise.all(jobs);
  fs.writeFileSync(path.join(dir, 'list.txt'), files.map(f => `file '${f}'`).join('\n'));
  run('ffmpeg', ['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', path.join(dir, 'list.txt'), '-c', 'copy', path.join(OUT, 'picture.mp4')]);
  console.log('画面完成', path.join(OUT, 'picture.mp4'));
}

function mux() {
  const mix = path.join(ROOT, 'docs', 'assets', 'film', 'mix');
  const video = path.join(ROOT, 'docs', 'assets', 'video');
  fs.mkdirSync(video, { recursive: true });
  for (const voice of ['male', 'female']) {
    const mixed = path.join(OUT, `mix-${voice}.wav`);
    const mp4 = path.join(video, `xiangyi-youju-film-${voice}.mp4`);
    run('ffmpeg', ['-v', 'error', '-y', '-i', path.join(OUT, 'picture.mp4'), '-i', mixed,
      // CRF 18，另设码率上限，保证每版不超过 50 MB（颗粒与纸纹很吃码率）
      '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-maxrate', '1800k', '-bufsize', '3600k',
      '-pix_fmt', 'yuv420p',
      '-r', String(FPS), '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', '-shortest', mp4]);
    console.log('成片', mp4);
  }
  fs.copyFileSync(path.join(OUT, 'xiangyi-youju-film.srt'), path.join(video, 'xiangyi-youju-film.srt'));
}

/* 另导出 WebM（VP9 + Opus），放在 artifacts/film/，不入库 */
function webm() {
  const video = path.join(ROOT, 'docs', 'assets', 'video');
  for (const voice of ['male', 'female']) {
    const out = path.join(OUT, `xiangyi-youju-film-${voice}.webm`);
    run('ffmpeg', ['-v', 'error', '-y', '-i', path.join(video, `xiangyi-youju-film-${voice}.mp4`), '-c:v', 'libvpx-vp9', '-b:v', '1800k',
      '-row-mt', '1', '-threads', '4', '-deadline', 'good', '-cpu-used', '5', '-c:a', 'libopus', '-b:a', '128k', out]);
    console.log('WebM', out);
  }
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  if (arg('--stills')) {
    const times = String(arg('--stills')).split(',').map(Number);
    const files = await stills(times, path.join(OUT, 'stills'));
    console.log(files.join('\n'));
    return;
  }
  if (arg('--sheet')) {
    const [a, b, step] = String(arg('--sheet')).split(',').map(Number);
    const times = [];
    for (let t = a; t <= b + 1e-6; t += step) times.push(Math.round(t * 1000) / 1000);
    extractClips();
    const name = arg('--name', `sheet-${a}-${b}`);
    const files = await stills(times, path.join(OUT, 'sheets', name));
    const out = contactSheet(files, path.join(OUT, 'sheets', `${name}.jpg`), Number(arg('--cols', 4)));
    console.log(out);
    return;
  }
  if (arg('--video')) { await renderVideo(); return; }
  if (arg('--mux')) { mux(); return; }
  if (arg('--webm')) { webm(); return; }
  // 全流程
  run('python3', [path.join(__dirname, 'build_timeline.py')]);
  await renderVideo();
  run('python3', [path.join(__dirname, 'score.py')]);
  run('python3', [path.join(__dirname, 'mix.py')]);
  mux();
  webm();
}

main().catch(e => { console.error(e); process.exit(1); });
