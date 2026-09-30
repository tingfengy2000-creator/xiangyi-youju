"""Small real-model acceptance run; never mocks model or backend responses."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]
WRONG = "蔚县剪纸以阳刻为主，阴刻为辅。蔚县剪纸善于多色点染。工坊每天开放并且无需预约。"
CORRECT = "蔚县剪纸以阴刻为主，阳刻为辅。蔚县剪纸善于多色点染。"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="少量真实模型端到端验收，会产生本地历史记录")
    parser.add_argument("--base-url", default="http://127.0.0.1:8780")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "artifacts/live-validation" / stamp
    output.mkdir(parents=True, exist_ok=True)
    report = {"at": stamp, "base_url": args.base_url, "mode": "real-local-inference", "cases": [], "passed": False}
    client = httpx.Client(base_url=args.base_url, timeout=30, trust_env=False)

    def wait(run_id, name):
        deadline, seen = time.monotonic() + 900, 0
        while time.monotonic() < deadline:
            response = client.get(f"/api/runs/{run_id}")
            response.raise_for_status()
            run = response.json()
            for event in run["events"]:
                if event["seq"] > seen:
                    print(f"{name}: {event['message']}", flush=True)
                    seen = event["seq"]
            if run["status"] != "running" and run.get("execution_finished", True):
                (output / f"{name}.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
                report["cases"].append({"name": name, "id": run_id, "status": run["status"],
                                        "model_calls": run["model_calls"], "elapsed_seconds": run["elapsed_seconds"],
                                        "revision_count": run["revision_count"], "error": run["error"]})
                return run
            time.sleep(0.8)
        raise TimeoutError("本地真实任务超过验收等待窗口")

    def create(name, text, budget=160, people=8, capacity=12, teachers=1):
        request = {"text": text, "requirements": {"region": "河北省蔚县", "project": "剪纸", "people": people,
                   "budget_per_person": budget, "available_minutes": 150, "preferred_plan": "deep", "start_time": "09:30",
                   "note": "为初次了解剪纸的游客安排有来源的讲解与入门体验，不能改变明确人数和经营报价。"},
                   "operating_overrides": {"capacity": capacity, "teachers": teachers, "rooms": 1, "reuse": True}}
        response = client.post("/api/runs", json=request)
        response.raise_for_status()
        return wait(response.json()["id"], name)

    def approve_and_export(run, name):
        response = client.post(f"/api/runs/{run['id']}/approve", json={"confirmed": True, "plan_id": run["plan"]["id"]})
        response.raise_for_status()
        exports = {}
        for audience in ("visitor", "organizer"):
            response = client.get(f"/api/runs/{run['id']}/export", params={"audience": audience})
            response.raise_for_status()
            exports[audience] = response.text
            (output / f"{name}-{audience}.html").write_text(response.text, encoding="utf-8")
        return exports

    material_changed = False
    try:
        assert client.get("/api/health").json()["model_ready"], "官方本地模型尚未就绪，不能冒充完成"
        catalog = client.get("/api/catalog").json()
        assert next(m for m in catalog["materials"] if m["id"] == "mat-paper-garden")["usage_status"] == "available", "请先在界面明确恢复演示素材的可用状态"
        first = create("regional-correction", WRONG)
        assert first["status"] == "awaiting_review", first.get("error")
        assert [c["status"] for c in first["claims"]] == ["contradicted", "supported", "insufficient"]
        assert first["claims"][0]["corrected_status"] == "supported"
        assert first["plan"]["total_cents"] == 108000 and first["plan"]["duration_minutes"] == 120
        assert next(p for p in first["planning"]["candidates"] if p["id"] == "light")["total_cents"] == 78400
        before = approve_and_export(first, "regional-correction")
        assert 'data:image/svg+xml;base64,' in before["visitor"]
        assert "工坊每天开放并且无需预约" not in before["visitor"]

        budget = create("budget-110", CORRECT, budget=110)
        assert budget["status"] == "awaiting_review", budget.get("error")
        assert all(c["status"] == "supported" for c in budget["claims"])
        assert budget["plan"]["id"] == "light" and budget["plan"]["total_cents"] == 78400
        assert budget["plan"]["duration_minutes"] == 90 and budget["revision_count"] >= 1
        assert not next(p for p in budget["planning"]["candidates"] if p["id"] == "deep")["feasible"]
        approve_and_export(budget, "budget-110")

        impossible = create("capacity-resource-conflict", CORRECT, people=16, capacity=8, teachers=1)
        assert impossible["status"] == "needs_input" and impossible["plan"] is None
        assert impossible["planning"]["feasible_ids"] == []
        assert impossible["requirements"]["people"] == 16 and impossible["profile"]["teachers"] == 1
        codes = {c["code"] for p in impossible["planning"]["candidates"] for c in p["conflicts"]}
        assert {"capacity_exceeded", "teacher_capacity_exceeded"} <= codes
        assert client.post(f"/api/runs/{impossible['id']}/approve", json={"confirmed": True, "plan_id": "light"}).status_code == 409

        response = client.patch("/api/materials/mat-paper-garden", json={"usage_status": "withdrawn"})
        response.raise_for_status()
        material_changed = True
        impacts = response.json()
        (output / "material-impact.json").write_text(json.dumps(impacts, ensure_ascii=False, indent=2), encoding="utf-8")
        impacted = next(r for r in impacts["affected_runs"] if r["id"] == budget["id"])
        assert impacted["card_ids"] and impacted["plan_ids"]
        assert client.get(f"/api/runs/{budget['id']}/export?audience=visitor").status_code == 409
        response = client.post(f"/api/runs/{budget['id']}/refresh")
        response.raise_for_status()
        refreshed = wait(response.json()["id"], "material-refreshed")
        assert refreshed["status"] == "awaiting_review", refreshed.get("error")
        assert all("mat-paper-garden" not in c["material_ids"] for c in refreshed["cards"])
        after = approve_and_export(refreshed, "material-refreshed")
        assert 'data:image/svg+xml;base64,' not in after["visitor"]
        assert "以阴刻为主" in after["visitor"]
        report["passed"] = True
    except Exception as error:
        report["failure"] = str(error)
        raise
    finally:
        if material_changed:
            response = client.patch("/api/materials/mat-paper-garden", json={"usage_status": "available"})
            report["material_restored"] = response.status_code == 200
        (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(output), **report}, ensure_ascii=False), flush=True)
        client.close()


if __name__ == "__main__":
    main()
