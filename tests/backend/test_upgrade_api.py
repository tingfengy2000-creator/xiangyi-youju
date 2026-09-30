"""升级边界的假模型/API集成回归，不是实际模型结果。

所有请求由内存ASGI TestClient处理；SQLite限定仓库artifacts隔离子目录。
不访问8780、Ollama或当前业务数据库；不读取冻结验收输入。
"""

from concurrent.futures import Future
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from backend import app as api
from backend import store, workflow


ROOT = Path(__file__).resolve().parents[2]
TEXT = "蔚县剪纸以阴刻为主，阳刻为辅。"


class ImmediateExecutor:
    def submit(self, function, *args):
        future = Future()
        result = function(*args)
        future.set_result(result)
        return future


def neutral_intent(**changes):
    return {"exclude_tags": [], "require_tags": [], "min_craft_minutes": None,
            "maximize_craft": False, "audience": None, "people": None,
            "budget_per_person": None, "available_minutes": None, "ambiguities": [], **changes}


@pytest.fixture
def harness(monkeypatch):
    directory = ROOT / "artifacts" / "test-results" / "upgrade-api" / uuid4().hex
    directory.mkdir(parents=True)
    monkeypatch.setattr(store, "DB_PATH", directory / "test.sqlite3")
    monkeypatch.setattr(api, "EXECUTOR", ImmediateExecutor())
    monkeypatch.setattr(api, "readiness", lambda: False)
    controls = {"intent": neutral_intent(), "calls": []}

    class FakeModel:
        def __init__(self, on_call=None):
            self.calls = []
            self.on_call = on_call or (lambda item: None)

        def ask(self, purpose, data, schema, instruction, *, max_attempts=2):
            record = {"purpose": purpose, "model": "upgrade-unit-test-fake-model", "ok": True}
            self.calls.append(record)
            controls["calls"].append(purpose)
            self.on_call(record)
            name = schema.__name__
            if name in ("Understanding", "ContentUnderstanding"):
                value = {"summary": "假模型仅验证业务状态", "audience": "测试客群", "claims": [
                    {"sentence_id": key, "text": text, "query": text}
                    for key, text in data["sentences"].items()
                ]}
                if name == "ContentUnderstanding":
                    assert set(data["requirements"]) == {"region", "project"}
            elif name == "NotePreferences":
                assert purpose == "提取文字活动偏好"
                assert set(data) == {"note"}
                value = deepcopy(controls["intent"])
                excluded, required = value.pop("exclude_tags"), value.pop("require_tags")
                value["tea_preference"] = "exclude" if "tea" in excluded else "include" if "tea" in required else "not_mentioned"
                if "tea" in excluded and "tea" in required:
                    value["tea_preference"] = "not_mentioned"
                    value["ambiguities"].append("文字同时要求保留茶歇和取消茶歇，请澄清")
            elif name == "Audit":
                value = {"judgments": [{"claim_id": claim["id"], "status": "supported" if claim["evidence"] else "insufficient",
                                        "evidence_ids": [claim["evidence"][0]["id"]] if claim["evidence"] else [],
                                        "reason": "假模型接口回归结果，不证明事实核验性能", "suggested_text": claim["text"]}
                                       for claim in data["claims"]]}
            elif name == "Choice":
                feasible = [candidate for candidate in data["candidates"] if candidate["feasible"]]
                value = {"plan_id": feasible[0]["id"] if feasible else "none", "explanation": "仅为接口回归选取程序候选"}
            elif name == "TeachingDraft":
                card = data["cards"][0]
                unit = {"text": card["text"], "claim_ids": card["claim_ids"], "source_ids": card["source_ids"]}
                value = {"short_script": [unit],
                         "observation_task": {**unit, "text": "请观察负责人提供且允许使用的剪纸示例。"},
                         "interaction_question": {**unit, "text": "哪一处细节引起了你的兴趣？"}}
            elif name == "TeachingScan":
                value = {"items": [{"item_id": unit["item_id"], "checked_text": unit["text"],
                                    "activity_scope_passed": True,
                                    "status": "supported" if unit["item_id"].startswith("script-") else "no_new_fact",
                                    "cultural_premises": [unit["text"]] if unit["item_id"].startswith("script-") else [],
                                    "claim_ids": unit["claim_ids"] if unit["item_id"].startswith("script-") else [],
                                    "source_ids": unit["source_ids"] if unit["item_id"].startswith("script-") else [],
                                    "reason": "假模型扫描用于状态保护回归"} for unit in data["items"]]}
            else:
                raise AssertionError(f"测试没有允许的模型schema：{name}")
            return schema.model_validate(value).model_dump()

    monkeypatch.setattr(workflow, "LocalModel", FakeModel)
    with TestClient(api.app) as client:
        yield client, controls


