"""Tests for api/batch_binding_resolver.py — batch resolve, grouping, fallback."""

import json
from frappe.tests.utils import FrappeTestCase

from formula_builder.api.batch_binding_resolver import (
    BatchBindingResolver,
    resolve_all_bindings_batch,
    _make_fingerprint,
    _is_batchable,
)

from formula_builder.api.data_source_registry import (
    batchable,
    is_batchable,
    register_source,
    get_handler,
)


# ── Test Helpers ─────────────────────────────────────────────────────────

# Create a mock batchable handler for testing
@register_source("test_batchable")
@batchable(fingerprint_fn=lambda cfg: cfg.get("group", "default"))
def _handle_test_batchable(binding, doc, resolved_so_far):
    """Simple handler that just returns the config value."""
    cfg = json.loads(binding.get("source_config", "{}"))
    return cfg.get("value")


def _resolve_test_batchable_batch(bindings, doc, resolved_so_far):
    """Batch resolver for test_batchable: sums all values."""
    results = {}
    for b in bindings:
        cfg = json.loads(b.get("source_config", "{}"))
        results[b["variable_name"]] = cfg.get("value")
    return results


_handle_test_batchable.resolve_batch = _resolve_test_batchable_batch


class TestBatchBindingResolverBasics(FrappeTestCase):
    """Basic resolver tests — split, group, execute."""

    def setUp(self):
        self.resolver = BatchBindingResolver()

    def test_empty_bindings(self):
        result = self.resolver.resolve_all_batch([])
        self.assertEqual(result, {})

    def test_make_fingerprint_deterministic(self):
        fp1 = _make_fingerprint("doctype_query", "Item", "weight_per_unit")
        fp2 = _make_fingerprint("doctype_query", "Item", "weight_per_unit")
        self.assertEqual(fp1, fp2, "Same inputs → same fingerprint")

    def test_make_fingerprint_different(self):
        fp1 = _make_fingerprint("doctype_query", "Item", "weight")
        fp2 = _make_fingerprint("doctype_query", "Item", "price")
        self.assertNotEqual(fp1, fp2, "Different inputs → different fingerprint")

    def test_is_batchable_detection(self):
        # Built-in handler marked @batchable
        self.assertTrue(is_batchable("doctype_query"))
        self.assertTrue(is_batchable("linked_doctype_field"))
        self.assertTrue(is_batchable("whole_doctype"))

        # Not marked → not batchable
        self.assertFalse(is_batchable("constant"))
        self.assertFalse(is_batchable("computed"))
        self.assertFalse(is_batchable("nonexistent"))

    def test_custom_handler_batchable(self):
        self.assertTrue(is_batchable("test_batchable"))

    def test_split_batchable(self):
        bindings = [
            {"variable_name": "a", "source_type": "doctype_query",
             "source_config": '{"doctype":"Item","fieldname":"weight_per_unit","aggregate":"first","filters":[["name","=","ITEM-1"]]}'},
            {"variable_name": "b", "source_type": "constant",
             "source_config": '{"value": 42}'},
            {"variable_name": "c", "source_type": "doctype_query",
             "source_config": '{"doctype":"Item","fieldname":"weight_per_unit","aggregate":"first","filters":[["name","=","ITEM-2"]]}'},
        ]
        batchable_list, non_batchable = self.resolver._split_batchable(bindings)

        self.assertEqual(len(batchable_list), 2, "2 doctype_query bindings → batchable")
        self.assertEqual(len(non_batchable), 1, "1 constant binding → non-batchable")
        self.assertEqual(non_batchable[0]["source_type"], "constant")


