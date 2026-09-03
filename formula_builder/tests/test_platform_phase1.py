"""Tests Phase 1 (A1–A5 platform) — pure-Python, KHÔNG cần site/DB.

Chạy:  python -m unittest formula_builder.tests.test_platform_phase1

Coverage:
    A1/A2 — registry metadata (list_source_types) dùng cho Autocomplete + schema editor.
    A3    — _execute_source_test / test_data_source (doc=None path, không cần DB).
    A4    — BatchBindingResolver.preview_groups: grouping + strategy classification.
    A5    — binding_scope: scope-match semantics thống nhất (global/doctype/field).

Lưu ý import order: phải import data_source_registry trước để module-level
`_register_all_to_central_registry()` nạp 17 built-in vào central SourceTypeRegistry
(import source_type_registry một mình → registry rỗng).
"""

import json
import unittest

# 1) Nạp built-in source types (module-level registration chạy khi import này).
import formula_builder.api.data_source_registry as dsr  # noqa: F401

from formula_builder.api.source_type_registry import (
    SourceTypeRegistry,
    list_source_types,
    test_data_source,
    validate_binding_source_config,
)
from formula_builder.api.batch_binding_resolver import (
    BatchBindingResolver,
    _get_batch_handler,
    _is_batchable,
)
from formula_builder.api.binding_scope import (
    binding_matches_any_doctype,
    binding_matches_scope,
    filter_bindings_for_scope,
    filter_bindings_for_scope_multi,
)

from formula_builder.api.data_source_registry import (
    batchable,
    register_source,
)


# ── Fixture: handler batchable KHÔNG có resolve_batch (để test strategy N+1) ──
@register_source("fb_phase1_batch_no_resolve")
@batchable(fingerprint_fn=lambda cfg: cfg.get("group", "default"))
def _handle_fb_phase1_no_batch(binding, doc, resolved_so_far):
    cfg = json.loads(binding.get("source_config", "{}"))
    return cfg.get("value")


# ── Fixture: handler KHÔNG batchable ────────────────────────────────────────
@register_source("fb_phase1_plain")
def _handle_fb_phase1_plain(binding, doc, resolved_so_far):
    cfg = json.loads(binding.get("source_config", "{}"))
    return cfg.get("value")


def _b(name, source_type, cfg=None, batch_group="", doctype="Quotation Item", field="total"):
    return {
        "variable_name": name,
        "variable_label": name,
        "source_type": source_type,
        "source_config": json.dumps(cfg or {}, ensure_ascii=False),
        "batch_group": batch_group,
        "applies_to_doctype": doctype,
        "applies_to_field": field,
    }


# ═══════════════════════════════════════════════════════════════════════════
# A1/A2 — Registry metadata contract
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistryMetadata(unittest.TestCase):
    CANONICAL_17 = {
        "constant", "child_table_aggregate", "linked_doctype_field", "whole_doctype",
        "doctype_query", "matrix_lookup", "reuse_formula_result",
        "composite_key_lookup", "aggregate_from_items", "pipeline", "global_default",
        "session_variable", "custom_function", "dynamic_link", "computed",
        "conditional", "fallback_chain",
    }

    def test_all_builtin_registered(self):
        names = {d["source_type"] for d in list_source_types()}
        self.assertEqual(len(self.CANONICAL_17), 17)
        missing = self.CANONICAL_17 - names
        self.assertEqual(missing, set(), f"built-in source types thiếu: {missing}")

    def test_entry_has_admin_fields(self):
        meta = {d["source_type"]: d for d in list_source_types()}
        for st in ("constant", "doctype_query", "aggregate_from_items", "composite_key_lookup"):
            self.assertIn(st, meta)
            d = meta[st]
            for key in ("source_type", "label", "description", "config_schema",
                        "app", "batchable", "supports_transform"):
                self.assertIn(key, d, f"{st} thiếu {key}")

    def test_batchable_flags_match_resolver(self):
        # Batchable theo resolver (handler attr) phải khớp metadata registry.
        # Chỉ kiểm tra 17 built-in — fixture test tạo thêm có thể chỉ nằm một phía
        # (legacy dict hoặc central registry), không thuộc contract parity này.
        meta = {d["source_type"]: d for d in list_source_types()}
        for st in self.CANONICAL_17:
            d = meta[st]
            self.assertEqual(
                _is_batchable(st), d["batchable"],
                f"{st}: _is_batchable != registry.batchable",
            )

    def test_legacy_registry_has_batch_fns(self):
        # Batchable built-in có resolve_batch → strategy resolve_batch khi preview.
        for st in ("linked_doctype_field", "whole_doctype", "doctype_query",
                   "matrix_lookup", "reuse_formula_result", "composite_key_lookup",
                   "aggregate_from_items"):
            self.assertIsNotNone(_get_batch_handler(st), f"{st} thiếu resolve_batch")


