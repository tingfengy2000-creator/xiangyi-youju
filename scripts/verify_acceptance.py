"""只读复核新验收输入、冻结实现与首跑工件；不连接模型、不改数据库。

默认核对包括本机完整HTML的全套文件；新克隆没有artifacts时可显式使用
--repo-only，仅检查已版本化材料，并明确报告跳过的本机体验包数量。
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/validation/semantic-cases"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-only", action="store_true", help="明确跳过被git忽略的本机完整HTML")
    args = parser.parse_args()
    errors, checked, skipped = [], [], []
    current_differs, patch_path = False, None

    def read(relative):
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("清单路径越出仓库：" + relative)
        return json.loads(path.read_text(encoding="utf-8"))

    def verify(relative, expected):
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT):
            errors.append("清单路径越出仓库：" + relative)
        elif args.repo_only and path.is_relative_to(ROOT / "artifacts"):
            skipped.append(relative)
        elif not path.is_file():
            errors.append("缺少文件：" + relative)
        elif digest(path) != expected:
            errors.append("SHA256不匹配：" + relative)
        else:
            checked.append(relative)

    try:
        input_freeze = read("docs/validation/semantic-cases/input-freeze.json")
        implementation = read("docs/validation/semantic-cases/implementation-freeze.json")
        started = read("docs/validation/semantic-cases/first-run/started.json")
        manifest = read("docs/validation/semantic-cases/first-run/artifact-manifest.json")
        summary = read("docs/validation/semantic-cases/first-run/summary.json")
        inputs = read(input_freeze["input_path"])
        verify(input_freeze["input_path"], input_freeze["input_sha256"])
        verify("docs/validation/semantic-cases/implementation-freeze.json", started["implementation_freeze_sha256"])
        patch_relative = "docs/validation/post-freeze-guard/patch-manifest.json"
        patches = {}
        if (ROOT / patch_relative).is_file():
            patch = read(patch_relative)
            rows = patch["implementation_changes"]
            if patch.get("kind") != "post_freeze_rejected_content_guard" or len(rows) != 1 or rows[0].get("path") != "backend/teaching.py":
                raise ValueError("冻结后补丁清单仅允许已声明的teaching拒绝原句保护")
            row = rows[0]
            if row.get("evaluated_snapshot") != "docs/validation/post-freeze-guard/frozen_teaching.py":
                raise ValueError("原评测教学模块快照路径不符")
            if row.get("before_sha256") != implementation["files"][row["path"]]:
                raise ValueError("补丁原文件哈希与评测冻结不符")
            if patch.get("evaluated_implementation_freeze_sha256") != started["implementation_freeze_sha256"]:
                raise ValueError("补丁未绑定当前首跑冻结")
            if patch.get("input_sha256") != input_freeze["input_sha256"] or patch.get("first_run_summary_sha256") != digest(DIRECTORY / "first-run/summary.json"):
                raise ValueError("补丁声明的输入或首跑摘要哈希不符")
            patches[row["path"]] = row
            patch_path = patch_relative
            for relative, expected in patch.get("additional_files", {}).items():
                verify(relative, expected)
        for relative, expected in implementation["files"].items():
            if relative in patches:
                row = patches[relative]
                verify(row["evaluated_snapshot"], expected)
                verify(relative, row["after_sha256"])
                current_differs = digest(ROOT / relative) != expected
                if not current_differs:
                    errors.append("清单声明冻结后补丁，但当前教学源码仍为原评测版")
            else:
                verify(relative, expected)
        for relative, expected in manifest["files"].items():
            verify(relative, expected)
        for relative, expected in input_freeze["data_sha256"].items():
            verify(relative, expected)
        counts = dict(Counter(row["expected_outcome"] for row in inputs["cases"]))
        if counts != {"deliver": 12, "confirm": 6, "refuse": 6}:
            errors.append("输入类别分母发生变化")
        if not summary.get("complete") or len(summary.get("paired", [])) != 24:
            errors.append("首跑摘要未包含全部24对")
        if not all(pair.get("same_input_snapshot") for pair in summary.get("paired", [])):
            errors.append("配对输入/资料/经营快照不一致")
        for policy in ("agent", "fixed"):
            checks = [read(f"docs/validation/semantic-cases/first-run/{case['id'].lower()}-{policy}-checks.json")
                      for case in inputs["cases"]]
            for category, count in counts.items():
                rows = [row for row in checks if row["expected_outcome"] == category]
                recorded = summary["policies"][policy]["categories"][category]
                if len(rows) != count or recorded["count"] != count or recorded["passed"] != sum(row["passed"] for row in rows):
                    errors.append(f"{policy}/{category}摘要计数与逐例记录不一致")
                if any(row["passed"] != all(item["passed"] for item in row["checks"]) for row in rows):
                    errors.append(f"{policy}/{category}逐例通过值与检查明细不一致")
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(type(error).__name__ + ": " + str(error))
    result = {"mode": "repository_only" if args.repo_only else "full_local_artifacts",
              "read_only": True, "model_calls": 0, "passed": not errors,
              "unique_files_verified": len(set(checked)), "local_html_skipped": len(set(skipped)),
              "current_differs_from_evaluated": current_differs,
              "post_freeze_patch": patch_path,
              "errors": errors,
              "boundary": "哈希和统计一致性复核不重新判定文化事实，不属于独立评测。"}
    if current_differs:
        result["evaluation_version_note"] = "24条首跑对应原评测版；原teaching字节另存快照。当前仅应用清单列出的事后审计保护补丁，不能把首跑成绩冒称补丁版实测。"
    if skipped:
        result["note"] = "本模式未核验本机HTML；完整包路径及哈希见首跑工件清单。"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
