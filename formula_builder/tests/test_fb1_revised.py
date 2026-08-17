"""Tests cho FB-1 REVISED (2026-08-16, sau review Owner).

Phạm vi:
  - composite_key_lookup (N-dim): exact, fallback_keys, case_insensitive,
    multiplier_chain, default, auto key_values, schema, fingerprint, batch.
  - aggregate_from_items: rows_source snapshot | child_table | doctype_query,
    key_field/key_value filter (template), aggregate sum/avg/min/max/count,
    key_value rỗng → gom toàn bộ, batch.

Chạy KHÔNG cần site: mock frappe.get_all / get_doc / log_error.
KHÔNG dùng RowCollection / hàm agg UPPERCASE — đã revert theo Owner.
"""

import json
import time
import unittest
from unittest import mock

import frappe

from formula_builder.api.data_source_registry import (
    _data_source_handlers,
    _handle_aggregate_from_items,
    _handle_composite_key_lookup,
    _resolve_aggregate_from_items_batch,
    _resolve_composite_key_lookup_batch,
    get_handler,
    is_batchable,
)
from formula_builder.api.source_type_registry import SourceTypeRegistry
from formula_builder.formula_utils.engine_public import FormulaEngine

# ── Fixtures ──────────────────────────────────────────────────────────────

MATRIX_ROWS = [
    {"item_code": "AL-01", "color": "BK", "thickness": "1.2", "surface": "S1", "price": 100.0},
    {"item_code": "AL-01", "color": "WH", "thickness": "1.2", "surface": "S1", "price": 110.0},
    {"item_code": "AL-01", "color": "BK", "thickness": "2.0", "surface": "S1", "price": 130.0},
    {"item_code": "AL-01", "color": "BK", "thickness": "ANY", "surface": "ANY", "price": 95.0},
    {"item_code": "AL-02", "color": "ANY", "thickness": "ANY", "surface": "ANY", "price": 60.0},
]

COST_LINES = [
    {"cost_bucket": "PHU_KIEN", "line_total": 10, "qty": 2, "item_code": "PK-1"},
    {"cost_bucket": "NVL", "line_total": 20, "qty": 1, "item_code": "VL-1"},
    {"cost_bucket": "PHU_KIEN", "line_total": 30, "qty": 3, "item_code": "PK-2"},
]


class _FakeDoc:
    def __init__(self, items=None, **kw):
        self.items = items
        self.__dict__.update(kw)

    def get(self, k, default=None):
        return getattr(self, k, default)


def _composite_binding(**over):
    cfg = {
        "doctype": "AL Pricing",
        "value_field": "price",
        "key_fields": ["item_code", "color", "thickness"],
        "default_value": 0,
    }
    cfg.update(over.get("config", {}))
    b = {
        "variable_name": over.get("variable_name", "price"),
        "source_type": "composite_key_lookup",
        "source_config": json.dumps(cfg),
        "data_type": over.get("data_type", "Float"),
    }
    if "default_value" in over and "config" not in over:
        b["default_value"] = over["default_value"]
    return b


def _afb(cfg, **over):
    b = {
        "variable_name": over.get("variable_name", "agg"),
        "source_type": "aggregate_from_items",
        "source_config": json.dumps(cfg),
        "data_type": over.get("data_type", "Float"),
    }
    if "default_value" in over:
        b["default_value"] = over["default_value"]
    return b


def _run_formula(formula, ctx):
    eng = FormulaEngine(formulas=[{"name": "res", "formula": formula}], on_error="null")
    return eng.calculate(ctx).get("res")


# ═══════════════════════════════════════════════════════════════════════════
# 1. composite_key_lookup — registration
# ═══════════════════════════════════════════════════════════════════════════


