"""Tests for Phase 1: SourceTypeRegistry, config_schema validation, transform layer."""

import json
from frappe.tests.utils import FrappeTestCase

from formula_builder.api.source_type_registry import (
    SourceTypeRegistry,
    SourceTypeDefinition,
    register_source,
    _validate_against_schema,
)
from formula_builder.api.batch_binding_resolver import (
    _apply_transform,
    BatchBindingResolver,
)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG SCHEMA VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigSchemaValidation(FrappeTestCase):
    """Test the built-in JSON Schema validator."""

    def test_valid_object(self):
        schema = {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0, "maximum": 150},
            },
        }
        config = {"name": "John", "age": 30}
        errors = _validate_against_schema(config, schema)
        self.assertEqual(errors, [], "Valid config should have no errors")

    def test_missing_required(self):
        schema = {
            "type": "object",
            "required": ["name", "age"],
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        config = {"name": "John"}
        errors = _validate_against_schema(config, schema)
        self.assertGreater(len(errors), 0, "Missing required field should error")
        self.assertIn("age", errors[0])

    def test_wrong_type(self):
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
            },
        }
        config = {"count": "not_a_number"}
        errors = _validate_against_schema(config, schema)
        self.assertGreater(len(errors), 0, "Wrong type should error")

    def test_enum_validation(self):
        schema = {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT"]},
            },
        }
        config1 = {"method": "GET"}
        self.assertEqual(_validate_against_schema(config1, schema), [])

        config2 = {"method": "DELETE"}
        errors = _validate_against_schema(config2, schema)
        self.assertGreater(len(errors), 0, "Invalid enum should error")

    def test_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "transform": {
                    "type": "object",
                    "properties": {
                        "formula": {"type": "string"},
                        "round": {"type": "integer", "minimum": 0},
                    },
                },
            },
        }
        config = {"transform": {"formula": "value * 2", "round": 2}}
        errors = _validate_against_schema(config, schema)
        self.assertEqual(errors, [], "Nested valid config should have no errors")

    def test_minimum_maximum(self):
        schema = {
            "type": "object",
            "properties": {
                "round": {"type": "integer", "minimum": 0, "maximum": 10},
            },
        }
        self.assertEqual(_validate_against_schema({"round": 5}, schema), [])
        self.assertGreater(len(_validate_against_schema({"round": -1}, schema)), 0)
        self.assertGreater(len(_validate_against_schema({"round": 11}, schema)), 0)

    def test_not_object_input(self):
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        errors = _validate_against_schema("not_an_object", schema)
        self.assertGreater(len(errors), 0, "Non-object input should error")

    def test_empty_schema(self):
        errors = _validate_against_schema({"anything": "goes"}, {})
        self.assertEqual(errors, [], "Empty schema should accept anything")

    def test_array_items(self):
        schema = {
            "type": "object",
            "properties": {
                "values": {"type": "array", "items": {"type": "integer"}},
            },
        }
        self.assertEqual(_validate_against_schema({"values": [1, 2, 3]}, schema), [])
        errors = _validate_against_schema({"values": [1, "bad", 3]}, schema)
        self.assertGreater(len(errors), 0, "Array with wrong item type should error")


