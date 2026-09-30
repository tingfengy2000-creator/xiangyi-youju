"""程序约束与表单冲突检查；不代表真实模型效果。"""
from backend.constraints import resolve_intent, split_input, compare_plans
from backend.schemas import Requirements, Intent


def intent(**changes):
    return Intent(exclude_tags=[], require_tags=[], min_craft_minutes=None, maximize_craft=False,
                  audience=None, people=None, budget_per_person=None, available_minutes=None,
                  ambiguities=[], **changes).model_dump()


def test_form_conflict_requires_choice_and_does_not_change_locked_values():
    req = Requirements(tea_preference="include").model_dump()
    note = intent()
    note.update(exclude_tags=["tea"], budget_per_person=110, maximize_craft=True)
    effective, conflicts, error = resolve_intent(req, note)
    assert {c["field"] for c in conflicts} == {"tea_preference", "budget_per_person"}
    assert effective["budget_per_person"] == req["budget_per_person"]
    assert "constraints" not in effective and error is None
    chosen, conflicts, error = resolve_intent(req, note, "form")
    assert chosen["constraints"]["require_tags"] == ["tea"]
    assert chosen["constraints"]["exclude_tags"] == []
    assert chosen["constraints"]["maximize_craft"] is True


def test_neutral_preferences_adopt_note_but_internal_contradictions_stop():
    note = intent()
    note.update(exclude_tags=["tea"], min_craft_minutes=60)
    effective, conflicts, problem = resolve_intent(Requirements().model_dump(), note)
    assert not conflicts and not problem
    assert effective["constraints"]["min_craft_minutes"] == 60
    assert effective["tea_preference"] == "exclude"
    note["require_tags"] = ["tea"]
    assert resolve_intent(Requirements().model_dump(), note)[2]


def test_compound_segmentation_keeps_every_character_and_original_position():
    text = "蔚县剪纸以阴刻为主，阳刻为辅；同时这里每天都有大师授课。"
    rows = split_input(text, compound=True)
    assert len(rows) == 2 and "".join(r["text"] for r in rows) == text
    assert all(r["original_sentence"] == text for r in rows)
    assert "阴刻为主，阳刻为辅" in rows[0]["text"]


def test_comparison_reports_actual_changes():
    before = {"id":"a", "total_cents":108000,"duration_minutes":120,"craft_minutes":60,
              "schedule":[{"title":"茶歇","module_id":"tea"}]}
    after = {"id":"b", "total_cents":79600,"duration_minutes":100,"craft_minutes":80,
             "schedule":[{"title":"手作延展","module_id":"extension"}]}
    comparison = compare_plans(before, after)
    assert any("1080 → 796元" in c for c in comparison["changes"])
    assert any("移除：茶歇" == c for c in comparison["changes"])


def test_comparison_reports_start_change_when_cost_and_modules_stay_the_same():
    before = {"id": "same", "total_cents": 57400, "duration_minutes": 70, "craft_minutes": 50,
              "module_ids": ["brief-story", "basic-craft"],
              "schedule": [{"title": "讲解", "module_id": "brief-story", "start": "09:00", "end": "09:20"},
                           {"title": "手作", "module_id": "basic-craft", "start": "09:20", "end": "10:10"}]}
    after = {**before, "schedule": [{"title": "讲解", "module_id": "brief-story", "start": "10:00", "end": "10:20"},
                                    {"title": "手作", "module_id": "basic-craft", "start": "10:20", "end": "11:10"}]}
    comparison = compare_plans(before, after)
    assert comparison["before"]["start_time"] == "09:00"
    assert comparison["after"]["start_time"] == "10:00"
    assert any("09:00 → 10:00" in change for change in comparison["changes"])
    assert not any("未改变" in change for change in comparison["changes"])