class TestCompositeKeyLookupRegistration(unittest.TestCase):
    def test_handler_registered(self):
        self.assertIn("composite_key_lookup", _data_source_handlers)
        self.assertIsNotNone(get_handler("composite_key_lookup"))
        self.assertTrue(is_batchable("composite_key_lookup"))

    def test_in_central_registry(self):
        registry = SourceTypeRegistry.get_instance()
        self.assertTrue(registry.has("composite_key_lookup"))
        schema = registry.get_config_schema("composite_key_lookup")
        self.assertEqual(schema["required"], ["doctype", "value_field"])
        self.assertIn("key_fields", schema["properties"])
        self.assertIn("fallback_keys", schema["properties"])
        self.assertIn("multipliers", schema["properties"])

    def test_backward_compat_matrix_lookup_still_present(self):
        self.assertIn("matrix_lookup", _data_source_handlers)
        self.assertTrue(is_batchable("matrix_lookup"))

    def test_no_collection_types_re_registered(self):
        # RowCollection + collection source types đã revert theo Owner
        registry = SourceTypeRegistry.get_instance()
        for st in ("child_table_rows", "doctype_rows", "matrix_grid", "aggregate"):
            self.assertFalse(registry.has(st), f"{st} phải bị revert")


# ═══════════════════════════════════════════════════════════════════════════
# 2. composite_key_lookup — resolve
# ═══════════════════════════════════════════════════════════════════════════


class TestCompositeKeyLookupResolve(unittest.TestCase):
    def setUp(self):
        self.ga = mock.patch.object(frappe, "get_all", return_value=list(MATRIX_ROWS))
        self.log = mock.patch.object(frappe, "log_error")
        self.ga.start()
        self.log.start()
        self.addCleanup(self.ga.stop)
        self.addCleanup(self.log.stop)

    def _row(self, **over):
        r = {"item_code": "AL-01", "color": "BK", "thickness": "1.2", "surface": "S1"}
        r.update(over)
        return r

    def test_exact_match_all_dims(self):
        b = _composite_binding()
        self.assertEqual(_handle_composite_key_lookup(b, None, {"row": self._row()}), 100.0)

    def test_auto_key_values_maps_from_row(self):
        b = _composite_binding()
        self.assertEqual(_handle_composite_key_lookup(b, None, {"row": self._row()}), 100.0)

    def test_explicit_key_values_override_auto(self):
        b = _composite_binding(config={"key_values": ["{{row.item_code}}", "WH", "1.2"]})
        self.assertEqual(_handle_composite_key_lookup(b, None, {"row": self._row()}), 110.0)

    def test_no_match_returns_default(self):
        b = _composite_binding(config={"default_value": 999})
        row = self._row(item_code="AL-99", color="XX", thickness="9.9")
        self.assertEqual(_handle_composite_key_lookup(b, None, {"row": row}), 999)

    def test_fallback_keys_drops_dimensions(self):
        b = _composite_binding(config={"fallback_keys": [["item_code", "color"], ["item_code"]]})
        row = self._row(thickness="9.9")  # không khớp exact (thickness)
        # fallback ['item_code','color'] → AL-01/BK/ANY/ANY (thickness ANY) → 95
        self.assertEqual(_handle_composite_key_lookup(b, None, {"row": row}), 95.0)

    def test_fallback_only_item_code(self):
        b = _composite_binding(config={"fallback_keys": [["item_code"]]})
        row = self._row(color="XX", thickness="9.9")
        # chỉ khớp item_code AL-01 — nhưng fixture không có row AL-01/ANY/ANY/ANY
        # → default 0
        self.assertEqual(_handle_composite_key_lookup(b, None, {"row": row}), 0)

    def test_case_insensitive_mode(self):
        b = _composite_binding(config={"match_mode": "case_insensitive"})
        row = self._row(color="bk", item_code="al-01")
        self.assertEqual(_handle_composite_key_lookup(b, None, {"row": row}), 100.0)

    def test_multiplier_chain_applies_multipliers(self):
        prices = [{"item_code": "AL-01", "color": "ANY", "thickness": "ANY",
                   "surface": "ANY", "price": 90.0}]

        def fake_get_all(doctype, filters=None, fields=None, **kw):
            if doctype == "AL Pricing":
                return prices
            if doctype == "AL Color Mult":
                return [{"multiplier": 1.5}]
            return []

        with mock.patch.object(frappe, "get_all", side_effect=fake_get_all):
            b = _composite_binding(config={
                "match_mode": "multiplier_chain",
                "fallback_keys": [["item_code"]],
                "multipliers": {
                    "color": {"doctype": "AL Color Mult", "match_field": "color",
                              "value_field": "multiplier"},
                },
            })
            row = self._row(color="BK", thickness="9.9")
            # base 90 × 1.5 (color multiplier) = 135
            self.assertEqual(_handle_composite_key_lookup(b, None, {"row": row}), 135.0)


