"""地域优先的本地证据检索；来源文本始终作为数据，不执行其中的指令。"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import jieba
from rank_bm25 import BM25Plus


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# 明确的地域别名表只做实体消歧，不编码核验答案。省名或混合地域不猜测。
_REGIONS = {
    "蔚县": "河北省蔚县",
    "河北蔚县": "河北省蔚县",
    "河北省蔚县": "河北省蔚县",
    "张家口市蔚县": "河北省蔚县",
    "河北省张家口市蔚县": "河北省蔚县",
    "丰宁": "河北省丰宁满族自治县",
    "丰宁县": "河北省丰宁满族自治县",
    "丰宁满族自治县": "河北省丰宁满族自治县",
    "河北省丰宁满族自治县": "河北省丰宁满族自治县",
    "河北省承德市丰宁满族自治县": "河北省丰宁满族自治县",
    "金山": "上海市金山区",
    "金山区": "上海市金山区",
    "上海市金山区": "上海市金山区",
}
_JIEBA = jieba.Tokenizer()
_STOPWORDS = {"的", "了", "是", "在", "和", "与", "为", "及", "它", "吗", "呢"}


def _load(relative_path: str):
    with (DATA / relative_path).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_sources() -> list:
    """读取精选片段；hash 仅表示保存摘录，不表示保存了整个网页。"""
    sources = _load("curated/sources.json") + _load("curated/public-case-sources.json")
    for source in sources:
        if hashlib.sha256(source["quote"].encode("utf-8")).hexdigest() != source["sha256"]:
            raise ValueError(f"来源摘录哈希不一致：{source['id']}")
    return sources


def load_materials() -> list:
    return _load("curated/materials.json")


def load_public_case(case_id: str | None = None) -> dict | None:
    if case_id is None:
        return None
    if case_id != "jinshan-paper-light":
        raise ValueError("未知公开活动案例")
    return _load("cases/jinshan-paper-light.json")


def load_profile(case_id: str | None = None) -> dict:
    if case_id:
        load_public_case(case_id)
        return _load("operating/jinshan-reconstruction.json")
    return _load("operating/demo-profile.json")


def normalize_region(region: str) -> str | None:
    return _REGIONS.get(str(region or "").strip())


def _tokens(text: str) -> list[str]:
    return [
        token.lower()
        for token in _JIEBA.cut_for_search(str(text))
        if token.strip() and token not in _STOPWORDS
        and re.search(r"[\w\u4e00-\u9fff]", token)
    ]


def search_evidence(
    query: str,
    region: str,
    project: str = "剪纸",
    sources: list | None = None,
    limit: int = 4,
) -> list:
    """先地域/项目/使用状态过滤，再按中文 BM25 排序。

    零结果代表本库没有匹配项，绝不等价于事实错误。score 仅为库内检索排序，
    不是可信度、概率或事实判定。sources 可传 SQLite 当前版本；不静默回退到种子。
    """
    canonical_region = normalize_region(region)
    if not canonical_region or not str(query).strip() or limit < 1:
        return []
    candidates = [
        source for source in (load_sources() if sources is None else sources)
        if normalize_region(source.get("region", "")) == canonical_region
        and source.get("project") == project
        and source.get("usage_status") == "available"
        and isinstance(source.get("quote"), str)
    ]
    if not candidates:
        return []
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    documents = [
        _tokens(" ".join([
            source.get("title", ""), source["quote"],
            " ".join(source.get("keywords", [])),
        ]))
        for source in candidates
    ]
    if not any(documents):
        return []
    scorer = BM25Plus(documents)
    scores = scorer.get_scores(query_tokens)
    query_terms = set(query_tokens)
    # BM25Plus 有非零基值，必须另行排除完全无词汇匹配的候选。
    ranked = sorted(
        ((index, float(score)) for index, score in enumerate(scores)
         if query_terms.intersection(documents[index])),
        key=lambda item: (-item[1], candidates[item[0]]["id"]),
    )
    result = []
    for index, score in ranked[:min(int(limit), 20)]:
        item = deepcopy(candidates[index])
        item["retrieval_score"] = round(score, 6)
        item["trust_boundary"] = "untrusted_source_data"
        result.append(item)
    return result
