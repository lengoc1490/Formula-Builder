"""Tests for v31 Phase 2: pipeline, conditional, fallback_chain composite source types."""

import json
from frappe.tests.utils import FrappeTestCase

from formula_builder.api.data_source_registry import (
    get_handler,
    _handle_pipeline,
    _handle_conditional,
    _handle_fallback_chain,
    validate_binding_source_config,
)
from formula_builder.api.source_type_registry import SourceTypeRegistry


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestPipelineSource(FrappeTestCase):
    """Test the pipeline composite source type."""

    def setUp(self):
        SourceTypeRegistry.reset_instance()

    def tearDown(self):
        SourceTypeRegistry.reset_instance()

    def test_pipeline_two_steps(self):
        """Chain: constant(10) → computed(value * 2) → 20."""
        binding = {
            "variable_name": "final",
            "source_type": "pipeline",
            "source_config": json.dumps({
                "steps": [
                    {"source_type": "constant", "source_config": {"value": 10}, "output_as": "base", "data_type": "Float"},
                    {"source_type": "computed", "source_config": {"formula": "base * 2", "dependencies": ["base"]}, "output_as": "final"},
                ],
                "merge_strategy": "last",
            }),
        }
        result = _handle_pipeline(binding, None, {})
        self.assertEqual(result, 20.0)

    def test_pipeline_three_steps(self):
        """Chain: constant(5) → * 3 → + 10 → 25."""
        binding = {
            "variable_name": "result",
            "source_type": "pipeline",
            "source_config": json.dumps({
                "steps": [
                    {"source_type": "constant", "source_config": {"value": 5}, "output_as": "a", "data_type": "Float"},
                    {"source_type": "computed", "source_config": {"formula": "a * 3", "dependencies": ["a"]}, "output_as": "b"},
                    {"source_type": "computed", "source_config": {"formula": "b + 10", "dependencies": ["b"]}, "output_as": "c"},
                ],
            }),
        }
        result = _handle_pipeline(binding, None, {})
        self.assertEqual(result, 25.0)

    def test_pipeline_merge_all(self):
        """merge_strategy='all' returns dict of all step outputs."""
        binding = {
            "variable_name": "all",
            "source_type": "pipeline",
            "source_config": json.dumps({
                "steps": [
                    {"source_type": "constant", "source_config": {"value": 100}, "output_as": "price", "data_type": "Float"},
                    {"source_type": "constant", "source_config": {"value": 5}, "output_as": "qty", "data_type": "Float"},
                    {"source_type": "computed", "source_config": {"formula": "price * qty", "dependencies": ["price", "qty"]}, "output_as": "total"},
                ],
                "merge_strategy": "all",
            }),
        }
        result = _handle_pipeline(binding, None, {})
        self.assertIsInstance(result, dict)
        self.assertEqual(result["price"], 100.0)
        self.assertEqual(result["total"], 500.0)

    def test_pipeline_empty_steps(self):
        binding = {"variable_name": "x", "source_type": "pipeline", "source_config": json.dumps({"steps": []}), "default_value": 42}
        self.assertEqual(_handle_pipeline(binding, None, {}), 42)

    def test_pipeline_with_context(self):
        binding = {
            "variable_name": "area",
            "source_type": "pipeline",
            "source_config": json.dumps({
                "steps": [{"source_type": "computed", "source_config": {"formula": "W_mm * H_mm / 1000000", "dependencies": ["W_mm", "H_mm"]}, "output_as": "area_m2"}],
            }),
        }
        result = _handle_pipeline(binding, None, {"W_mm": 2400, "H_mm": 2600})
        self.assertEqual(result, 6.24)

    def test_pipeline_validation(self):
        result = validate_binding_source_config({"source_type": "pipeline", "source_config": '{"merge_strategy": "last"}'})
        self.assertIsNotNone(result)
        self.assertIn("steps", result)