# ═══════════════════════════════════════════════════════════════════════════
# 3. composite_key_lookup — schema + fingerprint + batch
# ═══════════════════════════════════════════════════════════════════════════


class TestCompositeKeyLookupSchemaAndFingerprint(unittest.TestCase):
    def test_schema_validation_missing_required(self):
        registry = SourceTypeRegistry.get_instance()
        errors = registry.validate_source_config("composite_key_lookup", {"doctype": "X"})
        self.assertTrue(any("value_field" in e for e in errors))

    def test_schema_validation_valid(self):
        registry = SourceTypeRegistry.get_instance()
        cfg = {"doctype": "X", "value_field": "price", "key_fields": ["a", "b"]}
        errors = registry.validate_source_config("composite_key_lookup", cfg)
        self.assertEqual(errors, [])

    def test_schema_bad_match_mode(self):
        registry = SourceTypeRegistry.get_instance()
        cfg = {"doctype": "X", "value_field": "p", "match_mode": "evil"}
        errors = registry.validate_source_config("composite_key_lookup", cfg)
        self.assertTrue(any("match_mode" in e for e in errors))

    def test_fingerprint_deterministic(self):
        fn = get_handler("composite_key_lookup").fingerprint_fn
        cfg = {"doctype": "AL Pricing", "value_field": "price",
               "key_fields": ["a", "b"], "filters": [["x", "=", "y"]]}
        self.assertEqual(fn(cfg), fn(cfg))
        cfg2 = dict(cfg, value_field="cost")
        self.assertNotEqual(fn(cfg), fn(cfg2))


class TestCompositeKeyLookupBatch(unittest.TestCase):
    def test_batch_one_query_for_group(self):
        b1 = _composite_binding(variable_name="p1")
        b2 = _composite_binding(variable_name="p2")
        row = {"item_code": "AL-01", "color": "BK", "thickness": "1.2"}
        with mock.patch.object(frappe, "get_all", return_value=list(MATRIX_ROWS)) as ga, \
                mock.patch.object(frappe, "log_error"):
            res = _resolve_composite_key_lookup_batch([b1, b2], None, {"row": row})
        self.assertEqual(res["p1"], 100.0)
        self.assertEqual(res["p2"], 100.0)
        self.assertEqual(ga.call_count, 1)

    def test_batch_missing_rows_default(self):
        b = _composite_binding(variable_name="p", config={"default_value": 77})
        with mock.patch.object(frappe, "get_all", return_value=[]):
            res = _resolve_composite_key_lookup_batch([b], None, {"row": {}})
        self.assertEqual(res["p"], 77)


# ═══════════════════════════════════════════════════════════════════════════
# 4. aggregate_from_items — registration + config
# ═══════════════════════════════════════════════════════════════════════════


class TestAggregateFromItemsRegistration(unittest.TestCase):
    def test_handler_registered(self):
        self.assertIn("aggregate_from_items", _data_source_handlers)
        self.assertIsNotNone(get_handler("aggregate_from_items"))
        self.assertTrue(is_batchable("aggregate_from_items"))

    def test_in_central_registry(self):
        registry = SourceTypeRegistry.get_instance()
        self.assertTrue(registry.has("aggregate_from_items"))
        schema = registry.get_config_schema("aggregate_from_items")
        # value_field required (trừ aggregate=count qua required_unless)
        self.assertEqual(
            schema["required"], ["rows_source", "aggregate", "value_field"]
        )
        self.assertEqual(
            schema["required_unless"]["value_field"], {"if": "aggregate", "equals": "count"}
        )
        props = schema["properties"]
        for k in ("snapshot_doctype", "child_table_field", "doctype", "filters",
                  "key_field", "key_value", "value_field", "default_value"):
            self.assertIn(k, props)

    def test_schema_value_field_skipped_for_count(self):
        # aggregate=count không cần value_field → required_unless cho qua
        registry = SourceTypeRegistry.get_instance()
        errors = registry.validate_source_config(
            "aggregate_from_items",
            {"rows_source": "child_table", "aggregate": "count"},
        )
        self.assertFalse(any("value_field" in e for e in errors))

    def test_schema_value_field_required_for_sum(self):
        # aggregate=sum không có value_field → báo lỗi required
        registry = SourceTypeRegistry.get_instance()
        errors = registry.validate_source_config(
            "aggregate_from_items",
            {"rows_source": "child_table", "aggregate": "sum"},
        )
        self.assertTrue(any("value_field" in e for e in errors))

    def test_schema_bad_rows_source(self):
        registry = SourceTypeRegistry.get_instance()
        errors = registry.validate_source_config(
            "aggregate_from_items", {"rows_source": "evil", "aggregate": "sum"}
        )
        self.assertTrue(any("rows_source" in e for e in errors))

    def test_schema_bad_aggregate(self):
        registry = SourceTypeRegistry.get_instance()
        errors = registry.validate_source_config(
            "aggregate_from_items", {"rows_source": "child_table", "aggregate": "sums"}
        )
        self.assertTrue(any("aggregate" in e for e in errors))


