// 生成《乡艺有据 源码运行说明》Word 文档（黑色主色调，A4）
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, AlignmentType,
  BorderStyle, ShadingType, Header, Footer, PageNumber, PageBreak, LevelFormat, TabStopType,
} = require('docx');

const BLACK = '000000';
const GREY = '595959';
const CODEBG = 'F2F2F2';
const SERIF = { ascii: 'Times New Roman', hAnsi: 'Times New Roman', eastAsia: '宋体' };
const SANS = { ascii: 'Arial', hAnsi: 'Arial', eastAsia: '黑体' };
const MONO = { ascii: 'Consolas', hAnsi: 'Consolas', eastAsia: '宋体' };
const W = 9026; // A4 内容宽度（左右各 1440）

const run = (text, o = {}) => new TextRun({ text, font: o.font || SERIF, size: o.size || 24, bold: o.bold, color: o.color || BLACK, italics: o.italics });
const p = (text, o = {}) => new Paragraph({
  children: Array.isArray(text) ? text : [run(text, o)],
  alignment: o.align || AlignmentType.JUSTIFIED,
  spacing: { line: 360, before: o.before || 0, after: o.after ?? 120 },
  indent: o.noIndent ? undefined : { firstLine: 480 },
  keepNext: o.keepNext,
});
const h1 = (text) => new Paragraph({
  children: [run(text, { font: SANS, size: 32, bold: true })],
  spacing: { before: 360, after: 200, line: 360 }, keepNext: true, outlineLevel: 0,
  border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: BLACK, space: 4 } },
});
const h2 = (text) => new Paragraph({
  children: [run(text, { font: SANS, size: 28, bold: true })],
  spacing: { before: 240, after: 120, line: 360 }, keepNext: true, outlineLevel: 1,
});
const bullet = (text) => new Paragraph({
  children: Array.isArray(text) ? text : [run(text)],
  numbering: { reference: 'dots', level: 0 }, spacing: { line: 360, after: 60 },
});
const step = (text, ref = 'steps') => new Paragraph({
  children: Array.isArray(text) ? text : [run(text)],
  numbering: { reference: ref, level: 0 }, spacing: { line: 360, after: 60 },
});
const code = (lines) => lines.map((line, i) => new Paragraph({
  children: [new TextRun({ text: line || ' ', font: MONO, size: 19, color: BLACK })],
  shading: { type: ShadingType.CLEAR, color: 'auto', fill: CODEBG },
  spacing: { line: 276, before: i === 0 ? 60 : 0, after: i === lines.length - 1 ? 160 : 0 },
  indent: { left: 240, right: 240 }, keepLines: true, keepNext: i < lines.length - 1,
}));
const cellBorder = { style: BorderStyle.SINGLE, size: 6, color: BLACK };
const borders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder };
function table(head, rows, widths) {
  const sum = widths.reduce((a, b) => a + b, 0);
  const cols = widths.map((w) => Math.round((w / sum) * W));
  cols[cols.length - 1] += W - cols.reduce((a, b) => a + b, 0);
  const mk = (cells, header) => new TableRow({
    tableHeader: header, cantSplit: true,
    children: cells.map((text, i) => new TableCell({
      width: { size: cols[i], type: WidthType.DXA }, borders,
      shading: header ? { type: ShadingType.CLEAR, color: 'auto', fill: BLACK } : undefined,
      margins: { top: 60, bottom: 60, left: 100, right: 100 },
      children: String(text).split('\n').map((t) => new Paragraph({
        children: [run(t, { size: 21, bold: header, color: header ? 'FFFFFF' : BLACK, font: header ? SANS : SERIF })],
        spacing: { line: 300 },
      })),
    })),
  });
  return [new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: cols,
    rows: [mk(head, true), ...rows.map((r) => mk(r, false))] }), new Paragraph({ spacing: { after: 120 }, children: [] })];
}
const note = (text) => p([run('说明：', { bold: true, size: 21 }), run(text, { size: 21 })], { noIndent: true });

const NAME = '乡艺有据——可信非遗体验编排智能体';
const children = [];

