"""Test thuần cho `_dedupe_live_variables` (get_live_context) — không cần site.

Vì sao KHÔNG import thẳng module: `formula_builder.api.formula_builder` import
`frappe` ở cấp module, nên chỉ chạy được trong bench. Test này cần chạy được
bằng `python3 -I` (CI/không có site) nên đọc CHÍNH file nguồn, tách 4 hàm
thuần cần kiểm bằng AST rồi exec — vẫn là code thật, không phải bản chép.

Chạy:
    cd ~/myfrappe/apps/formula_builder
    python3 -I -c "import sys, unittest; sys.path.insert(0, '.'); \
        unittest.main(module='formula_builder.tests.test_live_context_dedupe', exit=True, verbosity=2)"
"""

import ast
import re
from pathlib import Path
from typing import Dict, List
import unittest

_SOURCE_PATH = Path(__file__).resolve().parents[1] / "api" / "formula_builder.py"

_PURE_FUNCS = (
    "_split_field_scope",
    "_merge_field_scope",
    "_with_field_scope",
    "_dedupe_live_variables",
)


def _load_pure_functions():
    """Tách các hàm thuần khỏi module (module gốc cần frappe) và exec."""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [n for n in tree.body
             if isinstance(n, ast.FunctionDef) and n.name in _PURE_FUNCS]
    found = {n.name for n in nodes}
    missing = set(_PURE_FUNCS) - found
    if missing:
        raise AssertionError("Không tìm thấy hàm trong nguồn: %s" % ", ".join(sorted(missing)))

    namespace = {"_re": re, "Dict": Dict, "List": List}
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(_SOURCE_PATH), "exec"), namespace)
    return namespace


_FUNCS = _load_pure_functions()
dedupe = _FUNCS["_dedupe_live_variables"]
split_scope = _FUNCS["_split_field_scope"]
merge_scope = _FUNCS["_merge_field_scope"]


class TestFieldScopeHelpers(unittest.TestCase):
    def test_split_pipe_and_comma(self):
        self.assertEqual(split_scope("width|height, qty"), ["width", "height", "qty"])

    def test_split_list_and_dedup(self):
        self.assertEqual(split_scope(["width", " width ", "", "qty"]), ["width", "qty"])

    def test_split_empty(self):
        self.assertEqual(split_scope(""), [])
        self.assertEqual(split_scope(None), [])
        self.assertEqual(split_scope([]), [])

    def test_merge_union(self):
        self.assertEqual(merge_scope("width", "height|qty"), ["width", "height", "qty"])

    def test_merge_one_empty_means_unlimited(self):
        # Rỗng = không giới hạn ⇒ gộp với bất kỳ = không giới hạn
        self.assertEqual(merge_scope("", "width"), [])
        self.assertEqual(merge_scope("width", ""), [])
        self.assertEqual(merge_scope("", ""), [])


class TestDedupeFieldScope(unittest.TestCase):
    def test_single_entry_normalised(self):
        out = dedupe([{"name": "A", "value": 1, "applies_to_field": "width|height"}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["only_fields"], ["width", "height"])
        self.assertEqual(out[0]["applies_to_field"], "width|height")

    def test_single_entry_without_scope_unrestricted(self):
        out = dedupe([{"name": "A", "value": 1}])
        self.assertEqual(out[0]["only_fields"], [])
        self.assertEqual(out[0]["applies_to_field"], "")

    def test_duplicate_union_scope(self):
        out = dedupe([
            {"name": "A", "value": 1, "applies_to_field": "width"},
            {"name": "A", "value": 2, "applies_to_field": "height"},
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["value"], 1)          # hoà ⇒ giữ entry đầu
        self.assertEqual(out[0]["only_fields"], ["width", "height"])
        self.assertEqual(out[0]["applies_to_field"], "width|height")

    def test_duplicate_one_unrestricted_wins_as_unlimited(self):
        out = dedupe([
            {"name": "A", "value": 1, "applies_to_field": "width"},
            {"name": "A", "value": 2, "applies_to_field": ""},
        ])
        self.assertEqual(out[0]["only_fields"], [])
        self.assertEqual(out[0]["applies_to_field"], "")

    def test_duplicate_later_has_value_keeps_position_and_scope(self):
        out = dedupe([
            {"name": "A", "value": None, "applies_to_field": "width",
             "source": "local", "source_type": "linked_doctype_field"},
            {"name": "B", "value": 9},
            {"name": "A", "value": 7, "applies_to_field": "qty",
             "source": "global", "source_type": "computed"},
        ])
        self.assertEqual([v["name"] for v in out], ["A", "B"])
        self.assertEqual(out[0]["value"], 7)
        self.assertEqual(out[0]["only_fields"], ["width", "qty"])
        self.assertEqual(len(out[0]["duplicate_sources"]), 1)

    def test_nameless_entry_untouched(self):
        raw = {"value": 1, "applies_to_field": "width"}
        out = dedupe([raw])
        self.assertEqual(out, [raw])


if __name__ == "__main__":
    unittest.main(verbosity=2)
