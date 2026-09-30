"""单场地、单组体验求解。模型不能修改本模块读取的经营报价。"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
    return spec


def solve_plans(requirements: dict, profile: dict) -> dict:
    """枚举两种方案并逐项报告冲突；不降低人数、不加教师、不自动并行。

    输入中的金额单位是元；全部账目单位是整数分。人均展示金额四舍五入，
    预算判定始终用总价与总预算比较，避免舍入掩盖超支。
    无解返回空 feasible_ids；输入非法抛 ValueError，不静默猜测用户需求。
    """
    if not isinstance(requirements, dict) or not isinstance(profile, dict):
        raise ValueError("需求和经营配置必须为对象")
    req, operating = deepcopy(requirements), deepcopy(profile)
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
        add(common, "operating_unavailable", "经营配置当前不可接待，需负责人更新状态。")
    if people > capacity:
        add(common, "capacity_exceeded", f"人数{people}超过单组容量{capacity}；不能自动拆组或虚构并行接待。")
    if teachers == 0:
        add(common, "teacher_unavailable", "手作环节没有可用教师，需人工确认真实人员资源。")
    elif people > teacher_capacity * teachers:
        add(common, "teacher_capacity_exceeded", f"人数{people}超过现有{teachers}位教师合计接待上限{teacher_capacity * teachers}。")
    if rooms == 0:
        add(common, "room_unavailable", "没有可用场地，不能生成可执行日程。")
    if not operating["reuse"]:
        add(common, "reuse_required", "未满足演示活动的工具复用要求；这是经营配置要求，不是法律规定。")

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