# ═══════════════════════════════════════════════════════════════════════════
# CONDITIONAL TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestConditionalSource(FrappeTestCase):
    """Test the conditional composite source type."""

    def setUp(self):
        SourceTypeRegistry.reset_instance()

    def tearDown(self):
        SourceTypeRegistry.reset_instance()

    def test_first_branch_matches(self):
        binding = {
            "variable_name": "price",
            "source_type": "conditional",
            "source_config": json.dumps({
                "branches": [
                    {"condition": "product_type == 'CUA_DI'", "source_type": "constant", "source_config": {"value": 1000}},
                    {"condition": "product_type == 'CUA_SO'", "source_type": "constant", "source_config": {"value": 500}},
                ],
                "default": {"source_type": "constant", "source_config": {"value": 0}},
            }),
        }
        self.assertEqual(_handle_conditional(binding, None, {"product_type": "CUA_DI"}), 1000.0)

    def test_second_branch_matches(self):
        binding = {
            "variable_name": "tier",
            "source_type": "conditional",
            "source_config": json.dumps({
                "branches": [
                    {"condition": "margin > 0.5", "source_type": "constant", "source_config": {"value": "high"}},
                    {"condition": "margin > 0.2", "source_type": "constant", "source_config": {"value": "medium"}},
                ],
                "default": {"source_type": "constant", "source_config": {"value": "low"}},
            }),
        }
        self.assertEqual(_handle_conditional(binding, None, {"margin": 0.3}), "medium")

    def test_no_match_uses_default(self):
        binding = {
            "variable_name": "cat",
            "source_type": "conditional",
            "source_config": json.dumps({
                "branches": [{"condition": "total > 100", "source_type": "constant", "source_config": {"value": "big"}}],
                "default": {"source_type": "constant", "source_config": {"value": "small"}},
            }),
        }
        self.assertEqual(_handle_conditional(binding, None, {"total": 50}), "small")

    def test_no_default_uses_binding_default(self):
        binding = {
            "variable_name": "fb",
            "source_type": "conditional",
            "source_config": json.dumps({
                "branches": [{"condition": "False", "source_type": "constant", "source_config": {"value": "never"}}],
            }),
            "default_value": 99,
        }
        self.assertEqual(_handle_conditional(binding, None, {}), 99)

    def test_complex_condition(self):
        binding = {
            "variable_name": "rate",
            "source_type": "conditional",
            "source_config": json.dumps({
                "branches": [
                    {"condition": "area > 10 and material == 'NHOM'", "source_type": "constant", "source_config": {"value": 0.08}},
                    {"condition": "area > 5 or material == 'KINH'", "source_type": "constant", "source_config": {"value": 0.05}},
                ],
                "default": {"source_type": "constant", "source_config": {"value": 0.03}},
            }),
        }
        self.assertEqual(_handle_conditional(binding, None, {"area": 6, "material": "NHOM"}), 0.05)

    def test_invalid_condition_skips(self):
        binding = {
            "variable_name": "x",
            "source_type": "conditional",
            "source_config": json.dumps({
                "branches": [
                    {"condition": "undefined_var > 10", "source_type": "constant", "source_config": {"value": "bad"}},
                    {"condition": "True", "source_type": "constant", "source_config": {"value": "good"}},
                ],
            }),
        }
        self.assertEqual(_handle_conditional(binding, None, {}), "good")

    def test_conditional_validation(self):
        result = validate_binding_source_config({"source_type": "conditional", "source_config": '{"default": {"source_type": "constant"}}'})
        self.assertIsNotNone(result)
        self.assertIn("branches", result)


