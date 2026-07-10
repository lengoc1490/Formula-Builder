"""Tests for formula_utils/engine_core.py — dependency resolution, calculation."""

from frappe.tests.utils import FrappeTestCase

from formula_builder.formula_utils import (
    FormulaEngine,
    FormulaError,
    FormulaBudgetExceeded,
    MODE_RAISE,
    MODE_NULL,
    MODE_DEFAULT,
    BASE_FUNCS,
)


class TestFormulaEngineBasic(FrappeTestCase):
    """Basic calculation tests."""

    def test_simple_arithmetic(self):
        engine = FormulaEngine(
            formulas=[{"name": "x", "formula": "a + b"}],
            safe_funcs=BASE_FUNCS,
        )
        result = engine.calculate({"a": 10, "b": 20})
        self.assertEqual(result["x"], 30)

    def test_multi_formula_dependencies(self):
        engine = FormulaEngine(
            formulas=[
                {"name": "subtotal", "formula": "qty * rate"},
                {"name": "vat", "formula": "subtotal * vat_rate"},
                {"name": "total", "formula": "subtotal + vat"},
            ],
            safe_funcs=BASE_FUNCS,
        )
        result = engine.calculate({"qty": 10, "rate": 100, "vat_rate": 0.1})
        self.assertEqual(result["subtotal"], 1000)
        self.assertEqual(result["vat"], 100)
        self.assertEqual(result["total"], 1100)

    def test_if_condition(self):
        engine = FormulaEngine(
            formulas=[{"name": "result", "formula": "IF(x > 10, 'high', 'low')"}],
            safe_funcs=BASE_FUNCS,
        )
        self.assertEqual(engine.calculate({"x": 20})["result"], "high")
        self.assertEqual(engine.calculate({"x": 5})["result"], "low")

    def test_nested_if(self):
        engine = FormulaEngine(
            formulas=[{"name": "grade", "formula": "IF(score >= 80, 'A', IF(score >= 60, 'B', 'C'))"}],
            safe_funcs=BASE_FUNCS,
        )
        self.assertEqual(engine.calculate({"score": 90})["grade"], "A")
        self.assertEqual(engine.calculate({"score": 70})["grade"], "B")
        self.assertEqual(engine.calculate({"score": 50})["grade"], "C")

    def test_division(self):
        engine = FormulaEngine(
            formulas=[{"name": "ratio", "formula": "a / b"}],
            safe_funcs=BASE_FUNCS,
        )
        result = engine.calculate({"a": 100, "b": 4})
        self.assertEqual(result["ratio"], 25)

    def test_division_by_zero_mode_null(self):
        engine = FormulaEngine(
            formulas=[{"name": "ratio", "formula": "a / b"}],
            safe_funcs=BASE_FUNCS,
            on_error="null",
        )
        result = engine.calculate({"a": 100, "b": 0})
        self.assertIsNone(result["ratio"])

    def test_division_by_zero_mode_default(self):
        engine = FormulaEngine(
            formulas=[{"name": "ratio", "formula": "a / b"}],
            safe_funcs=BASE_FUNCS,
            on_error="default",
            default_value=0,
        )
        result = engine.calculate({"a": 100, "b": 0})
        self.assertEqual(result["ratio"], 0)

    def test_mode_raise(self):
        engine = FormulaEngine(
            formulas=[{"name": "ratio", "formula": "1 / 0"}],
            safe_funcs=BASE_FUNCS,
            on_error="raise",
        )
        with self.assertRaises(FormulaError):
            engine.calculate({})

    def test_empty_formulas(self):
        engine = FormulaEngine(formulas=[], safe_funcs=BASE_FUNCS)
        result = engine.calculate({"a": 1})
        self.assertEqual(result, {})

    def test_string_concat(self):
        engine = FormulaEngine(
            formulas=[{"name": "full", "formula": "concat(first, ' ', last)"}],
            safe_funcs=BASE_FUNCS,
        )
        result = engine.calculate({"first": "John", "last": "Doe"})
        self.assertEqual(result["full"], "John Doe")

    def test_safe_div(self):
        engine = FormulaEngine(
            formulas=[{"name": "r", "formula": "safe_div(a, b, 0)"}],
            safe_funcs=BASE_FUNCS,
        )
        result = engine.calculate({"a": 100, "b": 0})
        self.assertEqual(result["r"], 0)

    def test_round(self):
        engine = FormulaEngine(
            formulas=[{"name": "r", "formula": "round(3.14159, 2)"}],
            safe_funcs=BASE_FUNCS,
        )
        result = engine.calculate({})
        self.assertEqual(result["r"], 3.14)

    def test_max(self):
        engine = FormulaEngine(
            formulas=[{"name": "m", "formula": "max(a, b, c)"}],
            safe_funcs=BASE_FUNCS,
        )
        result = engine.calculate({"a": 5, "b": 10, "c": 3})
        self.assertEqual(result["m"], 10)


