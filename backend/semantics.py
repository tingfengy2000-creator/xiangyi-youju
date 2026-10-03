"""Ground quantified durations in source text; no model authority over business data."""

from copy import deepcopy
import re

_NUMBER = r"[零〇一二两三四五六七八九十百\d]+(?:\.\d+)?"
_DURATION = re.compile(rf"(?P<number>{_NUMBER}|半)\s*(?P<before_half>个?半)?(?P<unit>个?小时|分钟)(?P<half>半)?")
_CRAFT = re.compile(r"手作|动手|制作|实操|剪刻|做作品")
_TOTAL = re.compile(r"总时长|全程|总共|一共|整个活动|整场|总计|活动时间|活动时长|行程|只能待|只留|停留|只有|仅有")


def chinese_number(value):
    if value == "半":
        return 0.5
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return float(value)
    digits = {c: n for n, chars in enumerate(("零〇", "一", "二两", "三", "四", "五", "六", "七", "八", "九")) for c in chars}
    total = current = 0
    for c in value:
        if c in digits:
            current = digits[c]
        elif c in "十百":
            total += (current or 1) * (10 if c == "十" else 100)
            current = 0
        else:
            raise ValueError("未识别的数字")
    return total + current


def ground_durations(note, preferences):
    """Only explicit source quantities may populate the two distinct duration fields.

    A narrow deterministic check corrects a common semantic scope error. Other
    preferences remain model extracted. Unsupported duration bounds ask a specific
    question instead of silently imposing a different constraint.
    """
    value = deepcopy(preferences)
    mentions, issues = [], []
    previous_end = 0
    for match in _DURATION.finditer(note):
        # The nearest explicit scope within this clause wins; never let a prior
        # craft mention contaminate a subsequent total-duration clause.
        clause_start = max(note.rfind(p, previous_end, match.start()) for p in "，,；;。！？!\n") + 1
        prefix = note[max(previous_end, clause_start):match.start()]
        suffix = note[match.end():re.search(r"[，,；;。！？!\n]", note[match.end():]).start() + match.end()] if re.search(r"[，,；;。！？!\n]", note[match.end():]) else note[match.end():]
        scopes = [(m.start(), "craft") for m in _CRAFT.finditer(prefix)] + [(m.start(), "total") for m in _TOTAL.finditer(prefix)]
        if not scopes:
            scopes = [(-m.start(), "craft") for m in _CRAFT.finditer(suffix)] + [(-m.start(), "total") for m in _TOTAL.finditer(suffix)]
        scope = max(scopes)[1] if scopes else "unclear"
        quantity = chinese_number(match["number"])
        unit = 60 if "小时" in match["unit"] else 1
        minutes = (quantity + (0.5 if match["before_half"] else 0)) * unit + (unit / 2 if match["half"] else 0)
        mentions.append({"text": note[max(previous_end, clause_start):match.end()], "start": match.start(), "end": match.end(), "minutes": minutes, "scope": scope})
        if scope == "unclear":
            issues.append(f"“{match[0]}”未明确指手作时长还是活动总时长，请说明。")
        elif minutes != int(minutes):
            issues.append(f"“{match[0]}”不是整分钟，当前模块按整分钟计算，请明确。")
        elif scope == "craft" and re.search(r"最多|至多|不超过|不多于|不超|仅限", prefix):
            issues.append(f"手作上限“{match[0]}”尚无对应约束项，请确认是否改用手作最低时长或调整模块。")
        elif scope == "total" and re.search(r"至少|不低于|不少于", prefix):
            issues.append(f"总时长下限“{match[0]}”不同于表单可用时长上限，请确认可用总时长。")
        previous_end = match.end()
    checks = []
    for field, scope, maximum in (("min_craft_minutes", "craft", 180), ("available_minutes", "total", 720)):
        candidates = {int(m["minutes"]) for m in mentions if m["scope"] == scope and m["minutes"] == int(m["minutes"])}
        if len(candidates) > 1:
            issues.append(f"{'手作' if scope == 'craft' else '总'}时长出现多个数值{sorted(candidates)}，请明确约束。")
        grounded = next(iter(candidates)) if len(candidates) == 1 else None
        if grounded is not None and not 1 <= grounded <= maximum:
            issues.append(f"{grounded}分钟超出当前{'手作' if scope == 'craft' else '总时长'}支持范围。")
            grounded = None
        # Absence of an explicit duration is not permission to invent one. If the
        # model infers an unsupported number, retain a source-grounding audit note.
        if value.get(field) != grounded:
            checks.append({"field": field, "model_value": value.get(field), "grounded_value": grounded,
                           "reason": "按原文数值与时长作用范围核对；未写总时长不从手作时长推断。"})
        value[field] = grounded
    value["ambiguities"] = list(dict.fromkeys(value.get("ambiguities", []) + issues))
    return value, {"duration_mentions": mentions, "corrections": checks}
