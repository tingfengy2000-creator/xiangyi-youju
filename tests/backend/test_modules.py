"""模块枚举只读取演示经营配置，不调用真实模型或业务API。"""

from copy import deepcopy
import json
from pathlib import Path
import re

import pytest

from backend.planner import plan_craft_minutes, ranking_reason, select_ranked_plan, solve_plans, summarize_conflicts


@pytest.fixture
def profile():
    path = Path(__file__).resolve().parents[2] / "data" / "operating" / "demo-profile.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def req():
    return {"people": 8, "budget_per_person": 160, "available_minutes": 150,
            "start_time": "09:30", "preferred_plan": "deep", "planning_mode": "modules", "constraints": {}}


def test_legacy_packages_remain_exact(req, profile):
    req["planning_mode"] = "packages"
    result = solve_plans(req, profile)
    assert [(p["id"], p["total_cents"], p["duration_minutes"]) for p in result["candidates"]] == [
        ("light", 78400, 90), ("deep", 108000, 120),
    ]
    req.pop("planning_mode")
    assert solve_plans(req, profile)["candidates"] == result["candidates"]


def test_modules_have_diverse_candidates_and_real_conflict(req, profile):
    original = deepcopy((req, profile))
    result = solve_plans(req, profile)
    assert (req, profile) == original
    assert 4 <= len(result["candidates"]) <= 6
    assert result["stats"]["enumerated"] == 64
    assert result["stats"]["feasible_count"] > len(result["feasible_ids"]) > 0
    assert any(not p["feasible"] for p in result["candidates"])
    assert len({p["duration_minutes"] for p in result["candidates"]}) >= 3
    assert len({tuple(p["module_ids"]) for p in result["candidates"]}) == len(result["candidates"])
    assert all(re.fullmatch(r"mod-[a-z0-9-]+", p["id"]) for p in result["candidates"])
    assert result == solve_plans(result["requirements_snapshot"], result["profile_snapshot"])


def test_explicit_no_tea_and_craft_minimum_change_real_modules(req, profile):
    req.update(budget_per_person=110, available_minutes=100,
               constraints={"exclude_tags": ["tea"], "min_craft_minutes": 60, "maximize_craft": True, "audience": "family"})
    result = solve_plans(req, profile)
    assert result["requirements_snapshot"]["constraints"] == req["constraints"]
    feasible = [p for p in result["candidates"] if p["feasible"]]
    assert feasible
    assert all("tea" not in p["module_ids"] for p in feasible)
    assert all(p["craft_minutes"] >= 60 and p["duration_minutes"] <= 100 and p["total_cents"] <= 88000 for p in feasible)
    assert len({p["craft_minutes"] for p in feasible}) >= 2
    assert feasible[0]["craft_minutes"] == max(p["craft_minutes"] for p in feasible)
    assert all("deep-story" not in p["module_ids"] for p in feasible)
    assert any(not p["feasible"] for p in result["candidates"])


def test_require_activity_and_mutual_exclusion(req, profile):
    req["constraints"] = {"require_tags": ["sharing", "observation"]}
    result = solve_plans(req, profile)
    for plan in result["candidates"]:
        ids = set(plan["module_ids"])
        assert len(ids.intersection({"brief-story", "deep-story"})) == 1
        assert len(ids.intersection({"basic-craft", "deep-craft"})) == 1
        assert len(ids) <= 6
        if plan["feasible"]:
            assert {"sharing", "color-observation"} <= ids
        if "craft-extension" in ids:
            assert ids.intersection({"basic-craft", "deep-craft"})


def test_schedule_and_ledger_recompute_from_only_configuration(req, profile):
    req["people"] = 9
    result = solve_plans(req, profile)
    modules = {m["id"]: m for m in profile["modules"]}
    for plan in result["candidates"]:
        expected = sum(c["fixed_cents"] + c["per_person_cents"] * req["people"] for identity in plan["module_ids"] for c in modules[identity]["costs"].values())
        assert expected == plan["total_cents"] == sum(row["cents"] for row in plan["ledger"])
        assert all(row["unit_cents"] * row["quantity"] == row["cents"] for row in plan["ledger"])
        assert sum(plan[key] for key in ("local_service_cents", "material_cents", "operations_cents")) == expected
        assert plan["duration_minutes"] == sum(modules[identity]["min_duration_minutes"] for identity in plan["module_ids"])
        for index, stage in enumerate(plan["schedule"]):
            assert stage["minutes"] == modules[stage["module_id"]]["min_duration_minutes"]
            assert stage["end_minute"] - stage["start_minute"] == stage["minutes"]
            assert "room-1" in stage["resource_ids"]
            assert "room-2" not in stage["resource_ids"]
            if index:
                assert stage["start_minute"] == plan["schedule"][index - 1]["end_minute"]


