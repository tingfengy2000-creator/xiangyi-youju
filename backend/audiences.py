"""体验对象（客群）的唯一定义：标签、讲解口吻与演示编排偏好。

访谈中文旅办负责人指出，活动变更主要来自对象不同（青少年、学生、老年人、
专业成年人、游客），为更有针对性地传播文化才调整。这里把“面向谁”变成
可复核的程序偏好：只补充活动标签要求和手作优先级，不改人数、报价、
教师或时长，也不越过用户明确排除的环节。偏好为演示配置，不是安全或教学认证。
"""

AUDIENCES = {
    "general": {
        "label": "普通游客",
        "style": "使用自然清晰的成年游客表达",
        "require_tags": [],
        "maximize_craft": False,
        "plan_note": "",
    },
    "family": {
        "label": "亲子家庭",
        "style": "面向亲子共同观察，短句易懂，家长陪伴讨论",
        "require_tags": [],
        "maximize_craft": False,
        "plan_note": "",
    },
    "student": {
        "label": "青少年学生",
        "style": "面向中小学生，短句、用词浅显、语气亲切",
        "require_tags": ["observation"],
        "maximize_craft": True,
        "plan_note": "青少年学生：多动手、加入观察环节",
    },
    "senior": {
        "label": "老年人",
        "style": "面向老年参与者，句子舒缓、少用新词",
        "require_tags": ["deep", "tea"],
        "maximize_craft": False,
        "plan_note": "老年人：多讲故事、手作轻量、留出茶歇休息",
    },
    "expert": {
        "label": "专业爱好者",
        "style": "面向有基础的成年爱好者，用词准确，可点明卡片中已有的地域与技法信息",
        "require_tags": ["deep", "observation"],
        "maximize_craft": True,
        "plan_note": "专业爱好者：深度讲述、深度手作、加入点染观察",
    },
}

AUDIENCE_IDS = tuple(AUDIENCES)


def label(audience: str) -> str:
    return AUDIENCES.get(audience, AUDIENCES["general"])["label"]


def apply_defaults(constraints: dict, known_tags: set[str]) -> tuple[dict, str]:
    """Return constraints with audience defaults merged, plus a short note.

    User-excluded tags always win, and tags the catalog does not offer are skipped,
    so the defaults can only narrow the candidates, never invent a module.
    """
    profile = AUDIENCES.get(constraints.get("audience"), AUDIENCES["general"])
    merged = dict(constraints)
    require = list(merged.get("require_tags", []))
    for tag in profile["require_tags"]:
        if tag in known_tags and tag not in merged.get("exclude_tags", []) and tag not in require:
            require.append(tag)
    merged["require_tags"] = require
    merged["maximize_craft"] = bool(merged.get("maximize_craft")) or profile["maximize_craft"]
    return merged, profile["plan_note"]
