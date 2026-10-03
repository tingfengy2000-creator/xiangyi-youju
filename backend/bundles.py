"""从已确认的结果快照导出 HTML，不再调用模型或生成新事实。"""

from __future__ import annotations

from html import escape
from base64 import b64encode
from pathlib import Path
from urllib.parse import urlparse

from .planner import solve_plans
from .teaching import render_teaching_html, validate_teaching


STATUS_LABELS = {
    "supported": "来源支持", "contradicted": "与来源矛盾",
    "conflicting": "资料分歧", "insufficient": "信息不足",
}


def _text(value) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _money(cents) -> str:
    if isinstance(cents, bool) or not isinstance(cents, int):
        raise ValueError("体验包金额必须为整数分")
    return f"¥{cents // 100:,}.{cents % 100:02d}"


def _mapping(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {item["id"]: item for item in value if isinstance(item, dict) and "id" in item}
    return {}


def _restricted(item) -> bool:
    if not isinstance(item, dict):
        return False
    status = item.get("usage_status", item.get("use_status", item.get("status", "available")))
    return item.get("usable") is False or status not in ("available", "active", "public", "supported")


def _source_link(evidence: dict) -> str:
    url = str(evidence.get("url", ""))
    parsed = urlparse(url)
    title = _text(evidence.get("title") or evidence.get("source_id") or "来源")
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return f'<a href="{_text(url)}" target="_blank" rel="noopener noreferrer">{title} ↗</a>'
    return title


def _confirmed(approval) -> bool:
    return isinstance(approval, dict) and (approval.get("confirmed") is True or approval.get("status") == "confirmed")


def _validate_run(run: dict, preview: bool = False):
    if not isinstance(run, dict):
        raise ValueError("导出需要完整运行快照")
    if run.get("status") in ("invalidated", "failed", "running", "blocked", "cancelled"):
        raise ValueError("当前运行已失效、未完成或失败，不能导出；请重新核验并确认")
    if run.get("mode") not in ("live", "replay", "preset"):
        raise ValueError("须明确标识真实运行、历史回放或预设案例")
    if preview and (run.get("status") not in ("awaiting_review", "confirmed")
                    or run.get("validation", {}).get("passed") is not True):
        raise ValueError("预览仅适用于已通过校验、待人工确认或已确认的运行")
    if not preview and not _confirmed(run.get("approval")):
        raise ValueError("须先完成负责人确认再导出体验包")
    plan = run.get("plan")
    if not isinstance(plan, dict) or plan.get("feasible") is not True or plan.get("conflicts"):
        raise ValueError("所选方案未通过约束校验，不能导出")
    if plan.get("is_demo") is not True:
        raise ValueError("首版仅支持演示测算体验包")
    approval = run.get("approval") or {}
    if not preview and approval.get("plan_id") and approval["plan_id"] != plan.get("id"):
        raise ValueError("负责人确认的方案与当前方案不一致")
    if not preview and "run_version" in approval and "version" in run and approval["run_version"] != run["version"]:
        raise ValueError("负责人确认版本已过期，须重新确认")
    planning = run.get("planning", {})
    profile = planning.get("profile_snapshot")
    requirements = planning.get("requirements_snapshot")
    if not isinstance(profile, dict) or not isinstance(requirements, dict):
        raise ValueError("缺少经营配置或需求快照，无法复算体验包")
    effective_requirements = run.get("effective_requirements", run.get("requirements"))
    if effective_requirements is not None:
        for key, value in effective_requirements.items():
            if key in requirements and requirements[key] != value:
                raise ValueError("运行需求与已校验需求快照不一致")
    recalculated = solve_plans(requirements, profile)
    checked = next((item for item in recalculated["candidates"] if item["id"] == plan.get("id")), None)
    if checked is None or not checked["feasible"]:
        raise ValueError("当前快照重新计算后不可行")
    for field in (
        "duration_minutes", "total_cents", "per_person_cents", "local_service_cents",
        "material_cents", "operations_cents", "paper_units", "schedule", "ledger", "title",
    ):
        if checked[field] != plan.get(field):
            raise ValueError(f"方案{field}与程序复算不一致，禁止导出")
    return checked, requirements, profile


CSS = """
:root{--paper:#f6f3eb;--ink:#223932;--muted:#727767;--red:#b94633;--line:#d9dccf;--white:#fffdf8}
*{box-sizing:border-box}body{margin:0;background:#e5e5dc;color:var(--ink);font:14px/1.85 "Microsoft YaHei","PingFang SC",sans-serif}
.sheet{max-width:1060px;margin:36px auto;background:var(--paper);box-shadow:0 10px 55px #22393214;padding:42px 54px}
.brand{display:flex;align-items:center;gap:14px;padding-bottom:24px;border-bottom:1px solid var(--line)}
.seal{background:var(--red);color:var(--paper);font:20px/1.2 SimSun,serif;letter-spacing:3px;padding:9px 5px 9px 8px;transform:rotate(-3deg)}
.wordmark{font:25px SimSun,serif;letter-spacing:5px}.submark,.eyebrow{font-size:10px;letter-spacing:2px;color:var(--muted)}
.edition{margin-left:auto;font-size:11px;color:var(--red)}.hero{margin:30px 0 26px;padding:35px;background:var(--ink);color:var(--paper);position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;width:170px;height:170px;border:1px solid #d3b58d40;border-radius:50%;right:-40px;top:-50px;box-shadow:0 0 0 24px #d3b58d10,0 0 0 50px #d3b58d10}
.hero-copy{position:relative;z-index:1;max-width:77%}.hero-art{position:absolute;width:245px;height:245px;object-fit:contain;right:-45px;top:-45px;opacity:.32;transform:rotate(-10deg)}.art-note{font-size:9px!important;color:#bfcbbb!important;margin-top:13px!important}
.hero .eyebrow{color:#c5ccbc}.hero h1{font:34px/1.5 SimSun,serif;letter-spacing:2px;margin:12px 0}.hero p{font-size:12px;color:#d3dbc9;margin:0;max-width:720px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--line);margin-bottom:30px;padding-bottom:22px;gap:16px}
.metric small{display:block;color:var(--muted);font-size:11px}.metric strong{font:25px/1.5 Georgia,SimSun,serif}.metric span{font-size:11px;color:var(--muted)}
h2{font:25px/1.5 SimSun,serif;letter-spacing:1px;margin:32px 0 15px}h2 .number{color:var(--red);font:13px Georgia,serif;margin-right:12px}h3{font-size:15px;font-weight:500;margin:0 0 9px}
.section-note{color:var(--muted);font-size:12px;margin-top:-7px}.card{background:var(--white);border:1px solid var(--line);padding:22px;margin:12px 0;break-inside:avoid}
.card p{margin:8px 0;white-space:pre-wrap;overflow-wrap:anywhere}.card-foot{border-top:1px solid var(--line);margin-top:15px;padding-top:10px;font-size:10px;color:var(--muted);overflow-wrap:anywhere}
.source-ref{display:inline-block;padding:2px 8px;border:1px solid #d9decf;color:#476852;margin:3px 5px 0 0;font-size:10px;text-decoration:none}
.notice{padding:15px 18px;border-left:3px solid var(--red);background:#f1e6dc;font-size:12px;margin:18px 0;overflow-wrap:anywhere}
.quiet{background:#e9ede2;border-left-color:#476852}.small{font-size:11px;color:var(--muted)}
.timeline{border-left:1px solid #bbc8b5;margin-left:8px;padding-left:24px}.stop{position:relative;padding:12px 0 18px;border-bottom:1px solid var(--line);break-inside:avoid}
.stop:before{content:"";position:absolute;left:-30px;top:21px;width:10px;height:10px;border-radius:50%;background:var(--red);border:2px solid var(--paper)}
.stop time{font:15px Georgia,serif;color:var(--red)}.stop h3{display:inline;margin-left:17px}.stop p{margin:4px 0 0;font-size:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:12px;margin:15px 0}th{text-align:left;font-weight:500;background:#e7ecdf}td,th{border-bottom:1px solid var(--line);padding:11px 12px;overflow-wrap:anywhere;vertical-align:top}td.amount,th.amount{text-align:right}.total td{font-weight:700;background:#e7ecdf}
blockquote{margin:12px 0;padding:12px 16px;background:#efeee4;border-left:2px solid #889776;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}
a{color:#476852;text-underline-offset:3px;overflow-wrap:anywhere}.tag{font-size:10px;background:#e6ece1;color:#476852;padding:3px 8px}.tag.alert{background:#f3e5dc;color:var(--red)}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:18px}.columns dl{margin:0}.columns dt{font-size:11px;color:var(--muted)}.columns dd{margin:0 0 12px;overflow-wrap:anywhere}
.sources{font-size:12px}.sources article{padding:15px 0;border-bottom:1px solid var(--line);break-inside:avoid}.sources h3{font-size:13px}.sources p{margin:4px 0;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;background:#efeee4;padding:15px}.footer{border-top:1px solid var(--line);margin-top:34px;padding-top:18px;display:flex;justify-content:space-between;gap:16px;font-size:10px;color:var(--muted);overflow-wrap:anywhere}
@media(max-width:700px){body{background:var(--paper)}.sheet{margin:0;padding:22px 20px;box-shadow:none}.hero{padding:24px}.hero h1{font-size:27px}.hero-copy{max-width:100%}.hero-art{opacity:.13}.metrics{grid-template-columns:1fr 1fr}.columns{grid-template-columns:1fr}.edition{max-width:100px;text-align:right}.wordmark{font-size:22px}.footer{display:block}th,td{padding:9px 6px}.organizer-ledger{font-size:10px}}
@page{size:A4;margin:15mm}@media print{body{background:white;font-size:11px}.sheet{max-width:none;margin:0;padding:0;box-shadow:none;background:white}.hero{print-color-adjust:exact;-webkit-print-color-adjust:exact}.hero h1{font-size:29px}.card{padding:15px}h2{break-after:avoid}a{color:var(--ink)}.notice{break-inside:avoid}.sources article{break-inside:avoid}.footer{position:static}.hero:after{display:none}}
"""


def render_bundle(run: dict, audience: str, preview: bool = False) -> str:
    """排版当前校验快照；预览明确待确认，正式导出必须有对应人工确认。"""
    if audience not in ("visitor", "organizer"):
        raise ValueError("导出对象须为visitor或organizer")
    plan, req, profile = _validate_run(run, preview=preview)
    teaching_html = ""
    if req.get("planning_mode") == "modules" or req.get("teaching_enabled"):
        teaching = run.get("teaching")
        teaching_run = {**run, "requirements": run.get("effective_requirements", run.get("requirements", {}))}
        check = validate_teaching(teaching, teaching_run)
        if check.get("passed") is not True:
            raise ValueError("教学表达未通过全内容事实扫描，不能预览或导出：" + "；".join(check.get("issues", [])))
        teaching_html = render_teaching_html({**teaching, "check": check}, audience)
    claims = {str(item["id"]): item for item in run.get("claims", []) if isinstance(item, dict) and "id" in item}
    source_versions = _mapping(run.get("source_versions"))
    material_versions = _mapping(run.get("material_versions"))
    evidence_by_id = {}
    for claim in claims.values():
        for evidence in claim.get("evidence", []):
            if isinstance(evidence, dict) and evidence.get("id"):
                evidence_by_id[str(evidence["id"])] = evidence
    evidence_sources = {str(item.get("source_id")) for item in evidence_by_id.values()}
    evidence_titles = {str(item.get("source_id")): item.get("title", "核对来源") for item in evidence_by_id.values()}

    def blocked_card(card):
        return (
            any(_restricted(source_versions.get(str(key))) for key in card.get("source_ids", []))
            or any(str(key) not in source_versions for key in card.get("source_ids", []))
            or any(_restricted(material_versions.get(str(key))) for key in card.get("material_ids", []))
            or any(str(key) not in material_versions for key in card.get("material_ids", []))
        )

    def supported_card(card):
        ids = card.get("claim_ids", [])
        if card.get("usable") is not True or blocked_card(card) or not ids:
            return False
        # 公告日期、招募和免费条件属于历史活动事实，组织者版保留来源核对，
        # 游客版不把它们排版成当前讲解卡，避免把旧公告误读为当前预约承诺。
        if audience == "visitor" and any(claims.get(str(key), {}).get("kind") == "public_activity_fact" for key in ids):
            return False
        if not card.get("source_ids") or any(str(key) not in evidence_sources for key in card["source_ids"]):
            return False
        verified_texts = []
        applicable_source_ids = set()
        for key in ids:
            claim = claims.get(str(key), {})
            if claim.get("status") != "supported" and claim.get("corrected_status") != "supported":
                return False
            if not claim.get("evidence"):
                return False
            corrected = claim.get("status") != "supported"
            verified_texts.append(str(claim.get("suggested_text" if corrected else "text", "")).strip())
            selected_ids = claim.get("corrected_evidence_ids" if corrected else "evidence_ids")
            for evidence in claim["evidence"]:
                if selected_ids is None or evidence.get("id") in selected_ids:
                    applicable_source_ids.add(str(evidence.get("source_id")))
        if not set(map(str, card["source_ids"])).issubset(applicable_source_ids):
            return False
        # 导出只排版已核验文字；不能在最后一步悄悄新增一句未经核验的事实。
        if not all(verified_texts) or str(card.get("text", "")).strip() not in {
            separator.join(verified_texts) for separator in ("", " ", "\n")
        }:
            return False
        return True

    cards = [item for item in run.get("cards", []) if isinstance(item, dict)]
    usable_cards = [card for card in cards if supported_card(card)]
    art = ""
    art_version = material_versions.get("mat-paper-garden", {})
    if (
        isinstance(art_version, dict) and art_version.get("usage_status") == "available"
        and any("mat-paper-garden" in card.get("material_ids", []) for card in usable_cards)
    ):
        # 仅允许仓库已审核的固定素材，不读取运行数据中的路径或远程地址。
        art_path = Path(__file__).resolve().parents[1] / "frontend" / "prototype" / "assets" / "paper-garden.svg"
        if art_path.is_file():
            data = b64encode(art_path.read_bytes()).decode("ascii")
            art = f'<img class="hero-art" alt="原创纸艺装饰图" src="data:image/svg+xml;base64,{data}">'
    mode_label = {"live": "真实本地模型运行", "replay": "历史运行回放", "preset": "预设案例样张"}[run["mode"]]
    title = "模拟体验样张" if audience == "visitor" else "组织者体验包 · 演示测算"
    if preview:
        title = "待人工确认预览稿 · " + title
    subtitle = "带着一份有出处的讲解，走近一方乡土。" if audience == "visitor" else "文化依据、资源约束与活动账本，保存在同一份确认快照中。"
    if preview and audience == "organizer":
        subtitle = "文化依据、资源约束与活动账本，供负责人核对后确认。"
    region = req.get("region", run.get("region", "地域以来源与讲解卡标注为准"))
    project = req.get("project", run.get("project", "剪纸文化体验"))
    public_case = run.get("public_case") if isinstance(run.get("public_case"), dict) else None
    public_case_notice = ""
    if public_case:
        public_case_notice = (
            '<div class="notice case-notice"><strong>公开活动案例重建</strong> · '
            f'{_text(public_case.get("title", "公开活动"))} · 来源：{_text(public_case.get("publisher", "原始发布机构"))} · '
            f'发布 {_text(public_case.get("published_at", "未标注"))} · 访问 {_text(public_case.get("accessed_at", "未标注"))}<br>'
            '公告条件仅用于历史案例重建，不能据此预约当前场地；教师、安全容量、成本和服务分账采用单独标记的团队演示配置，仍待主办方确认。'
            '</div>'
        )
    parts = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'; form-action \'none\'">',
        f'<title>{_text(title)} · 乡艺有据</title><style>{CSS}</style></head><body><main class="sheet">',
        '<header class="brand"><div class="seal">乡艺<br>有据</div><div><div class="wordmark">乡艺有据</div><div class="submark">可信非遗体验编排智能体</div></div>',
        f'<div class="edition">{_text(title)}<br>{_text(mode_label)}</div></header>',
        '<div class="notice"><strong>待人工确认预览稿</strong> · 当前内容仅供审阅，不表示负责人已确认本方案；完成确认后才能正式导出。</div>' if preview else '',
        f'<section class="hero">{art}<div class="hero-copy"><div class="eyebrow">{_text(region)} / {_text(project)}</div><h1>{_text(plan["title"])}，有据可循</h1><p>{subtitle}</p>' + ('<p class="art-note">原创装饰图，非传统作品或纹样复制</p>' if art else '') + '</div></section>',
        '<div class="metrics">',
        f'<div class="metric"><small>参与人数</small><strong>{req["people"]}</strong><span> 人</span></div>',
        f'<div class="metric"><small>活动时长</small><strong>{plan["duration_minutes"]}</strong><span> 分钟</span></div>',
        f'<div class="metric"><small>演示人均费用</small><strong>{_money(plan["per_person_cents"])}</strong></div>',
        f'<div class="metric"><small>开始时间</small><strong>{_text(req["start_time"])}</strong></div></div>',
        '<div class="notice">本文件为模拟体验样张。所有价格、服务报酬、场地与人员均为演示测算；非预约、非真实合作，不代表已取得文化素材或场地授权，不构成实际增收或净利润证明。</div>',
        public_case_notice,
        '<h2><span class="number">01</span>认识一方乡土</h2><p class="section-note">仅展示具有证据支持、当前使用状态允许的讲解卡。</p>',
    ]
    if not usable_cards:
        parts.append('<div class="card"><p>当前没有满足证据与使用条件的讲解卡。文化讲解内容需补充核验后再确认。</p></div>')
    for card in usable_cards:
        refs = "".join(f'<a class="source-ref" href="#source-{_text(key)}">{_text(evidence_titles.get(str(key), "核对来源"))}</a>' for key in card.get("source_ids", []))
        trace = (
            f'讲解卡 {_text(card.get("id"))} · 关联陈述 {_text(" / ".join(map(str, card.get("claim_ids", []))))}'
            if audience == "organizer" else "文化表述可从下方来源核对。"
        )
        parts.append(f'<article class="card"><h3>{_text(card.get("title", "讲解卡"))}</h3><p>{_text(card.get("text", ""))}</p><div class="card-foot">{refs}<br>{trace}</div></article>')
    if len(usable_cards) < len(cards):
        parts.append('<p class="small">部分内容因证据不足或使用状态变化未纳入本样张。</p>')
    if teaching_html:
        parts.append(teaching_html)

    parts.append('<h2><span class="number">02</span>在场的每一刻</h2><div class="timeline">')
    for stage in plan["schedule"]:
        resources = f' · 资源：{_text("、".join(stage["resource_ids"]))}' if audience == "organizer" else ""
        parts.append(f'<article class="stop"><time>{_text(stage["start"])}—{_text(stage["end"])}</time><h3>{_text(stage["title"])}</h3><p>{stage["minutes"]} 分钟{resources}</p></article>')
    parts.extend(['</div>', f'<div class="notice quiet">{_text(plan["scope_note"])} 工具复用是本演示活动要求；演示纸材用量为{plan["paper_units"]}份，不是实测生态改善。</div>'])

    if audience == "organizer":
        parts.extend([
            '<h2><span class="number">03</span>经营测算与资源边界</h2>',
            '<p class="section-note">账目单位为人民币。按经营配置复算，服务报酬不等于村民净收入。</p>',
            '<table class="organizer-ledger"><thead><tr><th>项目与演示收款角色</th><th class="amount">单价 × 数量</th><th class="amount">小计</th></tr></thead><tbody>',
        ])
        for row in plan["ledger"]:
            parts.append(f'<tr><td>{_text(row["label"])}<br><span class="small">{_text(row["payee"])}</span></td><td class="amount">{_money(row["unit_cents"])} × {row["quantity"]}</td><td class="amount">{_money(row["cents"])}</td></tr>')
        parts.extend([
            f'<tr class="total"><td>演示总支出</td><td></td><td class="amount">{_money(plan["total_cents"])}</td></tr></tbody></table>',
            f'<div class="columns"><div class="card"><h3>本地服务报酬</h3><p>{_money(plan["local_service_cents"])}</p><p class="small">讲解、手作教学与茶歇服务费用之和；非利润、非净增收。</p></div><div class="card"><h3>当前接待资源</h3><p>单组容量 {profile["capacity"]} 人 · 教师 {profile["teachers"]} 位 · 场地 {profile["rooms"]} 处</p><p class="small">一个组在同一场地顺序活动，不自动拆组或新增并行接待。</p></div></div>',
            f'<div class="notice quiet">人均预算上限 {_money(run["planning"]["budget_per_person_cents"])}；可用时间 {req["available_minutes"]} 分钟。预算按总价精确校验，人均显示四舍五入至分。</div>',
            '<h2><span class="number">04</span>原文、修订与证据</h2>',
        ])
        # 关联受限来源/素材的正文既不用于游客讲解，也不复制到组织者附件。
        restricted_claims = {str(key) for card in cards if blocked_card(card) for key in card.get("claim_ids", [])}
        for claim_id, claim in claims.items():
            related = claim.get("evidence", [])
            blocked = claim_id in restricted_claims or any(_restricted(source_versions.get(str(e.get("source_id")))) for e in related)
            status = claim.get("status", "insufficient")
            label = STATUS_LABELS.get(status, "未识别状态")
            tag_class = "tag" if status == "supported" else "tag alert"
            parts.append(f'<article class="card"><h3>陈述 {_text(claim_id)} <span class="{tag_class}">{_text(label)}</span></h3>')
            if blocked:
                parts.append('<p>此陈述关联受限或已撤回的内容；原文、修订与摘录均不复制。请查看来源元数据并重新整理。</p>')
            else:
                parts.extend([
                    f'<p><span class="small">原文</span><br>{_text(claim.get("text"))}</p>',
                    f'<p><span class="small">核验说明</span><br>{_text(claim.get("reason"))}</p>',
                ])
                if claim.get("suggested_text"):
                    corrected = ("原句保留（已有来源支持）" if claim.get("status") == "supported"
                                 else "修订已获来源支持" if claim.get("corrected_status") == "supported"
                                 else "建议尚未获得来源支持，未纳入游客版")
                    parts.append(f'<p><span class="small">{corrected}</span><br>{_text(claim["suggested_text"])}</p>')
                for evidence in related:
                    parts.append(f'<blockquote>{_text(evidence.get("quote"))}<br><span class="small">{_text(evidence.get("id"))} · {_text(evidence.get("locator"))}</span></blockquote>')
            refs = " / ".join(str(e.get("source_id", "")) for e in related)
            parts.append(f'<div class="card-foot">关联来源：{_text(refs or "无可用证据")}</div></article>')
        for card in cards:
            if not supported_card(card):
                parts.append(f'<div class="notice">讲解卡 {_text(card.get("id"))} 未纳入游客版：证据或使用条件未满足。未复制受限正文。</div>')
        parts.append('<h2><span class="number">05</span>负责人确认与版本追溯</h2>')
        approval = run.get("approval") or {}
        parts.append('<div class="columns"><div class="card"><h3>负责人确认</h3><dl>')
        approval_rows = (
            (("确认状态", "待人工确认预览稿"), ("确认时间", "待负责人确认"),
             ("待核对方案", plan["title"]), ("预览运行版本", run.get("version", "未记录")))
            if preview else (
                ("确认状态", "已确认当前模拟体验方案"), ("确认时间", approval.get("at", "未记录")),
                ("确认方案", plan["title"]), ("确认运行版本", approval.get("run_version", "未记录")),
            )
        )
        for label, value in approval_rows:
            parts.append(f'<dt>{_text(label)}</dt><dd>{_text(value)}</dd>')
        parts.append('</dl></div><div class="card"><h3>运行快照</h3><dl>')
        for label, value in (
            ("运行编号", run.get("id")), ("运行方式", mode_label),
            ("经营配置编号", profile.get("id")), ("经营配置版本", profile.get("version")),
        ):
            parts.append(f'<dt>{_text(label)}</dt><dd>{_text(value)}</dd>')
        parts.append('</dl></div></div><table><thead><tr><th>资料 / 素材</th><th>版本</th><th>导出快照中的使用状态</th></tr></thead><tbody>')
        for kind, versions in (("来源", source_versions), ("素材", material_versions)):
            for identity, metadata in versions.items():
                metadata = metadata if isinstance(metadata, dict) else {"version": metadata}
                usage = metadata.get("usage_status", "unknown")
                usage_label = {"available": "可用于当前用途", "withdrawn": "已撤回", "restricted": "使用受限"}.get(usage, "状态未明确")
                parts.append(f'<tr><td>{kind} · {_text(identity)}</td><td>{_text(metadata.get("version", "未记录"))}</td><td>{usage_label}</td></tr>')
        parts.append('</tbody></table>')

    sources_for_cards = {str(key) for card in usable_cards for key in card.get("source_ids", [])}
    source_items = {}
    for evidence in evidence_by_id.values():
        source_id = str(evidence.get("source_id", ""))
        if audience == "organizer" or source_id in sources_for_cards:
            source_items.setdefault(source_id, []).append(evidence)
    parts.append('<h2><span class="number">据</span>文化来源与使用说明</h2><div class="sources">')
    if not source_items:
        parts.append('<p>当前无可展示来源；本样张未据此新增文化事实。</p>')
    for source_id, evidence_list in source_items.items():
        evidence = evidence_list[0]
        locators = "；".join(dict.fromkeys(str(item.get("locator", "未注明位置")) for item in evidence_list))
        source_prefix = f"{_text(source_id)} · " if audience == "organizer" else ""
        parts.append(f'<article id="source-{_text(source_id)}"><h3>{source_prefix}{_source_link(evidence)}</h3><p>地域：{_text(evidence.get("region", "未注明"))} · 原文位置：{_text(locators)}</p><p>获取时间：{_text(evidence.get("accessed_at", "未注明"))}</p><p class="small">{_text(evidence.get("use_note", "公开资料仅作事实核验参考；不推定素材、商业使用或场地授权。"))}</p></article>')
    parts.extend([
        '</div><div class="notice quiet">正式活动仍须由负责人落实场地、人员、报价及文化内容使用条件。资料与使用状态发生变化时，应重新核验并确认；此文件仅记录导出时的快照。</div>',
        f'<footer class="footer"><span>乡艺有据 · 让文化有出处，让体验可核对</span><span>运行 {_text(run.get("id"))} · {_text(mode_label)}</span></footer>',
        '</main></body></html>',
    ])
    return "".join(parts)
