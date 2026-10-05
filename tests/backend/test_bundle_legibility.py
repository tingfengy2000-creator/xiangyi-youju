"""导出体验包的中文文字在屏幕上不小于12px；打印正文基准单独保留。"""

import re

from backend.bundles import CSS


def test_exported_bundle_text_is_at_least_12px_on_screen():
    small = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS):
        for size in re.findall(r"font-size:([0-9.]+)px", body):
            if float(size) < 12 and not (selector.strip().endswith("body") and "background:white" in body):
                small.append(f"{selector.strip()} {size}px")
    assert not small, small