# ═══════════════════════════════════════════════════════════════════════════
# A2 — required_unless validation (không cần DB)
# ═══════════════════════════════════════════════════════════════════════════

class TestRequiredUnless(unittest.TestCase):
    def test_aggregate_count_not_need_value_field(self):
        ok = validate_binding_source_config(
            "aggregate_from_items",
            json.dumps({"rows_source": "child_table", "child_table_field": "items",
                        "aggregate": "count"}),
        )
        self.assertTrue(ok["valid"], ok)

    def test_aggregate_sum_requires_value_field(self):
        bad = validate_binding_source_config(
            "aggregate_from_items",
            json.dumps({"rows_source": "child_table", "child_table_field": "items",
                        "aggregate": "sum"}),
        )
        self.assertFalse(bad["valid"])
        self.assertTrue(any("value_field" in e for e in bad["errors"]))


# ═══════════════════════════════════════════════════════════════════════════
# A3 — test_data_source doc=None path (source không cần doc context)
# ═══════════════════════════════════════════════════════════════════════════

class TestDataSourceTestAPI(unittest.TestCase):
    def test_constant_doc_none(self):
        out = test_data_source("constant", json.dumps({"value": "5"}))
        self.assertTrue(out["success"], out)
        self.assertEqual(out["value"], 5.0)
        self.assertEqual(out["type"], "float")

    def test_unknown_source(self):
        out = test_data_source("no_such_type", "{}")
        self.assertIn("error", out)

    def test_validation_runs_before_execute(self):
        out = test_data_source("session_variable", json.dumps({}))
        self.assertEqual(out.get("error"), "Validation failed")
        self.assertIn("key", json.dumps(out.get("validation_errors", [])))


# ═══════════════════════════════════════════════════════════════════════════
# A4 — BatchBindingResolver.preview_groups (grouping + strategy)
# ═══════════════════════════════════════════════════════════════════════════

