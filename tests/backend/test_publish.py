"""作品发布新版本：作品保持可用，引用旧版本的运行需要重新核验。"""

import pytest

from tests.backend.test_store import isolated_store, make_run  # noqa: F401  (fixture reuse)
from backend.evidence import load_materials


def test_publish_moves_to_next_edition_and_marks_runs_for_update(isolated_store):
    run = make_run("uses-work")
    run["material_versions"] = isolated_store.versions(load_materials())
    run["cards"][0]["material_ids"] = ["mat-work-floral-window"]
    isolated_store.save_run(run)
    result = isolated_store.publish_edition("mat-work-floral-window")
    record = result["record"]
    assert record["edition"] == 2 and record["usage_status"] == "available" and record["version"] == 2
    assert "新作" in record["title"]
    saved = isolated_store.get_run("uses-work")
    assert saved["status"] == "invalidated" and saved["approval"] is None
    assert saved["affected"][0]["card_ids"] == ["card-technique"]
    assert "第2版" in saved["events"][-1]["message"]


def test_publish_without_a_prepared_edition_is_refused(isolated_store):
    with pytest.raises(ValueError):
        isolated_store.publish_edition("mat-work-opera-mask")
    isolated_store.publish_edition("mat-work-floral-window")
    with pytest.raises(ValueError):
        isolated_store.publish_edition("mat-work-floral-window")


def test_demo_works_are_labelled_and_priced_in_cents():
    works = [m for m in load_materials() if m.get("source_type") == "craftsperson_demo"]
    assert len(works) == 2
    for work in works:
        assert work["is_demo"] is True and "虚构" in work["author"]
        assert isinstance(work["product"]["price_cents"], int) and "不经手资金" in work["product"]["sale_note"]
