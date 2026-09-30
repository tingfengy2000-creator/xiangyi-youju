"""金额、资源约束和导出边界的回归检查。"""

from copy import deepcopy

import pytest

from backend.bundles import render_bundle
from backend.planner import DEFAULT_PLANS, solve_plans


@pytest.fixture
def req():
    return {"people": 8, "budget_per_person": 160, "available_minutes": 150, "start_time": "09:30", "preferred_plan": "deep"}


@pytest.fixture
def profile():
    return {"id": "demo-yuxian", "version": 1, "is_demo": True, "capacity": 12, "teachers": 1, "rooms": 1, "reuse": True, "plans": deepcopy(DEFAULT_PLANS)}


def test_default_two_plans_reconcile(req, profile):
    before = deepcopy((req, profile))
    result = solve_plans(req, profile)
    assert (req, profile) == before
    assert result["feasible_ids"] == ["light", "deep"]
    for plan, expected in zip(result["candidates"], [(78400, 52000, 14400, 90), (108000, 74000, 18000, 120)]):
        assert (plan["total_cents"], plan["local_service_cents"], plan["material_cents"], plan["duration_minutes"]) == expected
        assert sum(row["cents"] for row in plan["ledger"]) == plan["total_cents"]
        assert all(row["cents"] == row["unit_cents"] * row["quantity"] for row in plan["ledger"])
        assert sum(stage["minutes"] for stage in plan["schedule"]) == plan["duration_minutes"]
        assert all(stage["end_minute"] - stage["start_minute"] == stage["minutes"] for stage in plan["schedule"])
        assert all(left["end_minute"] == right["start_minute"] for left, right in zip(plan["schedule"], plan["schedule"][1:]))
        assert [stage["resource_ids"] for stage in plan["schedule"]] == [["room-1"], ["room-1", "teacher-1"], ["room-1"]]
    assert result["candidates"][0]["per_person_cents"] == 9800
    assert result["candidates"][1]["per_person_cents"] == 13500


def test_budget_110_requires_light(req, profile):
    req["budget_per_person"] = 110
    result = solve_plans(req, profile)
    assert result["feasible_ids"] == ["light"]
    assert result["requirements_snapshot"]["preferred_plan"] == "deep"
    assert [item["code"] for item in result["candidates"][1]["conflicts"]] == ["budget_exceeded"]


def test_cannot_invent_parallel_reception(req, profile):
    req["people"] = 16
    profile["capacity"] = 8
    result = solve_plans(req, profile)
    assert result["feasible_ids"] == []
    assert result["profile_snapshot"]["teachers"] == 1
    assert result["requirements_snapshot"]["people"] == 16
    for plan in result["candidates"]:
        codes = {item["code"] for item in plan["conflicts"]}
        assert {"capacity_exceeded", "teacher_capacity_exceeded"} <= codes
        assert len(plan["schedule"]) == 3
        assert all("room-2" not in item["resource_ids"] for item in plan["schedule"])


@pytest.mark.parametrize("field,code", [("teachers", "teacher_unavailable"), ("rooms", "room_unavailable")])
def test_missing_resource(req, profile, field, code):
    profile[field] = 0
    result = solve_plans(req, profile)
    assert not result["feasible_ids"]
    assert all(code in {item["code"] for item in plan["conflicts"]} for plan in result["candidates"])
    missing_id = "teacher-1" if field == "teachers" else "room-1"
    assert all(missing_id not in stage["resource_ids"] for plan in result["candidates"] for stage in plan["schedule"])


def test_same_group_capacity_does_not_scale_with_rooms(req, profile):
    req["people"] = 16
    profile.update(rooms=2, teachers=2)
    result = solve_plans(req, profile)
    assert not result["feasible_ids"]
    assert all("capacity_exceeded" in {c["code"] for c in p["conflicts"]} for p in result["candidates"])


def test_prices_really_come_from_profile(req, profile):
    profile["plans"]["light"]["lecture_cents"] += 125
    result = solve_plans(req, profile)
    assert result["candidates"][0]["total_cents"] == 78525
    assert result["candidates"][1]["total_cents"] == 108000


def test_budget_uses_exact_total_not_rounded_average(req, profile):
    req.update(people=3, budget_per_person="169.34")
    profile["plans"]["light"]["lecture_cents"] += 3
    result = solve_plans(req, profile)
    light = result["candidates"][0]
    assert light["total_cents"] == 54403
    req["budget_per_person"] = "181.34"
    light = solve_plans(req, profile)["candidates"][0]
    assert light["per_person_cents"] == 18134
    assert not light["feasible"]  # 544.03 > 181.34 * 3 = 544.02


@pytest.mark.parametrize("change", [
    {"people": 0}, {"people": True}, {"people": 8.5}, {"budget_per_person": "NaN"},
    {"budget_per_person": -1}, {"budget_per_person": "1.001"}, {"start_time": "24:10"},
    {"start_time": "9:30"}, {"date": "2026-02-30"}, {"date": "2026-9-30"},
    {"available_minutes": 0}, {"preferred_plan": "unlimited"},
])
def test_invalid_requirement_fails_closed(req, profile, change):
    req.update(change)
    with pytest.raises(ValueError):
        solve_plans(req, profile)


def test_midnight_and_operating_status(req, profile):
    req["start_time"] = "23:30"
    profile["status"] = "closed"
    result = solve_plans(req, profile)
    assert result["feasible_ids"] == []
    assert {"crosses_midnight", "operating_unavailable"} <= {item["code"] for item in result["candidates"][0]["conflicts"]}


