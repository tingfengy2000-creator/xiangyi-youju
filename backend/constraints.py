"""Turn extracted preferences into bounded program constraints; never silently replace forms."""

from copy import deepcopy
import re

LABELS = {"people": "参与人数", "budget_per_person": "人均预算", "available_minutes": "可用时长",
          "audience": "客群", "tea_preference": "茶歇偏好", "min_craft_minutes": "手作最低时长"}


def resolve_intent(requirements, intent, resolution="ask"):
    effective = deepcopy(requirements)
    proposed = {key: intent.get(key) for key in ("people", "budget_per_person", "available_minutes", "audience")}
    excluded, required = set(intent["exclude_tags"]), set(intent["require_tags"])
    if excluded.intersection(required) or intent.get("ambiguities"):
        return effective, [], "文字需求存在矛盾或超出当前模块能力，请先澄清：" + "；".join(intent.get("ambiguities", []) or sorted(excluded & required))
    proposed["tea_preference"] = "exclude" if "tea" in excluded else "include" if "tea" in required else None
    proposed["min_craft_minutes"] = intent.get("min_craft_minutes")
    conflicts = []
    for field, mentioned in proposed.items():
        if mentioned is None:
            continue
        original = effective.get(field, {"audience": "general", "tea_preference": "any", "min_craft_minutes": 0}.get(field))
        neutral = (field == "tea_preference" and original == "any") or (field == "min_craft_minutes" and original == 0)
        if not neutral and original != mentioned:
            conflicts.append({"field": field, "label": LABELS[field], "form_value": original, "note_value": mentioned,
                              "reason": "文字需求与表单不同；不会由模型自动覆盖。"})
        elif neutral:
            effective[field] = mentioned
    if conflicts and resolution != "form":
        return effective, conflicts, None
    # A human choosing the form only overrides conflicting fields, not the whole free-text request.
    tea = effective.get("tea_preference", "any")
    if any(c["field"] == "tea_preference" for c in conflicts):
        excluded.discard("tea")
        required.discard("tea")
    if tea == "exclude":
        excluded.add("tea")
        required.discard("tea")
    elif tea == "include":
        required.add("tea")
        excluded.discard("tea")
    effective["constraints"] = {"exclude_tags": sorted(excluded), "require_tags": sorted(required),
                                "min_craft_minutes": effective.get("min_craft_minutes", 0),
                                "audience": effective.get("audience", "general"),
                                "maximize_craft": intent["maximize_craft"]}
    return effective, conflicts, None


def split_input(text, compound=False):
    """Lossless deterministic boundaries; do not ask the model to rewrite claims before auditing."""
    sentences = [s.strip() for s in re.findall(r"[^。！？!?\n]+[。！？!?]?", text) if s.strip()]
    rows = []
    for number, sentence in enumerate(sentences, 1):
        parts = re.split(r"(?<=[；;])|(?<=[，,])(?=且|而且|并且|同时|另外|此外)", sentence) if compound else [sentence]
        for part in parts:
            if part.strip():
                rows.append({"id": f"s{len(rows)+1}", "text": part.strip(), "original_sentence": sentence,
                             "original_sentence_id": f"sentence-{number}"})
    return rows


def compare_plans(before, after):
    def snapshot(plan):
        return {**{k: plan.get(k) for k in ("id", "title", "total_cents", "duration_minutes", "craft_minutes", "module_ids")},
                "start_time": plan["schedule"][0].get("start") if plan.get("schedule") else None}
    if not before or not after:
        return None
    changes = []
    for key, label, divisor, suffix in [("total_cents", "总预算", 100, "元"), ("duration_minutes", "活动时长", 1, "分钟"),
                                        ("craft_minutes", "手作时长", 1, "分钟")]:
        if before.get(key) is not None and after.get(key) is not None and before[key] != after[key]:
            changes.append(f"{label}：{before[key] / divisor:g} → {after[key] / divisor:g}{suffix}")
    old = {s.get("module_id", s["title"]): s["title"] for s in before["schedule"]}
    new = {s.get("module_id", s["title"]): s["title"] for s in after["schedule"]}
    if removed := [name for key, name in old.items() if key not in new]:
        changes.append("移除：" + "、".join(removed))
    if added := [name for key, name in new.items() if key not in old]:
        changes.append("增加：" + "、".join(added))
    if before.get("schedule") and after.get("schedule"):
        old_start, new_start = before["schedule"][0].get("start"), after["schedule"][0].get("start")
        if old_start != new_start:
            changes.append(f"开始时间：{old_start} → {new_start}；日程已重新排定。")
    return {"before": snapshot(before), "after": snapshot(after), "changes": changes or ["本次条件变化未改变所选日程与费用。"]}