def payload(**changes):
    value = {"text": TEXT, "requirements": {"planning_mode": "modules", "people": 8,
             "budget_per_person": 160, "available_minutes": 150, "note": "程序回归用备注，不代表模型语义效果"},
             "constraint_resolution": "ask"}
    value.update(changes)
    return value


def submit(client, value):
    response = client.post("/api/runs", json=value)
    assert response.status_code == 202, response.text
    result = client.get("/api/runs/" + response.json()["id"])
    assert result.status_code == 200
    return result.json()


def test_note_form_conflict_stops_before_audit_and_confirmation(harness):
    client, controls = harness
    controls["intent"] = neutral_intent(people=9, budget_per_person=120)
    run = submit(client, payload())
    assert run["status"] == "needs_confirmation"
    assert {c["field"] for c in run["requirement_conflicts"]} == {"people", "budget_per_person"}
    assert run["requirements"]["people"] == run["effective_requirements"]["people"] == 8
    assert run["requirements"]["budget_per_person"] == run["effective_requirements"]["budget_per_person"] == 160
    assert run["model_calls"] == 2
    assert controls["calls"] == ["理解需求与拆分陈述", "提取文字活动偏好"]
    assert run["planning"] is None and run["plan"] is None and run["approval"] is None
    assert run["execution_finished"] is True
    assert client.post(f"/api/runs/{run['id']}/approve", json={"confirmed": True, "plan_id": "light"}).status_code == 409
    assert client.get(f"/api/runs/{run['id']}/export").status_code == 409
    assert client.get(f"/api/runs/{run['id']}/export", params={"preview": True}).status_code == 409


def test_keep_form_is_explicit_and_preserves_nonconflicting_note_preferences(harness):
    client, controls = harness
    controls["intent"] = neutral_intent(budget_per_person=120, exclude_tags=["tea"], maximize_craft=True)
    value = payload()
    value["requirements"]["tea_preference"] = "include"
    waiting = submit(client, value)
    assert waiting["status"] == "needs_confirmation"
    value.update(constraint_resolution="form", previous_run_id=waiting["id"])
    chosen = submit(client, value)
    assert chosen["status"] == "awaiting_review", chosen["error"]
    assert chosen["effective_requirements"]["budget_per_person"] == 160
    assert chosen["effective_requirements"]["constraints"]["require_tags"] == ["tea"]
    assert chosen["effective_requirements"]["constraints"]["exclude_tags"] == []
    assert chosen["effective_requirements"]["constraints"]["maximize_craft"] is True
    assert "tea" in chosen["plan"]["module_ids"]
    assert chosen["approval"] is None
    assert client.get(f"/api/runs/{waiting['id']}").json()["status"] == "needs_confirmation"


def test_accept_note_by_user_updated_form_then_resubmit_can_continue(harness):
    client, controls = harness
    controls["intent"] = neutral_intent(people=9, budget_per_person=120, exclude_tags=["tea"])
    value = payload()
    waiting = submit(client, value)
    assert waiting["status"] == "needs_confirmation"
    updated = deepcopy(value)
    for conflict in waiting["requirement_conflicts"]:
        updated["requirements"][conflict["field"]] = conflict["note_value"]
    updated["previous_run_id"] = waiting["id"]
    accepted = submit(client, updated)
    assert accepted["status"] == "awaiting_review", accepted["error"]
    assert accepted["requirement_conflicts"] == []
    assert accepted["requirements"]["people"] == accepted["effective_requirements"]["people"] == 9
    assert accepted["requirements"]["budget_per_person"] == 120
    assert "tea" not in accepted["plan"]["module_ids"]
    assert client.get(f"/api/runs/{waiting['id']}").json()["approval"] is None


def test_refresh_does_not_accept_unresolved_conflicts(harness):
    client, controls = harness
    controls["intent"] = neutral_intent(people=9)
    waiting = submit(client, payload())
    response = client.post(f"/api/runs/{waiting['id']}/refresh")
    assert response.status_code == 202
    refreshed = client.get(f"/api/runs/{response.json()['id']}").json()
    assert refreshed["status"] == "needs_confirmation"
    assert refreshed["parent_id"] == waiting["id"]
    assert refreshed["requirements"]["people"] == 8
    assert refreshed["planning"] is None


