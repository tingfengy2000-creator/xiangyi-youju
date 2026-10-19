import json
from pathlib import Path

from backend.audiences import AUDIENCE_IDS, apply_defaults
from backend.planner import solve_plans

PROFILE = json.loads((Path(__file__).resolve().parents[2] / "data/operating/demo-profile.json").read_text(encoding="utf-8"))


def plan_for(audience, **constraints):
    base = {"exclude_tags": [], "require_tags": [], "min_craft_minutes": 0, "audience": audience, "maximize_craft": False}
    base.update(constraints)
    req = dict(people=8, budget_per_person=160, available_minutes=150, start_time="09:30", preferred_plan="deep",
               planning_mode="modules", audience=audience, constraints=base)
    return solve_plans(req, PROFILE)["candidates"][0]


def test_five_audiences_get_distinct_feasible_plans():
    plans = {audience: plan_for(audience) for audience in AUDIENCE_IDS}
    assert all(plan["feasible"] for plan in plans.values())
    assert plans["general"]["module_ids"] == ["brief-story", "basic-craft"]
    assert plans["student"]["craft_minutes"] == 80 and "color-observation" in plans["student"]["module_ids"]
    assert plans["senior"]["module_ids"] == ["deep-story", "basic-craft", "tea"]
    assert set(plans["expert"]["module_ids"]) >= {"deep-story", "deep-craft", "color-observation"}
    assert len({tuple(plan["module_ids"]) for plan in plans.values() if plan is not plans["family"]}) == 4
    assert "按体验对象配置" in plans["student"]["explanation"]


def test_explicit_exclusion_beats_audience_default():
    plan = plan_for("senior", exclude_tags=["tea"])
    assert "tea" not in plan["module_ids"]


def test_defaults_never_add_tags_the_catalog_lacks():
    merged, _ = apply_defaults({"audience": "senior", "require_tags": [], "exclude_tags": [], "maximize_craft": False}, {"story", "craft"})
    assert merged["require_tags"] == []


def test_amounts_and_people_are_untouched_by_audience():
    general, student = plan_for("general"), plan_for("student")
    assert sum(item["cents"] for item in student["ledger"]) == student["total_cents"]
    assert general["total_cents"] == 57400 and student["total_cents"] == 87400


def test_deterministic_selection_follows_audience_preference():
    from backend.planner import select_ranked_plan, ranking_reason
    base = {"exclude_tags": [], "require_tags": [], "min_craft_minutes": 0, "audience": "student", "maximize_craft": False}
    req = dict(people=8, budget_per_person=160, available_minutes=150, start_time="09:30", preferred_plan="deep",
               planning_mode="modules", audience="student", constraints=base)
    planning = solve_plans(req, PROFILE)
    chosen = select_ranked_plan(planning, req)
    assert chosen["craft_minutes"] == 80 and chosen["module_ids"] == ["brief-story", "color-observation", "deep-craft", "craft-extension"]
    assert "青少年学生" in ranking_reason(planning, req)
