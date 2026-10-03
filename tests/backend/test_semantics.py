"""Source grounding and claim category guards; these are program tests, not LLM scores."""
import pytest
from backend.semantics import ground_durations
from backend.constraints import split_input
from backend.workflow import validated_judgments


def prefs(**changes):
    return {"min_craft_minutes": None, "available_minutes": None, "ambiguities": [], **changes}


@pytest.mark.parametrize("text,craft,total", [
    ("制作环节务必满一小时，能多做一会儿就更好。", 60, None),
    ("总共两个小时，手作至少四十五分钟。", 45, 120),
    ("手作练习至少九十分钟，总时间两小时，不要用延长文字介绍来凑制作时长。", 90, 120),
    ("手作至少60分钟，整个活动只有100分钟。", 60, 100),
    ("全程一个半小时", None, 90),
    ("全程一小时半。", None, 90),
    ("请留出观察与提问时间", None, None),
])
def test_duration_scope_comes_from_source_not_model(text, craft, total):
    result, trace = ground_durations(text, prefs(min_craft_minutes=35, available_minutes=35))
    assert result["min_craft_minutes"] == craft
    assert result["available_minutes"] == total
    assert trace["corrections"]


def test_unclear_or_unsupported_duration_does_not_silently_become_minimum():
    result, _ = ground_durations("至少五十分钟。", prefs())
    assert result["ambiguities"] and result["available_minutes"] is None
    result, _ = ground_durations("手作不超过五十分钟。", prefs())
    assert "上限" in result["ambiguities"][0]


def test_compound_claims_keep_complete_text_with_separate_operating_promise():
    text = "蔚县剪纸以阳刻为主、阴刻为辅，采用多色点染彩绘，而且本周六一定由国家级传承人亲自授课。"
    parts = split_input(text, compound=True)
    assert len(parts) == 3
    assert "".join(p["text"] for p in parts) == text
    assert len({p["original_sentence_id"] for p in parts}) == 1


@pytest.mark.parametrize("kind", ["operating_promise", "user_requirement"])
def test_non_cultural_statements_cannot_become_supported_cards(kind):
    claim = {"id": "c1", "text": "明天授课", "kind": kind, "evidence": []}
    model_row = {"claim_id": "c1", "status": "supported", "evidence_ids": [], "suggested_text": "明天授课", "reason": "wrong"}
    row = validated_judgments({"judgments": [model_row]}, [claim])[0]
    assert row["status"] == "insufficient" and row["suggested_text"] == ""