def test_over_capacity_and_missing_teacher_remain_unsolved(req, profile):
    req["people"] = 16
    profile.update(capacity=8, teachers=0, rooms=1)
    result = solve_plans(req, profile)
    assert result["feasible_ids"] == []
    assert result["stats"]["feasible_count"] == 0
    assert 4 <= len(result["candidates"]) <= 6
    for plan in result["candidates"]:
        codes = {c["code"] for c in plan["conflicts"]}
        assert {"capacity_exceeded", "teacher_unavailable"} <= codes
        assert all(not any(resource.startswith("teacher-") for resource in stage["resource_ids"]) for stage in plan["schedule"])
    assert result["requirements_snapshot"]["people"] == 16
    assert result["profile_snapshot"]["teachers"] == 0


def test_program_does_not_shorten_modules_to_meet_impossible_window(req, profile):
    req["available_minutes"] = 60
    result = solve_plans(req, profile)
    assert not result["feasible_ids"]
    assert all(p["duration_minutes"] >= 70 for p in result["candidates"])
    assert all("time_exceeded" in {c["code"] for c in p["conflicts"]} for p in result["candidates"])


def test_conflicting_explicit_preferences_do_not_get_silently_relaxed(req, profile):
    req["constraints"] = {"exclude_tags": ["tea"], "require_tags": ["tea"]}
    result = solve_plans(req, profile)
    assert not result["feasible_ids"]
    assert result["requirements_snapshot"]["constraints"] == req["constraints"]


def test_profile_price_and_teacher_changes_are_read(req, profile):
    baseline = solve_plans(req, profile)
    for m in profile["modules"]:
        if m["exclusive_group"] == "story":
            m["costs"]["local_service"]["fixed_cents"] += 125
    changed = solve_plans(req, profile)
    before = {p["id"]: p for p in baseline["candidates"]}
    shared = [p for p in changed["candidates"] if p["id"] in before]
    assert shared
    assert all(p["total_cents"] == before[p["id"]]["total_cents"] + 125 for p in shared)
    for m in profile["modules"]:
        if m["exclusive_group"] == "craft":
            m["teacher_needed"] = 2
    assert not solve_plans(req, profile)["feasible_ids"]


@pytest.mark.parametrize("constraints", [
    {"min_craft_minutes": -1}, {"min_craft_minutes": True}, {"min_craft_minutes": 1.2},
    {"audience": "unknown"}, {"exclude_tags": "tea"}, {"require_tags": ["unknown"]},
    {"exclude_tags": ["tea", "tea"]}, {"maximize_craft": "true"}, {"invent_teacher": True},
])
def test_invalid_constraints_are_not_guessed(req, profile, constraints):
    req["constraints"] = constraints
    with pytest.raises(ValueError):
        solve_plans(req, profile)


def test_no_fake_conflict_when_every_combination_is_feasible(req, profile):
    req.update(budget_per_person=10000, available_minutes=720)
    result = solve_plans(req, profile)
    assert result["stats"]["feasible_count"] == result["stats"]["enumerated"] == 64
    assert all(p["feasible"] for p in result["candidates"])
    assert len(result["candidates"]) == 6


def test_teaching_enabled_does_not_bypass_package_exclusion(req, profile):
    req.update(planning_mode="packages", teaching_enabled=True, constraints={"exclude_tags": ["tea"]})
    result = solve_plans(req, profile)
    assert result["feasible_ids"] == []
    assert all("excluded_tag" in {c["code"] for c in p["conflicts"]} for p in result["candidates"])
    assert [p["total_cents"] for p in result["candidates"]] == [78400, 108000]
    assert [p["duration_minutes"] for p in result["candidates"]] == [90, 120]


def test_package_minimum_craft_and_direct_form_fields(req, profile):
    req.update(planning_mode="packages", teaching_enabled=True, constraints={"min_craft_minutes": 60})
    assert solve_plans(req, profile)["feasible_ids"] == ["deep"]
    req["constraints"]["min_craft_minutes"] = 70
    assert not solve_plans(req, profile)["feasible_ids"]
    req.pop("constraints")
    req.update(tea_preference="exclude", min_craft_minutes=0)
    assert not solve_plans(req, profile)["feasible_ids"]


def test_packages_cannot_invent_missing_activity(req, profile):
    req.update(planning_mode="packages", constraints={"require_tags": ["observation"]})
    result = solve_plans(req, profile)
    assert not result["feasible_ids"]
    assert all("required_tag_missing" in {c["code"] for c in p["conflicts"]} for p in result["candidates"])