# ═══════════════════════════════════════════════════════════════════════════
# SOURCE TYPE REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestSourceTypeRegistry(FrappeTestCase):
    """Test the central SourceTypeRegistry."""

    def setUp(self):
        # Reset singleton for clean tests
        SourceTypeRegistry.reset_instance()
        self.registry = SourceTypeRegistry.get_instance()

    def tearDown(self):
        SourceTypeRegistry.reset_instance()

    def test_singleton(self):
        reg1 = SourceTypeRegistry.get_instance()
        reg2 = SourceTypeRegistry.get_instance()
        self.assertIs(reg1, reg2, "get_instance should return same instance")

    def test_register_with_metadata(self):
        def my_handler(binding, doc, resolved):
            return 42

        definition = self.registry.register(
            "test_handler",
            my_handler,
            label="Test Handler",
            description="A test handler for unit tests",
            config_schema={
                "type": "object",
                "required": ["key"],
                "properties": {"key": {"type": "string"}},
            },
            app="test_app",
            batchable=True,
            fingerprint_fn=lambda cfg: cfg.get("key", ""),
            supports_transform=True,
            supports_cache=True,
            default_cache_ttl=300,
        )

        self.assertEqual(definition.source_type, "test_handler")
        self.assertEqual(definition.label, "Test Handler")
        self.assertEqual(definition.app, "test_app")
        self.assertTrue(definition.batchable)
        self.assertTrue(definition.supports_transform)
        self.assertTrue(self.registry.has("test_handler"))

    def test_get_handler(self):
        def my_handler(binding, doc, resolved):
            return "result"

        self.registry.register("test_get", my_handler, label="Test")

        handler = self.registry.get_handler("test_get")
        self.assertIsNotNone(handler)
        result = handler({}, None, {})
        self.assertEqual(result, "result")

    def test_get_nonexistent(self):
        self.assertIsNone(self.registry.get_handler("does_not_exist"))
        self.assertFalse(self.registry.has("does_not_exist"))

    def test_list_all(self):
        self.registry.register("type_a", lambda: None, label="Type A", app="app1")
        self.registry.register("type_b", lambda: None, label="Type B", app="app2")
        self.registry.register("type_c", lambda: None, label="Type C", app="app1")

        all_types = self.registry.list_all()
        self.assertGreaterEqual(len(all_types), 3)

        # App sorting: non-formula_builder first alphabetically
        app1_types = self.registry.list_by_app("app1")
        self.assertEqual(len(app1_types), 2)

    def test_list_source_type_names(self):
        self.registry.register("type_x", lambda: None, label="X")
        self.registry.register("type_y", lambda: None, label="Y")

        names = self.registry.list_source_type_names()
        self.assertIn("type_x", names)
        self.assertIn("type_y", names)

    def test_validate_source_config_valid(self):
        self.registry.register(
            "test_validate",
            lambda: None,
            label="Validate Test",
            config_schema={
                "type": "object",
                "required": ["doctype", "fieldname"],
                "properties": {
                    "doctype": {"type": "string"},
                    "fieldname": {"type": "string"},
                },
            },
        )
        errors = self.registry.validate_source_config(
            "test_validate",
            {"doctype": "Item", "fieldname": "weight_per_unit"},
        )
        self.assertEqual(errors, [], "Valid config should have no errors")

    def test_validate_source_config_missing_required(self):
        self.registry.register(
            "test_validate_2",
            lambda: None,
            label="Validate Test 2",
            config_schema={
                "type": "object",
                "required": ["doctype", "fieldname"],
                "properties": {
                    "doctype": {"type": "string"},
                    "fieldname": {"type": "string"},
                },
            },
        )
        errors = self.registry.validate_source_config(
            "test_validate_2",
            {"doctype": "Item"},  # missing fieldname
        )
        self.assertGreater(len(errors), 0, "Missing required field should error")

    def test_validate_unknown_source_type(self):
        errors = self.registry.validate_source_config("nonexistent", {})
        self.assertGreater(len(errors), 0, "Unknown source type should error")

    def test_validate_binding_config(self):
        self.registry.register(
            "test_binding",
            lambda: None,
            label="Binding Test",
            config_schema={
                "type": "object",
                "required": ["key"],
                "properties": {"key": {"type": "string"}},
            },
        )
        errors = self.registry.validate_binding_config({
            "source_type": "test_binding",
            "source_config": '{"key": "hello"}',
        })
        self.assertEqual(errors, [], "Valid binding should have no errors")

    def test_validate_binding_bad_json(self):
        self.registry.register("test_json", lambda: None, label="JSON Test")
        errors = self.registry.validate_binding_config({
            "source_type": "test_json",
            "source_config": "{bad json",
        })
        self.assertGreater(len(errors), 0, "Bad JSON should error")

    def test_to_dict_excludes_handler(self):
        def handler(): pass
        definition = self.registry.register("test_dict", handler, label="Dict Test")
        d = definition.to_dict()
        self.assertEqual(d["source_type"], "test_dict")
        self.assertEqual(d["label"], "Dict Test")
        self.assertNotIn("handler", d, "to_dict should NOT include the handler callable")

    def test_get_config_schema(self):
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        self.registry.register("test_schema", lambda: None, label="S", config_schema=schema)
        retrieved = self.registry.get_config_schema("test_schema")
        self.assertEqual(retrieved, schema)

    def test_get_stats(self):
        self.registry.register("s1", lambda: None, label="S1", app="app_a", batchable=True)
        self.registry.register("s2", lambda: None, label="S2", app="app_a", batchable=False)
        self.registry.register("s3", lambda: None, label="S3", app="app_b", batchable=True)

        stats = self.registry.get_stats()
        self.assertEqual(stats["total_source_types"], 3)
        self.assertEqual(stats["total_batchable"], 2)
        self.assertIn("app_a", stats["by_app"])
        self.assertEqual(stats["by_app"]["app_a"]["total"], 2)