class TestTopologicalSort(FrappeTestCase):
    """Test dependency ordering and circular detection."""

    def test_linear_chain(self):
        engine = FormulaEngine(
            formulas=[
                {"name": "a", "formula": "1 + 1"},
                {"name": "b", "formula": "a * 2"},
                {"name": "c", "formula": "b + 3"},
            ],
            safe_funcs=BASE_FUNCS,
        )
        self.assertEqual(engine._topo_order, ["a", "b", "c"])

    def test_diamond_dependency(self):
        engine = FormulaEngine(
            formulas=[
                {"name": "a", "formula": "x + y"},
                {"name": "b", "formula": "a * 2"},
                {"name": "c", "formula": "a + 3"},
                {"name": "d", "formula": "b + c"},
            ],
            safe_funcs=BASE_FUNCS,
        )
        # a must come before b and c; b and c before d
        topo = engine._topo_order
        self.assertEqual(topo[0], "a")
        self.assertEqual(topo[-1], "d")
        self.assertLess(topo.index("a"), topo.index("b"))
        self.assertLess(topo.index("a"), topo.index("c"))
        self.assertLess(topo.index("b"), topo.index("d"))
        self.assertLess(topo.index("c"), topo.index("d"))

    def test_circular_dependency_detected(self):
        with self.assertRaises(FormulaError):
            FormulaEngine(
                formulas=[
                    {"name": "a", "formula": "b + 1"},
                    {"name": "b", "formula": "a + 1"},
                ],
                safe_funcs=BASE_FUNCS,
            )

    def test_self_reference(self):
        with self.assertRaises(FormulaError):
            FormulaEngine(
                formulas=[{"name": "a", "formula": "a + 1"}],
                safe_funcs=BASE_FUNCS,
            )


class TestIncrementalContext(FrappeTestCase):
    """Test incremental evaluation."""

    def test_create_and_calculate_incremental(self):
        engine = FormulaEngine(
            formulas=[
                {"name": "a", "formula": "x * 2"},
                {"name": "b", "formula": "a + y"},
            ],
            safe_funcs=BASE_FUNCS,
        )
        ctx = engine.create_context({"x": 10, "y": 5})
        self.assertTrue(ctx.initialized)
        self.assertEqual(ctx.outputs["a"], 20)
        self.assertEqual(ctx.outputs["b"], 25)

        # Chỉ thay đổi y
        result, stats = engine.calculate_incremental(ctx, {"y": 100}, return_stats=True)
        self.assertEqual(result["a"], 20)   # unchanged
        self.assertEqual(result["b"], 120)  # recalculated
        self.assertEqual(stats.changed_inputs, 1)
        self.assertEqual(stats.recalculated_nodes, 1)
        self.assertEqual(stats.skipped_nodes, 1)

    def test_stale_context_raises(self):
        engine1 = FormulaEngine(
            formulas=[{"name": "a", "formula": "x + 1"}],
            safe_funcs=BASE_FUNCS,
        )
        ctx = engine1.create_context({"x": 5})

        # Create a DIFFERENT engine (different formula)
        engine2 = FormulaEngine(
            formulas=[{"name": "a", "formula": "x + 2"}],  # different formula
            safe_funcs=BASE_FUNCS,
        )

        with self.assertRaises(FormulaError):
            engine2.calculate_incremental(ctx, {"x": 10})

    def test_no_change_skips_all(self):
        engine = FormulaEngine(
            formulas=[
                {"name": "a", "formula": "x + 1"},
                {"name": "b", "formula": "y + 1"},
            ],
            safe_funcs=BASE_FUNCS,
        )
        ctx = engine.create_context({"x": 10, "y": 20})
        result, stats = engine.calculate_incremental(ctx, {}, return_stats=True)
        self.assertEqual(stats.changed_inputs, 0)
        self.assertEqual(stats.skipped_nodes, 2)


class TestBudgetGuard(FrappeTestCase):
    """Test operation budget limiting."""

    def test_budget_exceeded(self):
        # Budget reset MỖI LẦN calculate() → cần nhiều ops trong 1 call
        engine = FormulaEngine(
            formulas=[
                {"name": "a", "formula": "x + 1"},
                {"name": "b", "formula": "a + 1"},
                {"name": "c", "formula": "b + 1"},
                {"name": "d", "formula": "c + 1"},
            ],
            safe_funcs=BASE_FUNCS,
            max_operations=3,  # Chỉ cho phép 3 ops → sẽ exceed ở formula thứ 4
        )
        with self.assertRaises(FormulaBudgetExceeded):
            engine.calculate({"x": 1})

    def test_budget_reset_per_call(self):
        engine = FormulaEngine(
            formulas=[{"name": "a", "formula": "x + 1"}],
            safe_funcs=BASE_FUNCS,
            max_operations=2,
        )
        # Mỗi calculate.reset counter mới
        for _ in range(5):
            result = engine.calculate({"x": 1})
            self.assertEqual(result["a"], 2)


class TestRecalculateFull(FrappeTestCase):
    """Test manual full recalculation."""

    def test_recalculate_then_incremental(self):
        engine = FormulaEngine(
            formulas=[
                {"name": "a", "formula": "x * 2"},
                {"name": "b", "formula": "a + y"},
            ],
            safe_funcs=BASE_FUNCS,
        )
        ctx = engine.create_context({"x": 10, "y": 5})
        self.assertEqual(ctx.outputs, {"a": 20, "b": 25})

        # Full recalc với new inputs
        out = engine.recalculate_full(ctx, {"x": 100, "y": 50})
        self.assertEqual(out, {"a": 200, "b": 250})

        # Incremental sau đó
        result, stats = engine.calculate_incremental(ctx, {"x": 1}, return_stats=True)
        self.assertEqual(result["a"], 2)
        self.assertEqual(result["b"], 52)
        self.assertEqual(stats.recalculated_nodes, 2)  # a + b đều recalc
