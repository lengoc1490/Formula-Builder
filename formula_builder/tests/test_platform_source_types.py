"""Tests for the v31 Phase 3 platform-expansion source types.

Covers:
  - matrix_lookup (S2): exact match, fallback row/col, default, case-insensitive,
    template resolution, batch resolve, schema validation, fingerprint.
  - reuse_formula_result (S1): sum/min/max/avg/first/last, line matching by
    item_code, scope_field/scope_value lookup, document_name, default, batch.

These tests run WITHOUT a site: they import the real formula_builder modules
with the real frappe package present, but mock every DB-facing call
(frappe.get_all / frappe.get_doc / frappe.log_error).
"""

import json
import unittest
from unittest import mock

import frappe

from formula_builder.api.data_source_registry import (
    _data_source_handlers,
    _resolve_matrix_lookup_batch,
    _resolve_reuse_formula_result_batch,
    _handle_matrix_lookup,
    _handle_reuse_formula_result,
    get_handler,
    is_batchable,
    resolve_bindings_with_deps,
)
from formula_builder.api.source_type_registry import SourceTypeRegistry

# Fake matrix rows (as returned by frappe.get_all → list of dicts)
MATRIX_ROWS = [
    {"size": "1000", "thickness": "5", "price": 120.0},
    {"size": "1000", "thickness": "8", "price": 150.0},
    {"size": "1500", "thickness": "5", "price": 180.0},
    {"size": "1500", "thickness": "8", "price": 220.0},
    {"size": "ANY", "thickness": "8", "price": 210.0},    # fallback row
    {"size": "1500", "thickness": "ANY", "price": 190.0},  # fallback col
    {"size": "ANY", "thickness": "ANY", "price": 99.0},    # fallback both
]


def _matrix_binding(**over):
    cfg = {
        "doctype": "AL Pricing Matrix",
        "row_key_field": "size",
        "col_key_field": "thickness",
        "value_field": "price",
        "row_key": "{{row.size}}",
        "col_key": "{{row.thickness}}",
        "default_value": 0,
        "fallback_row_key": "ANY",
        "fallback_col_key": "ANY",
    }
    cfg.update(over.get("config", {}))
    b = {
        "variable_name": over.get("variable_name", "price"),
        "source_type": "matrix_lookup",
        "source_config": json.dumps(cfg),
        "data_type": over.get("data_type", "Float"),
    }
    if "default_value" in over and "config" not in over:
        b["default_value"] = over["default_value"]
    return b


class TestMatrixLookupRegistration(unittest.TestCase):
    def test_handler_registered(self):
        self.assertIn("matrix_lookup", _data_source_handlers)
        self.assertIsNotNone(get_handler("matrix_lookup"))
        self.assertTrue(is_batchable("matrix_lookup"))

    def test_handler_is_callable(self):
        self.assertTrue(callable(get_handler("matrix_lookup")))


