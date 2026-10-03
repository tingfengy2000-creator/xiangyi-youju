"""分众教学的程序契约测试；假模型仅检验保护逻辑，不代表真实推理质量。"""

from copy import deepcopy

import pytest

from backend.bundles import render_bundle
from backend.evidence import load_profile, load_sources
from backend.model import ModelFailure
from backend.planner import solve_plans
from backend.teaching import CREATIVE_LABEL, generate_teaching, render_teaching_html, validate_teaching
from backend.teaching import can_recheck_scan, recheck_teaching_scan


def make_run(audience="general"):
    source = next(s for s in load_sources() if s["id"] == "src-yuxian-technique")
    text = "蔚县剪纸以阴刻为主，阳刻为辅。"
    return {"requirements": {"audience": audience}, "claims": [
        {"id": "c1", "text": text, "status": "supported", "evidence_ids": [source["id"]]}],
        "cards": [{"id": "card-c1", "text": text, "claim_ids": ["c1"],
                   "source_ids": [source["id"]], "material_ids": [], "usable": True}],
        "sources_snapshot": [source], "source_versions": {
            source["id"]: {"version": source["version"], "usage_status": "available"}}}


class FakeLLM:
    def __init__(self, draft_change=None, scan_change=None, fail_stage=None):
        self.calls, self.requests = [], []
        self.draft_change = draft_change or (lambda value: value)
        self.scan_change = scan_change or (lambda value: value)
        self.fail_stage = fail_stage

    def ask(self, purpose, data, schema, instruction, *, max_attempts=2):
        assert max_attempts == 1
        self.calls.append({"purpose": purpose})
        self.requests.append(deepcopy(data))
        if self.fail_stage == len(self.calls):
            raise ModelFailure("单元测试模拟模型不可用")
        if schema.__name__ == "TeachingDraft":
            card = data["cards"][0]
            unit = {"text": card["text"], "claim_ids": card["claim_ids"], "source_ids": card["source_ids"]}
            observation = "请和孩子一起观察负责人提供且允许使用的剪纸示例。" if data["audience"] == "family" else "请观察负责人提供且允许使用的剪纸示例。"
            return self.draft_change({"short_script": [unit],
                                      "observation_task": {**unit, "text": observation},
                                      "interaction_question": {**unit, "text": "哪一个细节最吸引你？"}})
        rows = []
        for item in data["items"]:
            factual = item["item_id"].startswith("script-")
            rows.append({"item_id": item["item_id"], "checked_text": item["text"],
                         "status": "supported" if factual else "no_new_fact",
                         "cultural_premises": [item["text"]] if factual else [],
                         "activity_scope_passed": True,
                         "claim_ids": item["claim_ids"] if factual else [],
                         "source_ids": item["source_ids"] if factual else [],
                         "reason": "假模型对事实与纯观察动作的测试判定"})
        return self.scan_change({"items": rows})


@pytest.mark.parametrize("audience", ["general", "family"])
def test_generation_and_all_item_scan_have_two_calls(audience):
    llm, run = FakeLLM(), make_run(audience)
    result = generate_teaching(llm, run)
    assert result["check"]["passed"] is True
    assert result["check"]["model_calls_used"] == len(llm.calls) == 2
    assert result["creative_label"] == CREATIVE_LABEL
    assert result["audience"] == audience
    assert len(llm.requests[1]["items"]) == 3
    assert {item["item_id"] for item in llm.requests[1]["items"]} == {"script-1", "observation", "interaction"}
    assert validate_teaching(result, run)["passed"]
    assert "和孩子一起" in result["observation_task"]["text"] if audience == "family" else "和孩子一起" not in result["observation_task"]["text"]


def test_corrected_supported_card_is_allowed():
    run = make_run()
    run["claims"][0].update(status="contradicted", text="原始错误说法。",
                             suggested_text=run["cards"][0]["text"], corrected_status="supported",
                             corrected_evidence_ids=["src-yuxian-technique"])
    assert generate_teaching(FakeLLM(), run)["check"]["passed"]