# ═══════════════════════════════════════════════════════════════════════════
# FALLBACK CHAIN TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestFallbackChainSource(FrappeTestCase):
    """Test the fallback_chain composite source type."""

    def setUp(self):
        SourceTypeRegistry.reset_instance()

    def tearDown(self):
        SourceTypeRegistry.reset_instance()

    def test_first_link_succeeds(self):
        binding = {
            "variable_name": "result",
            "source_type": "fallback_chain",
            "source_config": json.dumps({
                "chain": [
                    {"source_type": "constant", "source_config": {"value": 100}, "label": "primary"},
                    {"source_type": "constant", "source_config": {"value": 200}, "label": "fallback"},
                ],
            }),
        }
        self.assertEqual(_handle_fallback_chain(binding, None, {}), 100.0)

    def test_first_returns_none_uses_second(self):
        binding = {
            "variable_name": "result",
            "source_type": "fallback_chain",
            "source_config": json.dumps({
                "chain": [
                    {"source_type": "constant", "source_config": {}, "label": "broken"},
                    {"source_type": "constant", "source_config": {"value": 42}, "label": "backup"},
                ],
            }),
        }
        self.assertEqual(_handle_fallback_chain(binding, None, {}), 42.0)

    def test_chain_exhausted_returns_default(self):
        binding = {
            "variable_name": "result",
            "source_type": "fallback_chain",
            "source_config": json.dumps({
                "chain": [
                    {"source_type": "constant", "source_config": {}, "label": "f1"},
                    {"source_type": "constant", "source_config": {}, "label": "f2"},
                ],
            }),
            "default_value": 999,
        }
        self.assertEqual(_handle_fallback_chain(binding, None, {}), 999)

    def test_empty_chain(self):
        binding = {"variable_name": "x", "source_type": "fallback_chain", "source_config": json.dumps({"chain": []}), "default_value": 77}
        self.assertEqual(_handle_fallback_chain(binding, None, {}), 77)

    def test_pipeline_as_link(self):
        binding = {
            "variable_name": "final",
            "source_type": "fallback_chain",
            "source_config": json.dumps({
                "chain": [{
                    "source_type": "pipeline",
                    "source_config": {
                        "steps": [
                            {"source_type": "constant", "source_config": {"value": 3}, "output_as": "base", "data_type": "Float"},
                            {"source_type": "computed", "source_config": {"formula": "base * 7", "dependencies": ["base"]}, "output_as": "result"},
                        ],
                    },
                    "label": "pipe",
                }],
            }),
        }
        self.assertEqual(_handle_fallback_chain(binding, None, {}), 21.0)

    def test_fallback_with_transform(self):
        binding = {
            "variable_name": "x",
            "source_type": "fallback_chain",
            "source_config": json.dumps({
                "chain": [{
                    "source_type": "constant",
                    "source_config": {"value": 50},
                    "label": "with_xform",
                    "transform": {"multiply": 2, "round": 0},
                }],
            }),
        }
        self.assertEqual(_handle_fallback_chain(binding, None, {}), 100.0)

    def test_fallback_validation(self):
        result = validate_binding_source_config({"source_type": "fallback_chain", "source_config": "{}"})
        self.assertIsNotNone(result)
        self.assertIn("chain", result)


# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCompositeNesting(FrappeTestCase):
    """Test that composite types can be nested."""

    def setUp(self):
        SourceTypeRegistry.reset_instance()

    def tearDown(self):
        SourceTypeRegistry.reset_instance()

    def test_conditional_inside_pipeline(self):
        binding = {
            "variable_name": "final",
            "source_type": "pipeline",
            "source_config": json.dumps({
                "steps": [
                    {"source_type": "constant", "source_config": {"value": 3}, "output_as": "x", "data_type": "Float"},
                    {"source_type": "conditional", "source_config": {"branches": [{"condition": "True", "source_type": "constant", "source_config": {"value": 100}}], "default": {"source_type": "constant", "source_config": {"value": 0}}}, "output_as": "price"},
                    {"source_type": "computed", "source_config": {"formula": "price * 2", "dependencies": ["price"]}, "output_as": "doubled"},
                ],
            }),
        }
        self.assertEqual(_handle_pipeline(binding, None, {}), 200.0)

    def test_deep_nesting(self):
        """Pipeline → fallback → conditional."""
        binding = {
            "variable_name": "deep",
            "source_type": "pipeline",
            "source_config": json.dumps({
                "steps": [
                    {"source_type": "constant", "source_config": {"value": "A"}, "output_as": "cat", "data_type": "Data"},
                    {"source_type": "fallback_chain", "source_config": {"chain": [{"source_type": "conditional", "source_config": {"branches": [{"condition": "True", "source_type": "constant", "source_config": {"value": 888}}]}, "label": "inner"}]}, "output_as": "deep_result"},
                ],
            }),
        }
        self.assertEqual(_handle_pipeline(binding, None, {}), 888.0)


