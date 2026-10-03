"""业务契约单元测试：明确使用假模型/MockTransport，不是模型效果或真实运行记录。

SQLite 仅放本仓库 artifacts/test-results/workflow；不访问正在运行的 HTTP 服务。
"""

from concurrent.futures import Future
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest

from backend import app as api
from backend import model, store, workflow
from backend.evidence import load_sources


ROOT = Path(__file__).resolve().parents[2]
TEXT = "蔚县剪纸以阴刻为主，阳刻为辅。"


class ImmediateExecutor:
    """只用于单元测试，立即执行以避免定时等待和污染主后台线程。"""

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as error:
            future.set_exception(error)
            raise
        return future


def answer(schema_name, data, *, selection=None):
    if schema_name == "Understanding":
        return {"summary": "假模型测试摘要", "audience": "测试游客", "claims": [
            {"sentence_id": key, "text": text, "query": text}
            for key, text in data["sentences"].items()
        ]}
    if schema_name == "Audit":
        return {"judgments": [{
            "claim_id": c["id"], "status": "supported" if c["evidence"] else "insufficient",
            "evidence_ids": [c["evidence"][0]["id"]] if c["evidence"] else [],
            "reason": "假模型单元测试返回，不作为效果证据", "suggested_text": c["text"],
        } for c in data["claims"]]}
    feasible = [c["id"] for c in data["candidates"] if c["feasible"]]
    preferred = data["requirements"]["preferred_plan"]
    return {"plan_id": selection or (preferred if preferred in feasible else feasible[0] if feasible else "none"),
            "explanation": "假模型从程序候选中选择，仅检验接口与约束"}


@pytest.fixture
def client(monkeypatch):
    directory = ROOT / "artifacts/test-results/workflow" / uuid4().hex
    directory.mkdir(parents=True)
    monkeypatch.setattr(store, "DB_PATH", directory / "test.sqlite3")
    monkeypatch.setattr(api, "EXECUTOR", ImmediateExecutor())
    monkeypatch.setattr(api, "readiness", lambda: False)
    with TestClient(api.app) as value:
        yield value


@pytest.fixture
def fake_model(monkeypatch):
    """可注入错误的严格 schema 假模型，用来验证系统拒绝路径。"""
    controls = {"transform": lambda purpose, data, payload: payload, "instances": []}

    class FakeModel:
        def __init__(self, on_call=None):
            self.calls = []
            self.on_call = on_call or (lambda _: None)
            controls["instances"].append(self)

        def ask(self, purpose, data, schema, instruction):
            if len(self.calls) >= 8:
                raise model.ModelFailure("假模型单元测试调用预算上限")
            record = {"purpose": purpose, "model": "unit-test-fake-model", "ok": True}
            self.calls.append(record)
            self.on_call(record)
            value = controls["transform"](purpose, data, answer(schema.__name__, data))
            return schema.model_validate(value).model_dump()

    monkeypatch.setattr(workflow, "LocalModel", FakeModel)
    return controls


def submit(client, text=TEXT, **changes):
    response = client.post("/api/runs", json={"text": text, **changes})
    assert response.status_code == 202, response.text
    return client.get("/api/runs/" + response.json()["id"]).json()


def judgment(claim_id="c1", status="supported", evidence_ids=None, suggested_text=""):
    return {"claim_id": claim_id, "status": status,
            "evidence_ids": ["src-yuxian-technique"] if evidence_ids is None else evidence_ids,
            "reason": "合成审核结果用于程序校验", "suggested_text": suggested_text}


def claim(evidence=None):
    sources = [s for s in load_sources() if s["region"] == "河北省蔚县"]
    return {"id": "c1", "text": TEXT, "evidence": sources if evidence is None else evidence}


@pytest.mark.parametrize("rows", [[], [judgment("unknown")], [judgment(), judgment()],
    [judgment(evidence_ids=["src-fengning-technique"])], [judgment(evidence_ids=[])],
    [judgment(status="conflicting", evidence_ids=["src-yuxian-technique", "src-yuxian-color"])],
])
def test_judgment_rejects_missing_duplicate_unknown_or_unlocated_evidence(rows):
    with pytest.raises(ValueError):
        workflow.validated_judgments({"judgments": rows}, [claim()])


def test_no_evidence_can_only_be_insufficient():
    with pytest.raises(ValueError):
        workflow.validated_judgments({"judgments": [judgment()]}, [claim([])])
    result = workflow.validated_judgments(
        {"judgments": [judgment(status="insufficient", evidence_ids=[], suggested_text="虚构的修订")]}, [claim([])])
    assert result[0]["status"] == "insufficient"
    assert result[0]["suggested_text"] == ""


