"""按简单要求生成讲解词草稿：只转述已收录的官方资料摘录，再交给现有逐句核验。

访谈中的手艺人与文旅办负责人都表示，传承人多凭经验讲，没有成稿的讲解词。
这里只做第一步“写草稿”：本地模型拿到当前地域、项目下仍可用的资料摘录，
按体验对象的口吻写 2–5 句。草稿不是结论，必须再经过“核验并编排体验”，
逐句对照来源后才能进入讲解卡和体验包。

本地模型不可用或返回不合格时，不假装生成：改为载入部署时预置的讲解词草稿，
并在结果中写明 origin=deployment_preset 与失败原因。预置草稿同样只由资料摘录写成，
同样要经过逐句核验。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from .audiences import AUDIENCES, AUDIENCE_IDS, label
from .config import ROOT
from .evidence import normalize_region
from .model import LocalModel, ModelFailure
from .schemas import StrictModel

PRESETS_PATH = ROOT / "data" / "curated" / "draft-presets.json"
SENTENCES_BY_MINUTES = {3: 3, 5: 4, 10: 5}


class DraftSentence(StrictModel):
    text: str = Field(min_length=4, max_length=80)
    source_ids: list[str] = Field(min_length=1, max_length=3)


class DraftScript(StrictModel):
    sentences: list[DraftSentence] = Field(min_length=2, max_length=5)


INSTRUCTION = """你为非遗体验写一段讲解词草稿，草稿之后会被逐句对照来源核验。
只能转述facts中的quote，每句写明所依据的source_ids，一句最多合并两条事实。
每句都以项目名称开头或用“它”指代，主语清楚；不新增朝代、年代、人物、寓意、评价或比较，不写营业、价格、预约、授课安排。
不使用facts以外的地域名称。按audience_style调整口吻和句式，句数恰好为sentence_count，每句一个句号结尾。"""


def _presets() -> dict:
    return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))


def _preset(region: str, project: str, audience: str) -> dict | None:
    for item in _presets()["drafts"]:
        if normalize_region(item["region"]) == normalize_region(region) and item["project"] == project and item["audience"] == audience:
            return item
    return None


def generate_draft(sources: list, region: str, project: str, audience: str, minutes: int, llm=None) -> dict:
    if audience not in AUDIENCE_IDS:
        raise ValueError("体验对象须为" + "/".join(AUDIENCE_IDS))
    if minutes not in SENTENCES_BY_MINUTES:
        raise ValueError("讲解时长须为3、5或10分钟")
    facts = [
        {"source_id": s["id"], "title": s["title"], "quote": s["quote"]}
        for s in sources
        if normalize_region(s.get("region", "")) == normalize_region(region) and s.get("project") == project
        and s.get("usage_status") == "available"
    ]
    if not facts:
        raise ValueError("当前地域和项目没有可用资料，不能生成讲解词")
    allowed = {fact["source_id"] for fact in facts}
    count = min(SENTENCES_BY_MINUTES[minutes], len(facts))
    llm = llm or LocalModel()
    base = {"region": region, "project": project, "audience": audience, "audience_label": label(audience),
            "minutes": minutes, "model_calls": 0, "status": "draft_unverified",
            "note": "草稿尚未核验：请点击“核验并编排体验”，逐句对照来源后再使用。"}
    try:
        result = llm.ask("按要求生成讲解词草稿", {
            "project": project, "region": region, "audience": audience,
            "audience_style": AUDIENCES[audience]["style"], "sentence_count": count, "facts": facts,
        }, DraftScript, INSTRUCTION, max_attempts=2)
        sentences = result["sentences"]
        if len(sentences) != count or any(not set(row["source_ids"]) <= allowed for row in sentences):
            raise ModelFailure("草稿句数或引用超出给定资料，未采用")
        text = "".join(row["text"].strip().rstrip("。") + "。" for row in sentences)
        return {**base, "origin": "local_model", "text": text, "sentences": sentences,
                "source_ids": sorted({sid for row in sentences for sid in row["source_ids"]}),
                "model_calls": len(llm.calls)}
    except ModelFailure as error:
        preset = _preset(region, project, audience)
        if preset is None:
            raise
        return {**base, "origin": "deployment_preset", "text": preset["text"], "sentences": [],
                "source_ids": preset["source_ids"], "model_calls": len(llm.calls), "model_error": str(error),
                "preset_note": _presets()["note"]}
