// 生成《乡艺有据 评委操作手册》Word 文档（黑色主色调，A4，与《源码运行说明》同一版式）
// 用法：node scripts/submission/build-judge-manual.cjs 评委操作手册.docx
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, AlignmentType,
  BorderStyle, ShadingType, Header, Footer, PageNumber, PageBreak, LevelFormat, TabStopType, ImageRun,
} = require('docx');

const FIG = path.join(__dirname, '../../docs/submission/judge-manual');
const BLACK = '000000';
const GREY = '595959';
const SERIF = { ascii: 'Times New Roman', hAnsi: 'Times New Roman', eastAsia: '宋体' };
const SANS = { ascii: 'Arial', hAnsi: 'Arial', eastAsia: '黑体' };
const W = 9026; // A4 内容宽度（左右各 1440）
const IMG_W = 590; // 图片显示宽度（像素，约等于内容宽度）

const run = (text, o = {}) => new TextRun({ text, font: o.font || SERIF, size: o.size || 24, bold: o.bold, color: o.color || BLACK });
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
const h3 = (text) => new Paragraph({
  children: [run(text, { font: SANS, size: 24, bold: true })],
  spacing: { before: 160, after: 80, line: 360 }, keepNext: true, outlineLevel: 2,
});
const label = (text) => new Paragraph({
  children: [run(text, { font: SANS, size: 22, bold: true })],
  spacing: { before: 120, after: 60, line: 320 }, keepNext: true,
});
const bullet = (text) => new Paragraph({
  children: Array.isArray(text) ? text : [run(text)],
  numbering: { reference: 'dots', level: 0 }, spacing: { line: 360, after: 60 },
});
// 每个操作流程使用独立编号，保证从 1 开始、连续不跳号
const STEP_REFS = [];
function procedure(ref, items, keepLast = false) {
  STEP_REFS.push(ref);
  return items.map((item, i) => new Paragraph({
    children: Array.isArray(item) ? item : [run(item)],
    numbering: { reference: ref, level: 0 }, spacing: { line: 360, after: 60 },
    keepNext: keepLast || i < items.length - 1, keepLines: true,
  }));
}
const b = (text) => run(text, { bold: true });
const t = (text) => run(text);

const cellBorder = { style: BorderStyle.SINGLE, size: 6, color: BLACK };
const borders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder };
let tableNo = 0;
let figureNo = 0;
const TABLE_TITLES = [];
const FIGURE_TITLES = [];
function table(title, head, rows, widths) {
  tableNo += 1; TABLE_TITLES.push(`表 ${tableNo}  ${title}`);
  const sum = widths.reduce((a, c) => a + c, 0);
  const cols = widths.map((w) => Math.round((w / sum) * W));
  cols[cols.length - 1] += W - cols.reduce((a, c) => a + c, 0);
  // 除最后一行外，各行段落均与下一段同页，使表格不被拆到两页
  const mk = (cells, header, last) => new TableRow({
    tableHeader: header, cantSplit: true,
    children: cells.map((text, i) => new TableCell({
      width: { size: cols[i], type: WidthType.DXA }, borders,
      shading: header ? { type: ShadingType.CLEAR, color: 'auto', fill: BLACK } : undefined,
      margins: { top: 60, bottom: 60, left: 100, right: 100 },
      children: String(text).split('\n').map((line) => new Paragraph({
        children: [run(line, { size: 21, bold: header, color: header ? 'FFFFFF' : BLACK, font: header ? SANS : SERIF })],
        spacing: { line: 300 }, keepNext: !last, keepLines: true,
      })),
    })),
  });
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 80 },
      children: [run(`表 ${tableNo}  ${title}`, { font: SANS, size: 21, bold: true })] }),
    new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: cols, rows: [mk(head, true, false), ...rows.map((r, i) => mk(r, false, i === rows.length - 1))] }),
    new Paragraph({ spacing: { after: 120 }, children: [] }),
  ];
}
function figure(file, title, widthPx = IMG_W) {
  figureNo += 1; FIGURE_TITLES.push(`图 ${figureNo}  ${title}`);
  const data = fs.readFileSync(path.join(FIG, file));
  const w = data.readUInt32BE(16), h = data.readUInt32BE(20); // PNG 尺寸
  const frame = { style: BorderStyle.SINGLE, size: 6, color: BLACK, space: 1 };
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 60 },
      border: { top: frame, bottom: frame, left: frame, right: frame },
      children: [new ImageRun({ type: 'png', data, transformation: { width: widthPx, height: Math.round((h * widthPx) / w) },
        altText: { title, description: title, name: file } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [run(`图 ${figureNo}  ${title}`, { font: SANS, size: 21, bold: true })] }),
  ];
}
const note = (text) => p([run('说明：', { bold: true, size: 21 }), run(text, { size: 21 })], { noIndent: true });