# ═══════════════════════════════════════════════════════════════════════════
# 5. aggregate_from_items — child_table
# ═══════════════════════════════════════════════════════════════════════════


class TestAggregateFromItemsChildTable(unittest.TestCase):
    def setUp(self):
        self.log = mock.patch.object(frappe, "log_error")
        self.log.start()
        self.addCleanup(self.log.stop)
        self.doc = _FakeDoc(items=COST_LINES)

    def _cfg(self, **over):
        cfg = {
            "rows_source": "child_table",
            "child_table_field": "items",
            "key_field": "cost_bucket",
            "value_field": "line_total",
            "aggregate": "sum",
        }
        cfg.update(over)
        return cfg

    def test_sum_by_key_template(self):
        cfg = self._cfg(key_value="{{resolved.bucket_code}}")
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {"bucket_code": "PHU_KIEN"}), 40.0)

    def test_sum_other_key(self):
        cfg = self._cfg(key_value="NVL")
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {}), 20.0)

    def test_sum_all_when_key_value_empty(self):
        cfg = self._cfg(key_value="")
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {}), 60.0)

    def test_count(self):
        cfg = self._cfg(key_value="{{resolved.bucket_code}}", aggregate="count")
        b = _afb(cfg, data_type="Int")
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {"bucket_code": "PHU_KIEN"}), 2)

    def test_avg(self):
        cfg = self._cfg(key_value="PHU_KIEN", aggregate="avg")
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {}), 20.0)

    def test_min_max(self):
        cfg = self._cfg(key_value="PHU_KIEN", aggregate="min")
        self.assertEqual(_handle_aggregate_from_items(_afb(cfg), self.doc, {}), 10.0)
        cfg = self._cfg(key_value="PHU_KIEN", aggregate="max")
        self.assertEqual(_handle_aggregate_from_items(_afb(cfg), self.doc, {}), 30.0)

    def test_no_match_default(self):
        cfg = self._cfg(key_value="XXX")
        b = _afb(cfg, default_value=0)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {}), 0)

    def test_no_doc_returns_default(self):
        cfg = self._cfg(key_value="PHU_KIEN")
        b = _afb(cfg, default_value=0)
        self.assertEqual(_handle_aggregate_from_items(b, None, {}), 0)

    def test_multi_field_filter_and_key(self):
        # filters multi-field (Frappe-style) kết hợp AND với key_field/key_value
        cfg = self._cfg(
            filters=[["qty", ">", 1], ["item_code", "=", "{{resolved.item}}"]],
            key_value="PHU_KIEN",
        )
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {"item": "PK-2"}), 30.0)

    def test_multi_field_filter_no_key(self):
        # filters multi-field, không có key_field → sum toàn bộ row thỏa filter
        cfg = self._cfg(key_value="", filters=[["qty", ">", 1]])
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {}), 40.0)

    def test_multi_field_filter_in_op(self):
        # filter 'in' — giữ các item_code ∈ {PK-1, VL-1}
        cfg = self._cfg(key_value="", filters=[["item_code", "in", ["PK-1", "VL-1"]]])
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {}), 30.0)