class TestPreviewGroups(unittest.TestCase):
    def setUp(self):
        self.resolver = BatchBindingResolver()

    def test_same_fingerprint_groups_together(self):
        bindings = [
            _b("a", "doctype_query", {"doctype": "Item", "fieldname": "net_weight", "filters": []}),
            _b("b", "doctype_query", {"doctype": "Item", "fieldname": "net_weight", "filters": []}),
        ]
        pre = self.resolver.preview_groups(bindings)
        self.assertEqual(pre["summary"]["total_groups"], 1)
        g = pre["groups"][0]
        self.assertEqual(g["strategy"], "resolve_batch")
        self.assertEqual(g["binding_count"], 2)
        self.assertEqual(pre["summary"]["estimated_queries"], 1)

    def test_different_fingerprint_splits(self):
        bindings = [
            _b("a", "doctype_query", {"doctype": "Item", "fieldname": "net_weight", "filters": []}),
            _b("b", "doctype_query", {"doctype": "Item", "fieldname": "price", "filters": []}),
        ]
        pre = self.resolver.preview_groups(bindings)
        self.assertEqual(pre["summary"]["total_groups"], 2)

    def test_explicit_batch_group_overrides_fingerprint(self):
        bindings = [
            _b("a", "doctype_query", {"doctype": "Item", "fieldname": "net_weight"}, batch_group="g1"),
            _b("b", "doctype_query", {"doctype": "Item", "fieldname": "price"}, batch_group="g1"),
        ]
        pre = self.resolver.preview_groups(bindings)
        self.assertEqual(pre["summary"]["total_groups"], 1)
        self.assertTrue(pre["groups"][0]["explicit_batch_group"])

    def test_non_batchable_counts_individual(self):
        bindings = [
            _b("cnst", "constant", {"value": "5"}),
            _b("plain", "fb_phase1_plain", {"value": "1"}),
        ]
        pre = self.resolver.preview_groups(bindings)
        self.assertEqual(pre["summary"]["total_groups"], 0)
        self.assertEqual(pre["summary"]["individual_bindings"], 2)
        self.assertEqual(pre["summary"]["estimated_queries"], 2)
        self.assertEqual(len(pre["individual_bindings"]), 2)
        reasons = [i["reason"] for i in pre["individual_bindings"]]
        self.assertTrue(all("không batchable" in r for r in reasons))

    def test_batchable_without_resolve_batch_is_individual(self):
        # Handler batchable nhưng KHÔNG có resolve_batch → nhóm rơi xuống
        # _execute_individual (N+1) trong execution thật.
        bindings = [
            _b("x", "fb_phase1_batch_no_resolve", {"value": "1", "group": "z"}),
            _b("y", "fb_phase1_batch_no_resolve", {"value": "2", "group": "z"}),
        ]
        pre = self.resolver.preview_groups(bindings)
        self.assertEqual(pre["summary"]["total_groups"], 1)
        self.assertEqual(pre["groups"][0]["strategy"], "execute_individual")
        self.assertEqual(pre["groups"][0]["binding_count"], 2)
        # 2 binding nhóm individual → ước lượng 2 query (N+1).
        self.assertEqual(pre["summary"]["estimated_queries"], 2)
        self.assertEqual(pre["summary"]["individual_bindings"], 2)

    def test_empty(self):
        pre = self.resolver.preview_groups([])
        self.assertEqual(pre["summary"]["total_bindings"], 0)
        self.assertEqual(pre["summary"]["estimated_queries"], 0)


# ═══════════════════════════════════════════════════════════════════════════
# A5 — binding_scope semantics
# ═══════════════════════════════════════════════════════════════════════════