def test_scan_contract_repair_is_once_and_preserves_content_and_evidence():
    def inconsistent(value):
        value["items"][1]["cultural_premises"] = ["扫描字段自相矛盾的模拟项"]
        return value
    llm, run = FakeLLM(scan_change=inconsistent), make_run()
    first = generate_teaching(llm, run)
    assert not first["check"]["passed"] and can_recheck_scan(first, run)
    llm.scan_change = lambda value: value
    revised = recheck_teaching_scan(llm, first, run)
    assert revised["check"]["passed"] and revised["check"]["model_calls_used"] == 3
    assert revised["short_script"] == first["short_script"]
    assert revised["check"]["input_sha256"] == first["check"]["input_sha256"]
    assert len(llm.calls) == 3 and not can_recheck_scan(revised, run)
    with pytest.raises(ValueError):
        recheck_teaching_scan(llm, revised, run)


def test_unsupported_scan_cannot_be_rejudged_until_it_passes():
    def unsupported(value):
        value["items"][0]["status"] = "insufficient"
        return value
    llm, run = FakeLLM(scan_change=unsupported), make_run()
    first = generate_teaching(llm, run)
    assert not first["check"]["passed"] and not can_recheck_scan(first, run)
    with pytest.raises(ValueError):
        recheck_teaching_scan(llm, first, run)


def failed_teaching_candidate(status="unsupported", scope=True):
    """真实扫描流程的假模型失败候选，不跳过结构或来源绑定。"""
    def verdict(value):
        value["items"][0].update(status=status, activity_scope_passed=scope)
        return value
    return generate_teaching(FakeLLM(scan_change=verdict), make_run())


@pytest.mark.parametrize("status,scope", [("unsupported", True), ("insufficient", True), ("supported", False)])
def test_regeneration_cannot_rescan_identical_rejected_text(status, scope):
    failed = failed_teaching_candidate(status, scope)
    assert not failed["check"]["passed"]
    # 默认假扫描若被调用就会改判支持；门禁必须在扫描前阻断。
    llm = FakeLLM()
    result = generate_teaching(llm, make_run(), feedback=failed)
    assert not result["check"]["passed"]
    assert len(llm.calls) == result["check"]["model_calls_used"] == 1
    assert result["check"]["rejected_content_reuse"][0]["previous_item_id"] == "script-1"
    assert result["short_script"] == failed["short_script"]
    assert not can_recheck_scan(result, make_run())
    with pytest.raises(ValueError):
        render_teaching_html(result, "visitor")


def test_changing_another_unit_does_not_release_rejected_sentence():
    failed = failed_teaching_candidate()
    def change_other(value):
        value["interaction_question"]["text"] = "你更喜欢哪一处细节？"
        return value
    llm = FakeLLM(draft_change=change_other)
    result = generate_teaching(llm, make_run(), feedback=failed)
    assert len(llm.calls) == 1 and not result["check"]["passed"]
    assert result["check"]["rejected_content_reuse"]


@pytest.mark.parametrize("text", [
    "蔚 县 剪 纸 以 阴 刻 为 主，阳 刻 为 辅！",
    "蔚县剪纸以阴刻为主,阳刻为辅!",
    "蔚县剪纸以阴刻为主\u200b、阳刻为辅？",
    "这里仍要讲蔚县剪纸以阴刻为主、阳刻为辅这一点。",
])
def test_moved_or_formatted_rejected_text_is_still_blocked(text):
    failed = failed_teaching_candidate()
    def move_and_reformat(value):
        value["short_script"][0]["text"] = "蔚县剪纸的主要技法为阴刻。"
        value["observation_task"]["text"] = text
        return value
    llm = FakeLLM(draft_change=move_and_reformat)
    result = generate_teaching(llm, make_run(), feedback=failed)
    assert len(llm.calls) == 1 and not result["check"]["passed"]
    assert any(row["item_id"] == "observation" for row in result["check"]["rejected_content_reuse"])


@pytest.mark.parametrize("text", ["蔚县剪纸的主要技法为阴刻。", "蔚县剪纸以阴刻为主要技法、阳刻为辅助技法。"])
def test_genuinely_changed_candidate_still_requires_full_scan(text):
    failed = failed_teaching_candidate()
    def repair(value):
        value["short_script"][0]["text"] = text
        return value
    llm = FakeLLM(draft_change=repair)
    result = generate_teaching(llm, make_run(), feedback=failed)
    assert len(llm.calls) == 2 and result["check"]["passed"]
    assert llm.requests[1]["items"][0]["text"] == text
    # 文字有实质变化只允许重新扫描，不直接授予支持状态。
    def still_unsupported(value):
        value["items"][0]["status"] = "unsupported"
        return value
    rejected = generate_teaching(FakeLLM(draft_change=repair, scan_change=still_unsupported), make_run(), feedback=failed)
    assert not rejected["check"]["passed"]
    assert not can_recheck_scan(rejected, make_run())