# ═══════════════════════════════════════════════════════════════════════════
# REGISTER_SOURCE DECORATOR TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRegisterSourceDecorator(FrappeTestCase):
    """Test the @register_source decorator with metadata."""

    def setUp(self):
        SourceTypeRegistry.reset_instance()

    def tearDown(self):
        SourceTypeRegistry.reset_instance()

    def test_decorator_registers_in_registry(self):
        @register_source(
            "deco_test",
            label="Decorator Test",
            description="Testing the decorator",
            config_schema={"type": "object", "required": ["param"], "properties": {"param": {"type": "string"}}},
            app="test_deco_app",
            batchable=True,
            supports_transform=True,
        )
        def _handler(binding, doc, resolved):
            return binding.get("source_config", {}).get("param", "default")

        registry = SourceTypeRegistry.get_instance()
        self.assertTrue(registry.has("deco_test"))

        definition = registry.get("deco_test")
        self.assertEqual(definition.label, "Decorator Test")
        self.assertEqual(definition.app, "test_deco_app")
        self.assertTrue(definition.batchable)
        self.assertTrue(definition.supports_transform)

        # Handler should work
        result = _handler({"source_config": '{"param": "hello"}'}, None, {})
        self.assertEqual(result, "hello")

    def test_decorator_defaults(self):
        @register_source("deco_minimal")
        def _handler(binding, doc, resolved):
            return "ok"

        registry = SourceTypeRegistry.get_instance()
        definition = registry.get("deco_minimal")
        self.assertEqual(definition.label, "Deco Minimal")
        self.assertEqual(definition.app, "formula_builder")
        self.assertFalse(definition.batchable)
        self.assertFalse(definition.supports_transform)