def test_supported_claim_cannot_be_silently_rewritten():
    result = workflow.validated_judgments(
        {"judgments": [judgment(suggested_text="不同且未经支持的文本")]}, [claim()])
    assert result[0]["suggested_text"] == TEXT


@pytest.mark.parametrize("mutation", ["omit-sentence", "partial-sentence", "duplicate-sentence", "invent-text"])
def test_understanding_cannot_omit_shrink_duplicate_or_invent_sentences(client, fake_model, mutation):
    def transform(purpose, data, value):
        if purpose == "理解需求与拆分陈述":
            if mutation == "omit-sentence":
                value["claims"] = value["claims"][:1]
            elif mutation == "partial-sentence":
                value["claims"][0]["text"] = "蔚县剪纸"
            elif mutation == "duplicate-sentence":
                value["claims"].append(deepcopy(value["claims"][0]))
            else:
                value["claims"][0]["text"] = "模型虚构的原文"
        return value

    fake_model["transform"] = transform
    result = submit(client, TEXT + "蔚县剪纸采用多色点染彩绘。")
    assert result["status"] == "failed"
    assert result["cards"] == []
    assert result["model_calls"] == 1


def test_budget_change_selects_real_recomputed_candidate_without_changing_resources(client, fake_model):
    first = submit(client)
    assert first["status"] == "awaiting_review"
    assert first["plan"]["id"] == "deep"
    assert first["plan"]["total_cents"] == 108000
    assert first["plan"]["duration_minutes"] == 120
    changed = submit(client, requirements={"budget_per_person": 110})
    assert changed["status"] == "awaiting_review"
    assert changed["plan"]["id"] == "light"
    assert changed["plan"]["total_cents"] == 78400
    assert changed["plan"]["duration_minutes"] == 90
    assert changed["requirements"]["people"] == 8
    assert changed["profile"]["teachers"] == 1
    assert changed["profile"]["plans"] == first["profile"]["plans"]
    assert any(c["code"] == "budget_exceeded" for c in changed["initial_conflicts"])
    assert 0 < changed["revision_count"] <= 2
    assert changed["model_calls"] <= 8


def test_unavailable_resources_require_input_and_never_invent_parallel_reception(client, fake_model):
    result = submit(client, requirements={"people": 16},
                    operating_overrides={"capacity": 8, "teachers": 0, "rooms": 0})
    assert result["status"] == "needs_input"
    assert result["plan"] is None
    assert result["planning"]["feasible_ids"] == []
    assert result["requirements"]["people"] == 16
    assert result["profile"]["teachers"] == 0
    for candidate in result["planning"]["candidates"]:
        codes = {conflict["code"] for conflict in candidate["conflicts"]}
        assert {"capacity_exceeded", "teacher_unavailable", "room_unavailable"} <= codes
        assert all(not stage["resource_ids"] for stage in candidate["schedule"])
    assert not any(c["purpose"] == "选择与解释体验方案" for c in result["model_metrics"])


@pytest.mark.parametrize("region", ["丰宁", "不明地域"])
def test_regional_resources_are_not_transferred_to_other_or_unknown_regions(client, fake_model, region):
    result = submit(client, requirements={"region": region})
    assert result["status"] == "needs_input"
    assert result["plan"] is None
    assert result["profile"]["region"] == "河北省蔚县"
    assert client.post(f"/api/runs/{result['id']}/approve", json={"confirmed": True, "plan_id": "deep"}).status_code == 409


def test_model_cannot_override_program_ranking_with_infeasible_plan(client, fake_model):
    def transform(purpose, data, value):
        if purpose == "选择与解释体验方案":
            value["plan_id"] = "deep"
        return value

    fake_model["transform"] = transform
    result = submit(client, requirements={"budget_per_person": 110})
    assert result["status"] == "awaiting_review"
    assert result["plan"]["id"] == "light"
    assert result["selection_method"] == "deterministic_preference_ranking"
    assert not any(c["purpose"] == "选择与解释体验方案" for c in result["model_metrics"])
    assert 0 < result["revision_count"] <= 2
    assert result["model_calls"] <= 8
    assert client.post(f"/api/runs/{result['id']}/approve", json={"confirmed": True, "plan_id": "deep"}).status_code == 409