class TestMatrixLookupResolve(unittest.TestCase):
    """Core lookup semantics: exact, fallback, default."""

    def setUp(self):
        self.get_all_patcher = mock.patch.object(frappe, "get_all", return_value=list(MATRIX_ROWS))
        self.log_patcher = mock.patch.object(frappe, "log_error")
        self.get_all_patcher.start()
        self.log_patcher.start()
        self.addCleanup(self.get_all_patcher.stop)
        self.addCleanup(self.log_patcher.stop)

    def test_exact_match(self):
        row = {"size": "1000", "thickness": "5"}
        val = _handle_matrix_lookup(_matrix_binding(), None, {"row": row})
        self.assertEqual(val, 120.0)

    def test_exact_match_other_cell(self):
        row = {"size": "1500", "thickness": "8"}
        val = _handle_matrix_lookup(_matrix_binding(), None, {"row": row})
        self.assertEqual(val, 220.0)

    def test_missing_cell_uses_fallback_row(self):
        # (size=2000, thickness=8): no exact, fallback row "ANY" + col 8 → 210
        row = {"size": "2000", "thickness": "8"}
        val = _handle_matrix_lookup(_matrix_binding(), None, {"row": row})
        self.assertEqual(val, 210.0)

    def test_missing_cell_uses_fallback_col(self):
        # (size=1500, thickness=12): no exact, row 1500 + fallback col ANY → 190
        row = {"size": "1500", "thickness": "12"}
        val = _handle_matrix_lookup(_matrix_binding(), None, {"row": row})
        self.assertEqual(val, 190.0)

    def test_missing_cell_uses_fallback_both(self):
        # (size=2000, thickness=12): no exact, fallback row+col → 99
        row = {"size": "2000", "thickness": "12"}
        val = _handle_matrix_lookup(_matrix_binding(), None, {"row": row})
        self.assertEqual(val, 99.0)

    def test_no_match_at_all_returns_default(self):
        # No fallback keys configured → any miss falls through to default_value
        cfg = {"row_key": "2000", "col_key": "99", "fallback_row_key": None, "fallback_col_key": None}
        val = _handle_matrix_lookup(_matrix_binding(config=cfg), None, {})
        self.assertEqual(val, 0)

    def test_fallback_both_when_both_configured(self):
        row = {"size": "2000", "thickness": "99"}
        val = _handle_matrix_lookup(_matrix_binding(), None, {"row": row})
        self.assertEqual(val, 99.0)

    def test_case_insensitive_mode(self):
        rows = [
            {"size": "SMALL", "color": "Red", "price": 50.0},
            {"size": "LARGE", "color": "Red", "price": 90.0},
        ]
        with mock.patch.object(frappe, "get_all", return_value=rows):
            cfg = {
                "doctype": "X Matrix",
                "row_key_field": "size",
                "col_key_field": "color",
                "value_field": "price",
                "row_key": "small",
                "col_key": "red",
                "default_value": 0,
                "match_mode": "case_insensitive",
            }
            b = _matrix_binding(config=cfg)
            val = _handle_matrix_lookup(b, None, {})
        self.assertEqual(val, 50.0)

    def test_literal_keys(self):
        rows = [{"size": "ANY", "thickness": "ANY", "price": 7.0}]
        with mock.patch.object(frappe, "get_all", return_value=rows):
            cfg = {
                "doctype": "X Matrix",
                "row_key_field": "size",
                "col_key_field": "thickness",
                "value_field": "price",
                "row_key": "ANY",
                "col_key": "ANY",
                "default_value": 0,
            }
            val = _handle_matrix_lookup(_matrix_binding(config=cfg), None, {})
        self.assertEqual(val, 7.0)

    def test_missing_value_cell_treated_as_no_match(self):
        rows = [{"size": "1000", "thickness": "5", "price": None}]
        with mock.patch.object(frappe, "get_all", return_value=rows):
            cfg = {
                "doctype": "X Matrix",
                "row_key_field": "size",
                "col_key_field": "thickness",
                "value_field": "price",
                "row_key": "1000",
                "col_key": "5",
                "default_value": -1,
            }
            val = _handle_matrix_lookup(_matrix_binding(config=cfg), None, {})
        self.assertEqual(val, -1)

    def test_empty_rows_returns_default(self):
        with mock.patch.object(frappe, "get_all", return_value=[]):
            val = _handle_matrix_lookup(_matrix_binding(), None, {"row": {"size": "1", "thickness": "1"}})
        self.assertEqual(val, 0)

    def test_get_all_error_returns_default(self):
        with mock.patch.object(frappe, "get_all", side_effect=Exception("boom")):
            val = _handle_matrix_lookup(_matrix_binding(), None, {"row": {"size": "1000", "thickness": "5"}})
        self.assertEqual(val, 0)