def test_reuse_is_explicit_demo_constraint(req, profile):
    profile["reuse"] = False
    result = solve_plans(req, profile)
    assert not result["feasible_ids"]
    assert result["candidates"][0]["material_cents"] == 19200
    assert result["candidates"][1]["material_cents"] == 22800


@pytest.fixture
def approved_run(req, profile):
    planning = solve_plans(req, profile)
    evidence = {"id": "e-1", "source_id": "s-1", "title": "蔚县官方条目", "url": "https://www.ihchina.cn/project_details/20184.html", "quote": "以阴刻为主，阳刻为辅", "locator": "项目介绍第3段", "region": "河北蔚县", "accessed_at": "2026-09-30", "use_note": "仅供事实核验"}
    return {
        "id": "run-test", "version": 1, "status": "approved", "mode": "live",
        "requirements": req, "text": "错误原稿", "planning": planning, "plan": planning["candidates"][1],
        "approval": {"confirmed": True, "at": "2026-09-30T12:00:00+08:00", "plan_id": "deep", "run_version": 1},
        "claims": [{"id": "c-1", "text": "蔚县剪纸以阳刻为主。", "status": "contradicted", "reason": "主次与来源不同", "suggested_text": "蔚县剪纸以阴刻为主，阳刻为辅。", "corrected_status": "supported", "evidence": [evidence]}],
        "cards": [{"id": "card-1", "title": "读懂一张剪纸", "text": "蔚县剪纸以阴刻为主，阳刻为辅。", "claim_ids": ["c-1"], "source_ids": ["s-1"], "material_ids": ["m-1"], "usable": True}],
        "source_versions": {"s-1": {"version": 1, "usage_status": "available"}},
        "material_versions": {"m-1": {"version": 1, "usage_status": "available"}},
    }


def test_visitor_and_organizer_have_distinct_complete_exports(approved_run):
    visitor = render_bundle(approved_run, "visitor")
    organizer = render_bundle(approved_run, "organizer")
    assert "模拟体验样张" in visitor
    assert "蔚县剪纸以阴刻为主，阳刻为辅。" in visitor
    assert "蔚县剪纸以阳刻为主。" not in visitor
    assert "蔚县剪纸以阳刻为主。" in organizer
    assert "项目介绍第3段" in visitor
    assert "¥1,080.00" in organizer
    assert "单价 × 数量" in organizer
    assert "单价 × 数量" not in visitor
    assert "非预约、非真实合作" in visitor and "非预约、非真实合作" in organizer


def test_material_withdrawal_removes_body_from_both_exports(approved_run):
    approved_run["material_versions"]["m-1"]["usage_status"] = "withdrawn"
    for audience in ("visitor", "organizer"):
        html = render_bundle(approved_run, audience)
        assert "蔚县剪纸以阴刻为主，阳刻为辅。" not in html
        assert "蔚县剪纸以阳刻为主。" not in html


def test_unsupported_card_excluded_from_visitor(approved_run):
    approved_run["claims"][0].pop("corrected_status")
    html = render_bundle(approved_run, "visitor")
    assert "蔚县剪纸以阴刻为主，阳刻为辅。" not in html


def test_real_local_art_changes_with_material_usage(approved_run):
    approved_run["material_versions"] = {"mat-paper-garden": {"version": 1, "usage_status": "available"}}
    approved_run["cards"][0]["material_ids"] = ["mat-paper-garden"]
    original = render_bundle(approved_run, "visitor")
    assert "data:image/svg+xml;base64," in original
    # 新运行去掉撤回素材引用，保留证据仍支持的纯文字卡。
    approved_run["material_versions"]["mat-paper-garden"].update(version=2, usage_status="withdrawn")
    approved_run["cards"][0]["material_ids"] = []
    refreshed = render_bundle(approved_run, "visitor")
    assert "data:image/svg+xml;base64," not in refreshed
    assert "蔚县剪纸以阴刻为主，阳刻为辅。" in refreshed


def test_untrusted_text_and_urls_are_safe(approved_run):
    approved_run["cards"][0]["title"] = '<script>alert("bad")</script>'
    approved_run["claims"][0]["evidence"][0]["url"] = "javascript:alert(1)"
    html = render_bundle(approved_run, "visitor")
    assert "<script>" not in html
    assert "javascript:" not in html
    assert "&lt;script&gt;" in html
    assert "Content-Security-Policy" in html


def test_export_cannot_invent_new_unverified_card_text(approved_run):
    approved_run["cards"][0]["text"] += "本活动保证村民收入翻倍。"
    html = render_bundle(approved_run, "visitor")
    assert "收入翻倍" not in html
    assert "当前没有满足证据与使用条件的讲解卡" in html


def test_missing_provenance_removes_card(approved_run):
    approved_run["source_versions"] = {}
    html = render_bundle(approved_run, "visitor")
    assert "蔚县剪纸以阴刻为主，阳刻为辅。" not in html


@pytest.mark.parametrize("mutation", ["unapproved", "invalidated", "price", "schedule", "approval-version", "requirements"])
def test_export_rejects_unapproved_or_stale_tampered_data(approved_run, mutation):
    if mutation == "unapproved":
        approved_run["approval"]["confirmed"] = False
    elif mutation == "invalidated":
        approved_run["status"] = "invalidated"
    elif mutation == "price":
        approved_run["plan"]["total_cents"] += 1
    elif mutation == "schedule":
        approved_run["plan"]["schedule"][0]["end"] = "10:00"
        approved_run["plan"]["schedule"][0]["minutes"] = 1
    elif mutation == "approval-version":
        approved_run["approval"]["run_version"] = 0
    elif mutation == "requirements":
        approved_run["requirements"]["people"] = 9
    with pytest.raises(ValueError):
        render_bundle(approved_run, "visitor")