def test_removing_a_rejected_observation_allows_checked_replacement():
    def unsafe_draft(value):
        value["observation_task"]["text"] = "请马上使用专业刻刀制作。"
        return value
    def denied_scope(value):
        value["items"][1]["activity_scope_passed"] = False
        return value
    failed = generate_teaching(FakeLLM(draft_change=unsafe_draft, scan_change=denied_scope), make_run())
    assert not failed["check"]["passed"]
    llm = FakeLLM()
    result = generate_teaching(llm, make_run(), feedback=failed)
    assert len(llm.calls) == 2 and result["check"]["passed"]
    assert "专业刻刀" not in result["observation_task"]["text"]


@pytest.mark.parametrize("field", ["observation_task", "interaction_question"])
def test_creative_label_does_not_allow_hidden_unsupported_cultural_premise(field):
    def draft(value):
        value[field]["text"] = "请解释蔚县剪纸的红色为什么能够辟邪？"
        return value

    def scan(value):
        identifier = "observation" if field == "observation_task" else "interaction"
        row = next(row for row in value["items"] if row["item_id"] == identifier)
        row.update(status="insufficient", cultural_premises=["红色能够辟邪"],
                   claim_ids=["c1"], source_ids=["src-yuxian-technique"], reason="现有证据没有颜色寓意")
        return value

    llm = FakeLLM(draft, scan)
    result = generate_teaching(llm, make_run())
    assert result["check"]["passed"] is False
    assert "辟邪" in result[field]["text"]  # 失败候选保留，未伪装为成功或替换为模板。
    assert result["creative_label"] == CREATIVE_LABEL
    assert len(llm.calls) == 2
    with pytest.raises(ValueError):
        render_teaching_html(result, "visitor")


def test_missing_observation_scan_fails_closed():
    def omit(value):
        value["items"] = [item for item in value["items"] if item["item_id"] != "observation"]
        return value

    result = generate_teaching(FakeLLM(scan_change=omit), make_run())
    assert result["check"]["passed"] is False
    assert any("逐项覆盖" in issue for issue in result["check"]["issues"])


@pytest.mark.parametrize("text", ["请用专业刻刀完成一个图案。", "请大家接着参加染色制作和乡土茶歇。"])
def test_nonfactual_action_cannot_add_tool_operations_or_operating_activities(text):
    def draft(value):
        value["observation_task"]["text"] = text
        return value

    def scan(value):
        row = next(r for r in value["items"] if r["item_id"] == "observation")
        row.update(activity_scope_passed=False, reason="动作超出开放观察与问答范围")
        return value

    llm = FakeLLM(draft_change=draft, scan_change=scan)
    result = generate_teaching(llm, make_run())
    assert len(llm.calls) == 2
    assert not result["check"]["passed"]
    assert any("教学范围" in issue for issue in result["check"]["issues"])
    assert result["observation_task"]["text"] == text


def test_missing_activity_scope_verdict_is_not_assumed_safe():
    def scan(value):
        value["items"][1].pop("activity_scope_passed")
        return value

    result = generate_teaching(FakeLLM(scan_change=scan), make_run())
    assert not result["check"]["passed"]
    assert result["check"]["error_kind"] == "ValidationError"


def test_scan_cannot_say_no_fact_while_listing_fact():
    def lie(value):
        value["items"][1]["cultural_premises"] = ["这是未经核验的文化寓意"]
        return value

    assert generate_teaching(FakeLLM(scan_change=lie), make_run())["check"]["passed"] is False


@pytest.mark.parametrize("bad_ref", ["source", "claim"])
def test_new_or_unlinked_reference_blocks_before_scan(bad_ref):
    def draft(value):
        value["short_script"][0]["source_ids" if bad_ref == "source" else "claim_ids"] = ["invented-id"]
        return value

    llm = FakeLLM(draft_change=draft)
    result = generate_teaching(llm, make_run())
    assert not result["check"]["passed"]
    assert len(llm.calls) == 1


def test_wrong_checked_text_and_scan_reference_are_rejected():
    def scan(value):
        value["items"][0]["checked_text"] = "只审核另一句无关文本。"
        value["items"][0]["source_ids"] = ["src-fengning-technique"]
        return value

    result = generate_teaching(FakeLLM(scan_change=scan), make_run())
    assert not result["check"]["passed"]
    assert any("扫描文本" in issue for issue in result["check"]["issues"])