class TestMatrixLookupBatch(unittest.TestCase):
    def setUp(self):
        self.log_patcher = mock.patch.object(frappe, "log_error")
        self.log_patcher.start()
        self.addCleanup(self.log_patcher.stop)

    def test_batch_resolves_multiple_bindings(self):
        rows = list(MATRIX_ROWS)
        with mock.patch.object(frappe, "get_all", return_value=rows) as ga:
            bindings = [
                _matrix_binding(variable_name="a", config={"row_key": "{{row.size}}", "col_key": "{{row.thickness}}"}),
                _matrix_binding(variable_name="b", config={"row_key": "2000", "col_key": "8"}),
            ]
            result = _resolve_matrix_lookup_batch(bindings, None, {"row": {"size": "1500", "thickness": "8"}})
        # Only 1 DB call for the whole group
        self.assertEqual(ga.call_count, 1)
        self.assertEqual(result["a"], 220.0)
        self.assertEqual(result["b"], 210.0)  # fallback row ANY + col 8

    def test_batch_default_on_error(self):
        with mock.patch.object(frappe, "get_all", side_effect=Exception("db down")):
            result = _resolve_matrix_lookup_batch([_matrix_binding()], None, {})
        self.assertEqual(result["price"], 0)


class TestMatrixLookupSchemaAndFingerprint(unittest.TestCase):
    def test_validation_missing_required(self):
        registry = SourceTypeRegistry.get_instance()
        errors = registry.validate_source_config("matrix_lookup", {"row_key_field": "size"})
        self.assertTrue(any("doctype" in e for e in errors))
        self.assertTrue(any("value_field" in e for e in errors))

    def test_validation_valid_config(self):
        registry = SourceTypeRegistry.get_instance()
        cfg = {
            "doctype": "AL Pricing Matrix",
            "row_key_field": "size",
            "col_key_field": "thickness",
            "value_field": "price",
        }
        self.assertEqual(registry.validate_source_config("matrix_lookup", cfg), [])

    def test_validation_bad_enum(self):
        registry = SourceTypeRegistry.get_instance()
        cfg = {"doctype": "X", "value_field": "v", "match_mode": "wild"}
        errors = registry.validate_source_config("matrix_lookup", cfg)
        self.assertTrue(any("match_mode" in e for e in errors))

    def test_fingerprint_deterministic(self):
        fn = get_handler("matrix_lookup").fingerprint_fn
        cfg1 = {"doctype": "A", "row_key_field": "r", "col_key_field": "c", "value_field": "v"}
        cfg2 = {"doctype": "A", "row_key_field": "r", "col_key_field": "c", "value_field": "v"}
        cfg3 = {"doctype": "B", "row_key_field": "r", "col_key_field": "c", "value_field": "v"}
        self.assertEqual(fn(cfg1), fn(cfg2))
        self.assertNotEqual(fn(cfg1), fn(cfg3))

    def test_validate_binding_config_integration(self):
        registry = SourceTypeRegistry.get_instance()
        binding = _matrix_binding()
        self.assertEqual(registry.validate_binding_config(binding), [])


class _FakeLine(dict):
    """dict-based child table row with .get()"""


class _FakeTargetDoc:
    """Minimal stand-in for a frappe Document returned by frappe.get_doc."""

    def __init__(self, lines, line_field="cost_lines"):
        self._lines = lines
        self._line_field = line_field

    def get(self, key, default=None):
        if key == self._line_field:
            return self._lines
        return default


def _reuse_binding(aggregation="sum", **over):
    cfg = {
        "formula_document": "AL Cost Template",
        "scope_field": "quotation",
        "scope_value": "{{doc.quotation}}",
        "line_field": "cost_lines",
        "line_match": "{{row.item_code}}",
        "result_field": "line_cost",
        "aggregation": aggregation,
        "default_value": 0,
    }
    cfg.update(over.get("config", {}))
    b = {
        "variable_name": over.get("variable_name", "reused_cost"),
        "source_type": "reuse_formula_result",
        "source_config": json.dumps(cfg),
        "data_type": over.get("data_type", "Float"),
    }
    return b


class TestReuseFormulaResultRegistration(unittest.TestCase):
    def test_handler_registered(self):
        self.assertIn("reuse_formula_result", _data_source_handlers)
        self.assertIsNotNone(get_handler("reuse_formula_result"))
        self.assertTrue(is_batchable("reuse_formula_result"))