class TestBindingScope(unittest.TestCase):
    def test_global_applies_everywhere(self):
        self.assertTrue(binding_matches_scope(
            {"applies_to_doctype": "", "applies_to_field": ""}, "Quotation Item", "total"))
        self.assertTrue(binding_matches_scope(
            {"applies_to_doctype": None, "applies_to_field": ""}, "AL Bom Item", ""))

    def test_doctype_match_field_blank(self):
        # Binding gắn doctype nhưng không set field → áp mọi field của doctype.
        self.assertTrue(binding_matches_scope(
            {"applies_to_doctype": "Quotation Item", "applies_to_field": ""},
            "Quotation Item", "total"))

    def test_doctype_match_field_match(self):
        self.assertTrue(binding_matches_scope(
            {"applies_to_doctype": "Quotation Item", "applies_to_field": "total"},
            "Quotation Item", "total"))

    def test_caller_without_field_accepts_all_fields_of_doctype(self):
        # Caller không cung cấp field ("" hoặc None) → mọi binding của doctype khớp.
        self.assertTrue(binding_matches_scope(
            {"applies_to_doctype": "Quotation Item", "applies_to_field": "total"},
            "Quotation Item", ""))
        self.assertTrue(binding_matches_scope(
            {"applies_to_doctype": "Quotation Item", "applies_to_field": ""},
            "Quotation Item", ""))

    def test_doctype_mismatch_rejected(self):
        self.assertFalse(binding_matches_scope(
            {"applies_to_doctype": "AL Bom Item", "applies_to_field": "total"},
            "Quotation Item", "total"))

    def test_field_mismatch_rejected(self):
        self.assertFalse(binding_matches_scope(
            {"applies_to_doctype": "Quotation Item", "applies_to_field": "base"},
            "Quotation Item", "total"))

    def test_filter_bindings_python_side(self):
        bindings = [
            {"variable_name": "g", "applies_to_doctype": "", "applies_to_field": ""},
            {"variable_name": "d", "applies_to_doctype": "Quotation Item", "applies_to_field": ""},
            {"variable_name": "df", "applies_to_doctype": "Quotation Item", "applies_to_field": "total"},
            {"variable_name": "df_other", "applies_to_doctype": "Quotation Item", "applies_to_field": "base"},
            {"variable_name": "w", "applies_to_doctype": "AL Bom Item", "applies_to_field": "total"},
        ]
        got = [b["variable_name"] for b in
               filter_bindings_for_scope(bindings, "Quotation Item", "total")]
        self.assertEqual(got, ["g", "d", "df"])

    def test_filter_global_only(self):
        bindings = [
            {"variable_name": "g", "applies_to_doctype": "", "applies_to_field": ""},
            {"variable_name": "g2", "applies_to_doctype": "", "applies_to_field": "other"},
            {"variable_name": "w", "applies_to_doctype": "Quotation Item", "applies_to_field": "total"},
        ]
        got = [b["variable_name"] for b in
               filter_bindings_for_scope(bindings, "Quotation Item", "total")]
        # g2: doctype rỗng nhưng field 'other' — không khớp 'total' trên doctype cụ thể.
        self.assertEqual(got, ["g", "w"])


# ═══════════════════════════════════════════════════════════════════════════
# A5 — binding_scope đa doctype (pattern pricing: KHÔNG có 1 doc đơn,
#       doctype list ["", "Quotation Item", "AL Bom Item"] — Phase 2/3/4)
# ═══════════════════════════════════════════════════════════════════════════

PRICING_DOCTYPES = ("Quotation Item", "AL Bom Item")


