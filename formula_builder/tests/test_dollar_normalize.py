"""Test thuần cho việc bỏ tiền tố `$` của biến toàn cục ($NAME → NAME).

Mục tiêu: autocomplete của Formula Builder chèn biến global dạng `$TEN`, trong
khi FormulaEngine chỉ hiểu tên trần. Test này chốt 3 điều:
  · `$NAME` → `NAME` (cả khi nằm trong biểu thức phức tạp);
  · `$snap.<field>` GIỮ NGUYÊN (cú pháp snapshot);
  · chuỗi trong nháy GIỮ NGUYÊN (dữ liệu, không phải biến).

Không cần frappe, không cần DB. Chạy:
    cd ~/myfrappe/apps/formula_builder
    python3 -I -c "import sys, unittest; sys.path.insert(0, '.'); \
        unittest.main(module='formula_builder.tests.test_dollar_normalize', exit=True, verbosity=2)"
"""

import unittest

from formula_builder.formula_utils.normalize import (
    normalize_formula,
    strip_dollar_prefix,
)


class TestStripDollarPrefix(unittest.TestCase):
    """Quét `$` ở mức chuỗi thô."""

    def test_simple_name(self):
        self.assertEqual(strip_dollar_prefix("$VAT_RATE * 2"), "VAT_RATE * 2")

    def test_multiple_names(self):
        self.assertEqual(strip_dollar_prefix("$A + $B_1"), "A + B_1")

    def test_snap_kept(self):
        self.assertEqual(strip_dollar_prefix("$snap.total"), "$snap.total")

    def test_snap_and_global_mixed(self):
        self.assertEqual(
            strip_dollar_prefix("$snap.total + $RATE"), "$snap.total + RATE"
        )

    def test_snapshot_is_not_snap(self):
        # Tên khác `snap` (dù cùng tiền tố chữ) vẫn phải bỏ `$`
        self.assertEqual(strip_dollar_prefix("$snapshot"), "snapshot")

    def test_string_literal_untouched(self):
        self.assertEqual(
            strip_dollar_prefix("'$NAME' + \"$OTHER\" + $REAL"),
            "'$NAME' + \"$OTHER\" + REAL",
        )

    def test_escaped_quote_inside_literal(self):
        raw = "'it\\'s $NAME' + $X"
        self.assertEqual(strip_dollar_prefix(raw), "'it\\'s $NAME' + X")

    def test_dollar_without_name(self):
        # `$` không đi kèm tên biến → giữ nguyên (tiền tệ, ký tự lạ…)
        self.assertEqual(strip_dollar_prefix("$ 5"), "$ 5")
        self.assertEqual(strip_dollar_prefix("1$ + a"), "1$ + a")
        self.assertEqual(strip_dollar_prefix("$$X"), "$X")

    def test_empty_and_none(self):
        self.assertEqual(strip_dollar_prefix(""), "")
        self.assertIsNone(strip_dollar_prefix(None))


class TestNormalizeFormulaDollar(unittest.TestCase):
    """normalize_formula áp luật bỏ `$` cùng các chuẩn hoá khác."""

    def test_global_in_expression(self):
        self.assertEqual(
            normalize_formula("$VAT_RATE * 2", frozenset()), "VAT_RATE * 2"
        )

    def test_snap_preserved(self):
        self.assertEqual(
            normalize_formula("$snap.total + 1", frozenset()), "$snap.total + 1"
        )

    def test_literal_preserved_others_converted(self):
        # '=' → '==', `$A`/`$C` → A/C, literal '$B' giữ nguyên
        self.assertEqual(
            normalize_formula("IF($A = 1, '$B', $C)", frozenset({"IF"})),
            "IF(A == 1, '$B', C)",
        )

    def test_html_dollar_entity(self):
        # `&dollar;` phải được gỡ entity TRƯỚC bước bỏ `$`
        self.assertEqual(
            normalize_formula("&dollar;RATE + 1", frozenset()), "RATE + 1"
        )

    def test_idempotent(self):
        expr = "IF($A > 0, $B, '$C')"
        once = normalize_formula(expr, frozenset({"IF"}))
        twice = normalize_formula(once, frozenset({"IF"}))
        self.assertEqual(once, twice)


class TestEngineAcceptsDollar(unittest.TestCase):
    """Chốt hợp đồng cuối: FormulaEngine tính được công thức có `$NAME`."""

    def test_engine_evaluates_dollar_global(self):
        from formula_builder.formula_utils import FormulaEngine

        engine = FormulaEngine([{"name": "out", "formula": "$RATE * 2"}])
        result = engine.calculate({"RATE": 5})
        self.assertEqual(result.get("out"), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