class TestReuseFormulaResultResolve(unittest.TestCase):
    def setUp(self):
        self.get_all_patcher = mock.patch.object(frappe, "get_all")
        self.get_doc_patcher = mock.patch.object(frappe, "get_doc")
        self.log_patcher = mock.patch.object(frappe, "log_error")
        self.get_all_mock = self.get_all_patcher.start()
        self.get_doc_mock = self.get_doc_patcher.start()
        self.log_patcher.start()
        self.addCleanup(self.get_all_patcher.stop)
        self.addCleanup(self.get_doc_patcher.stop)
        self.addCleanup(self.log_patcher.stop)

    def _lines(self):
        return [
            _FakeLine(item_code="A", line_cost=100.0),
            _FakeLine(item_code="A", line_cost=50.0),
            _FakeLine(item_code="B", line_cost=30.0),
            _FakeLine(item_code="B", line_cost=20.0),
        ]

    def test_sum_aggregation_matching_lines(self):
        self.get_all_mock.return_value = [{"name": "CT-0001"}]
        self.get_doc_mock.return_value = _FakeTargetDoc(self._lines())
        b = _reuse_binding("sum")
        val = _handle_reuse_formula_result(b, _FakeTargetDoc([], "quotation"), {"row": {"item_code": "A"}})
        self.assertEqual(val, 150.0)

    def test_avg_aggregation(self):
        self.get_all_mock.return_value = [{"name": "CT-0001"}]
        self.get_doc_mock.return_value = _FakeTargetDoc(self._lines())
        b = _reuse_binding("avg")
        val = _handle_reuse_formula_result(b, _FakeTargetDoc([], "quotation"), {"row": {"item_code": "A"}})
        self.assertEqual(val, 75.0)

    def test_min_max_aggregation(self):
        self.get_doc_mock.return_value = _FakeTargetDoc(self._lines())
        cfg = {"document_name": "CT-0001"}
        self.assertEqual(
            _handle_reuse_formula_result(_reuse_binding("min", config=cfg), None, {"row": {"item_code": "B"}}),
            20.0,
        )
        self.assertEqual(
            _handle_reuse_formula_result(_reuse_binding("max", config=cfg), None, {"row": {"item_code": "B"}}),
            30.0,
        )

    def test_first_last_aggregation(self):
        self.get_doc_mock.return_value = _FakeTargetDoc(self._lines())
        cfg = {"document_name": "CT-0001"}
        self.assertEqual(
            _handle_reuse_formula_result(_reuse_binding("first", config=cfg), None, {"row": {"item_code": "B"}}),
            30.0,
        )
        self.assertEqual(
            _handle_reuse_formula_result(_reuse_binding("last", config=cfg), None, {"row": {"item_code": "B"}}),
            20.0,
        )

    def test_no_matching_lines_returns_default(self):
        self.get_all_mock.return_value = [{"name": "CT-0001"}]
        self.get_doc_mock.return_value = _FakeTargetDoc(self._lines())
        b = _reuse_binding("sum")
        val = _handle_reuse_formula_result(b, None, {"row": {"item_code": "ZZZ"}})
        self.assertEqual(val, 0)

    def test_scope_lookup_uses_scope_field_filter(self):
        self.get_all_mock.return_value = [{"name": "CT-0001"}]
        self.get_doc_mock.return_value = _FakeTargetDoc(self._lines())
        b = _reuse_binding("sum")
        doc = _FakeTargetDoc([], "quotation")
        # doc.get('quotation') must return the scope value; _FakeTargetDoc returns default for unknown keys,
        # so pass scope_value directly in config to control resolution.
        cfg = json.loads(b["source_config"])
        cfg["scope_value"] = "QTN-100"
        b["source_config"] = json.dumps(cfg)
        val = _handle_reuse_formula_result(b, doc, {"row": {"item_code": "A"}})
        # assert the locate query used scope_field + scope_value
        filters = self.get_all_mock.call_args.kwargs.get("filters")
        self.assertEqual(filters, [["quotation", "=", "QTN-100"]])
        self.assertEqual(val, 150.0)

    def test_document_name_direct(self):
        self.get_doc_mock.return_value = _FakeTargetDoc(self._lines())
        cfg = {
            "formula_document": "AL Cost Template",
            "document_name": "CT-0009",
            "line_field": "cost_lines",
            "line_match": "{{row.item_code}}",
            "result_field": "line_cost",
            "aggregation": "sum",
            "default_value": 0,
        }
        b = _reuse_binding(config=cfg)
        val = _handle_reuse_formula_result(b, None, {"row": {"item_code": "A"}})
        self.assertEqual(val, 150.0)
        # get_doc must have been called with the document_name
        self.get_doc_mock.assert_called_once_with("AL Cost Template", "CT-0009")

    def test_missing_target_doc_returns_default(self):
        self.get_all_mock.return_value = []
        b = _reuse_binding("sum")
        val = _handle_reuse_formula_result(b, None, {"row": {"item_code": "A"}})
        self.assertEqual(val, 0)

    def test_get_doc_error_returns_default(self):
        self.get_all_mock.return_value = [{"name": "CT-0001"}]
        self.get_doc_mock.side_effect = Exception("doc gone")
        b = _reuse_binding("sum")
        val = _handle_reuse_formula_result(b, None, {"row": {"item_code": "A"}})
        self.assertEqual(val, 0)

    def test_bare_field_line_match(self):
        self.get_all_mock.return_value = [{"name": "CT-0001"}]
        self.get_doc_mock.return_value = _FakeTargetDoc(self._lines())
        cfg = {
            "formula_document": "AL Cost Template",
            "document_name": "CT-0001",
            "line_field": "cost_lines",
            "line_match": "item_code",
            "result_field": "line_cost",
            "aggregation": "sum",
            "default_value": 0,
        }
        b = _reuse_binding(config=cfg)
        val = _handle_reuse_formula_result(b, None, {"row": {"item_code": "B"}})
        self.assertEqual(val, 50.0)


