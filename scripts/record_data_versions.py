"""Record or check data versions for two-machine handoff results.

Hashes are taken from the Git object of the tested commit, so Windows CRLF
checkouts and Linux LF checkouts produce the same value. The working tree is
reported separately and never replaces the Git hash.

Examples:
    python scripts/record_data_versions.py --sha <完整SHA>
    python scripts/record_data_versions.py --sha <完整SHA> --worktree
    python scripts/record_data_versions.py --check docs/validation/two-machine/<记录>.json
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TRACKED = (
    "data/curated/sources.json",
    "data/curated/materials.json",
    "data/curated/public-case-sources.json",
    "data/operating/demo-profile.json",
    "data/operating/jinshan-reconstruction.json",
    "requirements-lock.txt",
    "package-lock.json",
)
HASH_BASIS = "sha256 of git show <tested_code_sha>:<path>"


def git(*arguments: str) -> bytes:
    return subprocess.run(["git", *arguments], cwd=ROOT, check=True, capture_output=True).stdout


def full_sha(revision: str) -> str:
    return git("rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()


def blob_bytes(sha: str, path: str) -> bytes:
    return git("show", f"{sha}:{path}")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record(sha: str, include_worktree: bool) -> dict:
    sha = full_sha(sha)
    versions, worktree = {}, {}
    for path in TRACKED:
        stored = blob_bytes(sha, path)
        versions[path] = digest(stored)
        if include_worktree:
            file = ROOT / path
            raw = file.read_bytes() if file.exists() else None
            entry = {"exists": raw is not None}
            if raw is not None:
                entry["sha256"] = digest(raw)
                entry["same_bytes_as_git"] = raw == stored
                entry["same_after_crlf_to_lf"] = raw.replace(b"\r\n", b"\n") == stored
            worktree[path] = entry
    result = {"tested_code_sha": sha, "hash_basis": HASH_BASIS, "data_versions": versions}
    if include_worktree:
        head = git("rev-parse", "HEAD").decode().strip()
        dirty = git("status", "--porcelain", "--", *TRACKED).decode().splitlines()
        result["worktree"] = {
            "head": head,
            "head_is_tested_code": head == sha,
            "dirty_tracked_files": dirty,
            "files": worktree,
            "note": "工作区字节仅用于排查换行或本地修改；正式 data_versions 以 Git 对象为准。",
        }
    return result


def classify(expected: str, stored: bytes) -> str:
    if expected == digest(stored):
        return "match_git_blob"
    if expected == digest(stored.replace(b"\n", b"\r\n")):
        return "match_after_lf_to_crlf"
    return "no_match"


def check(record_path: Path) -> int:
    data = json.loads(record_path.read_text(encoding="utf-8"))
    sha = full_sha(data["tested_code_sha"])
    rows = []
    for path, expected in sorted(data.get("data_versions", {}).items()):
        try:
            stored = blob_bytes(sha, path)
        except subprocess.CalledProcessError:
            rows.append({"path": path, "status": "missing_in_commit"})
            continue
        rows.append({"path": path, "status": classify(expected, stored),
                     "recorded": expected, "git_blob": digest(stored)})
    summary = {
        "record": record_path.as_posix(),
        "tested_code_sha": sha,
        "hash_basis": HASH_BASIS,
        "files": rows,
        "all_match_git_blob": all(row["status"] == "match_git_blob" for row in rows),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["all_match_git_blob"] else 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sha", help="被测代码的完整或可解析的提交号")
    group.add_argument("--check", type=Path, help="检查已有双机记录中的 data_versions")
    parser.add_argument("--worktree", action="store_true", help="同时报告当前工作区字节，用于排查")
    arguments = parser.parse_args()
    if arguments.check:
        return check(arguments.check)
    print(json.dumps(record(arguments.sha, arguments.worktree), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