class TestAggregateFromItemsSumFieldAlias(unittest.TestCase):
    """Alias `sum_field` → `value_field` (backward-compat AL Cost Bucket cũ).

    AL Cost Bucket source_config cũ dùng `{"sum_field": "line_total", ...}`.
    FB aggregate_from_items chuẩn dùng `value_field` — alias chỉ để nhận config cũ,
    KHÔNG thay đổi schema chuẩn (`value_field` vẫn required, trừ aggregate=count).
    """

    def setUp(self):
        self.log = mock.patch.object(frappe, "log_error")
        self.log.start()
        self.addCleanup(self.log.stop)
        self.doc = _FakeDoc(items=COST_LINES)

    def _cfg(self, **over):
        cfg = {
            "rows_source": "child_table",
            "child_table_field": "items",
            "key_field": "cost_bucket",
            "sum_field": "line_total",
            "aggregate": "sum",
        }
        cfg.update(over)
        return cfg

    def test_sum_uses_sum_field_alias(self):
        # config cũ AL: chỉ có sum_field, không có value_field → sum vẫn đúng
        cfg = self._cfg(key_value="PHU_KIEN")
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {}), 40.0)

    def test_sum_field_alias_with_template_key(self):
        cfg = self._cfg(key_value="{{resolved.bucket_code}}")
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {"bucket_code": "PHU_KIEN"}), 40.0)

    def test_sum_field_alias_count(self):
        # aggregate=count không cần value_field — sum_field bị bỏ qua, count vẫn đúng
        cfg = self._cfg(key_value="PHU_KIEN", aggregate="count")
        b = _afb(cfg, data_type="Int")
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {}), 2)

    def test_value_field_precedence_over_sum_field(self):
        # cả hai cùng tồn tại → value_field thắng (ưu tiên config chuẩn)
        cfg = self._cfg(key_value="PHU_KIEN", value_field="qty")
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, self.doc, {}), 5.0)

    def test_sum_field_alias_batch(self):
        # batch path cũng đọc sum_field alias
        bindings = [
            _afb(self._cfg(key_value="PHU_KIEN"), variable_name="agg_a"),
            _afb(self._cfg(key_value="NVL"), variable_name="agg_b"),
        ]
        res = _resolve_aggregate_from_items_batch(bindings, self.doc, {})
        self.assertEqual(res["agg_a"], 40.0)
        self.assertEqual(res["agg_b"], 20.0)

    def test_fingerprint_resolves_alias(self):
        # fingerprint phải dùng giá trị đã resolve (value_field or sum_field)
        # → config sum_field tương đương config value_field → cùng fingerprint (không miss cache).
        fn = get_handler("aggregate_from_items").fingerprint_fn
        cfg_vf = {"rows_source": "child_table", "child_table_field": "items",
                  "key_field": "cost_bucket", "key_value": "NVL",
                  "value_field": "line_total", "aggregate": "sum"}
        cfg_sf = dict(cfg_vf)
        cfg_sf.pop("value_field")
        cfg_sf["sum_field"] = "line_total"
        self.assertEqual(fn(cfg_sf), fn(cfg_vf))

    def test_fingerprint_distinct_field_value(self):
        # sum_field khác field → fingerprint khác (tránh cache chéo)
        fn = get_handler("aggregate_from_items").fingerprint_fn
        cfg_sf = {"rows_source": "child_table", "child_table_field": "items",
                  "key_field": "cost_bucket", "sum_field": "line_total", "aggregate": "sum"}
        cfg_sf2 = dict(cfg_sf, sum_field="qty")
        self.assertNotEqual(fn(cfg_sf), fn(cfg_sf2))


# ═══════════════════════════════════════════════════════════════════════════
# 6. aggregate_from_items — doctype_query + snapshot
# ═══════════════════════════════════════════════════════════════════════════