class TestReuseFormulaResultBatch(unittest.TestCase):
    def setUp(self):
        self.get_all_patcher = mock.patch.object(frappe, "get_all")
        self.get_doc_patcher = mock.patch.object(frappe, "get_doc")
        self.log_patcher = mock.patch.object(frappe, "log_error")
        self.get_all_mock = self.get_all_patcher.start()
        self.get_doc_mock = self.get_doc_patcher.start()
        self.log_patcher.start()
        self.addCleanup(self.get_all_patcher.stop)
        self.addCleanup(self.get_doc_patcher.stop)
        self.addCleanup(self.log_patcher.stop)

    def test_batch_reuses_same_doc(self):
        lines = [
            _FakeLine(item_code="A", line_cost=100.0),
            _FakeLine(item_code="A", line_cost=50.0),
            _FakeLine(item_code="B", line_cost=30.0),
        ]
        self.get_all_mock.return_value = [{"name": "CT-0001"}]
        self.get_doc_mock.return_value = _FakeTargetDoc(lines)
        cfg = {
            "formula_document": "AL Cost Template",
            "document_name": "CT-0001",
            "line_field": "cost_lines",
            "line_match": "{{row.item_code}}",
            "result_field": "line_cost",
            "aggregation": "sum",
            "default_value": 0,
        }
        bindings = [
            _reuse_binding(variable_name="cost_a", config=cfg),
            _reuse_binding(variable_name="cost_b", config=cfg),
        ]
        result = _resolve_reuse_formula_result_batch(
            bindings, None, {"row": {"item_code": "A"}}
        )
        # get_doc called once for both bindings (doc reused from cache)
        self.assertEqual(self.get_doc_mock.call_count, 1)
        self.assertEqual(result["cost_a"], 150.0)
        self.assertEqual(result["cost_b"], 150.0)