// ---------- 封面 ----------
children.push(
  new Paragraph({ spacing: { before: 2600 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
    children: [run('乡艺有据', { font: SANS, size: 72, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 },
    children: [run('可信非遗体验编排智能体', { font: SANS, size: 36 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
    border: { top: { style: BorderStyle.SINGLE, size: 18, color: BLACK, space: 12 }, bottom: { style: BorderStyle.SINGLE, size: 18, color: BLACK, space: 12 } },
    children: [run('源码运行说明', { font: SANS, size: 48, bold: true })] }),
  new Paragraph({ spacing: { before: 3400 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [run('文档版本：V1.0', { size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [run('适用代码版本：源码包随附版本', { size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [run('2026 年 10 月', { size: 24 })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---------- 目录 ----------
const toc = [
  ['1', '概述'], ['2', '运行环境'], ['3', '依赖说明'], ['4', '本地大模型'], ['5', '部署与启动'],
  ['6', '使用说明'], ['7', '测试与验证'], ['8', '配置与数据'], ['9', '常见问题'], ['10', '资料来源与版权说明'],
];
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 360 }, children: [run('目　录', { font: SANS, size: 32, bold: true })] }));
for (const [n, t] of toc) {
  children.push(new Paragraph({ spacing: { line: 440 }, tabStops: [{ type: TabStopType.LEFT, position: 720 }],
    children: [run(n, { font: SANS, size: 26 }), run('\t' + t, { font: SANS, size: 26 })] }));
}
children.push(new Paragraph({ children: [new PageBreak()] }));

// ---------- 1 概述 ----------
children.push(h1('1  概述'), h2('1.1  作品简介'),
  p('乡艺有据是一套面向非遗体验活动的本地智能体系统，部署在一台电脑上即可离线运行。系统围绕三项能力设计：一是“讲对”，讲解词逐句对照官方资料核验，给出支持、矛盾、资料分歧或信息不足的结论及原文出处，并可按体验对象和讲解时长生成讲解词草稿后再核验；二是“因人而讲”，面向普通游客、亲子家庭、青少年学生、老年人、专业爱好者五类对象，在人数、预算、时长、教师和场地约束下编排活动并复算账目；三是“作品常新”，手艺人发布新作后，系统定位引用旧版本的讲解卡与手册，重新核验并经人工确认后导出游客版与组织者版手册。'),
  p('系统采用“模型理解、程序把关、人来拍板”的结构：本地大模型负责理解需求、拆分陈述与起草表达；确定性程序负责证据核对、约束求解、金额复算与版本校验；所有交付内容须经人工确认后才能导出。'),
  h2('1.2  源码包内容'),
  ...table(['路径', '内容'], [
    ['源码运行说明.pdf / .docx', '本文档'],
    ['xiangyi-youju/', '作品完整源代码，含部署与启动脚本'],
    ['xiangyi-youju/部署.bat', 'Windows 一键部署：创建环境、安装依赖、下载并校验本地大模型'],
    ['xiangyi-youju/启动.bat', 'Windows 一键启动：启动本地模型服务与业务服务，打开浏览器'],
    ['xiangyi-youju/免模型启动.bat', '不部署大模型：只安装 Python 依赖并启动业务服务，打开浏览器'],
    ['xiangyi-youju/界面原型.bat', '无需安装环境，直接打开界面原型（预设案例）'],
    ['运行记录与样例/', '本地真实运行的原始记录、导出手册样例与内部对照实验记录'],
  ], [3, 7]),
  h2('1.3  源代码结构'),
  ...table(['目录', '说明'], [
    ['backend/', 'Python 业务服务：app.py（接口）、workflow.py（智能体工作流）、evidence.py（资料检索）、planner.py（约束编排与账目）、teaching.py（分众教学与扫描）、drafts.py（讲解词生成）、audiences.py（体验对象）、store.py（版本与运行库）、bundles.py（手册导出）、model.py（本地模型调用）、config.py（配置）'],
    ['frontend/prototype/', '浏览器界面：index.html、live.js、live.css 与原创纹样素材，无需构建'],
    ['data/curated/', '官方文化资料摘录（sources.json）、演示素材与作品（materials.json）、部署预置讲解词（draft-presets.json）、公开活动资料'],
    ['data/operating/', '演示经营配置：活动模块、价格、教师、场地与容量'],
    ['data/cases/', '公开活动资料案例重建配置'],
    ['scripts/', 'setup_local.py（下载并校验运行时与模型）、start_local.py（启动）、verify_live.py（真实模型小规模检查）、browser-options.cjs（测试浏览器配置）'],
    ['tests/', 'backend/ 后端自动化测试；e2e/ 浏览器端到端测试；acceptance/ 对照实验输入'],
  ], [2.2, 7.8]),
  h2('1.4  系统架构'),
  ...table(['层次', '组成', '说明'], [
    ['界面层', '浏览器（Edge / Chrome）', '三个页面：乡土发现、可信内容工坊、体验与共益'],
    ['业务服务层', 'FastAPI + Uvicorn', '本机 127.0.0.1:8780，提供核验、编排、确认、导出、版本管理接口'],
    ['智能体工作流', 'LangGraph', '理解与拆分 → 证据检索 → 逐句核验 → 约束求解 → 分众教学与扫描，单项任务模型调用上限 8 次'],
    ['模型推理层', 'Ollama + Qwen3-14B（Q4_K_M）', '本机 127.0.0.1:11439，离线推理，不访问云端'],
    ['数据层', 'SQLite + JSON', '运行记录、版本快照与确认记录存于 SQLite；资料与配置为 JSON 文件'],
  ], [2, 3, 5]),
);

// ---------- 2 运行环境 ----------
children.push(h1('2  运行环境'), h2('2.1  硬件要求'),
  ...table(['项目', '最低要求', '推荐配置'], [
    ['处理器', '64 位 4 核', '8 核及以上'],
    ['内存', '16 GB', '32 GB'],
    ['显卡', 'NVIDIA 显卡，显存 12 GB', 'NVIDIA 显卡，显存 16 GB 及以上'],
    ['硬盘', '可用空间 40 GB（含模型约 9 GB 及安装临时文件）', 'SSD，可用空间 60 GB'],
    ['网络', '仅首次部署时下载依赖与模型需要联网', '—'],
  ], [2, 4, 4]),
  note('作品验证环境为 Windows 11 x64、NVIDIA GeForce RTX 5090（32 GB 显存），单项任务完整运行约 10 秒。无独立显卡时 Ollama 可使用 CPU 推理，可以运行但速度明显变慢。'),
  h2('2.2  软件环境'),
  ...table(['软件', '版本', '用途与获取方式'], [
    ['操作系统', 'Windows 10 / 11（64 位）', '一键部署脚本面向 Windows；Linux、macOS 可按 4.4 节手动部署'],
    ['Python', '3.12（64 位）', '运行业务服务；python.org 下载，安装时勾选 “Add python.exe to PATH” 与 “py launcher”'],
    ['Ollama', 'v0.35.0', '本地大模型推理；部署脚本自动下载到项目目录，无需单独安装'],
    ['显卡驱动', 'NVIDIA 最新稳定版', 'GPU 推理'],
    ['浏览器', 'Microsoft Edge / Google Chrome 最新版', '访问系统界面、打开导出的手册'],
    ['Node.js', '20 及以上', '仅在运行浏览器端到端测试时需要'],
  ], [2, 3, 5]),
  h2('2.3  端口与运行目录'),
  ...table(['项目', '值', '说明'], [
    ['业务服务端口', '127.0.0.1:8780', '仅绑定本机，可用 start_local.py --port 修改'],
    ['模型服务端口', '127.0.0.1:11439', '独立端口，不与其他 Ollama 实例冲突'],
    ['运行目录', 'artifacts/runtime/', 'Ollama 程序、日志与运行数据库 app.sqlite3'],
    ['模型目录', 'models/', 'GGUF 模型文件、Modelfile 与 Ollama 模型存储'],
  ], [2.4, 3, 4.6]),
  note('所有环境、模型与数据均保存在项目目录内，不修改系统环境变量，不影响电脑上的其他软件。建议将 xiangyi-youju 文件夹放在不含中文和空格的路径下（如 D:\\xiangyi-youju）。'),
);

// ---------- 3 依赖说明 ----------
children.push(h1('3  依赖说明'), h2('3.1  Python 依赖'),
  p('直接依赖见 requirements.txt，完整锁定版本（含间接依赖）见 requirements-lock.txt，部署时按锁定文件安装，保证与验证环境一致。'),
  ...table(['包', '版本', '用途', '许可'], [
    ['fastapi', '0.142.1', '业务接口服务', 'MIT'],
    ['uvicorn', '0.54.0', 'ASGI 服务器', 'BSD-3-Clause'],
    ['langgraph', '1.2.12', '智能体工作流编排', 'MIT'],
    ['httpx', '0.28.1', '访问本机模型服务', 'BSD-3-Clause'],
    ['jieba', '0.42.1', '中文分词（资料检索）', 'MIT'],
    ['rank-bm25', '0.2.2', 'BM25 检索排序', 'Apache-2.0'],
    ['pytest', '9.1.1', '自动化测试', 'MIT'],
  ], [2.2, 1.6, 3.6, 2.2]),
  h2('3.2  前端与测试依赖'),
  bullet('浏览器界面为原生 HTML、CSS 与 JavaScript，不依赖第三方前端框架，无需构建，也不加载任何外部网络资源。'),
  bullet('浏览器端到端测试使用 Playwright 1.62.1（Apache-2.0），由 package.json 与 package-lock.json 锁定。'),
  h2('3.3  模型与推理组件'),
  ...table(['组件', '版本', '许可'], [
    ['Ollama（Windows x64）', 'v0.35.0', 'MIT'],
    ['Qwen3-14B（GGUF，Q4_K_M 量化）', 'Hugging Face 修订 530227a7', 'Apache-2.0'],
  ], [4, 3.5, 2.5]),
);

// ---------- 4 本地大模型 ----------
children.push(h1('4  本地大模型'), h2('4.1  选用模型'),
  ...table(['项目', '内容'], [
    ['模型', 'Qwen3-14B（通义千问 Qwen3 系列，140 亿参数），开源权重，可商用'],
    ['量化格式', 'GGUF，Q4_K_M 量化，文件 Qwen3-14B-Q4_K_M.gguf，约 9 GB'],
    ['来源', 'Hugging Face 官方仓库 Qwen/Qwen3-14B-GGUF，固定修订 530227a7d994db8eca5ab5ced2fb692b614357fd'],
    ['推理框架', 'Ollama v0.35.0（官方 GitHub Releases 发布包）'],
    ['系统内注册名', 'xiangyi-qwen3:14b-q4_k_m'],
    ['推理参数', 'temperature 0，seed 42，上下文 8192，单次最多输出 2300 token，关闭思考模式；结构化输出按 JSON Schema 约束'],
    ['使用约束', '不微调，不调用任何云端模型接口，单项任务模型调用上限 8 次，方案修订最多 2 轮'],
  ], [2.4, 7.6]),
  h2('4.2  为什么不随包提供'),
  p('模型文件约 9 GB，超出提交材料的合理大小。源码包内的部署脚本会从官方地址下载与验证环境完全相同的版本，并逐个校验 SHA-256，确保评审复现的模型与作品验证时一致。'),
  h2('4.3  自动部署（推荐）'),
  p('双击 xiangyi-youju/部署.bat，脚本依次完成以下工作，全部文件只写入项目目录：'),
  step('创建 Python 3.12 虚拟环境 .venv，并按 requirements-lock.txt 安装依赖。'),
  step('从 Ollama 官方 GitHub Releases 下载 v0.35.0 Windows 发布包，校验 SHA-256 后解压到 artifacts/runtime/ollama/。'),
  step('从 Hugging Face 官方仓库下载 Qwen3-14B-Q4_K_M.gguf 到 models/，按仓库记录的 SHA-256 校验；下载分片进行，中断后重新运行可断点续传。'),
  step('生成 models/Modelfile；首次启动时由 start_local.py 自动注册为 xiangyi-qwen3:14b-q4_k_m。'),
  note('下载速度取决于网络，模型下载通常需要数十分钟。脚本默认使用多连接下载，可用参数调整：.venv\\Scripts\\python.exe scripts\\setup_local.py --model-workers 8。'),
  h2('4.4  手动部署（网络受限或非 Windows 系统）'),
  p('如无法使用自动部署，可按以下步骤手动完成，效果与自动部署相同。', { keepNext: true }),
  step([run('安装 Ollama：', { bold: true }), run('从 Ollama 官网（ollama.com/download）下载对应系统的安装包并安装。')], 'manual'),
  step([run('下载模型文件：', { bold: true }), run('在浏览器打开 huggingface.co/Qwen/Qwen3-14B-GGUF，在 Files 中下载 Qwen3-14B-Q4_K_M.gguf，放入 xiangyi-youju/models/。国内网络可使用镜像站 hf-mirror.com 的同名仓库。也可直接执行 ollama pull qwen3:14b 获取 Ollama 官方库中的同一模型（默认即 Q4_K_M 量化），此时把下面 Modelfile 的第一行改为 FROM qwen3:14b。')], 'manual'),
  step([run('编写 Modelfile：', { bold: true }), run('在 models/ 下新建文本文件 Modelfile，内容如下：')], 'manual'),
  ...code(['FROM ./Qwen3-14B-Q4_K_M.gguf', 'PARAMETER num_ctx 8192', 'PARAMETER temperature 0']),
  step([run('在独立端口启动模型服务并注册模型', { bold: true }), run('（在 models/ 目录下执行）：')], 'manual'),
  ...code(['# Windows（命令提示符）', 'set OLLAMA_HOST=127.0.0.1:11439', 'start ollama serve', 'ollama create xiangyi-qwen3:14b-q4_k_m -f Modelfile', '', '# Linux / macOS', 'export OLLAMA_HOST=127.0.0.1:11439', 'ollama serve &', 'ollama create xiangyi-qwen3:14b-q4_k_m -f Modelfile']),
  step([run('安装依赖并启动业务服务', { bold: true }), run('（在 xiangyi-youju/ 目录下执行）：')], 'manual'),
  ...code(['# Windows', 'py -3.12 -m venv .venv', '.venv\\Scripts\\python.exe -m pip install -r requirements-lock.txt', 'set XY_OLLAMA_URL=http://127.0.0.1:11439', '.venv\\Scripts\\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8780', '', '# Linux / macOS', 'python3.12 -m venv .venv', '.venv/bin/python -m pip install -r requirements-lock.txt', 'export XY_OLLAMA_URL=http://127.0.0.1:11439', '.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8780']),
  h2('4.5  确认模型就绪'),
  p('浏览器访问 http://127.0.0.1:8780/api/health，返回 "status": "ready" 且 "model_ready": true 即表示模型已就绪；界面顶部的运行状态也会显示本地模型可用。'),
);

// ---------- 5 部署与启动 ----------
children.push(h1('5  部署与启动'), h2('5.1  首次部署（Windows）'),
  step('安装 Python 3.12（64 位）与 NVIDIA 显卡驱动。', 'deploy'),
  step('将 xiangyi-youju 文件夹复制到不含中文和空格的路径，例如 D:\\xiangyi-youju。', 'deploy'),
  step('双击“部署.bat”，等待依赖安装与模型下载校验完成（窗口显示“部署完成”）。', 'deploy'),
  h2('5.2  启动系统'),
  p('双击“启动.bat”。脚本在本机 11439 端口启动模型服务，首次启动时自动注册模型，随后在 8780 端口启动业务服务，并自动打开 http://127.0.0.1:8780/。也可在命令行执行：'),
  ...code(['.venv\\Scripts\\python.exe scripts\\start_local.py']),
  p('关闭启动窗口或按 Ctrl+C 即停止业务服务。模型在最后一次调用约 15 分钟后自动从显存卸载；如需立即结束模型服务，可在任务管理器中结束 artifacts\\runtime\\ollama 目录下的 ollama.exe 进程。'),
  h2('5.3  免模型启动（不部署大模型）'),
  p('只想查看源码与业务服务、暂不下载约 10 GB 的大模型时，双击“免模型启动.bat”。脚本只创建虚拟环境并安装 Python 依赖（已安装则跳过），不下载、不启动模型服务，随后在 8780 端口启动业务服务并打开浏览器。等效命令：'),
  ...code(['.venv\\Scripts\\python.exe scripts\\start_local.py --api-only']),
  p('此时界面顶部显示“本地模型尚未就绪”，各项功能表现如下：'),
  ...table(['功能', '免模型启动下的表现'], [
    ['首页、资料库与作品浏览', '正常使用（16 条官方资料摘录、3 件演示作品）'],
    ['资料启用/停用、作品发布新版本', '正常使用，由程序完成，不调用模型'],
    ['按要求生成讲解词', '返回部署时预置的讲解词草稿，并标明“草稿尚未核验”'],
    ['核验并编排体验、依据最新资料重新核验', '运行记录为失败，如实提示“本地模型不可用或调用超时”，不以预设结果代替'],
    ['确认方案与导出手册', '需要一次核验通过的运行，本模式无法新产生；导出样例见“运行记录与样例/手册样例”'],
  ], [3.6, 6.4]),
  note('若此前用“启动.bat”启动过，模型服务可能仍在后台运行，此时业务服务会正常调用模型。如需确认无模型状态，先在任务管理器中结束 ollama.exe 进程。'),
  bullet([run('界面原型：', { bold: true }), run('双击“界面原型.bat”，直接用浏览器打开 frontend/prototype/index.html，无需安装任何环境。此模式使用界面中明确标注的预设案例，不连接业务服务。')]),
);

// ---------- 6 使用说明 ----------
children.push(h1('6  使用说明'), h2('6.1  界面组成'),
  ...table(['页面', '功能'], [
    ['乡土发现', '首页：作品介绍、三幕故事与适用人群'],
    ['可信内容工坊', '输入或生成讲解词，逐句核验并查看原文出处与修订建议'],
    ['体验与共益', '选择体验对象并填写人数、预算、时长、教师与场地，查看方案对比、日程、账目与本地服务报酬；管理作品版本；确认并导出手册'],
  ], [2.4, 7.6]),
  h2('6.2  典型操作流程'),
  p('页面顶部可打开“三幕演示引导”，引导只负责填入示例条件和定位按钮，所有任务仍需操作者点击执行，结论以真实运行结果为准。'),
  step([run('讲对：', { bold: true }), run('进入“可信内容工坊”，保留默认文案，点击“核验并编排体验”。系统逐句给出结论：例如“蔚县剪纸以阳刻为主”判为与来源矛盾并给出修订，展开可查看原文、出处与位置。')], 'use'),
  step([run('生成讲解词：', { bold: true }), run('在“还没有讲解词？”区域选择讲给谁、讲多久，点击“按要求生成讲解词”，草稿填入文案框并标明来源，再点击“核验并编排体验”逐句核对。')], 'use'),
  step([run('因人而讲：', { bold: true }), run('进入“体验与共益”，将体验对象改为“青少年学生”，点击“按当前条件重新编排”，查看活动组合、手作时长与账目的前后对比。')], 'use'),
  step([run('作品常新：', { bold: true }), run('在“作品常新 · 手册跟着更新”区域点击某件作品的“发布新版本”，旧手册即暂停导出；点击“依据最新资料重新核验”生成使用新作品的方案。')], 'use'),
  step([run('确认与导出：', { bold: true }), run('勾选确认说明，点击“确认当前方案”，再分别下载游客版与组织者版手册（HTML，可离线打开或打印）。')], 'use'),
  note('系统中的价格、服务报酬、教师、场地、手艺人作品与标价均为演示配置，导出的手册会明确标注。'),
);

// ---------- 7 测试与验证 ----------
children.push(h1('7  测试与验证'), h2('7.1  后端自动化测试'),
  ...code(['.venv\\Scripts\\python.exe -m pytest tests\\backend -q']),
  p('共 271 项测试，覆盖资料检索、逐句核验门禁、约束编排与金额复算、分众教学扫描、讲解词生成、版本联动与导出校验等。测试使用程序内置的模拟模型验证程序规则，不需要部署大模型。'),
  h2('7.2  界面测试'),
  ...code(['npm ci', 'set BROWSER_CHANNEL=msedge', 'npm test']),
  p('在 1440 与 390 两种宽度下检查三个页面无横向溢出、无脚本错误、中文字号不小于 12 像素。设置 BROWSER_CHANNEL=msedge 时直接使用电脑上的 Edge 浏览器；也可执行 npx playwright install chromium 安装测试浏览器。'),
  h2('7.3  真实模型检查'),
  p('部署模型并启动系统后，可运行以下检查，它们会真实调用本地模型并在运行库中留下记录：'),
  ...code(['.venv\\Scripts\\python.exe scripts\\verify_live.py', 'set LIVE_BASE_URL=http://127.0.0.1:8780', 'npm run test:live', 'npm run test:modules']),
  h2('7.4  运行记录与样例'),
  p('“运行记录与样例”目录收录本地真实运行的原始记录（输入、各步骤模型输出、核验结论、方案、账目、调用次数与耗时）、由真实运行导出的游客版与组织者版手册样例，以及 24 项任务的内部对照实验记录，可与本系统运行结果相互对照。'),
);

// ---------- 8 配置与数据 ----------
children.push(h1('8  配置与数据'), h2('8.1  数据文件'),
  ...table(['文件', '内容'], [
    ['data/curated/sources.json', '官方文化资料摘录：标题、发布方、地域、项目、原文短引、原文位置、访问日期与链接'],
    ['data/curated/materials.json', '原创界面纹样与演示作品：版本、使用状态、说明与演示标价'],
    ['data/curated/draft-presets.json', '部署时预置的讲解词草稿（模型不可用时载入，同样逐句核验）'],
    ['data/operating/demo-profile.json', '演示经营配置：八个活动模块的时长、费用、教师、场地、容量与适用对象'],
    ['artifacts/runtime/app.sqlite3', '运行库：任务输入、事件、模型结构化输出、版本快照、确认与影响关系（首次启动时自动创建）'],
  ], [3.6, 6.4]),
  h2('8.2  环境变量'),
  ...table(['变量', '默认值', '说明'], [
    ['XY_OLLAMA_URL', 'http://127.0.0.1:11439', '本地模型服务地址，只允许本机地址'],
    ['XY_DATABASE_PATH', 'artifacts/runtime/app.sqlite3', '运行库位置，须位于项目目录内；可指定新文件以空库开始'],
  ], [2.6, 3.4, 4]),
  note('首次启动时资料种子写入运行库；之后在界面中修改的作品版本与使用状态保存在运行库中，重启不会丢失。'),
);

// ---------- 9 常见问题 ----------
children.push(h1('9  常见问题'),
  ...table(['现象', '原因与处理'], [
    ['部署时提示未找到 py', '未安装 Python 3.12 或安装时未勾选 py launcher，请重新安装'],
    ['模型下载中断或很慢', '重新运行“部署.bat”即可断点续传；也可按 4.4 节手动下载后放入 models/'],
    ['启动时提示请先运行 setup_local.py', '模型或 Ollama 尚未下载完成，请先完成“部署.bat”'],
    ['界面显示本地模型不可用', '检查 11439 端口的模型服务是否在运行、模型是否注册成功；查看 artifacts/runtime/ollama.log'],
    ['单次任务明显变慢', '显存不足或未使用 GPU；确认显卡驱动正常，关闭其他占用显存的程序'],
    ['8780 端口被占用', '执行 start_local.py --port 8790 改用其他端口，浏览器访问对应地址'],
    ['想从空白数据重新演示', '设置 XY_DATABASE_PATH 指向项目内的新文件后启动，系统会自动建库并写入资料种子'],
  ], [3.4, 6.6]),
);

// ---------- 10 资料来源与版权 ----------
children.push(h1('10  资料来源与版权说明'),
  bullet('文化资料摘自中国非物质文化遗产网、河北省文化和旅游厅等官方公开资料，版权归原发布方；系统仅保存短摘录、出处与位置，用于逐句核验。'),
  bullet('界面纹样“纸上庭园”为作品原创；系统中的演示作品、手艺人、价格、教师与场地均为虚构演示数据。'),
  bullet('Qwen3 模型权重遵循 Apache-2.0 许可，Ollama 遵循 MIT 许可，其余第三方组件遵循第 3 章所列各自许可。'),
  bullet('作品源代码为参赛作品原创，仅供大赛评审查看与复现使用。'),
);

const doc = new Document({
  creator: '', lastModifiedBy: '', title: NAME + ' 源码运行说明',
  styles: { default: { document: { run: { font: SERIF, size: 24, color: BLACK } } } },
  numbering: { config: ['steps', 'manual', 'deploy', 'use'].map((reference) => ({ reference, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 360 } }, run: { font: SERIF } } }] }))
    .concat([{ reference: 'dots', levels: [{ level: 0, format: LevelFormat.BULLET, text: '●', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 300 } }, run: { size: 16 } } }] }]) },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } }, titlePage: true },
    headers: {
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BLACK, space: 4 } },
        children: [run(NAME + '  源码运行说明', { size: 18, color: GREY })] })] }),
      first: new Header({ children: [new Paragraph({ children: [] })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: ['— ', PageNumber.CURRENT, ' —'], font: SERIF, size: 18, color: GREY })] })] }),
      first: new Footer({ children: [new Paragraph({ children: [] })] }),
    },
    children,
  }],
});
Packer.toBuffer(doc).then((buffer) => { fs.writeFileSync(process.argv[2], buffer); console.log('written', process.argv[2]); });