class TestAggregateFromItemsDoctypeQuery(unittest.TestCase):
    def test_sum_by_key(self):
        cfg = {
            "rows_source": "doctype_query",
            "doctype": "BOM Item",
            "filters": [["parent", "=", "{doc.name}"]],
            "key_field": "cost_bucket",
            "key_value": "NVL",
            "value_field": "line_total",
            "aggregate": "sum",
        }
        b = _afb(cfg)
        doc = _FakeDoc(name="BOM-1")
        with mock.patch.object(frappe, "get_all",
                               return_value=[{"cost_bucket": "NVL", "line_total": 7},
                                             {"cost_bucket": "PK", "line_total": 3}]):
            self.assertEqual(_handle_aggregate_from_items(b, doc, {}), 7.0)

    def test_resolved_filter_value(self):
        cfg = {
            "rows_source": "doctype_query",
            "doctype": "BOM Item",
            "filters": [["company", "=", "{resolved.company}"]],
            "key_field": "",
            "value_field": "line_total",
            "aggregate": "sum",
        }
        b = _afb(cfg)
        with mock.patch.object(frappe, "get_all",
                               return_value=[{"line_total": 1}, {"line_total": 2}]) as ga:
            self.assertEqual(_handle_aggregate_from_items(b, None, {"company": "NxCom"}), 3.0)
        # Kiểm tra filter đã resolve template {resolved.company}
        filters_passed = ga.call_args.kwargs.get("filters") or ga.call_args[0][1]
        self.assertIn(["company", "=", "NxCom"], filters_passed)


class TestAggregateFromItemsSnapshot(unittest.TestCase):
    def setUp(self):
        self.log = mock.patch.object(frappe, "log_error")
        self.log.start()
        self.addCleanup(self.log.stop)
        self.snap_json = json.dumps({
            "items": [
                {"cost_bucket": "A", "line_total": 5},
                {"cost_bucket": "B", "line_total": 9},
                {"cost_bucket": "A", "line_total": 1},
            ]
        })

    def test_sum_by_key_from_snapshot(self):
        class SnapDoc:
            def __init__(self, payload):
                self.bom_set_snapshot = payload

            def get(self, k, d=None):
                return getattr(self, k, d)

        cfg = {
            "rows_source": "snapshot",
            "snapshot_doctype": "AL BOM Version",
            "snapshot_name": "SNAP-1",
            "snapshot_field": "bom_set_snapshot",
            "rows_path": "items",
            "key_field": "cost_bucket",
            "key_value": "A",
            "value_field": "line_total",
            "aggregate": "sum",
        }
        b = _afb(cfg)
        with mock.patch.object(frappe, "get_doc", return_value=SnapDoc(self.snap_json)):
            self.assertEqual(_handle_aggregate_from_items(b, None, {}), 6.0)

    def test_missing_snapshot_returns_default(self):
        cfg = {
            "rows_source": "snapshot",
            "snapshot_doctype": "AL BOM Version",
            "snapshot_name": "SNAP-NONE",
            "key_field": "cost_bucket",
            "key_value": "A",
            "value_field": "line_total",
            "aggregate": "sum",
        }
        b = _afb(cfg, default_value=0)
        with mock.patch.object(frappe, "get_doc", side_effect=Exception("not found")):
            self.assertEqual(_handle_aggregate_from_items(b, None, {}), 0)

    def test_snapshot_name_template_from_doc(self):
        cfg = {
            "rows_source": "snapshot",
            "snapshot_doctype": "AL BOM Version",
            "snapshot_name": "{{doc.snapshot_ref}}",
            "snapshot_field": "bom_set_snapshot",
            "rows_path": "items",
            "key_field": "cost_bucket",
            "key_value": "B",
            "value_field": "line_total",
            "aggregate": "sum",
        }
        b = _afb(cfg)
        doc = _FakeDoc(snapshot_ref="SNAP-9")

        class SnapDoc:
            def __init__(self, payload):
                self.bom_set_snapshot = payload

            def get(self, k, d=None):
                return getattr(self, k, d)

        with mock.patch.object(frappe, "get_doc", return_value=SnapDoc(self.snap_json)) as gd:
            self.assertEqual(_handle_aggregate_from_items(b, doc, {}), 9.0)
            self.assertEqual(gd.call_args[0], ("AL BOM Version", "SNAP-9"))

    def test_snapshot_multi_field_filter(self):
        class SnapDoc:
            def __init__(self, payload):
                self.bom_set_snapshot = payload

            def get(self, k, d=None):
                return getattr(self, k, d)

        # snapshot + multi-field filter: cost_bucket=A AND line_total >= 5 → chỉ A/5
        cfg = {
            "rows_source": "snapshot",
            "snapshot_doctype": "AL BOM Version",
            "snapshot_name": "SNAP-1",
            "snapshot_field": "bom_set_snapshot",
            "rows_path": "items",
            "key_field": "cost_bucket",
            "key_value": "A",
            "value_field": "line_total",
            "aggregate": "sum",
            "filters": [["line_total", ">=", 5]],
        }
        b = _afb(cfg)
        with mock.patch.object(frappe, "get_doc", return_value=SnapDoc(self.snap_json)):
            self.assertEqual(_handle_aggregate_from_items(b, None, {}), 5.0)