def test_multiple_sentences_in_single_item_are_not_partially_scanned():
    def draft(value):
        value["observation_task"]["text"] = "请观察图案。它能带来好运。"
        return value

    llm = FakeLLM(draft_change=draft)
    result = generate_teaching(llm, make_run())
    assert not result["check"]["passed"]
    assert len(llm.calls) == 1


@pytest.mark.parametrize("stage", [1, 2])
def test_model_failure_preserves_failure_without_fallback(stage):
    llm = FakeLLM(fail_stage=stage)
    result = generate_teaching(llm, make_run())
    assert not result["check"]["passed"]
    assert result["check"]["error_kind"] == "ModelFailure"
    assert len(llm.calls) == stage
    assert bool(result["short_script"]) == (stage == 2)


def test_exhausted_shared_budget_prevents_unchecked_generation():
    llm = FakeLLM()
    llm.calls = [{}] * 7
    result = generate_teaching(llm, make_run())
    assert result["generation_mode"] == "not_generated"
    assert result["check"]["model_calls_used"] == 0
    assert len(llm.calls) == 7


@pytest.mark.parametrize("change", ["content", "audience", "source-version", "withdrawn", "card-unusable"])
def test_post_scan_mutation_or_usage_change_invalidates_teaching(change):
    run = make_run()
    result = generate_teaching(FakeLLM(), run)
    if change == "content":
        result["interaction_question"]["text"] = "为什么该图案必定带来好运？"
    elif change == "audience":
        run["requirements"]["audience"] = "family"
    elif change == "source-version":
        run["sources_snapshot"][0]["version"] += 1
    elif change == "withdrawn":
        run["sources_snapshot"][0]["usage_status"] = "withdrawn"
    else:
        run["cards"][0]["usable"] = False
    assert validate_teaching(result, run)["passed"] is False


def test_no_supported_card_prevents_model_use():
    run = make_run()
    run["claims"][0]["status"] = "insufficient"
    llm = FakeLLM()
    assert not generate_teaching(llm, run)["check"]["passed"]
    assert llm.calls == []


def test_export_has_creative_label_and_organizer_provenance():
    result = generate_teaching(FakeLLM(), make_run("family"))
    assert "一起观察，一起发现" in render_teaching_html(result, "visitor")
    assert CREATIVE_LABEL in render_teaching_html(result, "visitor")
    assert "src-yuxian-technique" in render_teaching_html(result, "organizer")


def test_new_sources_have_hash_provenance_and_keep_original_ids():
    rows = load_sources()
    new = [r for r in rows if r["document_id"].startswith("hebei-")]
    assert len(new) == 6
    assert len({r["url"] for r in new}) == 2
    assert all(r["region"] == "河北省蔚县" and r["locator"] and r["published_at"] for r in new)
    assert len({r["id"] for r in rows}) == len(rows)


def bundle_run(mode="packages", teaching_enabled=True):
    """真实经营配置加合成模型审核，所有输出只用于隔离单元测试。"""
    run = make_run("family")
    requirements = {"region": "河北省蔚县", "project": "剪纸", "people": 8,
                    "budget_per_person": 160, "available_minutes": 150,
                    "start_time": "09:30", "preferred_plan": "deep", "audience": "family",
                    "planning_mode": mode, "teaching_enabled": teaching_enabled}
    planning = solve_plans(requirements, load_profile())
    plan = next(p for p in planning["candidates"] if p["feasible"])
    run.update(id="synthetic-teaching-bundle", version=1, mode="live", status="awaiting_review",
               requirements=requirements, planning=planning, plan=plan, validation={"passed": True})
    run["claims"][0]["evidence"] = deepcopy(run["sources_snapshot"])
    run["teaching"] = generate_teaching(FakeLLM(), run)
    assert run["teaching"]["check"]["passed"]
    return run


@pytest.mark.parametrize("audience", ["visitor", "organizer"])
def test_preview_needs_no_approval_and_does_not_create_one(audience):
    run = bundle_run()
    before = deepcopy(run)
    html = render_bundle(run, audience, preview=True)
    assert "待人工确认预览稿" in html
    assert "一起观察，一起发现" in html
    assert CREATIVE_LABEL in html
    assert "已确认当前模拟体验方案" not in html
    assert run == before and "approval" not in run
    with pytest.raises(ValueError, match="负责人确认"):
        render_bundle(run, audience)


