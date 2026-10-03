"""Rerun the original six as development regression; never overwrite first failures."""
import argparse
from concurrent.futures import Future
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="New unique lowercase regression label")
    args = parser.parse_args()
    import re
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.name):
        parser.error("name must be lowercase kebab-case")
    output = ROOT / "docs/validation/semantic-regression" / args.name
    output.mkdir(parents=True, exist_ok=False)
    os.environ["XY_DATABASE_PATH"] = str(ROOT / "artifacts/runtime" / ("regression-" + args.name + ".sqlite3"))
    from fastapi.testclient import TestClient
    from backend import app as api, store
    from backend.model import readiness
    from run_upgrade import evaluate

    class ImmediateExecutor:
        def submit(self, function, *values):
            result = Future()
            result.set_result(function(*values))
            return result

    def write(name, value):
        with (output / name).open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    api.EXECUTOR = ImmediateExecutor()
    assert readiness(), "本地模型未就绪，不能用假结果替代"
    old = ROOT / "tests/acceptance/upgrade-holdout.json"
    first = ROOT / "docs/validation/upgrade-cases"
    historical_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [old, *first.glob("*.json")]}
    normalized_hashes = {path.replace("\\", "/"): hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                         for path in historical_hashes}
    write("manifest.json", {"purpose": "old_six_development_regression_not_fresh_evaluation", "first_records_sha256": historical_hashes,
                            "first_records_lf_sha256": normalized_hashes,
                            "hash_note": "原始SHA保留本机字节；LF版仅统一CRLF行尾，便于跨平台核对已存在的Git历史记录，不改原记录。"})
    rows = []
    with TestClient(api.app) as client:
        for case in json.loads(old.read_text(encoding="utf-8"))["cases"]:
            created = client.post("/api/runs", json=case["input"])
            created.raise_for_status()
            identity = created.json()["id"]
            run = store.get_run(identity)
            assert run["execution_finished"]
            blocked = client.get(f"/api/runs/{identity}/export").status_code
            checks = evaluate(case, run, blocked)
            if case["id"] in {"UH-01", "UH-02", "UH-05"}:
                checks.append({"check": "完整交付就绪", "passed": run["status"] == "awaiting_review"})
                if run["status"] == "awaiting_review":
                    response = client.post(f"/api/runs/{identity}/approve", json={"confirmed": True, "plan_id": run["plan"]["id"]})
                    checks.append({"check": "验收脚本确认接口", "passed": response.status_code == 200})
                    for audience in ("visitor", "organizer"):
                        bundle = client.get(f"/api/runs/{identity}/export", params={"audience": audience})
                        checks.append({"check": audience + "完整导出", "passed": bundle.status_code == 200})
                        if bundle.status_code == 200:
                            (output / (case["id"].lower() + "-" + audience + ".html")).write_text(bundle.text, encoding="utf-8")
                    write(case["id"].lower() + "-confirmed.json", store.get_run(identity))
            write(case["id"].lower() + ".json", run)
            row = {"case_id": case["id"], "status": run["status"], "passed": all(c["passed"] for c in checks),
                   "model_calls": run["model_calls"], "elapsed_seconds": run["elapsed_seconds"], "checks": checks, "error": run.get("error")}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    assert all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest for path, digest in historical_hashes.items())
    write("summary.json", {"cases": rows, "passed": sum(row["passed"] for row in rows), "total": len(rows), "historical_records_unchanged": True})
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