class TestReuseFormulaResultSchemaAndFingerprint(unittest.TestCase):
    def test_validation_missing_required(self):
        registry = SourceTypeRegistry.get_instance()
        errors = registry.validate_source_config("reuse_formula_result", {"aggregation": "sum"})
        self.assertTrue(any("formula_document" in e for e in errors))
        self.assertTrue(any("result_field" in e for e in errors))

    def test_validation_valid_config(self):
        registry = SourceTypeRegistry.get_instance()
        cfg = {"formula_document": "AL Cost Template", "result_field": "line_cost"}
        self.assertEqual(registry.validate_source_config("reuse_formula_result", cfg), [])

    def test_validation_bad_aggregation(self):
        registry = SourceTypeRegistry.get_instance()
        cfg = {"formula_document": "X", "result_field": "v", "aggregation": "median"}
        errors = registry.validate_source_config("reuse_formula_result", cfg)
        self.assertTrue(any("aggregation" in e for e in errors))

    def test_fingerprint_deterministic(self):
        fn = get_handler("reuse_formula_result").fingerprint_fn
        cfg1 = {"formula_document": "A", "result_field": "v", "aggregation": "sum"}
        cfg2 = {"formula_document": "A", "result_field": "v", "aggregation": "sum"}
        cfg3 = {"formula_document": "A", "result_field": "v", "aggregation": "max"}
        self.assertEqual(fn(cfg1), fn(cfg2))
        self.assertNotEqual(fn(cfg1), fn(cfg3))

    def test_validate_binding_config_integration(self):
        registry = SourceTypeRegistry.get_instance()
        binding = _reuse_binding()
        self.assertEqual(registry.validate_binding_config(binding), [])


class TestPlatformSourceTypesIntegration(unittest.TestCase):
    """resolve_bindings_with_deps end-to-end with the new source types."""

    def test_resolve_bindings_with_matrix_lookup(self):
        with mock.patch.object(frappe, "get_all", return_value=list(MATRIX_ROWS)), \
             mock.patch.object(frappe, "log_error"):
            bindings = [
                {
                    "variable_name": "unit_price",
                    "source_type": "matrix_lookup",
                    "source_config": json.dumps({
                        "doctype": "AL Pricing Matrix",
                        "row_key_field": "size",
                        "col_key_field": "thickness",
                        "value_field": "price",
                        "row_key": "1500",
                        "col_key": "8",
                        "default_value": 0,
                    }),
                    "data_type": "Float",
                },
                {
                    "variable_name": "default_price",
                    "source_type": "matrix_lookup",
                    "source_config": json.dumps({
                        "doctype": "AL Pricing Matrix",
                        "row_key_field": "size",
                        "col_key_field": "thickness",
                        "value_field": "price",
                        "row_key": "NOPE",
                        "col_key": "8",
                        "fallback_row_key": "ANY",
                        "default_value": 0,
                    }),
                    "data_type": "Float",
                },
            ]
            resolved = resolve_bindings_with_deps(bindings, None)
        self.assertEqual(resolved["unit_price"], 220.0)
        self.assertEqual(resolved["default_price"], 210.0)

    def test_resolve_bindings_with_reuse_formula_result(self):
        lines = [
            _FakeLine(item_code="A", line_cost=100.0),
            _FakeLine(item_code="A", line_cost=50.0),
        ]
        with mock.patch.object(frappe, "get_all", return_value=[{"name": "CT-1"}]), \
             mock.patch.object(frappe, "get_doc", return_value=_FakeTargetDoc(lines)), \
             mock.patch.object(frappe, "log_error"):
            bindings = [
                {
                    "variable_name": "reused",
                    "source_type": "reuse_formula_result",
                    "source_config": json.dumps({
                        "formula_document": "AL Cost Template",
                        "scope_field": "quotation",
                        "scope_value": "QTN-1",
                        "line_field": "cost_lines",
                        "line_match": "{{row.item_code}}",
                        "result_field": "line_cost",
                        "aggregation": "sum",
                        "default_value": 0,
                    }),
                    "data_type": "Float",
                },
            ]
            resolved = resolve_bindings_with_deps(bindings, None)
        self.assertEqual(resolved["reused"], 150.0)


if __name__ == "__main__":
    unittest.main()