class TestBindingScopeMultiDoctype(unittest.TestCase):
    def test_global_matches_any_doctype(self):
        g = {"variable_name": "g", "applies_to_doctype": "", "applies_to_field": ""}
        self.assertTrue(binding_matches_any_doctype(g, PRICING_DOCTYPES, ""))
        self.assertTrue(binding_matches_any_doctype(g, PRICING_DOCTYPES, "total"))

    def test_doctype_in_set_field_blank_matches(self):
        # Binding doctype-scoped, không set field → áp mọi field của doctype đó.
        b = {"variable_name": "d", "applies_to_doctype": "Quotation Item",
             "applies_to_field": ""}
        self.assertTrue(binding_matches_any_doctype(b, PRICING_DOCTYPES, "total"))
        self.assertTrue(binding_matches_any_doctype(b, PRICING_DOCTYPES, ""))

    def test_doctype_in_set_field_match(self):
        b = {"variable_name": "df", "applies_to_doctype": "AL Bom Item",
             "applies_to_field": "unit_price"}
        self.assertTrue(binding_matches_any_doctype(b, PRICING_DOCTYPES, "unit_price"))

    def test_doctype_in_set_field_mismatch_rejected(self):
        b = {"variable_name": "df", "applies_to_doctype": "Quotation Item",
             "applies_to_field": "unit_price"}
        self.assertFalse(binding_matches_any_doctype(b, PRICING_DOCTYPES, "base"))
        # vẫn khớp khi caller không cung cấp field (không đổi hành vi cũ).
        self.assertTrue(binding_matches_any_doctype(b, PRICING_DOCTYPES, ""))

    def test_doctype_outside_set_rejected(self):
        b = {"variable_name": "o", "applies_to_doctype": "Sales Order Item",
             "applies_to_field": ""}
        self.assertFalse(binding_matches_any_doctype(b, PRICING_DOCTYPES, ""))
        b2 = {"variable_name": "o2", "applies_to_doctype": "Sales Order Item",
              "applies_to_field": "total"}
        self.assertFalse(binding_matches_any_doctype(b2, PRICING_DOCTYPES, "total"))

    def test_doctype_empty_field_set_excluded_on_concrete_scope(self):
        # Binding field-only (doctype rỗng) — KHÔNG global → không khớp doctype
        # cụ thể nào trong tập pricing (đồng nhất get_live_context với context
        # có doctype cụ thể).
        b = {"variable_name": "x", "applies_to_doctype": "", "applies_to_field": "other"}
        self.assertFalse(binding_matches_any_doctype(b, PRICING_DOCTYPES, ""))
        self.assertFalse(binding_matches_any_doctype(b, PRICING_DOCTYPES, "other"))

    def test_empty_doctype_set_delegates_no_doctype_semantics(self):
        # doctypes rỗng (không có doctype context) → defer đúng
        # binding_matches_scope(binding, "", field) — đồng nhất
        # get_scope_bindings(doctype="") của scope 1 doctype.
        global_b = {"variable_name": "g", "applies_to_doctype": "", "applies_to_field": ""}
        self.assertTrue(binding_matches_any_doctype(global_b, (), ""))
        # Binding gắn doctype cụ thể KHÔNG khớp khi không có doctype context.
        dt = {"variable_name": "dt", "applies_to_doctype": "Quotation Item",
              "applies_to_field": ""}
        self.assertFalse(binding_matches_any_doctype(dt, (), "total"))
        dt2 = {"variable_name": "dt2", "applies_to_doctype": "Quotation Item",
               "applies_to_field": "unit_price"}
        self.assertFalse(binding_matches_any_doctype(dt2, (), "unit_price"))

    def test_accepts_single_doctype_str(self):
        b = {"variable_name": "d", "applies_to_doctype": "Quotation Item",
             "applies_to_field": ""}
        self.assertTrue(binding_matches_any_doctype(b, "Quotation Item", "total"))
        self.assertFalse(binding_matches_any_doctype(b, "AL Bom Item", "total"))

    def test_filter_multi_composition(self):
        bindings = [
            {"variable_name": "g", "applies_to_doctype": "", "applies_to_field": ""},
            {"variable_name": "qi", "applies_to_doctype": "Quotation Item", "applies_to_field": ""},
            {"variable_name": "qi_total", "applies_to_doctype": "Quotation Item", "applies_to_field": "total"},
            {"variable_name": "bom", "applies_to_doctype": "AL Bom Item", "applies_to_field": "unit_price"},
            {"variable_name": "so", "applies_to_doctype": "Sales Order Item", "applies_to_field": ""},
        ]
        # Lọc theo tập doctype pricing, không có field → g, qi, qi_total, bom
        # (so nằm ngoài tập; field-chỉ định không bị ép vì không có field context).
        got = [b["variable_name"] for b in
               filter_bindings_for_scope_multi(bindings, PRICING_DOCTYPES, "")]
        self.assertEqual(got, ["g", "qi", "qi_total", "bom"])
        # Với field context "unit_price": global + binding khớp doctype+field
        # (bom). qi (doctype-scoped, không set field) áp mọi field của Quotation
        # Item → vẫn giữ (đúng luật "không set field = áp mọi field", không đổi
        # kết quả khi binding không set applies_to_field).
        got2 = [b["variable_name"] for b in
                filter_bindings_for_scope_multi(bindings, PRICING_DOCTYPES, "unit_price")]
        self.assertEqual(got2, ["g", "qi", "bom"])
        # doctypes rỗng → chỉ global (đồng nhất get_scope_bindings("")).
        got3 = [b["variable_name"] for b in
                filter_bindings_for_scope_multi(bindings, (), "")]
        self.assertEqual(got3, ["g"])


if __name__ == "__main__":
    unittest.main()
