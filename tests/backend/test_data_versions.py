"""双机记录的数据版本按 Git 对象计算，换行转换不能伪装成另一份资料。"""

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("record_data_versions", ROOT / "scripts/record_data_versions.py")
versions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(versions)


def test_classify_separates_git_blob_crlf_and_unknown_bytes():
    stored = b'{\n  "a": 1\n}\n'
    assert versions.classify(hashlib.sha256(stored).hexdigest(), stored) == "match_git_blob"
    crlf = hashlib.sha256(stored.replace(b"\n", b"\r\n")).hexdigest()
    assert versions.classify(crlf, stored) == "match_after_lf_to_crlf"
    assert versions.classify("0" * 64, stored) == "no_match"


def test_record_uses_tested_commit_objects_for_every_tracked_file():
    head = versions.full_sha("HEAD")
    result = versions.record(head, include_worktree=True)
    assert result["tested_code_sha"] == head and len(head) == 40
    assert set(result["data_versions"]) == set(versions.TRACKED)
    for path, value in result["data_versions"].items():
        assert value == hashlib.sha256(versions.blob_bytes(head, path)).hexdigest()
        entry = result["worktree"]["files"][path]
        if entry["exists"] and not result["worktree"]["dirty_tracked_files"]:
            assert entry["same_after_crlf_to_lf"]


def test_check_reports_mismatch_without_rewriting_record(tmp_path, capsys):
    head = versions.full_sha("HEAD")
    good = versions.record(head, include_worktree=False)
    record = {"tested_code_sha": head, "data_versions": dict(good["data_versions"])}
    record["data_versions"]["data/curated/sources.json"] = "f" * 64
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    assert versions.check(path) == 1
    report = json.loads(capsys.readouterr().out)
    statuses = {row["path"]: row["status"] for row in report["files"]}
    assert statuses["data/curated/sources.json"] == "no_match"
    assert statuses["data/curated/materials.json"] == "match_git_blob"
    assert path.read_bytes() == before