# ═══════════════════════════════════════════════════════════════════════════
# TRANSFORM LAYER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestTransformLayer(FrappeTestCase):
    """Test the _apply_transform function."""

    def test_no_transform_config(self):
        binding = {"variable_name": "x", "source_config": '{"doctype": "Item", "fieldname": "weight"}'}
        result = _apply_transform(42, binding, {})
        self.assertEqual(result, 42, "Without transform config, value should pass through unchanged")

    def test_multiply_transform(self):
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({"doctype": "Item", "fieldname": "price", "transform": {"multiply": 1000}}),
        }
        result = _apply_transform(3.5, binding, {})
        self.assertEqual(result, 3500.0)

    def test_divide_transform(self):
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({"transform": {"divide": 100}}),
        }
        result = _apply_transform(500, binding, {})
        self.assertEqual(result, 5.0)

    def test_add_transform(self):
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({"transform": {"add": 50}}),
        }
        result = _apply_transform(100, binding, {})
        self.assertEqual(result, 150.0)

    def test_round_transform(self):
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({"transform": {"round": 2}}),
        }
        result = _apply_transform(3.14159, binding, {})
        self.assertEqual(result, 3.14)

    def test_cast_int_transform(self):
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({"transform": {"cast": "int"}}),
        }
        result = _apply_transform(3.99, binding, {})
        self.assertEqual(result, 3)
        self.assertIsInstance(result, int)

    def test_chained_transforms(self):
        """Multiply, then round, then cast should work in defined order."""
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({
                "transform": {
                    "multiply": 1.1,
                    "round": 0,
                }
            }),
        }
        result = _apply_transform(100, binding, {})
        self.assertEqual(result, 110.0)  # 100 * 1.1 = 110.0, round to 0 = 110.0

    def test_formula_transform(self):
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({
                "transform": {"formula": "value * 2 + 10"}
            }),
        }
        result = _apply_transform(5, binding, {})
        self.assertEqual(result, 20.0)

    def test_formula_with_resolved_vars(self):
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({
                "transform": {"formula": "value * rate"}
            }),
        }
        result = _apply_transform(100, binding, {"rate": 1.5})
        self.assertEqual(result, 150.0)

    def test_transform_with_none_value(self):
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({"transform": {"multiply": 1000}}),
        }
        result = _apply_transform(None, binding, {})
        self.assertIsNone(result, "None value should remain None")

    def test_transform_dict_config(self):
        """source_config as dict (not JSON string) should also work."""
        binding = {
            "variable_name": "x",
            "source_config": {"transform": {"multiply": 3}},
        }
        result = _apply_transform(7, binding, {})
        self.assertEqual(result, 21.0)

    def test_invalid_formula_fallback(self):
        """If formula eval fails, return original value."""
        binding = {
            "variable_name": "x",
            "source_config": json.dumps({
                "transform": {"formula": "value / 0"}  # division by zero
            }),
        }
        result = _apply_transform(100, binding, {})
        self.assertEqual(result, 100, "Failed transform should return original value")


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION: TRANSFORM IN BATCH RESOLVER
# ═══════════════════════════════════════════════════════════════════════════

class TestTransformInBatchResolver(FrappeTestCase):
    """Test that transforms are applied during batch resolution."""

    def setUp(self):
        SourceTypeRegistry.reset_instance()
        self.resolver = BatchBindingResolver()

    def tearDown(self):
        SourceTypeRegistry.reset_instance()

    def test_constant_with_transform(self):
        """Constant value 50 with transform multiply=10 → 500."""
        bindings = [{
            "variable_name": "price",
            "source_type": "constant",
            "source_config": json.dumps({
                "value": 50,
                "transform": {"multiply": 10, "round": 0},
            }),
            "data_type": "Float",
        }]
        result = self.resolver.resolve_all_batch(bindings)
        self.assertEqual(result["price"], 500.0)

    def test_constant_with_formula_transform(self):
        bindings = [{
            "variable_name": "base",
            "source_type": "constant",
            "source_config": json.dumps({"value": 100}),
            "data_type": "Float",
        }, {
            "variable_name": "final",
            "source_type": "constant",
            "source_config": json.dumps({
                "value": 5,
                "transform": {"formula": "value * 1.5 + 10"},
            }),
            "data_type": "Float",
        }]
        result = self.resolver.resolve_all_batch(bindings)
        self.assertEqual(result["base"], 100.0)
        self.assertEqual(result["final"], 17.5)  # 5 * 1.5 + 10

    def test_batch_resolver_preserves_pre_resolved(self):
        bindings = [{
            "variable_name": "total",
            "source_type": "constant",
            "source_config": json.dumps({"value": 200}),
            "data_type": "Float",
        }]
        result = self.resolver.resolve_all_batch(
            bindings, pre_resolved={"existing": 42}
        )
        self.assertEqual(result["existing"], 42)
        self.assertEqual(result["total"], 200.0)


