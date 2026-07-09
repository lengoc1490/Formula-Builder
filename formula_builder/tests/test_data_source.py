"""Tests for api/data_source_registry.py — binding resolution, validation."""

from frappe.tests.utils import FrappeTestCase

from formula_builder.api.data_source_registry import (
    register_source,
    get_handler,
    _validate_filter_expr,
    _get_dependency_graph,
    _topological_sort,
    resolve_bindings_with_deps,
    detect_circular_bindings,
    validate_binding_source_config,
    _cast,
)


class TestDataSourceRegistry(FrappeTestCase):
    """Test handler registration and lookup."""

    def test_register_and_lookup(self):
        handler = get_handler("constant")
        self.assertIsNotNone(handler, "constant handler should exist")
        self.assertTrue(callable(handler))

    def test_all_handlers_exist(self):
        expected = [
            "constant", "linked_doctype_field", "whole_doctype",
            "child_table_aggregate", "global_default", "session_variable",
            "doctype_query", "custom_function", "dynamic_link", "computed",
        ]
        for name in expected:
            self.assertIsNotNone(get_handler(name),
                                 f"Handler '{name}' should be registered")

    def test_unknown_handler_returns_none(self):
        self.assertIsNone(get_handler("nonexistent"))


class TestCircularDetection(FrappeTestCase):
    """Test circular dependency detection in bindings."""

    def test_no_cycle(self):
        bindings = [
            {"variable_name": "a", "source_type": "constant"},
            {"variable_name": "b", "source_type": "constant"},
        ]
        self.assertIsNone(detect_circular_bindings(bindings))

    def test_simple_cycle(self):
        bindings = [
            {"variable_name": "a", "source_type": "computed",
             "source_config": '{"formula": "b + 1", "dependencies": ["b"]}'},
            {"variable_name": "b", "source_type": "computed",
             "source_config": '{"formula": "a + 1", "dependencies": ["a"]}'},
        ]
        result = detect_circular_bindings(bindings)
        self.assertIsNotNone(result, "Should detect cycle")
        self.assertIn("Cycle", result)

    def test_self_reference(self):
        bindings = [
            {"variable_name": "a", "source_type": "computed",
             "source_config": '{"formula": "a + 1", "dependencies": ["a"]}'},
        ]
        error = validate_binding_source_config(bindings[0])
        self.assertIsNotNone(error)
        self.assertIn("Self-reference", error)

    def test_diamond_no_cycle(self):
        bindings = [
            {"variable_name": "a", "source_type": "constant"},
            {"variable_name": "b", "source_type": "constant"},
            {"variable_name": "c", "source_type": "computed",
             "source_config": '{"formula": "a + b", "dependencies": ["a", "b"]}'},
            {"variable_name": "d", "source_type": "computed",
             "source_config": '{"formula": "a + c", "dependencies": ["a", "c"]}'},
        ]
        self.assertIsNone(detect_circular_bindings(bindings))


class TestResolveBindings(FrappeTestCase):
    """Test resolve_bindings_with_deps."""

    def test_resolve_constants(self):
        bindings = [
            {"variable_name": "a", "source_type": "constant",
             "source_config": '{"value": 42, "type": "Int"}',
             "data_type": "Int"},
            {"variable_name": "b", "source_type": "constant",
             "source_config": '{"value": 3.14, "type": "Float"}',
             "data_type": "Float"},
            {"variable_name": "c", "source_type": "constant",
             "source_config": '{"value": "hello", "type": "String"}',
             "data_type": "String"},
        ]
        resolved = resolve_bindings_with_deps(bindings, doc=None)
        self.assertEqual(resolved["a"], 42)
        self.assertEqual(resolved["b"], 3.14)
        self.assertEqual(resolved["c"], "hello")

    def test_resolve_with_deps(self):
        bindings = [
            {"variable_name": "base", "source_type": "constant",
             "source_config": '{"value": 100, "type": "Float"}',
             "data_type": "Float"},
            {"variable_name": "factor", "source_type": "constant",
             "source_config": '{"value": 0.1, "type": "Float"}',
             "data_type": "Float"},
            {"variable_name": "result", "source_type": "computed",
             "source_config": '{"formula": "base * factor", "dependencies": ["base", "factor"]}'},
        ]
        resolved = resolve_bindings_with_deps(bindings, doc=None)
        self.assertEqual(resolved["result"], 10)
        self.assertEqual(resolved["base"], 100)
        self.assertEqual(resolved["factor"], 0.1)

    def test_empty_bindings(self):
        resolved = resolve_bindings_with_deps([], doc=None)
        self.assertEqual(resolved, {})

    def test_missing_handler_fallback(self):
        bindings = [
            {"variable_name": "x", "source_type": "nonexistent_type",
             "source_config": "{}", "default_value": 99},
        ]
        resolved = resolve_bindings_with_deps(bindings, doc=None)
        self.assertEqual(resolved["x"], 99)


class TestValidateBindingConfig(FrappeTestCase):
    """Test source_config validation for each handler type."""

    def test_linked_doctype_requires_fields(self):
        binding = {
            "variable_name": "v",
            "source_type": "linked_doctype_field",
            "source_config": "{}",
        }
        error = validate_binding_source_config(binding)
        self.assertIsNotNone(error)
        self.assertIn("link_field", error)

    def test_child_table_aggregate_requires_fields(self):
        binding = {
            "variable_name": "v",
            "source_type": "child_table_aggregate",
            "source_config": "{}",
        }
        error = validate_binding_source_config(binding)
        self.assertIsNotNone(error)
        self.assertIn("child_table_field", error)

    def test_computed_requires_formula(self):
        binding = {
            "variable_name": "v",
            "source_type": "computed",
            "source_config": "{}",
        }
        error = validate_binding_source_config(binding)
        self.assertIsNotNone(error)
        self.assertIn("formula", error)

    def test_constant_no_validation(self):
        binding = {
            "variable_name": "v",
            "source_type": "constant",
            "source_config": '{"value": 5}',
        }
        error = validate_binding_source_config(binding)
        self.assertIsNone(error)

    def test_invalid_json(self):
        binding = {
            "variable_name": "v",
            "source_type": "constant",
            "source_config": "{not json}",
        }
        error = validate_binding_source_config(binding)
        self.assertIsNotNone(error)
        self.assertIn("valid JSON", error)


class TestCastHelper(FrappeTestCase):
    """Test _cast type conversion."""

    def test_cast_float(self):
        self.assertEqual(_cast("3.14", "Float"), 3.14)
        self.assertEqual(_cast("100", "Currency"), 100.0)

    def test_cast_int(self):
        self.assertEqual(_cast("3.14", "Int"), 3)

    def test_cast_bool(self):
        self.assertEqual(_cast("1", "Check"), True)
        self.assertEqual(_cast("0", "Check"), False)

    def test_cast_none(self):
        self.assertIsNone(_cast(None, "Float"))

    def test_cast_invalid(self):
        self.assertEqual(_cast("abc", "Int"), "abc")  # fallback to original