@pytest.mark.parametrize("status", ["needs_input", "running", "invalidated", "failed", "cancelled"])
def test_preview_rejects_non_reviewable_status(status):
    run = bundle_run()
    run["status"] = status
    with pytest.raises(ValueError):
        render_bundle(run, "visitor", preview=True)


@pytest.mark.parametrize("validation", [{}, {"passed": False}, {"passed": "true"}])
def test_preview_requires_successful_validation(validation):
    run = bundle_run()
    run["validation"] = validation
    with pytest.raises(ValueError, match="已通过校验"):
        render_bundle(run, "organizer", preview=True)


def test_preview_of_confirmed_run_does_not_reuse_approval_for_another_candidate():
    run = bundle_run()
    run["status"] = "confirmed"
    run["approval"] = {"confirmed": True, "at": "SYNTHETIC-PRIOR-TIME",
                       "plan_id": "deep", "run_version": 1}
    assert run["plan"]["id"] == "light"
    html = render_bundle(run, "organizer", preview=True)
    assert "SYNTHETIC-PRIOR-TIME" not in html
    assert "待负责人确认" in html
    with pytest.raises(ValueError, match="当前方案不一致"):
        render_bundle(run, "organizer")


def test_effective_requirements_are_the_recalculation_boundary():
    run = bundle_run()
    effective = {**run["requirements"], "budget_per_person": 110}
    run["effective_requirements"] = effective
    run["planning"] = solve_plans(effective, load_profile())
    run["plan"] = next(p for p in run["planning"]["candidates"] if p["feasible"])
    html = render_bundle(run, "organizer", preview=True)
    assert "¥110.00" in html
    assert "¥784.00" in html
    run["effective_requirements"]["people"] = 9
    with pytest.raises(ValueError, match="需求快照不一致"):
        render_bundle(run, "organizer", preview=True)


@pytest.mark.parametrize("preview", [True, False])
@pytest.mark.parametrize("change", ["missing", "text", "source-withdrawn", "material-withdrawn", "scan-missing"])
def test_teaching_export_and_preview_fail_closed_on_mutation(preview, change):
    run = bundle_run()
    run.update(status="confirmed", approval={"confirmed": True, "plan_id": run["plan"]["id"], "run_version": 1})
    if change == "missing":
        run.pop("teaching")
    elif change == "text":
        run["teaching"]["interaction_question"]["text"] = "为什么这种剪纸可以辟邪？"
    elif change == "source-withdrawn":
        run["source_versions"]["src-yuxian-technique"]["usage_status"] = "withdrawn"
    elif change == "material-withdrawn":
        run["cards"][0]["material_ids"] = ["mat-paper-garden"]
        run["material_versions"] = {"mat-paper-garden": {"version": 2, "usage_status": "withdrawn"}}
    else:
        run["teaching"]["check"]["items"] = []
    with pytest.raises(ValueError, match="教学表达"):
        render_bundle(run, "visitor", preview=preview)


@pytest.mark.parametrize("preview", [True, False])
def test_modules_always_require_teaching_even_when_flag_false(preview):
    run = bundle_run("modules", teaching_enabled=False)
    run.update(status="confirmed", approval={"confirmed": True, "plan_id": run["plan"]["id"], "run_version": 1})
    assert "一起观察，一起发现" in render_bundle(run, "organizer", preview=preview)
    run.pop("teaching")
    with pytest.raises(ValueError, match="教学表达"):
        render_bundle(run, "organizer", preview=preview)


@pytest.mark.parametrize("audience", ["visitor", "organizer"])
def test_confirmed_teaching_export_matches_validated_content(audience):
    run = bundle_run()
    run.update(status="confirmed", approval={"confirmed": True, "at": "SYNTHETIC-CONFIRMED-TIME",
                                            "plan_id": run["plan"]["id"], "run_version": 1})
    html = render_bundle(run, audience)
    assert "待人工确认预览稿" not in html
    assert "一起观察，一起发现" in html
    assert run["teaching"]["interaction_question"]["text"] in html
    assert "src-yuxian-technique" in html
    run["plan"]["total_cents"] += 1
    with pytest.raises(ValueError, match="复算不一致"):
        render_bundle(run, audience, preview=True)