# ═══════════════════════════════════════════════════════════════════════════
# 6b. aggregate_from_items — resolved (rows từ context — AL B5 aggregation)
# ═══════════════════════════════════════════════════════════════════════════


class TestAggregateFromItemsResolved(unittest.TestCase):
    """rows_source='resolved' — rows là list dict đã resolve trong context.

    Dùng cho AL B5: gom line_total theo cost_bucket từ bom_result (đã tính ở
    B4) đưa vào pre_resolved={'bom_lines': [...]} của BatchBindingResolver.
    """

    def setUp(self):
        self.log = mock.patch.object(frappe, "log_error")
        self.log.start()
        self.addCleanup(self.log.stop)

    def _cfg(self, **over):
        cfg = {
            "rows_source": "resolved",
            "rows_var": "bom_lines",
            "key_field": "cost_bucket",
            "value_field": "line_total",
            "aggregate": "sum",
        }
        cfg.update(over)
        return cfg

    def test_sum_by_key(self):
        cfg = self._cfg(key_value="PHU_KIEN")
        b = _afb(cfg)
        res = _handle_aggregate_from_items(b, None, {"bom_lines": COST_LINES})
        self.assertEqual(res, 40.0)

    def test_sum_other_key(self):
        cfg = self._cfg(key_value="NVL")
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, None, {"bom_lines": COST_LINES}), 20.0)

    def test_sum_all_when_key_empty(self):
        cfg = self._cfg(key_value="")
        b = _afb(cfg)
        self.assertEqual(_handle_aggregate_from_items(b, None, {"bom_lines": COST_LINES}), 60.0)

    def test_key_value_template(self):
        # key_value dùng {{resolved.bucket_code}} — giống binding B5 per-bucket
        cfg = self._cfg(key_value="{{resolved.bucket_code}}")
        b = _afb(cfg)
        self.assertEqual(
            _handle_aggregate_from_items(b, None, {"bom_lines": COST_LINES, "bucket_code": "NVL"}),
            20.0,
        )

    def test_missing_rows_var_returns_default(self):
        # không có bom_lines trong context → default (rows source lỗi)
        cfg = self._cfg(key_value="NVL")
        b = _afb(cfg, default_value=0)
        self.assertEqual(_handle_aggregate_from_items(b, None, {}), 0)

    def test_non_list_rows_var_returns_default(self):
        cfg = self._cfg(key_value="NVL")
        b = _afb(cfg, default_value=0)
        self.assertEqual(_handle_aggregate_from_items(b, None, {"bom_lines": "not-a-list"}), 0)

    def test_count(self):
        cfg = self._cfg(key_value="{{resolved.bucket_code}}", aggregate="count")
        b = _afb(cfg, data_type="Int")
        self.assertEqual(
            _handle_aggregate_from_items(b, None, {"bom_lines": COST_LINES, "bucket_code": "PHU_KIEN"}),
            2,
        )

    def test_batch_shared_rows(self):
        # batch path: shared rows từ rows_var — mỗi binding resolve key riêng
        b1 = _afb(self._cfg(key_value="PHU_KIEN"), variable_name="pk")
        b2 = _afb(self._cfg(key_value="NVL"), variable_name="nvl")
        res = _resolve_aggregate_from_items_batch([b1, b2], None, {"bom_lines": COST_LINES})
        self.assertEqual(res["pk"], 40.0)
        self.assertEqual(res["nvl"], 20.0)

    def test_schema_allows_resolved_and_rows_var(self):
        registry = SourceTypeRegistry.get_instance()
        errors = registry.validate_source_config(
            "aggregate_from_items",
            {"rows_source": "resolved", "rows_var": "bom_lines", "key_field": "cost_bucket",
             "value_field": "line_total", "aggregate": "sum"},
        )
        self.assertEqual(errors, [])
        schema = registry.get_config_schema("aggregate_from_items")
        self.assertIn("resolved", schema["properties"]["rows_source"]["enum"])
        self.assertIn("rows_var", schema["properties"])

    def test_fingerprint_includes_rows_var(self):
        fn = get_handler("aggregate_from_items").fingerprint_fn
        cfg_a = {"rows_source": "resolved", "rows_var": "bom_lines",
                 "key_field": "cost_bucket", "value_field": "line_total", "aggregate": "sum"}
        cfg_b = dict(cfg_a, rows_var="other_lines")
        self.assertNotEqual(fn(cfg_a), fn(cfg_b))


