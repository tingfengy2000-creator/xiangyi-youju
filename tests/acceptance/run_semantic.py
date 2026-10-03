"""冻结输入的一次性真实内部成对验收，不是独立第三方评测。

先由实现负责人确认稳定后执行 --freeze，再执行 --run。不得拿首次结果调试后
覆盖重跑；若进程中断，保留已有 run/started/checks 文件作为未完成记录。
API 用 TestClient 与隔离 SQLite，模型仍真实访问本仓库 Ollama，不使用假模型。
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "tests/acceptance/semantic-holdout.json"
DIRECTORY = ROOT / "docs/validation/semantic-cases"
FREEZE = DIRECTORY / "implementation-freeze.json"
OUTPUT = DIRECTORY / "first-run"
PACKS = ROOT / "artifacts/semantic-acceptance/packs"
DATABASE = ROOT / "artifacts/runtime/semantic-acceptance.sqlite3"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def write_once(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def protected_files():
    paths = sorted((ROOT / "backend").glob("*.py"))
    paths += sorted((ROOT / "data/curated").glob("*.json"))
    paths += sorted((ROOT / "data/operating").glob("*.json"))
    paths += [INPUT, Path(__file__), ROOT / "requirements.txt",
              DIRECTORY / "comparison-protocol.md"]
    return {path.relative_to(ROOT).as_posix(): digest(path) for path in paths if path.exists()}


def validate_inputs():
    from backend.schemas import RunInput

    declaration = json.loads((DIRECTORY / "input-freeze.json").read_text(encoding="utf-8"))
    if digest(INPUT) != declaration["input_sha256"]:
        raise RuntimeError("冻结输入已经变化，停止验收")
    document = json.loads(INPUT.read_text(encoding="utf-8"))
    counts = Counter(case["expected_outcome"] for case in document["cases"])
    if dict(counts) != document["outcome_counts"] or len(document["cases"]) != 24:
        raise RuntimeError("类别/总数与预声明不一致")
    identities = [case["id"] for case in document["cases"]]
    if len(set(identities)) != 24:
        raise RuntimeError("案例编号重复")
    for case in document["cases"]:
        RunInput.model_validate(case["input"])
    return document


def freeze_implementation():
    validate_inputs()
    write_once(FREEZE, {
        "schema_version": 1,
        "frozen_at": utc_now(),
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "input_sha256": digest(INPUT),
        "files": protected_files(),
        "model": "xiangyi-qwen3:14b-q4_k_m",
        "parameters": {"think": False, "temperature": 0, "num_ctx": 8192, "num_predict": 2300, "seed": 42},
        "policies": ["agent", "fixed"],
        "comparison_protocol": "docs/validation/semantic-cases/comparison-protocol.md",
        "order": "偶数索引agent→fixed，奇数索引fixed→agent；不对首次失败重试整条任务",
        "approval_note": "测试脚本显式调用负责人确认接口检验门禁；不声称真实经营人员已审核内容。",
        "evaluation_limit": "同团队编写、同模型教学扫描、小样本一次策略消融；不属于独立第三方或泛化评测。",
    })
    print("实现与输入已冻结；尚未调用模型。", flush=True)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fragments = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"style", "script"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.fragments.append(data)


def plain_text(html):
    parser = PlainText()
    parser.feed(html)
    return " ".join(parser.fragments)


def craft_minutes(plan, profile):
    if "craft_minutes" in plan:
        return plan["craft_minutes"]
    spec = profile.get("plans", {}).get(plan.get("id"), {})
    return spec.get("stages", [0, 0, 0])[1]


def evaluate(case, run, delivery):
    from backend.planner import solve_plans
    from backend.teaching import validate_teaching

    checks = []

    def check(name, passed, detail=None):
        row = {"check": name, "passed": bool(passed)}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)

    expected = case["expected"]
    outcome = case["expected_outcome"]
    intent = run.get("intent", {})
    effective = run.get("effective_requirements", run["requirements"])
    plan = run.get("plan") or {}
    planning = run.get("planning") or {}
    candidates = planning.get("candidates", [])
    claims = run.get("claims", [])
    for key, value in expected.get("intent", {}).items():
        if key.endswith("_contains"):
            actual = intent.get(key.removesuffix("_contains"), [])
            check("提取:" + key, set(value).issubset(actual), {"expected": value, "actual": actual})
        else:
            check("提取:" + key, intent.get(key) == value, {"expected": value, "actual": intent.get(key)})
    if expected.get("keep_form_numbers"):
        check("人数预算总时长保留明确输入", all(effective.get(k) == case["input"]["requirements"][k]
              for k in ("people", "budget_per_person", "available_minutes")))
    if expected.get("keep_resources"):
        check("接待资源未虚增", all(run["profile"].get(k) == v
              for k, v in case["input"]["operating_overrides"].items()))
    matched_ids = []
    for fragment in expected.get("fragments", []):
        matched = [c for c in claims if fragment["contains"] in c["text"]]
        check("陈述单独定位:" + fragment["contains"], len(matched) == 1)
        row = matched[0] if len(matched) == 1 else {}
        if row:
            matched_ids.append(row["id"])
        if "kind" in fragment:
            check("陈述类别:" + fragment["contains"], row.get("kind") == fragment["kind"], row.get("kind"))
        if "status" in fragment:
            check("核验状态:" + fragment["contains"], row.get("status") == fragment["status"], row.get("status"))
    if expected.get("fragments"):
        check("复合陈述保持不同编号", len(set(matched_ids)) == len(expected["fragments"]))
    if expected.get("corrections_reverified"):
        contradicted = [c for c in claims if c.get("status") == "contradicted"]
        check("修订文字再次核验通过", bool(contradicted) and all(c.get("corrected_status") == "supported" for c in contradicted))

    check("真实本地运行标识", run.get("mode") == "live")
    check("八次模型与两轮修订上限", run.get("model_calls", 0) <= 8 and run.get("revision_count", 0) <= 2)
    check("人工确认前双版禁止正式下载", all(delivery["before_export"].get(a) == 409 for a in ("visitor", "organizer")))
    check("运行初始快照无批准", run.get("approval") is None)
    if outcome == "deliver":
        check("完整交付样本不能以确认或拒绝代替成功", run["status"] == "awaiting_review", run["status"])
        check("程序方案可行", plan.get("feasible") is True and not plan.get("conflicts"))
        recomputed = solve_plans(effective, run["profile"])
        check("所选方案全字段复算一致", bool(plan) and any(row == plan for row in recomputed["candidates"]))
        check("程序验证通过", run.get("validation", {}).get("passed") is True)
        teaching_check = validate_teaching(run.get("teaching", {}), {**run, "requirements": effective})
        check("逐项教学扫描与内容绑定通过", teaching_check.get("passed") is True, teaching_check.get("issues"))
        check("双版草稿预览不偷偷确认", all(delivery["preview"].get(a) == 200 for a in ("visitor", "organizer"))
              and delivery.get("approval_after_preview") is None)
        check("显式确认接口成功", delivery.get("approval_status") == 200)
        check("确认后双版导出完整", all(delivery["exports"].get(a, {}).get("status") == 200 for a in ("visitor", "organizer")))
        approved = delivery.get("approved") or {}
        check("最终确认方案与已校验方案一致", bool(plan) and approved.get("plan") == plan and approved.get("status") == "confirmed")
        usable_cards = [c for c in run.get("cards", []) if c.get("usable")]
        source_map = {s["id"]: s for s in run.get("sources_snapshot", [])}
        check("可用讲解卡逐项有可定位来源", bool(usable_cards) and all(
            card.get("source_ids") and all(sid in source_map and all(source_map[sid].get(key) for key in
            ("url", "locator", "quote", "region", "project", "accessed_at", "use_note")) for sid in card["source_ids"])
            for card in usable_cards))
        claim_map = {c["id"]: c for c in claims}
        check("经营承诺与用户要求不作文化讲解", all(
            all(claim_map.get(cid, {}).get("kind") == "cultural_fact" for cid in card.get("claim_ids", [])) for card in usable_cards))
        for audience in ("visitor", "organizer"):
            content = delivery["exports"].get(audience, {}).get("plain_text", "")
            check(audience + "保留演示测算标识", "演示" in content)
            for unit in run.get("teaching", {}).get("short_script", []) + [run.get("teaching", {}).get("observation_task", {}), run.get("teaching", {}).get("interaction_question", {})]:
                check(audience + "同步同一教学:" + str(unit.get("id")), bool(unit.get("text")) and unit["text"] in content)
        for forbidden in expected.get("visitor_must_not_assert", []):
            check("游客版不携带未支持内容:" + forbidden, forbidden not in delivery["exports"].get("visitor", {}).get("plain_text", ""))
        for key, value in expected.get("selected", {}).items():
            if key in {"included_modules", "excluded_modules"}:
                actual = plan.get("module_ids", [])
                passed = set(value).issubset(actual) if key == "included_modules" else not set(value).intersection(actual)
            elif key in {"craft_minutes", "min_craft_minutes"}:
                actual = craft_minutes(plan, run["profile"])
                passed = actual == value if key == "craft_minutes" else actual >= value
            elif key in {"max_minutes", "max_total_cents"}:
                actual = plan.get("duration_minutes" if key == "max_minutes" else "total_cents")
                passed = actual is not None and actual <= value
            else:
                actual = plan.get(key)
                passed = actual == value
            check("方案预期:" + key, passed and bool(plan), {"expected": value, "actual": actual})
        if intent.get("maximize_craft"):
            feasible = [row for row in recomputed["candidates"] if row["feasible"]]
            best = max((craft_minutes(row, run["profile"]) for row in feasible), default=-1)
            check("明确手作偏好由程序排序", run.get("selection_method") == "deterministic_preference_ranking"
                  and bool(plan) and craft_minutes(plan, run["profile"]) == best)
    elif outcome == "confirm":
        check("必要确认状态", run["status"] == "needs_confirmation", run["status"])
        conflicts = {item["field"]: item for item in run.get("requirement_conflicts", [])}
        check("明确列出预期冲突字段", set(expected["conflict_fields"]).issubset(conflicts), sorted(conflicts))
        for field in expected["conflict_fields"]:
            row = conflicts.get(field, {})
            check("冲突字段保留两方值:" + field,
                  row.get("form_value") == case["input"]["requirements"][field]
                  and row.get("note_value") == expected["note_values"][field] and bool(row.get("reason")))
            check("等待确认时不覆盖表单:" + field,
                  run["requirements"][field] == case["input"]["requirements"][field]
                  and effective[field] == case["input"]["requirements"][field])
        check("冲突确认前不生成或批准执行方案", not plan and not run.get("approval"))
        check("确认前不能批准套餐绕过冲突", delivery.get("rejected_approval_status") == 409)
    else:
        check("正确拒绝状态", run["status"] == "needs_input", run["status"])
        check("求解明确无可行候选", bool(planning) and not planning.get("feasible_ids") and bool(candidates))
        conflicts = run.get("blocking_conflicts", []) + [conflict for candidate in candidates for conflict in candidate.get("conflicts", [])]
        codes = {row["code"] for row in conflicts}
        check("具体冲突代码覆盖", set(expected["conflict_codes"]).issubset(codes), sorted(codes))
        check("具体冲突有可读说明", all(any(row["code"] == code and row.get("message") for row in conflicts)
                                               for code in expected["conflict_codes"]))
        explanation = "；".join(row["message"] for row in conflicts)
        for number in expected.get("conflict_message_numbers", []):
            check("资源冲突显示数量:" + number, number in explanation)
        check("无解不生成或批准方案", not plan and not run.get("approval"))
        check("不可批准不可行套餐", delivery.get("rejected_approval_status") == 409)
    return checks


class PolicyExecutor:
    def __init__(self, policy):
        self.policy = policy

    def submit(self, function, *args):
        from backend.workflow import execute

        future = Future()
        result = execute(*args, policy=self.policy)
        future.set_result(result)
        return future


def exercise_delivery(client, run, case_id, policy, expected_outcome):
    from backend import store

    prefix = f"{case_id.lower()}-{policy}"
    endpoint = f"/api/runs/{run['id']}"
    delivery = {"before_export": {}, "preview": {}, "exports": {}}
    for audience in ("visitor", "organizer"):
        delivery["before_export"][audience] = client.get(endpoint + "/export", params={"audience": audience}).status_code
    if expected_outcome == "deliver" and run["status"] == "awaiting_review" and run.get("plan"):
        for audience in ("visitor", "organizer"):
            delivery["preview"][audience] = client.get(endpoint + "/export", params={"audience": audience, "preview": True}).status_code
        delivery["approval_after_preview"] = store.get_run(run["id"]).get("approval")
        response = client.post(endpoint + "/approve", json={"confirmed": True, "plan_id": run["plan"]["id"]})
        delivery["approval_status"] = response.status_code
        delivery["approved"] = store.get_run(run["id"])
        write_once(OUTPUT / (prefix + "-confirmed.json"), delivery["approved"])
        for audience in ("visitor", "organizer"):
            response = client.get(endpoint + "/export", params={"audience": audience})
            record = {"status": response.status_code}
            if response.status_code == 200:
                destination = PACKS / (prefix + "-" + audience + ".html")
                with destination.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(response.text)
                record.update(path=destination.relative_to(ROOT).as_posix(), sha256=digest(destination), plain_text=plain_text(response.text))
            delivery["exports"][audience] = record
    else:
        response = client.post(endpoint + "/approve", json={"confirmed": True, "plan_id": "light"})
        delivery["rejected_approval_status"] = response.status_code
    return delivery


def summarize(entries):
    result = {"type": "small_internal_acceptance_not_independent", "case_count": 24,
              "input_sha256": digest(INPUT), "first_run_started_at": None, "policies": {}, "paired": []}
    for policy in ("agent", "fixed"):
        selected = [entry for entry in entries if entry["policy"] == policy]
        by_category = {}
        for category in ("deliver", "confirm", "refuse"):
            rows = [entry for entry in selected if entry["expected_outcome"] == category]
            by_category[category] = {"count": len(rows), "passed": sum(row["passed"] for row in rows),
                                     "outcome_reached": sum(row["outcome_reached"] for row in rows),
                                     "failed": [row["case_id"] for row in rows if not row["passed"]],
                                     "statuses": dict(Counter(row["status"] for row in rows))}
        result["policies"][policy] = {
            "categories": by_category, "total_calls": sum(row["model_calls"] for row in selected),
            "elapsed_seconds_total": round(sum(row["elapsed_seconds"] for row in selected), 3),
            "elapsed_seconds_median": statistics.median([row["elapsed_seconds"] for row in selected]) if selected else None,
            "over_confirmation_on_deliver": sum(row["status"] == "needs_confirmation" for row in selected if row["expected_outcome"] == "deliver"),
            "over_refusal_on_deliver": sum(row["status"] == "needs_input" for row in selected if row["expected_outcome"] == "deliver"),
            "model_or_execution_failures": sum(row["status"] in {"model_error", "failed"} for row in selected),
            "unexpected_ready_on_confirm_or_refuse": sum(row["status"] in {"awaiting_review", "confirmed"}
                for row in selected if row["expected_outcome"] != "deliver"),
            "outcome_reached_but_full_checks_failed": [row["case_id"] for row in selected if row["outcome_reached"] and not row["passed"]],
        }
    for identity in sorted({row["case_id"] for row in entries}):
        pair = {row["policy"]: row for row in entries if row["case_id"] == identity}
        if set(pair) == {"agent", "fixed"}:
            result["paired"].append({"case_id": identity, "expected_outcome": pair["agent"]["expected_outcome"],
                                     "agent_passed": pair["agent"]["passed"], "fixed_passed": pair["fixed"]["passed"],
                                     "same_input_snapshot": pair["agent"]["snapshot_sha256"] == pair["fixed"]["snapshot_sha256"],
                                     "call_difference": pair["agent"]["model_calls"] - pair["fixed"]["model_calls"],
                                     "elapsed_difference_seconds": round(pair["agent"]["elapsed_seconds"] - pair["fixed"]["elapsed_seconds"], 3)})
    return result


def run_acceptance():
    import httpx
    from fastapi.testclient import TestClient
    from backend import app as api, store
    from backend.config import MODEL, OLLAMA_URL
    from backend.model import readiness

    document = validate_inputs()
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    if protected_files() != frozen["files"]:
        raise RuntimeError("实现冻结后受保护文件已变化，不允许以此运行首轮验收")
    if OUTPUT.exists() or PACKS.exists() or DATABASE.exists():
        raise FileExistsError("首次结果、体验包或隔离数据库已存在；禁止覆盖或重跑")
    if not readiness():
        raise RuntimeError("本地模型未就绪，尚未开始验收，不以预设代替")
    with httpx.Client(timeout=10, trust_env=False) as client:
        tags = client.get(OLLAMA_URL + "/api/tags").json()
        version = client.get(OLLAMA_URL + "/api/version").json()
    matching = [item for item in tags.get("models", []) if item.get("name") == MODEL]
    OUTPUT.mkdir(parents=True)
    PACKS.mkdir(parents=True)
    started = utc_now()
    write_once(OUTPUT / "started.json", {"started_at": started, "implementation_freeze_sha256": digest(FREEZE),
               "model": matching, "ollama": version, "database": DATABASE.relative_to(ROOT).as_posix(),
               "policy_order": "AB/BA交错", "mode": "live"})
    store.DB_PATH = DATABASE
    entries = []
    with TestClient(api.app) as client:
        for index, case in enumerate(document["cases"]):
            order = ("agent", "fixed") if index % 2 == 0 else ("fixed", "agent")
            pair_snapshot = None
            for policy in order:
                if protected_files() != frozen["files"]:
                    raise RuntimeError("运行期间受保护文件变化；已完成记录保留，立即停止")
                api.EXECUTOR = PolicyExecutor(policy)
                started_case = time.perf_counter()
                response = client.post("/api/runs", json=case["input"])
                response.raise_for_status()
                run = store.get_run(response.json()["id"])
                if not run.get("execution_finished"):
                    raise RuntimeError("同步真实任务未完成，不重试整条输入")
                prefix = f"{case['id'].lower()}-{policy}"
                write_once(OUTPUT / (prefix + "-run.json"), run)
                snapshot = {key: run[key] for key in ("text", "requirements", "operating_overrides", "profile", "sources_snapshot", "materials_snapshot")}
                snapshot_sha = stable_digest(snapshot)
                if pair_snapshot is not None and snapshot_sha != pair_snapshot:
                    raise RuntimeError("同一对输入或资料资源快照变化，停止配对比较")
                pair_snapshot = snapshot_sha
                delivery = exercise_delivery(client, run, case["id"], policy, case["expected_outcome"])
                checks = evaluate(case, run, delivery)
                if case["expected_outcome"] == "deliver":
                    outcome_reached = run["status"] == "awaiting_review" and delivery.get("approval_status") == 200 and all(
                        delivery["exports"].get(audience, {}).get("status") == 200 for audience in ("visitor", "organizer"))
                elif case["expected_outcome"] == "confirm":
                    outcome_reached = run["status"] == "needs_confirmation"
                else:
                    outcome_reached = run["status"] == "needs_input" and bool(run.get("planning")) and not run["planning"].get("feasible_ids")
                entry = {"case_id": case["id"], "policy": policy, "expected_outcome": case["expected_outcome"],
                         "run_id": run["id"], "status": run["status"], "model_calls": run["model_calls"],
                         "elapsed_seconds": run["elapsed_seconds"], "wall_seconds": round(time.perf_counter() - started_case, 3),
                         "snapshot_sha256": snapshot_sha, "passed": all(row["passed"] for row in checks), "outcome_reached": outcome_reached,
                         "failed_checks": [row["check"] for row in checks if not row["passed"]], "checks": checks,
                         "delivery": {key: value for key, value in delivery.items() if key != "approved"}}
                write_once(OUTPUT / (prefix + "-checks.json"), entry)
                entries.append(entry)
                with (OUTPUT / "progress.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({key: value for key, value in entry.items() if key not in {"checks", "delivery"}}, ensure_ascii=False) + "\n")
                print(json.dumps({key: value for key, value in entry.items() if key not in {"checks", "delivery", "snapshot_sha256"}}, ensure_ascii=False), flush=True)
    summary = summarize(entries)
    summary.update(first_run_started_at=started, completed_at=utc_now(), complete=True,
                   interpretation="三类分别计分；48次真实首跑中的模型扫描不是独立人工复核，时延受本机缓存/负载影响；相同通过结果不构成Agent更强证据。")
    write_once(OUTPUT / "summary.json", summary)
    write_once(OUTPUT / "artifact-manifest.json", {"created_at": utc_now(), "files": {
        path.relative_to(ROOT).as_posix(): digest(path) for path in sorted(OUTPUT.glob("*")) + sorted(PACKS.glob("*.html")) if path.is_file()
    }})
    print(json.dumps(summary["policies"], ensure_ascii=False, indent=2), flush=True)
    return 0 if all(row["passed"] for row in entries) else 1


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate-inputs", action="store_true")
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--run", action="store_true")
    arguments = parser.parse_args()
    if arguments.validate_inputs:
        document = validate_inputs()
        print(json.dumps({"counts": document["outcome_counts"], "input_sha256": digest(INPUT)}, ensure_ascii=False))
        return 0
    if arguments.freeze:
        freeze_implementation()
        return 0
    return run_acceptance()


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
