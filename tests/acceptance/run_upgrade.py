"""一次性真实内部验收；先冻结输入/提示，不调参、不覆盖首轮，不是独立评测。"""
from pathlib import Path
import hashlib
import json
import sys
import time
import httpx

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/validation/upgrade-cases"


def evaluate(case, run, export_status):
    expected = case["expected_semantics"]
    checks = []
    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})
    intent = run.get("intent", {})
    plan = run.get("plan") or {}
    planning = run.get("planning") or {}
    candidates = planning.get("candidates", [])
    for key, value in expected.get("must_extract", {}).items():
        if key == "exclude_tags_contains":
            check(key, set(value).issubset(intent.get("exclude_tags", [])))
        else:
            check(key, intent.get(key) == value)
    if expected.get("feasible_plan_required"):
        check("完整可行方案与教学通过", run["status"] == "awaiting_review" and plan.get("feasible") and run.get("teaching", {}).get("check", {}).get("passed"))
    for module in expected.get("selected_plan_must_exclude_modules", []):
        check("不包含模块:" + module, bool(plan) and module not in plan.get("module_ids", []))
    for key, field, op in [("selected_plan_min_craft_minutes", "craft_minutes", lambda a,b:a>=b),
                           ("selected_plan_max_total_cents", "total_cents", lambda a,b:a<=b),
                           ("selected_plan_max_minutes", "duration_minutes", lambda a,b:a<=b)]:
        if key in expected:
            check(key, field in plan and op(plan[field], expected[key]))
    if expected.get("must_keep_form_numbers"):
        check("人数预算时长不被模型改写", all(run.get("effective_requirements", run["requirements"])[k] == case["input"]["requirements"][k]
                                             for k in ("people", "budget_per_person", "available_minutes")))
    fragments = expected.get("must_separate_claim_fragments", [])
    matched = [[c for c in run.get("claims", []) if fragment in c["text"]] for fragment in fragments]
    if fragments:
        check("复合陈述逐个事实独立定位", all(len(rows) == 1 for rows in matched) and len({rows[0]["id"] for rows in matched if rows}) == len(fragments))
    for fragment, status in expected.get("expected_fact_statuses", {}).items():
        rows = [c for c in run.get("claims", []) if fragment in c["text"]]
        check("事实状态:" + fragment, len(rows) == 1 and rows[0]["status"] == status)
    if expected.get("correction_must_be_reverified"):
        wrong = [c for c in run.get("claims", []) if c["status"] == "contradicted"]
        check("矛盾修订再次核验", bool(wrong) and all(c.get("corrected_status") == "supported" for c in wrong))
    if expected.get("visitor_must_not_assert"):
        visitor_text = json.dumps({"cards": run.get("cards", []), "teaching": run.get("teaching", {})}, ensure_ascii=False)
        check("未经支持的承诺不进入游客内容", all(text not in visitor_text for text in expected["visitor_must_not_assert"]))
    if expected.get("must_pause_for_confirmation"):
        check("冲突明确等待确认", run["status"] == "needs_confirmation" and not run.get("plan"))
        fields = {item["field"] for item in run.get("requirement_conflicts", [])}
        check("冲突字段覆盖", set(expected["conflicting_fields_contains"]).issubset(fields))
        check("冲突不替换表单", all(run["requirements"][k] == v for k,v in expected["must_not_silently_replace_form_values"].items()))
    if expected.get("no_package_can_satisfy_all_preferences"):
        check("套餐不能忽略偏好继续可行", run["status"] == "needs_input" and not planning.get("feasible_ids") and not plan)
        check("提取排除茶歇与七十分钟", "tea" in intent.get("exclude_tags", []) and intent.get("min_craft_minutes") == 70)
        for candidate in candidates:
            check(candidate["id"] + "套餐价格时长不变", candidate["total_cents"] == expected["package_prices_cents_must_remain"][candidate["id"]]
                  and candidate["duration_minutes"] == expected["package_minutes_must_remain"][candidate["id"]])
        check("两套餐仍列出", {p["id"] for p in candidates} == {"light", "deep"})
    if expected.get("no_feasible_plan"):
        check("资源不足明确无解", run["status"] == "needs_input" and not plan and not planning.get("feasible_ids"))
        codes = {c["code"] for p in candidates for c in p["conflicts"]}
        check("容量与教师冲突有据", set(expected["conflict_codes_contains"]).issubset(codes))
        check("人数与资源未增加", run["requirements"]["people"] == expected["must_not_change_people"] and run["profile"]["teachers"] == 1 and run["profile"]["rooms"] == 1)
    check("未人工确认不能下载", export_status == 409 and run.get("approval") is None)
    if plan:
        from backend.planner import solve_plans
        recomputed = solve_plans(run.get("effective_requirements", run["requirements"]), run["profile"])
        check("所选方案全字段可复算", any(candidate == plan for candidate in recomputed["candidates"]))
    return checks


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    frozen = json.loads((OUTPUT / "freeze-manifest.json").read_text(encoding="utf-8"))
    path = ROOT / "tests/acceptance/upgrade-holdout.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == frozen["acceptance_sha256"]
    for name, digest in frozen["files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, "冻结后实现变化:" + name
    summary = {"type": "small_internal_acceptance_not_independent", "input_sha256": frozen["acceptance_sha256"], "cases": []}
    if (OUTPUT / "holdout-summary.json").exists():
        raise FileExistsError("首轮验收已存在，不覆盖或重跑；修复后复测应另记")
    with httpx.Client(base_url="http://127.0.0.1:8780", timeout=30, trust_env=False) as client:
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            response = client.post("/api/runs", json=case["input"])
            response.raise_for_status()
            run_id = response.json()["id"]
            deadline = time.monotonic() + 600
            while True:
                run = client.get("/api/runs/" + run_id).json()
                if run.get("execution_finished"):
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("不重试未完成的任务:" + run_id)
                time.sleep(1)
            destination = OUTPUT / (case["id"].lower() + ".json")
            with destination.open("x", encoding="utf-8") as handle:
                json.dump(run, handle, ensure_ascii=False, indent=2)
            status = client.get(f"/api/runs/{run_id}/export").status_code
            checks = evaluate(case, run, status)
            entry = {"case_id": case["id"], "run_id": run_id, "status": run["status"], "model_calls": run["model_calls"],
                     "elapsed_seconds": run["elapsed_seconds"], "passed": all(c["passed"] for c in checks), "checks": checks}
            summary["cases"].append(entry)
            (OUTPUT / "holdout-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(entry, ensure_ascii=False), flush=True)
    return 0 if all(c["passed"] for c in summary["cases"]) else 1


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