def test_program_selects_maximum_craft_without_changing_candidates(req, profile):
    req.update(budget_per_person=110, available_minutes=110,
               constraints={"exclude_tags": ["tea"], "maximize_craft": True, "audience": "family"})
    result = solve_plans(req, profile)
    before = deepcopy((result, req))
    selected = select_ranked_plan(result, req)
    assert selected is next(plan for plan in result["candidates"] if plan["id"] == selected["id"])
    assert selected["craft_minutes"] == 80
    assert selected["total_cents"] == 79600
    assert selected["duration_minutes"] == 100
    assert set(selected["module_ids"]) == {"brief-story", "deep-craft", "craft-extension"}
    assert "手作80分钟，总时长100分钟" in ranking_reason(result, req)
    assert (result, req) == before
    assert solve_plans(result["requirements_snapshot"], result["profile_snapshot"]) == result


def test_program_does_not_confuse_one_hour_craft_with_total_window(req, profile):
    req.update(people=10, budget_per_person=100, available_minutes=100,
               constraints={"exclude_tags": ["tea"], "min_craft_minutes": 60,
                            "maximize_craft": True, "audience": "family"})
    result = solve_plans(req, profile)
    selected = select_ranked_plan(result, req)
    assert (selected["craft_minutes"], selected["duration_minutes"], selected["total_cents"]) == (80, 100, 91000)
    assert req["available_minutes"] == 100
    assert req["constraints"]["min_craft_minutes"] == 60


def test_ordinary_modules_choose_lowest_actual_cost(req, profile):
    result = solve_plans(req, profile)
    selected = select_ranked_plan(result, req)
    assert selected["total_cents"] == 57400
    assert selected["duration_minutes"] == 70
    assert selected["craft_minutes"] == 50
    assert "演示总价从低到高" in ranking_reason(result, req)
    # 对照候选不可行不等于任务无解。
    assert any(not plan["feasible"] for plan in result["candidates"])
    assert summarize_conflicts(result) == []


def test_package_ranking_preserves_preference_and_revises_only_if_needed(req, profile):
    req.update(planning_mode="packages", preferred_plan="deep")
    result = solve_plans(req, profile)
    assert select_ranked_plan(result, req)["id"] == "deep"
    assert "保留该套餐" in ranking_reason(result, req)
    req["budget_per_person"] = 110
    result = solve_plans(req, profile)
    selected = select_ranked_plan(result, req)
    assert selected["id"] == "light"
    assert (selected["total_cents"], selected["duration_minutes"]) == (78400, 90)
    assert plan_craft_minutes(selected, result) == plan_craft_minutes(selected) == 50


def test_package_explicit_maximum_craft_has_priority_over_soft_plan_preference(req, profile):
    req.update(planning_mode="packages", preferred_plan="light", constraints={"maximize_craft": True})
    result = solve_plans(req, profile)
    selected = select_ranked_plan(result, req)
    assert selected["id"] == "deep"
    assert plan_craft_minutes(selected, result) == 60
    assert "手作60分钟，总时长120分钟" in ranking_reason(result, req)


def test_resource_refusal_explains_required_and_available_resources(req, profile):
    req.update(people=16, budget_per_person=160, available_minutes=180)
    profile.update(capacity=8, teachers=1, rooms=1)
    result = solve_plans(req, profile)
    before = deepcopy(result)
    assert select_ranked_plan(result, req) is None
    conflicts = summarize_conflicts(result)
    assert [item["code"] for item in conflicts[:2]] == ["capacity_exceeded", "teacher_capacity_exceeded"]
    messages = {item["code"]: item["message"] for item in conflicts}
    assert "人数16超过单组容量8" in messages["capacity_exceeded"]
    assert "需至少2位教师" in messages["teacher_capacity_exceeded"]
    assert "现有1位、每位上限12人，合计可接待12人" in messages["teacher_capacity_exceeded"]
    assert len(conflicts) == len({(item["code"], item["message"]) for item in conflicts})
    assert result == before
    assert "没有同时满足已确认条件" in ranking_reason(result, req)


@pytest.mark.parametrize("mode", ["packages", "modules"])
def test_missing_resources_summary_is_concrete_in_both_modes(req, profile, mode):
    req["planning_mode"] = mode
    profile.update(teachers=0, rooms=0)
    result = solve_plans(req, profile)
    messages = {item["code"]: item["message"] for item in summarize_conflicts(result)}
    assert "8人手作需至少1位教师" in messages["teacher_unavailable"]
    assert "现有0位" in messages["teacher_unavailable"]
    assert "至少需要1间场地，现有0间" in messages["room_unavailable"]
    assert select_ranked_plan(result, req) is None


def test_no_selection_when_fixed_packages_cannot_meet_explicit_preference(req, profile):
    req.update(planning_mode="packages", constraints={"exclude_tags": ["tea"], "min_craft_minutes": 70})
    result = solve_plans(req, profile)
    assert select_ranked_plan(result, req) is None
    assert {item["code"] for item in summarize_conflicts(result)} == {"excluded_tag", "craft_minutes_insufficient"}
    assert [(plan["total_cents"], plan["duration_minutes"]) for plan in result["candidates"]] == [(78400, 90), (108000, 120)]
