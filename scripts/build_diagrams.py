from pathlib import Path
from html import escape

OUT = Path(__file__).resolve().parents[1] / "docs" / "diagrams"
OUT.mkdir(parents=True, exist_ok=True)
PAPER, INK, RED, GREEN, MUTED = '#f5f2e9', '#223b33', '#b84631', '#e3e9dc', '#69716a'

def head(title, subtitle, height):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" viewBox="0 0 1600 {height}" role="img" aria-label="{escape(title)}">',
            f'<rect width="1600" height="{height}" fill="{PAPER}"/>',
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#7b877e"/></marker></defs>',
            '<g font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif">',
            f'<text x="65" y="76" font-size="37" fill="{INK}" font-weight="600">{escape(title)}</text>',
            f'<text x="66" y="116" font-size="19" fill="{MUTED}">{escape(subtitle)}</text>']

def box(parts, x, y, w, h, title, lines, dark=False):
    fill = INK if dark else '#fffdf7'
    fg = '#fffdf7' if dark else INK
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{fill}" stroke="#ccd2c4"/>')
    parts.append(f'<rect x="{x}" y="{y}" width="5" height="{h}" fill="{RED if dark else "#91a183"}"/>')
    parts.append(f'<text x="{x+24}" y="{y+37}" font-size="23" fill="{fg}" font-weight="600">{escape(title)}</text>')
    for i,line in enumerate(lines):
        parts.append(f'<text x="{x+24}" y="{y+71+i*28}" font-size="18" fill="{fg if dark else MUTED}">{escape(line)}</text>')

def arrow(parts, points, label=None, lx=0, ly=0):
    parts.append(f'<path d="{points}" fill="none" stroke="#7b877e" stroke-width="2" marker-end="url(#arrow)"/>')
    if label:
        parts.append(f'<text x="{lx}" y="{ly}" font-size="16" fill="{MUTED}">{escape(label)}</text>')

def save(parts, name):
    parts.extend(['</g>', '</svg>'])
    (OUT/name).write_text('\n'.join(parts) + '\n', encoding='utf-8', newline='\n')

p=head('乡艺有据｜总体技术架构', '本地模型 + 有状态Agent + 证据检索 + 确定性校验；当前为架构设计，AI后端待实现。', 1160)
box(p,65,165,445,115,'三页文化体验前端',['乡土发现 / 可信内容工坊 / 体验与共益','React + TypeScript；当前已有离线原型'])
box(p,585,165,420,115,'本地应用接口',['FastAPI · SSE阶段进度 · 体验包导出','任务快照与人工确认'])
box(p,1080,165,455,115,'现成中文模型 · 无需微调',['Qwen3-14B Q4_K_M + Ollama','使用现有RTX 5090；不调用云API'])
arrow(p,'M510 223 H580')
arrow(p,'M795 280 V335')
box(p,465,340,730,145,'LangGraph OSS · 有状态主Agent',['澄清地域 → 选择工具 → 根据缺口补查或修订','同一模型承担不同任务；预算封顶，未知可停','过程显示工具结果，不展示虚构思考'])
arrow(p,'M1307 280 V411 H1200','本地模型调用',1240,315)
box(p,65,540,335,310,'本地资料与任务存储',['SQLite + 文件 + JSONL','① 官方事实与地域版本','② 素材来源与使用边界','③ 演示/真实经营配置分开','④ 社区意愿与撤回状态','⑤ 任务、工具、模型版本记录'])
box(p,465,550,320,130,'地域检索与查证',['BM25 + 实体/时间过滤','来源ID与上下文定位'])
box(p,825,550,320,130,'讲解修订与编排',['有出处的事实与创意分开','最小修改，保留待确认'])
box(p,1185,550,350,130,'计划与账本工具',['时段 / 容量 / 预算 / 禁止事项','金额、比例与可行性由程序算'])
arrow(p,'M830 485 V515 H625 V545')
arrow(p,'M830 515 H985 V545')
arrow(p,'M985 515 H1360 V545')
arrow(p,'M400 610 H460','读取',413,597)
box(p,465,765,1070,130,'独立验证与使用边界',['检查引用存在、地域匹配、硬约束、金额总账、内容使用状态','不支持 → 待确认；条件冲突 → 有界修订；受限素材 → 不进入对外版本'],True)
arrow(p,'M625 680 V716 H1000 V760')
arrow(p,'M985 680 V710')
arrow(p,'M1360 680 V716 H1000')
box(p,465,970,1070,115,'人工确认后交付体验包',['文化讲解卡 + 活动安排 + 来源清单 + 预算与本地服务支出 + 未确认项','内部草稿、可对外使用版本、模型实时运行与历史回放明确区分'])
arrow(p,'M1000 895 V965')
p.append(f'<text x="65" y="1127" font-size="17" fill="{MUTED}">费用边界：新增软件许可/API费为零；现有硬件、电力与维护仍有成本。经营数据未接真实合作时均为演示假设。</text>')
save(p,'system-architecture.svg')

p=head('乡艺有据｜Agent任务执行与回退', '让模型决定下一步查什么，让程序确认事实引用、经营约束与费用是否成立。', 1220)
box(p,65,175,420,120,'01 接收与澄清',['地域、受众、人数、预算、时间','歧义先询问，不擅自替用户决定'])
box(p,590,175,420,120,'02 定向查证',['拆分事实 → 检索 → 查看上下文','支持 / 矛盾 / 不足 / 冲突'])
box(p,1115,175,420,120,'03 形成候选',['按证据修订讲解；读取经营配置','轻体验 / 深体验等有限候选'])
arrow(p,'M485 235 H585')
arrow(p,'M1010 235 H1110')
box(p,590,390,945,130,'04 程序验证',['来源ID存在，地域与版本一致；人数、时间、预算、容量可行','禁公开/撤回素材不得用于对外版本；金额分项相加等于总账'],True)
arrow(p,'M1325 295 V385')
box(p,65,390,420,130,'资料不足或冲突',['补检索 / 向用户澄清 / 保留未知','不以模型自信程度代替证据'])
arrow(p,'M700 295 V340 H275 V385')
box(p,65,625,420,145,'05 有界修订',['展示需要调整的条件','用户确认后修订；不放宽禁忌','最多2轮；所有模型调用统一计数'])
box(p,590,625,420,145,'05 等待确认',['条件无解或资料仍不足','保留已完成部分与缺口','不把半成品标为完成'])
box(p,1115,625,420,145,'05 通过并供人工复核',['展示证据、约束报告与账本','用户选择合法方案','确认使用范围及经营状态'])
arrow(p,'M850 520 V574 H275 V620','可修复冲突',445,562)
arrow(p,'M1000 520 V574 H800 V620','仍然未知',829,600)
arrow(p,'M1325 520 V620','检查通过',1340,577)
arrow(p,'M65 696 H35 V330 H545 V455 H585','修订后重验',67,354)
box(p,590,875,945,125,'06 输出与版本记录',['内部草稿：待确认项显式保留；对外版本：受限内容替换或排除','讲解卡 / 任务单 / 时间表 / 出处 / 费用流向 / 规则版本'])
arrow(p,'M1325 770 V870')
arrow(p,'M800 770 V870','仅内部草稿',815,826)
box(p,65,1060,1470,100,'评测与真实状态',['同模型同资料：固定强流程 vs 自适应Agent；记录误改、来源支持、整任务约束、耗时与调用数。预设演示不能当成实测。'])
arrow(p,'M1062 1000 V1055')
save(p,'agent-workflow.svg')
print('created 2 SVG diagrams')
