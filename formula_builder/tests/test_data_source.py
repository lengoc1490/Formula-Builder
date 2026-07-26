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
    _check_custom_function_allowed,
    _get_custom_function_whitelist,
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


# ═══════════════════════════════════════════════════════════════════════════
# Issue #5: Additional tests — whitelist bypass + resolution priority
# ═══════════════════════════════════════════════════════════════════════════


class TestCustomFunctionWhitelist(FrappeTestCase):
    """Test _check_custom_function_allowed — prevents prefix collision bypass."""

    def test_exact_match_allowed(self):
        """Module trùng chính xác với whitelist prefix phải được allow."""
        # "formula_builder.custom_functions" nằm trong default whitelist
        try:
            _check_custom_function_allowed("formula_builder.custom_functions")
        except Exception:
            self.fail("Exact match should be allowed")

    def test_sub_module_allowed(self):
        """Module con hợp lệ (prefix + '.xxx') phải được allow."""
        try:
            _check_custom_function_allowed("formula_builder.custom_functions.utils")
        except Exception:
            self.fail("Valid sub-module should be allowed")

    def test_prefix_collision_blocked(self):
        """Module có tên bắt đầu giống whitelist nhưng KHÔNG phải sub-module
        phải bị chặn (prefix collision bypass)."""
        with self.assertRaises(Exception):
            # "formula_builder.custom_functions_evil" match
            # "formula_builder.custom_functions" qua startswith() cũ
            # nhưng với logic mới (== hoặc startswith(prefix + ".")) thì bị chặn
            _check_custom_function_allowed("formula_builder.custom_functions_evil")

    def test_default_whitelist_has_expected_entries(self):
        """Default whitelist phải chứa các module an toàn."""
        whitelist = _get_custom_function_whitelist()
        self.assertIn("formula_builder.custom_functions", whitelist)
        self.assertIn("formula_builder.formula_utils", whitelist)
        self.assertIn("frappe.utils", whitelist)

    def test_completely_unknown_module_blocked(self):
        """Module không có trong whitelist phải bị chặn."""
        with self.assertRaises(Exception):
            _check_custom_function_allowed("os.system")


class TestResolutionPriority(FrappeTestCase):
    """Test resolution chain — đảm bảo priority giữa các data source đúng."""

    def test_constant_overrides_default_when_present(self):
        """Khi có constant binding, giá trị constant phải thắng default_value."""
        bindings = [
            {
                "variable_name": "rate",
                "source_type": "constant",
                "source_config": '{"value": 15.5, "type": "Float"}',
                "data_type": "Float",
                "default_value": 0,
            },
        ]
        resolved = resolve_bindings_with_deps(bindings, doc=None)
        self.assertEqual(resolved["rate"], 15.5)
        self.assertNotEqual(resolved["rate"], 0)

    def test_default_value_fallback_when_handler_missing(self):
        """Khi handler không tồn tại, phải fallback về default_value."""
        bindings = [
            {
                "variable_name": "unknown_source",
                "source_type": "nonexistent_handler_xyz",
                "source_config": "{}",
                "default_value": 42,
            },
        ]
        resolved = resolve_bindings_with_deps(bindings, doc=None)
        self.assertEqual(resolved["unknown_source"], 42)

    def test_computed_dependency_chain(self):
        """Computed binding phụ thuộc vào các binding khác phải resolve đúng
        theo topological order. A → B → C."""
        bindings = [
            {
                "variable_name": "base",
                "source_type": "constant",
                "source_config": '{"value": 10, "type": "Int"}',
                "data_type": "Int",
            },
            {
                "variable_name": "tax_rate",
                "source_type": "constant",
                "source_config": '{"value": 0.08, "type": "Float"}',
                "data_type": "Float",
            },
            {
                "variable_name": "tax_amount",
                "source_type": "computed",
                "source_config": '{"formula": "base * tax_rate", "dependencies": ["base", "tax_rate"]}',
                "data_type": "Float",
            },
            {
                "variable_name": "total",
                "source_type": "computed",
                "source_config": '{"formula": "base + tax_amount", "dependencies": ["base", "tax_amount"]}',
                "data_type": "Float",
            },
        ]
        resolved = resolve_bindings_with_deps(bindings, doc=None)
        self.assertEqual(resolved["base"], 10)
        self.assertEqual(resolved["tax_rate"], 0.08)
        self.assertAlmostEqual(resolved["tax_amount"], 0.8)
        self.assertAlmostEqual(resolved["total"], 10.8)

    def test_complex_diamond_dependency(self):
        """Diamond dependency graph: A và B → C, B → D → E, C và E → F.
        Không được có cycle và resolve phải đúng."""
        bindings = [
            {"variable_name": "a", "source_type": "constant",
             "source_config": '{"value": 5, "type": "Int"}', "data_type": "Int"},
            {"variable_name": "b", "source_type": "constant",
             "source_config": '{"value": 3, "type": "Int"}', "data_type": "Int"},
            {"variable_name": "c", "source_type": "computed",
             "source_config": '{"formula": "a * b", "dependencies": ["a", "b"]}',
             "data_type": "Int"},
            {"variable_name": "d", "source_type": "computed",
             "source_config": '{"formula": "b + 10", "dependencies": ["b"]}',
             "data_type": "Int"},
            {"variable_name": "e", "source_type": "computed",
             "source_config": '{"formula": "d * 2", "dependencies": ["d"]}',
             "data_type": "Int"},
            {"variable_name": "f", "source_type": "computed",
             "source_config": '{"formula": "c + e", "dependencies": ["c", "e"]}',
             "data_type": "Int"},
        ]
        # No cycle
        self.assertIsNone(detect_circular_bindings(bindings))
        resolved = resolve_bindings_with_deps(bindings, doc=None)
        self.assertEqual(resolved["a"], 5)
        self.assertEqual(resolved["b"], 3)
        self.assertEqual(resolved["c"], 15)        # 5 * 3
        self.assertEqual(resolved["d"], 13)        # 3 + 10
        self.assertEqual(resolved["e"], 26)        # 13 * 2
        self.assertEqual(resolved["f"], 41)        # 15 + 26