# ═══════════════════════════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility(FrappeTestCase):
    """Ensure v31 doesn't break v30 functionality."""

    def setUp(self):
        SourceTypeRegistry.reset_instance()

    def tearDown(self):
        SourceTypeRegistry.reset_instance()

    def test_old_register_source_still_works(self):
        """Old-style @register_source from data_source_registry still functions."""
        from formula_builder.api.data_source_registry import (
            register_source as old_register,
            get_handler as old_get_handler,
            _data_source_handlers,
        )

        @old_register("_compat_test_handler")
        def _handler(binding, doc, resolved):
            return "compat_ok"

        # Old dict access works
        self.assertIn("_compat_test_handler", _data_source_handlers)
        self.assertEqual(
            _data_source_handlers["_compat_test_handler"]({}, None, {}),
            "compat_ok",
        )

        # Old get_handler works
        self.assertIsNotNone(old_get_handler("_compat_test_handler"))

        # Cleanup
        del _data_source_handlers["_compat_test_handler"]

    def test_old_validate_binding_still_works(self):
        """validate_binding_source_config from data_source_registry should still work."""
        from formula_builder.api.data_source_registry import validate_binding_source_config

        # Valid constant
        result = validate_binding_source_config({
            "source_type": "constant",
            "source_config": '{"value": 42}',
        })
        self.assertIsNone(result)

        # Missing required field
        result = validate_binding_source_config({
            "source_type": "custom_function",
            "source_config": '{}',
        })
        self.assertIsNotNone(result)
        self.assertIn("module", result)


# ═══════════════════════════════════════════════════════════════════════════
# BUILT-IN HANDLERS METADATA TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestBuiltinHandlersMetadata(FrappeTestCase):
    """Verify all 10 built-in handlers have proper metadata in SourceTypeRegistry."""

    @classmethod
    def setUpClass(cls):
        SourceTypeRegistry.reset_instance()

    @classmethod
    def tearDownClass(cls):
        SourceTypeRegistry.reset_instance()

    def test_all_10_builtin_handlers_registered(self):
        expected_sources = [
            "constant", "linked_doctype_field", "whole_doctype",
            "child_table_aggregate", "global_default", "session_variable",
            "doctype_query", "custom_function", "dynamic_link", "computed",
        ]
        registry = SourceTypeRegistry.get_instance()
        for st in expected_sources:
            self.assertTrue(
                registry.has(st),
                f"Built-in source type '{st}' should be registered with metadata",
            )

    def test_builtin_handlers_have_labels(self):
        registry = SourceTypeRegistry.get_instance()
        for st in ("constant", "doctype_query", "computed"):
            definition = registry.get(st)
            self.assertIsNotNone(definition, f"Should have definition for {st}")
            self.assertIsNotNone(definition.label, f"{st} should have a label")
            self.assertGreater(len(definition.label), 0, f"{st} label should not be empty")

    def test_builtin_handlers_have_schemas(self):
        registry = SourceTypeRegistry.get_instance()
        for st in ("doctype_query", "custom_function", "computed"):
            definition = registry.get(st)
            self.assertIsNotNone(definition.config_schema, f"{st} should have config_schema")
            self.assertIn("required", definition.config_schema)
            self.assertIn("properties", definition.config_schema)

    def test_batchable_handlers(self):
        registry = SourceTypeRegistry.get_instance()
        batchable_sources = {"doctype_query", "linked_doctype_field", "whole_doctype"}
        for st in batchable_sources:
            definition = registry.get(st)
            self.assertTrue(definition.batchable, f"{st} should be batchable")

    def test_non_batchable_handlers(self):
        registry = SourceTypeRegistry.get_instance()
        non_batchable = {"computed", "constant", "session_variable"}
        for st in non_batchable:
            definition = registry.get(st)
            self.assertFalse(definition.batchable, f"{st} should NOT be batchable")

    def test_transformable_handlers(self):
        registry = SourceTypeRegistry.get_instance()
        transformable = {"constant", "doctype_query", "custom_function", "computed"}
        for st in transformable:
            definition = registry.get(st)
            self.assertTrue(definition.supports_transform, f"{st} should support transform")
