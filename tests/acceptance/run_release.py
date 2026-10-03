"""Reuse the original 24 inputs/checks exactly once as known-input version regression."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import run_semantic as baseline

DIRECTORY = ROOT / "docs/validation/release-candidate"
baseline.FREEZE = DIRECTORY / "implementation-freeze.json"
baseline.OUTPUT = DIRECTORY / "version-regression"
baseline.PACKS = ROOT / "artifacts/release-candidate/regression-packs"
baseline.DATABASE = ROOT / "artifacts/runtime/release-regression.sqlite3"

original_protected = baseline.protected_files
def protected_files():
    files = original_protected()
    for path in [Path(__file__), *sorted((ROOT / "frontend/prototype").glob("*.js")),
                 *sorted((ROOT / "frontend/prototype").glob("*.css")), ROOT / "frontend/prototype/index.html"]:
        files[path.relative_to(ROOT).as_posix()] = baseline.digest(path)
    return files
baseline.protected_files = protected_files

original_write = baseline.write_once
def write_once(path, value):
    if path == baseline.FREEZE:
        value.update(evaluation_type="known_input_version_regression",
                     historical_release="3833ce1", historical_results="docs/validation/semantic-cases/first-run",
                     evaluation_limit="原24条已见输入的版本回归，两流程各一次；不是新未见测试或第三方评测。")
    if path.name == "summary.json":
        value.update(type="known_input_version_regression_not_fresh_evaluation",
                     evaluated_commit=json.loads(baseline.FREEZE.read_text(encoding="utf-8"))["base_commit"],
                     interpretation="原24例已知输入，两流程各复跑一次，原始首跑不覆盖；不挑最佳结果，不宣称未见泛化或第三方评测。")
    return original_write(path, value)
baseline.write_once = write_once

if __name__ == "__main__":
    raise SystemExit(baseline.main())
