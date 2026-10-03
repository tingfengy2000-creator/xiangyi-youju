"""单场地、单组体验求解。模型不能修改本模块读取的经营报价。"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import combinations
import re


# 向后兼容演示默认值；正式调用读取独立经营资料 profile.plans。
DEFAULT_PLANS = {
    "light": {
        "title": "轻体验", "stages": [20, 50, 20], "lecture_cents": 20000,
        "craft_per_person_cents": 2500, "tea_per_person_cents": 1500,
        "tool_cents": 8000, "reusable_per_person_cents": 800,
        "disposable_per_person_cents": 1400, "operations_cents": 12000,
        "paper_per_person": 1,
    },
    "deep": {
        "title": "深体验", "stages": [30, 60, 30], "lecture_cents": 30000,
        "craft_per_person_cents": 3500, "tea_per_person_cents": 2000,
        "tool_cents": 10000, "reusable_per_person_cents": 1000,
        "disposable_per_person_cents": 1600, "operations_cents": 16000,
        "paper_per_person": 2,
    },
}


def plan_craft_minutes(plan: dict, planning: dict | None = None) -> int:
    """读取已求解手作分钟，兼容旧套餐快照；不增加或修改任何环节。"""
    if "craft_minutes" in plan:
        return plan["craft_minutes"]
    specification = (planning or {}).get("profile_snapshot", {}).get("plans", {}).get(plan["id"])
    if specification:
        return specification["stages"][1]
    return sum(stage["minutes"] for stage in plan.get("schedule", []) if stage["title"] == "剪纸手作")


def _feasible_candidates(planning: dict) -> list[dict]:
    """候选自身与求解结果须同时可行，不以文字解释替代校验结论。"""
    feasible_ids = set(planning.get("feasible_ids", []))
    return [plan for plan in planning.get("candidates", [])
            if plan.get("feasible") is True and not plan.get("conflicts") and plan["id"] in feasible_ids]


def select_ranked_plan(planning: dict, requirements: dict) -> dict | None:
    """按明确、可复算的偏好选择已有候选；模型不参与数值排序。

    返回原 candidates 中的对象，不添加说明字段或更改需求/经营快照。
    硬约束先由求解器检查。最大手作以分钟降序、总价/总时长/ID升序；
    普通模块按总价/总时长/ID升序，固定套餐先尊重已确认且可行的套餐偏好。
    """
    feasible = _feasible_candidates(planning)
    if not feasible:
        return None
    maximize_craft = requirements.get("constraints", {}).get("maximize_craft", False)
    if not maximize_craft and requirements.get("planning_mode", "packages") == "packages":
        preferred = next((plan for plan in feasible if plan["id"] == requirements.get("preferred_plan", "deep")), None)
        if preferred is not None:
            return preferred

    def preference(plan):
        numeric = (plan["total_cents"], plan["duration_minutes"], plan["id"])
        return (-plan_craft_minutes(plan, planning), *numeric) if maximize_craft else numeric

    return min(feasible, key=preference)


def ranking_reason(planning: dict, requirements: dict) -> str:
    """独立保存排序解释，保证候选快照仍能与求解工具严格复算比较。"""
    selected = select_ranked_plan(planning, requirements)
    if selected is None:
        return "程序检查后没有同时满足已确认条件的方案，不能自动放宽人数、报价、时长或资源。"
    if requirements.get("constraints", {}).get("maximize_craft", False):
        basis = "先满足全部硬约束，再按手作时长从多到少、演示总价从低到高、总时长从短到长、方案编号排序"
    elif requirements.get("planning_mode", "packages") == "packages" and selected["id"] == requirements.get("preferred_plan", "deep"):
        basis = "已确认偏好的固定套餐通过全部硬约束，保留该套餐"
    else:
        basis = "先满足全部硬约束，再按演示总价从低到高、总时长从短到长、方案编号排序"
    return (f"程序选择：{basis}。选定“{selected['title']}”，手作{plan_craft_minutes(selected, planning)}分钟，"
            f"总时长{selected['duration_minutes']}分钟，演示总价{selected['total_cents'] / 100:.2f}元。")


def summarize_conflicts(planning: dict) -> list[dict]:
    """无解时提取原求解冲突，保留具体数值；有解时不误报对照方案失败。"""
    if _feasible_candidates(planning):
        return []
    priority = {
        "operating_unavailable": 0, "capacity_exceeded": 1, "teacher_unavailable": 2,
        "teacher_count_insufficient": 3, "teacher_capacity_exceeded": 4, "room_unavailable": 5,
        "region_mismatch": 6, "reuse_required": 7,
    }
    seen, conflicts = set(), []
    for candidate in planning.get("candidates", []):
        for conflict in candidate.get("conflicts", []):
            identity = (conflict["code"], conflict["message"])
            if identity not in seen:
                seen.add(identity)
                conflicts.append({"code": identity[0], "message": identity[1]})
    return sorted(conflicts, key=lambda conflict: priority.get(conflict["code"], 8))


def _integer(value, field: str, minimum: int = 0, maximum: int = 1000000) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field}必须是整数")
    if not minimum <= value <= maximum:
        raise ValueError(f"{field}须在{minimum}至{maximum}之间")
    return value


def _currency(value, field: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field}必须是非负金额")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}必须是非负金额") from None
    if not amount.is_finite() or amount < 0 or amount > 1000000:
        raise ValueError(f"{field}须为0至1000000元的有限金额")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"{field}最多保留两位小数")
    return int(cents)


def _clock(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _validate_plan(plan_id: str, specification: dict) -> dict:
    if not isinstance(specification, dict):
        raise ValueError(f"经营配置{plan_id}须为对象")
    spec = deepcopy(specification)
    if not isinstance(spec.get("title"), str) or not spec["title"].strip():
        raise ValueError(f"经营配置{plan_id}缺少方案标题")
    stages = spec.get("stages")
    if not isinstance(stages, list) or len(stages) != 3:
        raise ValueError(f"经营配置{plan_id}须有讲解、手作、茶歇三个环节")
    for duration in stages:
        _integer(duration, f"{plan_id}环节分钟", 1, 1440)
    for key in (
        "lecture_cents", "craft_per_person_cents", "tea_per_person_cents",
        "tool_cents", "reusable_per_person_cents", "disposable_per_person_cents",
        "operations_cents", "paper_per_person",
    ):
        _integer(spec.get(key), f"{plan_id}.{key}", 0, 100000000)
    for key in ("tags", "audiences"):
        if key in spec and (not isinstance(spec[key], list) or any(not isinstance(item, str) or not item for item in spec[key]) or len(spec[key]) != len(set(spec[key]))):
            raise ValueError(f"{plan_id}.{key}须为不重复字符串列表")
    if "audiences" in spec and (not spec["audiences"] or not set(spec["audiences"]) <= {"general", "family"}):
        raise ValueError(f"{plan_id}.audiences须声明有效客群")
    return spec


def _validate_modules(values) -> list[dict]:
    if not isinstance(values, list) or not 2 <= len(values) <= 12:
        raise ValueError("模块经营配置须包含2至12个明确模块")
    modules = deepcopy(values)
    seen = set()
    categories = {"local_service", "material", "operations"}
    for module in modules:
        if not isinstance(module, dict):
            raise ValueError("经营模块须为对象")
        identity = module.get("id")
        if not isinstance(identity, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", identity) or identity in seen:
            raise ValueError("模块ID须为不重复的ASCII小写短名称")
        seen.add(identity)
        if not isinstance(module.get("title"), str) or not module["title"].strip():
            raise ValueError(f"{identity}缺少模块标题")
        for field in ("tags", "requires_tags", "audiences"):
            items = module.get(field)
            if not isinstance(items, list) or any(not isinstance(item, str) or not item for item in items) or len(items) != len(set(items)):
                raise ValueError(f"{identity}.{field}须为不重复的字符串列表")
        if not module["tags"] or not module["audiences"] or not set(module["audiences"]) <= {"general", "family"}:
            raise ValueError(f"{identity}须声明有效标签和适用客群")
        if module.get("exclusive_group") not in (None, "story", "craft"):
            raise ValueError(f"{identity}互斥分组须为story/craft/null")
        _integer(module.get("order"), f"{identity}.order", 0, 1000)
        _integer(module.get("min_duration_minutes"), f"{identity}.min_duration_minutes", 1, 720)
        _integer(module.get("teacher_needed"), f"{identity}.teacher_needed", 0, 1000)
        _integer(module.get("paper_per_person"), f"{identity}.paper_per_person", 0, 1000)
        costs = module.get("costs")
        if not isinstance(costs, dict) or set(costs) != categories:
            raise ValueError(f"{identity}须完整提供本地服务、材料和组织三类费用")
        for category, cost in costs.items():
            if not isinstance(cost, dict):
                raise ValueError(f"{identity}.{category}费用须为对象")
            for field in ("fixed_cents", "per_person_cents"):
                _integer(cost.get(field), f"{identity}.{category}.{field}", 0, 100000000)
            if not isinstance(cost.get("payee"), str) or not cost["payee"].strip():
                raise ValueError(f"{identity}.{category}缺少演示收款角色")
    return sorted(modules, key=lambda item: (item["order"], item["id"]))


def _module_constraints(raw, modules: list[dict]) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("模块约束须为对象")
    allowed = {"exclude_tags", "require_tags", "min_craft_minutes", "audience", "maximize_craft"}
    if set(raw) - allowed:
        raise ValueError("模块约束含未支持参数，请先明确有效需求")
    values = {"exclude_tags": [], "require_tags": [], "min_craft_minutes": 0,
              "audience": "general", "maximize_craft": False, **deepcopy(raw)}
    known_tags = {tag for module in modules for tag in module["tags"]}
    for field in ("exclude_tags", "require_tags"):
        tags = values[field]
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError(f"{field}须为明确的标签列表")
        if len(tags) != len(set(tags)) or set(tags) - known_tags:
            raise ValueError(f"{field}含重复或未配置的活动标签")
    _integer(values["min_craft_minutes"], "最低手作分钟", 0, 720)
    if values["audience"] not in ("general", "family"):
        raise ValueError("客群须为general或family")
    if not isinstance(values["maximize_craft"], bool):
        raise ValueError("maximize_craft须为明确布尔值")
    return values


def _package_constraints(req, specs):
    """固定套餐也不能绕过明确偏好；只在缺少规范化字段时读取表单参数。"""
    raw = deepcopy(req.get("constraints", {}))
    if not isinstance(raw, dict):
        raise ValueError("套餐约束须为对象")
    tea_preference = req.get("tea_preference", "any")
    if tea_preference not in ("any", "include", "exclude"):
        raise ValueError("tea_preference须为any/include/exclude")
    if "exclude_tags" not in raw and tea_preference == "exclude":
        raw["exclude_tags"] = ["tea"]
    if "require_tags" not in raw and tea_preference == "include":
        raw["require_tags"] = ["tea"]
    raw.setdefault("min_craft_minutes", req.get("min_craft_minutes", 0))
    raw.setdefault("audience", req.get("audience", "general"))
    known_tags = {"story", "craft", "tea", "observation", "sharing", "extension", "deep", "family"}
    known_tags.update(tag for spec in specs.values() for tag in spec.get("tags", []))
    return _module_constraints(raw, [{"tags": sorted(known_tags)}])


def _solve_modules(req, operating, common, people, budget_cents, available, start_minutes):
    modules = _validate_modules(operating.get("modules"))
    # 用补齐默认值的局部对象计算；需求快照保留用户已确认约束的原样，不代替用户改参数。
    req.setdefault("constraints", {})
    constraints = _module_constraints(req["constraints"], modules)
    operating["modules"] = deepcopy(modules)
    rows = []
    considered_subsets = 0
    categories = ("local_service", "material", "operations")
    cost_labels = {"local_service": "本地服务", "material": "材料工具", "operations": "组织费用"}
    teacher_capacity = operating["teacher_capacity"]
    for size in range(2, min(6, len(modules)) + 1):
        for selected in combinations(modules, size):
            considered_subsets += 1
            groups = [module["exclusive_group"] for module in selected if module["exclusive_group"]]
            if groups.count("story") != 1 or groups.count("craft") != 1:
                continue
            if any(not set(module["requires_tags"]) <= {tag for other in selected if other["id"] != module["id"] for tag in other["tags"]} for module in selected):
                continue
            tags = {tag for module in selected for tag in module["tags"]}
            duration = sum(module["min_duration_minutes"] for module in selected)
            craft_minutes = sum(module["min_duration_minutes"] for module in selected if "craft" in module["tags"])
            conflicts = deepcopy(common)

            def add(code, message):
                conflicts.append({"code": code, "message": message})

            excluded = sorted(tags.intersection(constraints["exclude_tags"]))
            missing = sorted(set(constraints["require_tags"]) - tags)
            if excluded:
                add("excluded_tag", "该组合含用户明确排除的活动标签：" + "、".join(excluded) + "；不能自行撤销排除条件。")
            if missing:
                add("required_tag_missing", "该组合缺少用户明确要求的活动标签：" + "、".join(missing) + "。")
            if craft_minutes < constraints["min_craft_minutes"]:
                add("craft_minutes_insufficient", f"手作时长{craft_minutes}分钟，低于要求的{constraints['min_craft_minutes']}分钟；不能虚增课程时间。")
            unsuitable = [module["title"] for module in selected if constraints["audience"] not in module["audiences"]]
            if unsuitable:
                add("audience_mismatch", "经营配置未将以下模块列为该客群适用项目：" + "、".join(unsuitable) + "。")
            minimum_teachers = max(module["teacher_needed"] for module in selected)
            if minimum_teachers:
                teachers_needed = max(minimum_teachers, (people + teacher_capacity - 1) // teacher_capacity)
                if operating["teachers"] == 0:
                    add("teacher_unavailable", f"{people}人手作需至少{teachers_needed}位教师（每位接待上限{teacher_capacity}人，模块最低{minimum_teachers}位），现有0位；不能虚构教师或并行接待。")
                elif operating["teachers"] < minimum_teachers:
                    add("teacher_count_insufficient", f"模块至少需要{minimum_teachers}位教师，现有{operating['teachers']}位；需人工落实资源。")
                if operating["teachers"] and people > teacher_capacity * operating["teachers"]:
                    add("teacher_capacity_exceeded", f"{people}人手作需至少{teachers_needed}位教师；现有{operating['teachers']}位、每位上限{teacher_capacity}人，合计可接待{teacher_capacity * operating['teachers']}人；不自动拆组或增加教师。")
            totals = dict.fromkeys(categories, 0)
            ledger, schedule, cursor = [], [], start_minutes
            for module in selected:
                for category in categories:
                    cost = module["costs"][category]
                    for rate_key, quantity, basis in (("fixed_cents", 1, "固定"), ("per_person_cents", people, "按人数")):
                        rate = cost[rate_key]
                        subtotal = rate * quantity
                        totals[category] += subtotal
                        if rate:
                            ledger.append({"label": f"{module['title']}·{cost_labels[category]}（{basis}）", "cents": subtotal,
                                           "payee": cost["payee"], "category": category, "unit_cents": rate,
                                           "quantity": quantity, "module_id": module["id"]})
                minutes = module["min_duration_minutes"]
                resources = ["room-1"] if operating["rooms"] else []
                if module["teacher_needed"]:
                    needed = max(module["teacher_needed"], (people + teacher_capacity - 1) // teacher_capacity)
                    resources += [f"teacher-{number + 1}" for number in range(min(needed, operating["teachers"]))]
                schedule.append({"title": module["title"], "start": _clock(cursor), "end": _clock(cursor + minutes),
                                 "minutes": minutes, "start_minute": cursor, "end_minute": cursor + minutes,
                                 "end_day_offset": (cursor + minutes) // 1440, "resource_ids": resources, "module_id": module["id"]})
                cursor += minutes
            total = sum(totals.values())
            if total > budget_cents * people:
                add("budget_exceeded", f"演示总价{total / 100:.2f}元超过总预算{budget_cents * people / 100:.2f}元；报价来自经营模块，不能私自降价。")
            if duration > available:
                add("time_exceeded", f"模块所需时长合计{duration}分钟，可用{available}分钟；不能缩短配置的必要教学时长。")
            if start_minutes + duration > 1440:
                add("crosses_midnight", "日程跨越午夜，当前同场地单日演示不支持。")
            ids = [module["id"] for module in selected]
            main_craft = next(module["title"] for module in selected if module["exclusive_group"] == "craft")
            explanation = f"经营配置组合{len(selected)}个模块，总时长{duration}分钟，其中手作{craft_minutes}分钟；演示总价{total / 100:.2f}元。"
            explanation += "满足当前已确认约束，按单组顺序使用现有资源。" if not conflicts else "存在冲突：" + "；".join(item["message"] for item in conflicts)
            rows.append({
                "id": "mod-" + "--".join(ids), "title": f"{main_craft} · {len(selected)}环节组合",
                "feasible": not conflicts, "conflicts": conflicts, "duration_minutes": duration,
                "total_cents": total, "per_person_cents": int((Decimal(total) / people).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
                "local_service_cents": totals["local_service"], "material_cents": totals["material"],
                "operations_cents": totals["operations"], "paper_units": sum(module["paper_per_person"] for module in selected) * people,
                "schedule": schedule, "ledger": ledger, "is_demo": True, "module_ids": ids, "tags": sorted(tags),
                "craft_minutes": craft_minutes, "score": craft_minutes if constraints["maximize_craft"] else -total,
                "score_basis": "优先手作分钟，其次总价" if constraints["maximize_craft"] else "优先低总价，其次总时长",
                "explanation": explanation,
                "scope_note": "独立模块演示报价，不沿用固定套餐价格；同场地单组顺序活动，不自动拆组或并行，不含交通、住宿及税费。客群标签和材料份数均为演示配置，非真实经营或安全认证。",
            })
    if not rows:
        raise ValueError("经营模块无法组成必需的讲解与手作，请负责人检查配置")

    def preference(row):
        first = -row["craft_minutes"] if constraints["maximize_craft"] else row["total_cents"]
        return first, row["total_cents"], row["duration_minutes"], row["id"]

    feasible = sorted((row for row in rows if row["feasible"]), key=preference)
    contrast_priority = {"budget_exceeded": 0, "excluded_tag": 1, "craft_minutes_insufficient": 2,
                         "required_tag_missing": 3, "audience_mismatch": 4, "time_exceeded": 5}
    failed = sorted((row for row in rows if not row["feasible"]), key=lambda row: (
        len(row["conflicts"]), min(contrast_priority.get(item["code"], 6) for item in row["conflicts"]),
        max(0, row["total_cents"] - budget_cents * people),
        max(0, row["duration_minutes"] - available), -row["craft_minutes"], row["id"],
    ))
    selected = []

    def take(row):
        if row not in selected:
            selected.append(row)

    if feasible:
        take(feasible[0])
        take(min(feasible, key=lambda row: (row["total_cents"], row["duration_minutes"], row["id"])))
        take(min(feasible, key=lambda row: (-row["craft_minutes"], row["total_cents"], row["id"])))
        take(min(feasible, key=lambda row: (row["duration_minutes"], row["total_cents"], row["id"])))
        limit = 5 if failed else 6
        while len(selected) < min(limit, len(feasible)):
            remaining = [row for row in feasible if row not in selected]
            take(min(remaining, key=lambda row: (
                -min(len(set(row["module_ids"]) ^ set(other["module_ids"])) for other in selected), preference(row),
            )))
    # 存在不可行组合时保留一个真实对照；全可行时绝不制造冲突。
    if failed:
        take(failed[0])
    for row in failed[1:]:
        if len(selected) >= 6:
            break
        take(row)
    return {
        "candidates": selected, "feasible_ids": [row["id"] for row in selected if row["feasible"]],
        "profile_snapshot": operating, "requirements_snapshot": req, "budget_per_person_cents": budget_cents,
        "planning_policy": "single-group-modules-v1",
        "stats": {"enumerated": len(rows), "feasible_count": len(feasible), "infeasible_count": len(failed),
                  "returned_count": len(selected), "considered_subsets": considered_subsets},
        "score_note": "score仅为明确偏好的确定性排序值，不是可信度、质量概率或实际社会效益。",
    }


def solve_plans(requirements: dict, profile: dict) -> dict:
    """枚举两种方案并逐项报告冲突；不降低人数、不加教师、不自动并行。

    输入中的金额单位是元；全部账目单位是整数分。人均展示金额四舍五入，
    预算判定始终用总价与总预算比较，避免舍入掩盖超支。
    无解返回空 feasible_ids；输入非法抛 ValueError，不静默猜测用户需求。
    """
    if not isinstance(requirements, dict) or not isinstance(profile, dict):
        raise ValueError("需求和经营配置必须为对象")
    req, operating = deepcopy(requirements), deepcopy(profile)
    mode = req.get("planning_mode", "packages")
    if mode not in ("packages", "modules"):
        raise ValueError("planning_mode须为packages或modules")
    people = _integer(req.get("people"), "人数", 1, 10000)
    budget_cents = _currency(req.get("budget_per_person"), "人均预算")
    available = _integer(req.get("available_minutes"), "可用分钟", 1, 1440)
    req.setdefault("start_time", "09:30")
    req.setdefault("preferred_plan", "deep")
    if not isinstance(req["preferred_plan"], str) or req["preferred_plan"] not in DEFAULT_PLANS:
        raise ValueError("偏好方案须为light或deep")
    if not isinstance(req["start_time"], str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", req["start_time"]
    ):
        raise ValueError("开始时间须为24小时制HH:MM")
    for date_key in ("date", "activity_date"):
        if date_key in req and req[date_key] is not None:
            value = req[date_key]
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("活动日期须为YYYY-MM-DD")
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ValueError("活动日期不是有效的公历日期") from None
    if operating.get("is_demo") is not True:
        raise ValueError("当前求解器仅支持明确标记is_demo=true的演示经营配置")
    capacity = _integer(operating.get("capacity"), "单组容量", 0, 10000)
    teachers = _integer(operating.get("teachers"), "教师数", 0, 1000)
    rooms = _integer(operating.get("rooms"), "场地数", 0, 1000)
    teacher_capacity = _integer(operating.get("teacher_capacity", 12), "每位教师接待上限", 1, 10000)
    if not isinstance(operating.get("reuse"), bool):
        raise ValueError("工具复用配置须为布尔值")
    status = operating.get("status", "active")
    if status not in ("active", "open", "paused", "closed", "unavailable"):
        raise ValueError("经营状态须为active/open/paused/closed/unavailable")
    specs = operating.get("plans", DEFAULT_PLANS)
    if not isinstance(specs, dict) or set(specs) != set(DEFAULT_PLANS):
        raise ValueError("经营配置须完整提供light和deep两种方案")
    specs = {key: _validate_plan(key, value) for key, value in specs.items()}
    operating["plans"] = deepcopy(specs)
    operating.setdefault("teacher_capacity", teacher_capacity)
    operating.setdefault("status", status)
    start_minutes = int(req["start_time"][:2]) * 60 + int(req["start_time"][3:])
    common = []

    def add(target, code, message):
        target.append({"code": code, "message": message})

    if status not in ("active", "open"):
        add(common, "operating_unavailable", f"经营配置状态为{status}，当前不可接待；需负责人核实并更新状态。")
    if people > capacity:
        add(common, "capacity_exceeded", f"人数{people}超过单组容量{capacity}；不能自动拆组或虚构并行接待。")
    if mode == "packages" and teachers == 0:
        add(common, "teacher_unavailable", f"{people}人手作需至少{(people + teacher_capacity - 1) // teacher_capacity}位教师（每位接待上限{teacher_capacity}人），现有0位；不能虚构教师或自动拆组。")
    elif mode == "packages" and people > teacher_capacity * teachers:
        add(common, "teacher_capacity_exceeded", f"{people}人手作需至少{(people + teacher_capacity - 1) // teacher_capacity}位教师；现有{teachers}位、每位上限{teacher_capacity}人，合计可接待{teacher_capacity * teachers}人；不自动拆组或增加教师。")
    if rooms == 0:
        add(common, "room_unavailable", "同场地顺序活动至少需要1间场地，现有0间；不能生成可执行日程。")
    if not operating["reuse"]:
        add(common, "reuse_required", "未满足演示活动的工具复用要求；这是经营配置要求，不是法律规定。")

    if mode == "modules":
        return _solve_modules(req, operating, common, people, budget_cents, available, start_minutes)

    package_constraints = _package_constraints(req, specs)
    candidates = []
    for plan_id in ("light", "deep"):
        spec = specs[plan_id]
        lecture = spec["lecture_cents"]
        craft = spec["craft_per_person_cents"] * people
        tea = spec["tea_per_person_cents"] * people
        consumable_rate = spec["reusable_per_person_cents"] if operating["reuse"] else spec["disposable_per_person_cents"]
        consumables = consumable_rate * people
        materials = spec["tool_cents"] + consumables
        local = lecture + craft + tea
        total = local + materials + spec["operations_cents"]
        duration = sum(spec["stages"])
        conflicts = deepcopy(common)
        package_tags = set(spec.get("tags", ["story", "craft", "tea"]))
        excluded = sorted(package_tags.intersection(package_constraints["exclude_tags"]))
        missing = sorted(set(package_constraints["require_tags"]) - package_tags)
        if excluded:
            add(conflicts, "excluded_tag", "固定套餐包含已排除的活动标签：" + "、".join(excluded) + "；不能私自删除已计价环节，可另选模块组合。")
        if missing:
            add(conflicts, "required_tag_missing", "固定套餐没有所要求的活动标签：" + "、".join(missing) + "；不能凭空增加环节。")
        if spec["stages"][1] < package_constraints["min_craft_minutes"]:
            add(conflicts, "craft_minutes_insufficient", f"固定套餐手作{spec['stages'][1]}分钟，低于要求的{package_constraints['min_craft_minutes']}分钟；不虚增教学时长。")
        if package_constraints["audience"] not in spec.get("audiences", ["general"]):
            add(conflicts, "audience_mismatch", "经营配置未将固定套餐列为该客群适用项目，需人工确认或改选模块。")
        if total > budget_cents * people:
            add(conflicts, "budget_exceeded", f"总价{total / 100:.2f}元超过总预算{budget_cents * people / 100:.2f}元；可比较更低价方案或由用户调整预算。")
        if duration > available:
            add(conflicts, "time_exceeded", f"需{duration}分钟，可用{available}分钟；不能压缩已配置教学时长。")
        if start_minutes + duration > 1440:
            add(conflicts, "crosses_midnight", "日程跨越午夜，当前单日演示不支持；需人工调整开始时间。")
        schedule, cursor = [], start_minutes
        for index, (title, minutes) in enumerate(zip(("文化讲解", "剪纸手作", "乡土茶歇"), spec["stages"])):
            resources = ["room-1"] if rooms else []
            # 所有现有教师在同一个组协作；绝不因此产生第二场活动或额外容量。
            if index == 1:
                resources.extend(f"teacher-{number + 1}" for number in range(teachers))
            schedule.append({
                "title": title, "start": _clock(cursor), "end": _clock(cursor + minutes),
                "minutes": minutes, "start_minute": cursor, "end_minute": cursor + minutes,
                "end_day_offset": (cursor + minutes) // 1440,
                "resource_ids": resources,
            })
            cursor += minutes
        ledger = [
            {"label": "文化讲解服务", "cents": lecture, "payee": "在地讲解人员（演示角色）", "category": "local_service", "unit_cents": lecture, "quantity": 1},
            {"label": "手作教学服务", "cents": craft, "payee": "在地手作教师（演示角色）", "category": "local_service", "unit_cents": spec["craft_per_person_cents"], "quantity": people},
            {"label": "乡土茶歇服务", "cents": tea, "payee": "在地茶歇服务者（演示角色）", "category": "local_service", "unit_cents": spec["tea_per_person_cents"], "quantity": people},
            {"label": "工具准备", "cents": spec["tool_cents"], "payee": "材料与工具准备（演示角色）", "category": "material", "unit_cents": spec["tool_cents"], "quantity": 1},
            {"label": "每人耗材", "cents": consumables, "payee": "耗材采购（演示角色）", "category": "material", "unit_cents": consumable_rate, "quantity": people},
            {"label": "组织成本", "cents": spec["operations_cents"], "payee": "活动组织（演示角色）", "category": "operations", "unit_cents": spec["operations_cents"], "quantity": 1},
        ]
        candidates.append({
            "id": plan_id, "title": spec["title"], "feasible": not conflicts, "conflicts": conflicts,
            "duration_minutes": duration, "total_cents": total,
            "per_person_cents": int((Decimal(total) / people).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "local_service_cents": local, "material_cents": materials, "operations_cents": spec["operations_cents"],
            "paper_units": spec["paper_per_person"] * people, "schedule": schedule,
            "ledger": ledger, "is_demo": True,
            "scope_note": "同一演示场地、一个组顺序活动；不含交通、住宿和税费。价格、角色、纸材份数均为演示配置，非预约或真实合作。",
        })
    return {
        "candidates": candidates,
        "feasible_ids": [candidate["id"] for candidate in candidates if candidate["feasible"]],
        "profile_snapshot": operating, "requirements_snapshot": req,
        "budget_per_person_cents": budget_cents,
        "planning_policy": "single-group-sequential-v1",
    }