def test_previous_run_comparison_uses_saved_snapshot_not_rewritten_old_plan(harness):
    client, controls = harness
    before = submit(client, payload())
    approved = client.post(f"/api/runs/{before['id']}/approve", json={"confirmed": True, "plan_id": before["plan"]["id"]})
    assert approved.status_code == 200, approved.text
    old_snapshot = client.get(f"/api/runs/{before['id']}").json()
    controls["intent"] = neutral_intent(exclude_tags=["tea"], min_craft_minutes=70, maximize_craft=True)
    after = submit(client, payload(previous_run_id=before["id"]))
    assert after["status"] == "awaiting_review", after["error"]
    assert after["comparison"]["before"]["id"] == old_snapshot["plan"]["id"]
    assert after["comparison"]["after"]["id"] == after["plan"]["id"]
    assert after["comparison"]["before"]["craft_minutes"] < after["comparison"]["after"]["craft_minutes"]
    assert after["previous_plan"] == old_snapshot["plan"]
    assert client.get(f"/api/runs/{before['id']}").json() == old_snapshot


def test_unknown_previous_run_cannot_create_partial_task(harness):
    client, controls = harness
    response = client.post("/api/runs", json=payload(previous_run_id="f" * 32))
    assert response.status_code == 404
    assert client.get("/api/runs").json()["runs"] == []
    assert controls["calls"] == []


@pytest.mark.parametrize("confirmed", [False, True])
def test_preview_is_read_only_for_pending_and_confirmed_runs(harness, confirmed):
    client, _ = harness
    run = submit(client, payload())
    if confirmed:
        response = client.post(f"/api/runs/{run['id']}/approve", json={"confirmed": True, "plan_id": run["plan"]["id"]})
        assert response.status_code == 200, response.text
    before = client.get(f"/api/runs/{run['id']}").json()
    alternative = next(p for p in before["planning"]["candidates"] if p["feasible"] and p["id"] != before["plan"]["id"])
    response = client.get(f"/api/runs/{run['id']}/export", params={"preview": True, "audience": "visitor", "plan_id": alternative["id"]})
    assert response.status_code == 200, response.text
    assert "inline" in response.headers["content-disposition"]
    assert "预览" in response.text
    after = client.get(f"/api/runs/{run['id']}").json()
    assert after == before
    assert after["approval"] is not None if confirmed else after["approval"] is None
    assert client.get(f"/api/runs/{run['id']}/export", params={"plan_id": alternative["id"]}).status_code in {409, 422}


@pytest.mark.parametrize("confirmed", [False, True])
def test_usage_change_rejects_preview_and_download_after_invalidation(harness, confirmed):
    client, _ = harness
    run = submit(client, payload())
    if confirmed:
        assert client.post(f"/api/runs/{run['id']}/approve", json={"confirmed": True, "plan_id": run["plan"]["id"]}).status_code == 200
    changed = client.patch("/api/materials/mat-paper-garden", json={"usage_status": "withdrawn"})
    assert changed.status_code == 200
    for preview in (False, True):
        response = client.get(f"/api/runs/{run['id']}/export", params={"preview": preview})
        assert response.status_code == 409
    stale = client.get(f"/api/runs/{run['id']}").json()
    assert stale["status"] == "invalidated" and stale["approval"] is None


def test_internal_note_contradiction_never_becomes_form_override(harness):
    client, controls = harness
    controls["intent"] = neutral_intent(exclude_tags=["tea"], require_tags=["tea"])
    run = submit(client, payload(constraint_resolution="form"))
    assert run["status"] == "needs_input"
    assert run["planning"] is None
    assert run["model_calls"] == 2
    assert client.get(f"/api/runs/{run['id']}/export", params={"preview": True}).status_code == 409


def test_empty_note_skips_preference_model_and_preserves_form(harness):
    client, controls = harness
    controls["intent"] = neutral_intent(people=9, audience="family", exclude_tags=["tea"])
    value = payload()
    value["requirements"].update(note="   ", audience="general", tea_preference="include")
    run = submit(client, value)
    assert run["status"] == "awaiting_review", run["error"]
    assert "提取文字活动偏好" not in controls["calls"]
    assert run["intent_origin"] == "empty_note_no_inference"
    assert run["requirement_conflicts"] == []
    assert run["effective_requirements"]["people"] == 8
    assert run["effective_requirements"]["audience"] == "general"
    assert run["effective_requirements"]["constraints"]["require_tags"] == ["tea"]