# ═══════════════════════════════════════════════════════════════════════════
# REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase2Registry(FrappeTestCase):
    """Test Phase 2 types are registered with proper metadata."""

    @classmethod
    def setUpClass(cls):
        SourceTypeRegistry.reset_instance()

    @classmethod
    def tearDownClass(cls):
        SourceTypeRegistry.reset_instance()

    def test_all_13_types_registered(self):
        registry = SourceTypeRegistry.get_instance()
        for st in ["pipeline", "conditional", "fallback_chain"]:
            self.assertTrue(registry.has(st))

    def test_phase2_types_have_schemas(self):
        registry = SourceTypeRegistry.get_instance()
        for st in ["pipeline", "conditional", "fallback_chain"]:
            d = registry.get(st)
            self.assertIsNotNone(d.config_schema)
            self.assertIn("required", d.config_schema)

    def test_pipeline_is_batchable(self):
        self.assertTrue(SourceTypeRegistry.get_instance().get("pipeline").batchable)

    def test_conditional_not_batchable(self):
        self.assertFalse(SourceTypeRegistry.get_instance().get("conditional").batchable)

    def test_list_all_includes_phase2(self):
        names = SourceTypeRegistry.get_instance().list_source_type_names()
        for st in ["pipeline", "conditional", "fallback_chain"]:
            self.assertIn(st, names)


# ═══════════════════════════════════════════════════════════════════════════
# REAL-WORLD SCENARIO TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRealWorldScenarios(FrappeTestCase):
    """Test realistic multi-industry scenarios."""

    def setUp(self):
        SourceTypeRegistry.reset_instance()

    def tearDown(self):
        SourceTypeRegistry.reset_instance()

    def test_aluminum_pricing_pipeline(self):
        """ALU GLASS: base price → tax → margin → final."""
        binding = {
            "variable_name": "final_price",
            "source_type": "pipeline",
            "source_config": json.dumps({
                "steps": [
                    {"source_type": "constant", "source_config": {"value": 113000}, "output_as": "raw", "data_type": "Float"},
                    {"source_type": "computed", "source_config": {"formula": "raw * (1 + tax)", "dependencies": ["raw", "tax"]}, "output_as": "with_tax"},
                    {"source_type": "computed", "source_config": {"formula": "with_tax * (1 + margin)", "dependencies": ["with_tax", "margin"]}, "output_as": "final"},
                ],
            }),
        }
        result = _handle_pipeline(binding, None, {"tax": 0.10, "margin": 0.16})
        self.assertAlmostEqual(result, 144188.0, delta=1)

    def test_api_resilience_pattern(self):
        """API down → cache → manual default."""
        binding = {
            "variable_name": "lme",
            "source_type": "fallback_chain",
            "source_config": json.dumps({
                "chain": [
                    {"source_type": "constant", "source_config": {"value": None}, "label": "api"},
                    {"source_type": "constant", "source_config": {"value": 2450}, "label": "cache"},
                    {"source_type": "constant", "source_config": {"value": 2500}, "label": "manual"},
                ],
            }),
        }
        self.assertEqual(_handle_fallback_chain(binding, None, {}), 2450.0)

    def test_multi_region_pricing(self):
        """Different regions → different price tables."""
        binding = {
            "variable_name": "price",
            "source_type": "conditional",
            "source_config": json.dumps({
                "branches": [
                    {"condition": "region == 'NORTH'", "source_type": "constant", "source_config": {"value": 100}},
                    {"condition": "region == 'SOUTH'", "source_type": "constant", "source_config": {"value": 120}},
                ],
                "default": {"source_type": "constant", "source_config": {"value": 95}},
            }),
        }
        self.assertEqual(_handle_conditional(binding, None, {"region": "NORTH"}), 100.0)
        self.assertEqual(_handle_conditional(binding, None, {"region": "SOUTH"}), 120.0)
        self.assertEqual(_handle_conditional(binding, None, {"region": "WEST"}), 95.0)