def test_human_confirmation_required_then_retraction_blocks_both_exports(client, fake_model):
    result = submit(client)
    run_url = f"/api/runs/{result['id']}"
    for audience in ("visitor", "organizer"):
        assert client.get(run_url + "/export", params={"audience": audience}).status_code == 409
    assert client.post(run_url + "/approve", json={"confirmed": False, "plan_id": "deep"}).status_code == 422
    assert client.post(run_url + "/approve", json={"confirmed": True, "plan_id": "deep"}).status_code == 200
    for audience in ("visitor", "organizer"):
        exported = client.get(run_url + "/export", params={"audience": audience})
        assert exported.status_code == 200
        assert "text/html" in exported.headers["content-type"]
        assert "演示测算" in exported.text
        assert "120" in exported.text
    changed = client.patch("/api/materials/mat-paper-garden", json={"usage_status": "withdrawn"})
    assert changed.status_code == 200
    assert changed.json()["affected_runs"][0]["card_ids"]
    current = client.get(run_url).json()
    assert current["status"] == "invalidated"
    assert current["approval"] is None
    for audience in ("visitor", "organizer"):
        assert client.get(run_url + "/export", params={"audience": audience}).status_code == 409
    assert client.post(run_url + "/approve", json={"confirmed": True, "plan_id": "deep"}).status_code == 409
    refreshed = client.post(run_url + "/refresh")
    assert refreshed.status_code == 202
    child = client.get("/api/runs/" + refreshed.json()["id"]).json()
    assert child["parent_id"] == result["id"]
    assert child["status"] == "awaiting_review"
    assert all("mat-paper-garden" not in card["material_ids"] for card in child["cards"])
    assert child["approval"] is None


def test_cross_origin_mutation_is_rejected(client):
    response = client.patch("/api/materials/mat-paper-garden", json={"usage_status": "withdrawn"},
                            headers={"origin": "https://unrelated.example.invalid"})
    assert response.status_code == 403
    assert store.records("materials")[0]["usage_status"] == "available"


def test_correction_evidence_change_locates_original_claim_and_blocks_export(client, fake_model):
    def transform(purpose, data, value):
        if purpose == "逐句证据核验":
            value["judgments"][0].update(
                status="contradicted", evidence_ids=["src-yuxian-region"], suggested_text=TEXT)
        elif purpose == "复核修订文本":
            value["judgments"][0].update(status="supported", evidence_ids=["src-yuxian-technique"])
        return value

    # 合成不同引用路径仅用于验证关系保存，不宣称此假判断的语义正确。
    fake_model["transform"] = transform
    result = submit(client, "蔚县剪纸以阳刻为主，阴刻为辅。")
    assert result["status"] == "awaiting_review"
    assert result["claims"][0]["corrected_status"] == "supported"
    assert result["cards"][0]["text"] == TEXT
    assert result["cards"][0]["source_ids"] == ["src-yuxian-technique"]
    run_url = f"/api/runs/{result['id']}"
    assert client.post(run_url + "/approve", json={"confirmed": True, "plan_id": "deep"}).status_code == 200
    changed = client.patch("/api/sources/src-yuxian-technique", json={"usage_status": "withdrawn"})
    assert changed.status_code == 200
    impact = changed.json()["affected_runs"][0]
    assert impact["claim_ids"] == ["c1"]
    assert impact["card_ids"] == ["card-c1"]
    assert client.get(run_url + "/export").status_code == 409


def test_real_model_wrapper_eight_call_cap_includes_json_retries(client, monkeypatch):
    """使用真实LocalModel包装器+模拟HTTP响应；没有真实模型推理。"""
    original_client = httpx.Client
    request_count = 0

    def handler(request):
        nonlocal request_count
        request_count += 1
        body = json.loads(request.content)
        data = json.loads(body["messages"][1]["content"])
        if request_count % 2:
            raw = "{"  # 每次首答格式故障，验证修复也消耗预算。
        else:
            raw = json.dumps(answer(body["format"]["title"], data, selection="none"), ensure_ascii=False)
        return httpx.Response(200, json={"message": {"content": raw}})

    monkeypatch.setattr(model.httpx, "Client", lambda *a, **kw: original_client(*a, **kw, transport=httpx.MockTransport(handler)))
    from backend.schemas import Understanding
    wrapper = model.LocalModel()
    for _ in range(4):
        wrapper.ask("接口预算回归", {"sentences": {"s1": TEXT}}, Understanding, "仅为预算回归")
    with pytest.raises(model.ModelFailure, match="8次"):
        wrapper.ask("超额调用", {}, Understanding, "仅为预算回归")
    assert len(wrapper.calls) == 8
    assert request_count == 8
    assert any("raw_output" in metrics for metrics in wrapper.calls)