# ═══════════════════════════════════════════════════════════════════════════
# 7. aggregate_from_items — batch
# ═══════════════════════════════════════════════════════════════════════════


class TestAggregateFromItemsBatch(unittest.TestCase):
    def setUp(self):
        self.log = mock.patch.object(frappe, "log_error")
        self.log.start()
        self.addCleanup(self.log.stop)
        self.doc = _FakeDoc(items=COST_LINES)

    def test_batch_shared_rows_source(self):
        cfg = {
            "rows_source": "child_table",
            "child_table_field": "items",
            "key_field": "cost_bucket",
            "key_value": "{{resolved.bucket_code}}",
            "value_field": "line_total",
            "aggregate": "sum",
        }
        b1 = _afb(cfg, variable_name="agg1")
        b2 = _afb(cfg, variable_name="agg2")
        res = _resolve_aggregate_from_items_batch([b1, b2], self.doc, {"bucket_code": "PHU_KIEN"})
        self.assertEqual(res["agg1"], 40.0)
        self.assertEqual(res["agg2"], 40.0)

    def test_batch_per_binding_key_value(self):
        cfg = {
            "rows_source": "child_table",
            "child_table_field": "items",
            "key_field": "cost_bucket",
            "key_value": "{{resolved.bucket_code}}",
            "value_field": "line_total",
            "aggregate": "sum",
        }
        b1 = _afb(cfg, variable_name="pk")
        b2 = _afb(cfg, variable_name="nvl")
        # Mỗi binding có resolved khác nhau (context per binding) — cùng doc
        res = _resolve_aggregate_from_items_batch([b1, b2], self.doc, {"bucket_code": "PHU_KIEN"})
        self.assertEqual(res["pk"], 40.0)
        res2 = _resolve_aggregate_from_items_batch([b1], self.doc, {"bucket_code": "NVL"})
        self.assertEqual(res2["pk"], 20.0)


# ═══════════════════════════════════════════════════════════════════════════
# 8. Benchmark smoke — eval throughput không suy giảm
# ═══════════════════════════════════════════════════════════════════════════


class TestBenchmarkSmoke(unittest.TestCase):
    def test_eval_throughput_reasonable(self):
        formula = "a + b * c - d / e + IF(a > 0, a * 2, b)"
        eng = FormulaEngine(formulas=[{"name": "res", "formula": formula}], on_error="null")
        ctx = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 2}
        for _ in range(200):
            eng.calculate(ctx)
        n = 2000
        t0 = time.perf_counter()
        for _ in range(n):
            eng.calculate(ctx)
        dt = time.perf_counter() - t0
        throughput = (n * 8) / dt
        self.assertGreater(throughput, 100_000, f"throughput too low: {throughput:.0f} nodes/s")
        print(f"  [benchmark] {throughput:.0f} nodes/s (baseline 2.0-2.5M)")

    def test_legacy_sumif_still_works(self):
        # Xác nhận không revert nhầm hàm agg lowercase sẵn có (dispatch yêu cầu).
        # Formula DSL không hỗ trợ kwargs → dùng vị trí. filter_array trên
        # list[dict] với key positional là collection-agg sẵn có còn hoạt động.
        from formula_builder.formula_utils.funcs.registry import BASE_FUNCS
        self.assertIn("sumif", BASE_FUNCS)
        self.assertIn("group_sum", BASE_FUNCS)
        rows = _run_formula(
            "filter_array(items, '>', 10, 'line_total')", {"items": COST_LINES}
        )
        self.assertEqual(rows, [
            {"cost_bucket": "NVL", "line_total": 20, "qty": 1, "item_code": "VL-1"},
            {"cost_bucket": "PHU_KIEN", "line_total": 30, "qty": 3, "item_code": "PK-2"},
        ])


if __name__ == "__main__":
    unittest.main()