const NAME = '乡艺有据——可信非遗体验编排智能体';
const children = [];

// ---------- 封面 ----------
children.push(
  new Paragraph({ spacing: { before: 2600 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 }, children: [run('乡艺有据', { font: SANS, size: 72, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [run('可信非遗体验编排智能体', { font: SANS, size: 36 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
    border: { top: { style: BorderStyle.SINGLE, size: 18, color: BLACK, space: 12 }, bottom: { style: BorderStyle.SINGLE, size: 18, color: BLACK, space: 12 } },
    children: [run('评委操作手册', { font: SANS, size: 48, bold: true })] }),
  new Paragraph({ spacing: { before: 3400 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [run('文档版本：V1.0', { size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [run('适用代码版本：源码包随附版本', { size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [run('2026 年 10 月', { size: 24 })] }),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---------- 目录 ----------
const TOC = [['1', '概述'], ['2', '运行方式与启动'], ['3', '主线操作流程'], ['4', '免模型启动与界面原型的查看范围'],
  ['5', '运行记录与样例的核对'], ['6', '数据与使用边界'], ['7', '常见问题']];
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 360 }, children: [run('目　录', { font: SANS, size: 32, bold: true })] }));
for (const [n, title] of TOC) {
  children.push(new Paragraph({ spacing: { line: 440 }, tabStops: [{ type: TabStopType.LEFT, position: 720 }],
    children: [run(n, { font: SANS, size: 26 }), run('\t' + title, { font: SANS, size: 26 })] }));
}
children.push(new Paragraph({ children: [new PageBreak()] }));

// ---------- 1 概述 ----------
children.push(h1('1  概述'), h2('1.1  作品简介'),
  p('乡艺有据是一套面向乡村非遗体验活动的本地智能体系统，部署在一台电脑上即可离线运行。系统以河北蔚县剪纸为主线案例，提供三项能力：一是讲解核验，讲解词逐句对照官方资料，给出“来源支持”“与来源矛盾”“资料存在分歧”或“信息不足”的结论及原文出处；二是因人编排，按体验对象及人数、预算、时长、教师和场地条件组合活动，由程序复算日程与账目；三是作品更新，手艺人发布作品新版本后，系统使引用旧版本的确认失效，重新核验后再交付。'),
  p('系统分工为：本地大模型负责理解需求、拆分陈述与起草表达；业务程序负责资料检索、约束求解、金额复算与版本校验；所有交付内容须经人工确认后方可导出游客版与组织者版手册。'),
  h2('1.2  提交材料构成'),
  ...table('提交材料构成', ['材料', '内容'], [
    ['附件 1  项目简表', '项目背景、立项思路、解决方案、商业模式与关键指标'],
    ['附件 2  项目说明书', '立项依据、项目创新内容、实施方案、应用前景分析'],
    ['附件 3  项目商业计划书', '方案概述、产品服务化、市场与竞争、商业模式、预期经济效益'],
    ['乡艺有据-源码与程序', '作品源代码与部署、启动脚本；《源码运行说明》；“运行记录与样例”目录'],
    ['评委操作手册', '本文档'],
  ], [3, 7]),
  h2('1.3  本手册的使用'),
  p('本手册说明运行方式的选择、主线操作步骤及运行记录的核对方法。环境安装、依赖、本地大模型部署与测试方法见《源码运行说明》。手册中的界面截图与预期结果均取自作品在验证环境（Windows 11，NVIDIA GeForce RTX 5090 显卡）中的真实运行。'),
);

// ---------- 2 运行方式与启动 ----------
children.push(h1('2  运行方式与启动'), h2('2.1  运行方式'),
  p('作品提供三种运行方式，可按评审电脑的条件选择。第 3 章主线流程需在完整部署方式下进行；不具备完整部署条件时，可按第 4 章查看界面与部分功能，并按第 5 章核对真实运行记录。'),
  ...table('运行方式', ['方式', '运行条件', '可查看内容', '启动文件'], [
    ['界面原型', '任意装有浏览器的电脑，无需安装', '界面布局与预设案例；界面标注“交互设计原型 · 预设案例，未接模型”', '界面原型.bat'],
    ['免模型启动', 'Windows 10/11（64 位），Python 3.12，安装依赖时需联网', '真实业务服务、资料与作品目录、作品发布新版本、预置讲解词草稿；核验与编排如实提示模型不可用', '免模型启动.bat'],
    ['完整部署', '在免模型启动条件基础上：NVIDIA 显卡显存 12 GB 及以上，内存 16 GB 及以上，硬盘可用空间 40 GB；首次部署下载约 10 GB', '全部功能，包括第 3 章主线流程', '部署.bat（首次）\n启动.bat'],
  ], [1.6, 3.2, 3.6, 1.6]),
  h2('2.2  完整部署与启动'),
  ...procedure('deploy', [
    '安装 Python 3.12（64 位），安装时勾选“Add python.exe to PATH”与“py launcher”；安装 NVIDIA 显卡驱动。',
    '解压“乡艺有据-源码与程序.zip”，将其中的 xiangyi-youju 文件夹放到不含中文和空格的路径下，例如 D:\\xiangyi-youju。',
    '双击 xiangyi-youju 文件夹中的“部署.bat”，等待窗口显示“部署完成”。模型下载中断时，重新运行该文件即可断点续传。',
    '双击“启动.bat”。启动窗口须保持开启，约 12 秒后浏览器自动打开 http://127.0.0.1:8780/。',
    '确认页面顶部显示“Qwen 本地引擎已就绪”。如显示“本地模型尚未就绪”，点击右上角“检查环境 ↗”重新检测；仍未就绪时，按《源码运行说明》第 9 章处理。',
  ]),
  h2('2.3  免模型启动'),
  ...procedure('nomodel', [
    '安装 Python 3.12（64 位），安装时勾选“Add python.exe to PATH”与“py launcher”。',
    '解压“乡艺有据-源码与程序.zip”，将其中的 xiangyi-youju 文件夹放到不含中文和空格的路径下。',
    '双击“免模型启动.bat”。脚本安装 Python 依赖（不下载大模型）后启动业务服务，并自动打开 http://127.0.0.1:8780/。启动窗口须保持开启。',
    '页面顶部显示“本地模型尚未就绪”，属本方式的正常状态。可查看的内容见第 4 章。',
  ]),
  note('只查看界面时，双击“界面原型.bat”即可，无需安装任何环境。该方式不连接业务服务。'),
  h2('2.4  界面构成'),
  p('系统界面由顶部导航、运行状态栏和三个页面组成（图 1）。'),
  ...figure('fig-home.png', '系统首页（乡土发现）', 470),
  ...table('界面构成', ['位置', '名称', '作用'], [
    ['顶部导航', '乡土发现', '首页：作品主张、三幕说明与适用人群'],
    ['', '可信内容工坊', '输入或生成讲解词，逐句核验，查看原文出处与修订'],
    ['', '体验与共益', '设置体验对象与条件，比较方案，查看日程与账目，管理作品版本，确认并导出手册'],
    ['运行状态栏', '状态文字', '显示当前任务状态，例如“核验完成，等待人工确认”'],
    ['', '查看运行信息', '显示任务编号、模型调用次数与耗时'],
    ['', '投屏大字', '放大界面字号，便于投屏查看'],
    ['', '三幕演示', '按主线填入示例条件并定位下一步按钮；不代为提交、确认或导出'],
    ['', '历史记录', '选择本机已保存的运行，仅回放结果'],
    ['', '检查环境 ↗', '重新检测本地模型是否就绪'],
  ], [2, 2.4, 5.6]),
);

// ---------- 3 主线操作流程 ----------
children.push(h1('3  主线操作流程'),
  p('主线以同一场蔚县剪纸体验为例，依次完成讲解核验、按体验对象重新编排、作品发布新版本后重新核验、人工确认与导出。3.1 至 3.4 节须在完整部署方式下按顺序操作，后一节以前一节产生的运行结果为基础；3.5 节各项在 3.4 节完成后进行。新部署的系统即处于初始数据状态，重复操作前须先恢复初始数据（见表 10）。'),
  p('每次核验或编排为一次本地任务，任务执行期间按钮显示“正在执行本地任务…”。验证环境中单次任务约 11 至 16 秒，模型调用 6 至 7 次。系统业务流程与分工见图 2。'),
  ...figure('fig-flow.png', '业务流程与分工'),
);

children.push(h2('3.1  讲解核验'),
  ...procedure('act1', [
    '点击运行状态栏中的“三幕演示”，页面出现演示引导条。',
    [t('在引导条中点击“填入主线案例”。系统切换到“可信内容工坊”，填入讲解地域“河北省蔚县”、非遗项目“剪纸”及待核验文案：'), b('蔚县剪纸以阳刻为主，阴刻为辅。蔚县剪纸善于多色点染。工坊每天开放并且无需预约。')],
    '点击高亮显示的“核验并编排体验”按钮，等待任务完成。',
    '在右侧“查证与修订”区域逐条查看结论。展开证据可查看原文、原文位置及“到原始资料核对 ↗”链接（图 3）。',
  ], true),
  label('预期结果'),
  ...table('讲解核验的预期结果', ['陈述', '类型', '结论', '处理'], [
    ['蔚县剪纸以阳刻为主，阴刻为辅。', '文化事实', '与来源矛盾', '修订为“蔚县剪纸以阴刻为主，阳刻为辅。”，修订文本再次核验获来源支持'],
    ['蔚县剪纸善于多色点染。', '文化事实', '来源支持', '保留原句'],
    ['工坊每天开放并且无需预约。', '经营承诺', '信息不足', '提示另行核实，不进入游客手册'],
  ], [3, 1.5, 1.6, 3.9]),
  p('同一任务同时生成首个活动方案：基础剪纸手作 · 2 环节组合，全程 70 分钟，其中手作 50 分钟，演示总价 574 元。'),
  ...figure('fig-act1.png', '讲解核验结果与原文出处', 400),
);

children.push(h2('3.2  按体验对象重新编排'),
  ...procedure('act2', [
    '在演示引导条中点击“换成：青少年学生”。系统切换到“体验与共益”，将体验对象设为“青少年学生”，编排方式设为“按需求组合活动模块”，文字需求设为“讲清楚工艺特色，留出观察和提问的时间。”。',
    '点击高亮显示的“按当前条件重新编排”按钮，等待任务完成。',
    '查看方案对比区（图 4）、候选方案、日程卡片及面向学生的讲解与互动问题；展开“查看每笔服务报酬与成本”可查看逐项账目。',
  ], true),
  label('预期结果'),
  ...table('方案前后对比', ['项目', '上一次方案（普通游客）', '本次方案（青少年学生）'], [
    ['方案', '基础剪纸手作 · 2 环节组合', '深度剪纸手作 · 4 环节组合'],
    ['活动环节', '乡土入门讲解、基础剪纸手作', '乡土入门讲解、点染色彩观察、深度剪纸手作、手作延伸练习'],
    ['全程时长', '70 分钟', '115 分钟'],
    ['手作时长', '50 分钟', '80 分钟'],
    ['演示总价', '574 元', '874 元'],
    ['其中本地服务报酬', '380 元', '584 元'],
  ], [2.4, 3.6, 4]),
  note('不使用演示引导时，可手动完成同样设置：在“可信内容工坊”中将“这场体验，您有什么想法？”改为上述文字需求，在“体验与共益”中将体验对象改为“青少年学生”，再点击“按当前条件重新编排”。金额均为演示经营配置的测算结果。'),
  ...figure('fig-act2.png', '按体验对象重新编排后的方案对比'),
);

children.push(h2('3.3  作品发布新版本后重新核验'),
  ...procedure('act3', [
    '在演示引导条中点击“定位到作品上新”。页面定位到“作品常新 · 手册跟着更新”区域中“演示作品·花卉窗花”的“发布新版本”按钮。',
    '点击“发布新版本”。该作品变为“演示作品·花卉窗花（新作）”第 2 版；运行状态显示“资料或作品有更新，需重新核验”，确认区显示“关联状态变化，本次确认已失效。”，预览、确认与下载按钮均不可用；下方列出受影响的讲解卡与体验方案（图 5）。',
    '点击“依据最新资料重新核验 ↗”，等待任务完成。',
    '任务完成后，运行状态恢复为“核验完成，等待人工确认”，新方案引用作品第 2 版。',
  ], true),
  ...figure('fig-act3.png', '作品发布新版本后，旧确认失效并列出受影响内容', 520),
);

children.push(h2('3.4  人工确认与手册导出'),
  ...procedure('confirm', [
    '在“把一场体验，交到游客手中。”区域点击游客版的“打开精美预览 ↗”查看手册预览稿（图 6），可在预览窗口右上角切换“组织者版”。查看后点击右上角“×”关闭预览窗口。',
    '勾选“我已核对本次讲解与选中方案，知悉演示经营数据及素材使用边界。”。',
    '点击“确认当前方案 ✓”。页面提示“已保存人工确认。可导出游客版与组织者版体验包。”。',
    '分别点击游客版与组织者版下方的“下载 HTML ↓”，保存两份手册。手册为单个 HTML 文件，可用浏览器离线打开或打印。',
  ]),
  ...table('两版手册的内容', ['内容', '游客版', '组织者版'], [
    ['文化讲解', '仅含核验通过的讲解，附可核对的出处', '讲解及每条来源的编号与使用状态'],
    ['活动日程', '时间与环节', '时间、环节及占用的教师与场地'],
    ['账目', '人均费用', '逐行账本：单价、数量、小计与收款角色'],
    ['手艺人作品', '展示当前版本作品与演示标价', '同左，并注明作品版本与记录版本'],
  ], [2, 4, 4]),
  ...figure('fig-preview.png', '游客版手册预览', 430),
);

children.push(h2('3.5  补充操作'),
  p('以下三项相互独立，用于查看系统在生成、资源不足和超出能力范围时的处理方式。请按 3.5.1 至 3.5.3 的顺序进行；3.5.3 的第 1 步先恢复默认的人数与资源条件。'),
  h3('3.5.1  按要求生成讲解词'),
  ...procedure('draft', [
    '进入“可信内容工坊”，在“还没有讲解词？”区域将“讲给谁”设为“青少年学生”，“讲多久”设为“约 5 分钟”。',
    '点击“按要求生成讲解词 ↗”。草稿填入待核验文案框，下方注明依据的资料条数及“尚未核验”。',
    '点击“核验并编排体验”，等待任务完成。',
  ], true),
  p('预期结果：验证运行中，草稿拆分为 8 条陈述，7 条获来源支持，“让作品更生动。”标为信息不足。', { noIndent: true }),
  h3('3.5.2  接待资源不足'),
  ...procedure('resource', [
    '进入“体验与共益”，在“编排条件”中点击“填入「超容量且资源不足」”。系统填入参与人数 16 人、小组容量上限 8 人、手作教师 1 人、可用场地 1 间。',
    '点击“按当前条件重新编排”，等待任务完成。',
  ], true),
  p('预期结果：方案区显示“条件已核算，当前无法接待”，并列出具体缺口，例如“人数16超过单组容量8；不能自动拆组或虚构并行接待。”；系统不自动拆组或增加教师，候选方案均不可确认或导出。', { noIndent: true }),
  h3('3.5.3  超出配置范围的需求'),
  ...procedure('stop', [
    '在“体验与共益”的“编排条件”中点击“重置”，恢复人数、预算、时长与资源的默认值。',
    '进入“可信内容工坊”，将“这场体验，您有什么想法？”的内容替换为“需要安排英语讲解”。',
    '点击“核验并编排体验”，等待任务完成。',
  ], true),
  p('预期结果：系统停止编排，提示“文字需求存在矛盾或超出当前模块能力，请先澄清：需要安排英语讲解”，不虚构未配置的服务。', { noIndent: true }),
);

// ---------- 4 免模型启动与界面原型 ----------
children.push(h1('4  免模型启动与界面原型的查看范围'),
  p('未部署本地大模型时，系统不以预设结果代替真实运行。两种方式下各项功能的表现见表 7。'),
  ...table('免模型启动与界面原型的查看范围', ['功能', '免模型启动', '界面原型'], [
    ['三个页面的界面浏览', '可用', '可用（预设案例）'],
    ['资料与作品目录，作品发布新版本', '可用，由程序完成，不调用模型', '不可用'],
    ['按要求生成讲解词', '载入部署时预置的讲解词草稿，并注明需要核验', '不可用'],
    ['讲解核验与活动编排', '运行记录为失败，如实提示“本地模型不可用或调用超时”', '点击“播放核验演示”播放预设核验过程；编排页为预设轻、深体验套餐'],
    ['人工确认与手册导出', '无法新产生，可查看第 5 章的手册样例', '不可用'],
  ], [3, 3.8, 3.2]),
);

// ---------- 5 运行记录与样例 ----------
children.push(h1('5  运行记录与样例的核对'),
  p('“乡艺有据-源码与程序/运行记录与样例”目录收录本地真实运行的原始记录、由真实运行导出的手册样例和内部对照实验记录，均由系统自动写出，未经人工改动。'),
  h2('5.1  真实运行记录'),
  p('“真实运行记录”目录下的 5 个 JSON 文件对应第 3 章的主线与补充操作，可用文本编辑器或浏览器打开。每条记录包含输入条件、各步骤模型输出、逐句结论、方案与账目、模型调用次数与耗时。'),
  ...table('真实运行记录', ['文件', '对应章节', '关键结果'], [
    ['01-讲对-讲解逐句核验-bca1a47e.json', '3.1', '“阳刻为主”判为与来源矛盾并修订；“多色点染”获来源支持；营业承诺标为信息不足'],
    ['02-因人而讲-换成青少年学生-8ef7b118.json', '3.2', '活动 2→4 个环节，手作 50→80 分钟，全程 70→115 分钟，演示总价 874 元'],
    ['03-作品常新-新作发布后重新核验-293b3c15.json', '3.3', '引用旧版作品的运行被标为待更新；新运行使用作品第 2 版'],
    ['04-按要求生成讲解词后核验-000174e4.json', '3.5.1', '8 条陈述中 7 条获来源支持，1 条标为信息不足'],
    ['05-未配置服务停下询问-eabb33d7.json', '3.5.3', '提出“需要安排英语讲解”后停止编排并请使用者澄清'],
  ], [4.4, 1.2, 4.4]),
  h2('5.2  手册样例'),
  p('“手册样例”目录中的“游客版手册-预览稿.html”与“组织者版手册-预览稿.html”由第 3 条运行记录经系统导出程序生成，可用浏览器直接打开或打印。预览稿标注“待人工确认预览稿”；正式导出须在系统中完成人工确认。'),
  h2('5.3  内部对照实验'),
  p('“内部对照实验”目录记录 24 项预先冻结的任务。每项任务分别由智能体工作流与同模型、同资料、同工具的固定流程各运行一次，结果如表 9。“comparison-protocol.md”为实验方案，“results.md”为结果说明，“首次运行原始记录”为全部原始输出。'),
  ...table('内部对照实验结果', ['任务类别', '题数', '智能体工作流通过', '固定流程通过'], [
    ['完整交付：可行方案、教学内容、确认后双版导出', '12', '12', '10'],
    ['必要确认：识别文字与表单冲突，不静默覆盖', '6', '6', '5'],
    ['正确拒绝：无解时给出具体冲突', '6', '5', '3'],
  ], [5.2, 1.2, 1.8, 1.8]),
  note('该实验为团队内部验收，题目由团队依据已知功能边界编写，不是第三方检测；未通过的 1 项原样保留在原始记录中。'),
);

// ---------- 6 数据与使用边界 ----------
children.push(h1('6  数据与使用边界'),
  bullet('文化资料为 16 条官方公开资料短摘录，来自中国非物质文化遗产网、河北省文化和旅游厅和上海市金山区人民政府，每条保存原文短引、出处、位置与访问日期。'),
  bullet('价格、服务报酬、教师、场地、手艺人作品与标价均为演示配置，不代表真实报价、订单、收入或合作；导出的手册中已明确标注。'),
  bullet('活动编排范围为单组、单场地、单日活动，在已配置的 8 个活动模块中组合；人数、报价、教师和场地不得由模型修改。'),
  bullet('系统为单机本地工作台，不设账号登录；作品版本与资料使用状态由操作者在界面中变更，变更后旧确认自动失效。'),
  bullet('系统全程离线运行，不调用云端模型接口，不产生模型调用费用。'),
);

// ---------- 7 常见问题 ----------
children.push(h1('7  常见问题'),
  ...table('常见问题', ['现象', '原因与处理'], [
    ['浏览器显示无法访问 127.0.0.1:8780', '业务服务尚未启动完成，或启动窗口已关闭。重新运行启动文件，并保持启动窗口开启'],
    ['页面顶部显示“本地模型尚未就绪”', '免模型启动时属正常状态。完整部署时点击“检查环境 ↗”；仍未就绪，按《源码运行说明》第 9 章处理'],
    ['出现“您写下的想法，与表单有一点不同。”', '文字需求与表单条件不一致，系统不自行覆盖。在卡片中选择“按表单条件继续”或“采纳文字里的条件 →”'],
    ['“确认当前方案 ✓”无法点击', '须先勾选确认说明；条件改动后须重新编排；作品或资料更新后须点击“依据最新资料重新核验 ↗”'],
    ['演示引导提示“作品都已是最新版”', '作品已发布过新版本。按下一行恢复初始数据后重新操作'],
    ['恢复初始数据', '关闭启动窗口，将 xiangyi-youju\\artifacts\\runtime 目录中以 app.sqlite3 开头的文件移至其他位置，再次启动即自动建立初始数据；此前的历史记录不再显示'],
    ['单次任务耗时明显较长', '显存不足或未使用显卡推理。关闭其他占用显存的程序后重试'],
  ], [3.4, 6.6]),
);

const doc = new Document({
  creator: '', lastModifiedBy: '', title: NAME + ' 评委操作手册',
  styles: { default: { document: { run: { font: SERIF, size: 24, color: BLACK } } } },
  numbering: { config: STEP_REFS.map((reference) => ({ reference, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 360 } }, run: { font: SERIF } } }] }))
    .concat([{ reference: 'dots', levels: [{ level: 0, format: LevelFormat.BULLET, text: '●', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 300 } }, run: { size: 16 } } }] }]) },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } }, titlePage: true },
    headers: {
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BLACK, space: 4 } },
        children: [run(NAME + '  评委操作手册', { size: 18, color: GREY })] })] }),
      first: new Header({ children: [new Paragraph({ children: [] })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: ['— ', PageNumber.CURRENT, ' —'], font: SERIF, size: 18, color: GREY })] })] }),
      first: new Footer({ children: [new Paragraph({ children: [] })] }),
    },
    children,
  }],
});
if (new Set(STEP_REFS).size !== STEP_REFS.length) throw new Error('操作流程编号引用重复，编号会串号');
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(process.argv[2], buffer);
  console.log('written', process.argv[2]);
  console.log(TABLE_TITLES.join('\n'));
  console.log(FIGURE_TITLES.join('\n'));
});
