import pytest

from backend.drafts import generate_draft
from backend.evidence import load_sources
from backend.model import ModelFailure


class FakeLLM:
    def __init__(self, result=None, fail=False):
        self.calls, self.result, self.fail = [], result, fail

    def ask(self, purpose, data, schema, instruction, *, max_attempts=2):
        self.calls.append({"purpose": purpose, "data": data})
        if self.fail:
            raise ModelFailure("本地模型不可用")
        return schema.model_validate(self.result(data)).model_dump()


def good(data):
    facts = data["facts"]
    return {"sentences": [{"text": f"{data['project']}{facts[i]['quote']}", "source_ids": [facts[i]["source_id"]]}
                          for i in range(data["sentence_count"])]}


def test_model_draft_only_uses_region_sources_and_sentence_count():
    llm = FakeLLM(good)
    result = generate_draft(load_sources(), "河北省蔚县", "剪纸", "student", 5, llm=llm)
    assert result["origin"] == "local_model" and result["status"] == "draft_unverified"
    sent = llm.calls[0]["data"]
    assert sent["sentence_count"] == 4 and all("fengning" not in fact["source_id"] for fact in sent["facts"])
    assert result["text"].count("。") == 4 and set(result["source_ids"]) <= {fact["source_id"] for fact in sent["facts"]}


def test_model_failure_loads_labelled_deployment_preset():
    result = generate_draft(load_sources(), "河北省蔚县", "剪纸", "senior", 5, llm=FakeLLM(fail=True))
    assert result["origin"] == "deployment_preset" and "model_error" in result
    assert "初始图案多为花卉" in result["text"] and "预置" in result["preset_note"]


def test_out_of_scope_citations_fall_back_instead_of_being_accepted():
    bad = lambda data: {"sentences": [{"text": "丰宁满族剪纸阳刻为主。", "source_ids": ["src-fengning-technique"]},
                                      {"text": "剪纸很好。", "source_ids": ["src-fengning-craft"]},
                                      {"text": "剪纸很好看。", "source_ids": ["src-yuxian-color"]}]}
    result = generate_draft(load_sources(), "河北省蔚县", "剪纸", "general", 3, llm=FakeLLM(bad))
    assert result["origin"] == "deployment_preset"


def test_every_preset_sentence_is_backed_by_a_listed_quote():
    from backend.drafts import _presets
    quotes = {s["id"]: s["quote"] for s in load_sources()}
    for item in _presets()["drafts"]:
        assert all(sid in quotes for sid in item["source_ids"])
        for sid in item["source_ids"]:
            assert quotes[sid] in item["text"]


def test_unknown_inputs_are_rejected():
    with pytest.raises(ValueError):
        generate_draft(load_sources(), "河北省蔚县", "剪纸", "tourist", 5, llm=FakeLLM(good))
    with pytest.raises(ValueError):
        generate_draft(load_sources(), "浙江省", "剪纸", "general", 5, llm=FakeLLM(good))