class TestBatchBindingResolverGrouping(FrappeTestCase):
    """Test grouping logic."""

    def setUp(self):
        self.resolver = BatchBindingResolver()

    def test_group_by_source_type_and_fingerprint(self):
        bindings = [
            {"variable_name": "item1_weight", "source_type": "doctype_query",
             "source_config": '{"doctype":"Item","fieldname":"weight_per_unit","aggregate":"first","filters":[["name","=","A"]]}'},
            {"variable_name": "item2_weight", "source_type": "doctype_query",
             "source_config": '{"doctype":"Item","fieldname":"weight_per_unit","aggregate":"first","filters":[["name","=","B"]]}'},
            {"variable_name": "item1_price", "source_type": "doctype_query",
             "source_config": '{"doctype":"Item Price","fieldname":"price_list_rate","aggregate":"first","filters":[["name","=","PRICE-A"]]}'},
        ]

        groups = self.resolver._group_by_fingerprint(bindings)

        # 2 groups: (Item/weight_per_unit) vs (Item Price/price_list_rate)
        self.assertEqual(len(groups), 2,
                         "Item vs Item Price → 2 groups (different doctypes)")

    def test_group_with_explicit_batch_group(self):
        bindings = [
            {"variable_name": "a", "source_type": "doctype_query",
             "source_config": '{"doctype":"Item","fieldname":"weight"}',
             "batch_group": "ITEM_DATA"},
            {"variable_name": "b", "source_type": "doctype_query",
             "source_config": '{"doctype":"Item Price","fieldname":"rate"}',
             "batch_group": "ITEM_DATA"},
            {"variable_name": "c", "source_type": "doctype_query",
             "source_config": '{"doctype":"Item","fieldname":"weight"}',
             "batch_group": "OTHER"},
        ]

        groups = self.resolver._group_by_fingerprint(bindings)

        # 3 groups: 2 from "ITEM_DATA" (same batch_group, different keys)
        # But actually same batch_group = same fingerprint → 2 groups total
        # Wait: bindings a and b both have batch_group="ITEM_DATA"
        # They'll be in the same group because fingerprint="ITEM_DATA" for both
        # Binding c has batch_group="OTHER" → separate group
        self.assertEqual(len(groups), 2)


class TestBatchBindingResolverResult(FrappeTestCase):
    """Test actual resolution results."""

    def setUp(self):
        self.resolver = BatchBindingResolver()

    def test_mixed_batchable_non_batchable(self):
        """Ensure batchable and non-batchable results are merged correctly."""
        bindings = [
            # Batchable test handler — returns config value
            {"variable_name": "var_a", "source_type": "test_batchable",
             "source_config": '{"value": 100, "group": "g1"}'},
            {"variable_name": "var_b", "source_type": "test_batchable",
             "source_config": '{"value": 200, "group": "g1"}'},
            # Non-batchable constant
            {"variable_name": "var_c", "source_type": "constant",
             "source_config": '{"value": 300}', "data_type": "Int"},
        ]

        result = self.resolver.resolve_all_batch(bindings)

        self.assertEqual(result["var_a"], 100)
        self.assertEqual(result["var_b"], 200)
        self.assertEqual(result["var_c"], 300)

    def test_resolve_with_pre_resolved(self):
        bindings = [
            {"variable_name": "final", "source_type": "constant",
             "source_config": '{"value": 999}', "data_type": "Int"},
        ]
        result = self.resolver.resolve_all_batch(
            bindings, pre_resolved={"existing": 42}
        )
        self.assertEqual(result.get("existing"), 42)
        self.assertEqual(result["final"], 999)

    def test_convenience_function(self):
        bindings = [
            {"variable_name": "x", "source_type": "test_batchable",
             "source_config": '{"value": 55, "group": "t"}'},
        ]
        result = resolve_all_bindings_batch(bindings)
        self.assertEqual(result["x"], 55)


class TestBatchBindingResolverEdgeCases(FrappeTestCase):
    """Edge cases and error handling."""

    def setUp(self):
        self.resolver = BatchBindingResolver()

    def test_missing_handler_falls_back_to_default(self):
        bindings = [
            {"variable_name": "bad", "source_type": "nonexistent_handler",
             "source_config": "{}", "default_value": 42},
        ]
        result = self.resolver.resolve_all_batch(bindings)
        self.assertEqual(result["bad"], 42)

    def test_handler_error_falls_back(self):
        """If handler throws, use default_value."""
        bindings = [
            {"variable_name": "broken", "source_type": "test_batchable",
             "source_config": '{"value": null is bad json}',
             "default_value": 88},
        ]
        # resolve_batch uses json.loads which will fail on bad config
        # But the batch handler doesn't use json.loads for this mock handler
        # Let's test with a proper error case: bad JSON in source_config
        bindings2 = [
            {"variable_name": "broken", "source_type": "constant",
             "source_config": "{bad json}", "default_value": 77},
        ]
        result = self.resolver.resolve_all_batch(bindings2)
        self.assertEqual(result["broken"], 77)


class TestBatchableDecorator(FrappeTestCase):
    """Test the @batchable decorator."""

    def test_decorator_sets_attributes(self):
        handler = get_handler("doctype_query")
        self.assertTrue(getattr(handler, 'batchable', False))
        self.assertIsNotNone(getattr(handler, 'fingerprint_fn', None))

    def test_decorator_without_fingerprint(self):
        @register_source("_test_batchable_no_fp")
        @batchable()
        def _handler(binding, doc, resolved):
            return "ok"

        self.assertTrue(getattr(_handler, 'batchable', False))
        # No fingerprint_fn set explicitly → use default grouping by source_type
