"""Tests for formula_utils/security.py — AST sandbox, formula validation.

Gồm cả tests cho security/safe_eval.py — wrapper validate-1-lần + eval-nhanh
(Pivot RCE 2026-08-16). Class TestSafeEval dùng unittest.TestCase thuần Python
để chạy được cả standalone lẫn trong frappe test runner.
"""

import unittest
from types import SimpleNamespace

from frappe.tests.utils import FrappeTestCase

from formula_builder.formula_utils.security import (
    SecurityValidator,
    FormulaValidator,
)
from formula_builder.formula_utils import (
    BASE_FUNCS,
    FormulaError,
    ValidationResult,
)
from formula_builder.security import safe_eval


class TestSecurityValidator(FrappeTestCase):
    """Test AST-level security checks."""

    def setUp(self):
        self.validator = SecurityValidator(max_depth=5, max_iter_size=1000)

    def test_valid_simple_formula(self):
        """Công thức đơn giản phải pass."""
        import ast
        tree = ast.parse("a + b * 2", mode="eval")
        try:
            self.validator.visit(tree)
        except Exception as e:
            self.fail(f"Valid formula should not raise: {e}")

    def test_blocks_import(self):
        """Chặn lệnh import."""
        import ast
        tree = ast.parse("__import__('os')", mode="eval")
        with self.assertRaises(FormulaError):
            self.validator.visit(tree)

    def test_blocks_eval(self):
        """Chặn eval."""
        import ast
        tree = ast.parse("eval('1+1')", mode="eval")
        with self.assertRaises(FormulaError):
            self.validator.visit(tree)

    def test_blocks_lambda(self):
        """Chặn lambda expression."""
        import ast
        tree = ast.parse("lambda x: x + 1", mode="eval")
        with self.assertRaises(FormulaError):
            self.validator.visit(tree)

    def test_blocks_function_def(self):
        """Chặn function definition."""
        import ast
        try:
            tree = ast.parse("def f(): pass", mode="exec")
        except SyntaxError:
            # mode="eval" blocks def natively — that's fine
            return
        with self.assertRaises(FormulaError):
            self.validator.visit(tree)

    def test_blocks_dangerous_name(self):
        """Chặn các tên nguy hiểm."""
        import ast

        dangerous = [
            "__import__", "globals", "locals", "vars", "dir",
            "__class__", "__bases__", "__subclasses__",
            "__builtins__", "__globals__", "__code__",
            "exec", "compile", "open", "breakpoint",
        ]
        for name in dangerous:
            # Sử dụng name như một biến trong biểu thức
            code = f"{name}"
            try:
                tree = ast.parse(code, mode="eval")
                self.validator.visit(tree)
                self.fail(f"Should have blocked '{name}'")
            except FormulaError:
                pass  # expected

    def test_blocks_deep_nesting(self):
        """Chặn subscript lồng nhau quá sâu."""
        validator = SecurityValidator(max_depth=3, max_iter_size=1000)
        import ast
        # a[1][2][3][4] — 4 levels of subscript
        tree = ast.parse("a[1][2][3][4]", mode="eval")
        with self.assertRaises(FormulaError):
            validator.visit(tree)

    def test_blocks_disallowed_attribute(self):
        """Chặn truy cập attribute không được phép."""
        import ast
        tree = ast.parse("obj.__class__", mode="eval")
        with self.assertRaises(FormulaError):
            self.validator.visit(tree)

    def test_allows_dict_get(self):
        """Cho phép .get() method."""
        import ast
        tree = ast.parse("data.get('key', 0)", mode="eval")
        try:
            self.validator.visit(tree)
        except FormulaError:
            self.fail("dict.get() should be allowed")

    def test_blocks_large_literal_list(self):
        """Chặn list literal quá lớn."""
        validator = SecurityValidator(max_depth=5, max_iter_size=5)
        import ast
        tree = ast.parse("[1, 2, 3, 4, 5, 6]", mode="eval")
        with self.assertRaises(FormulaError):
            validator.visit(tree)


class TestFormulaValidator(FrappeTestCase):
    """Test high-level FormulaValidator."""

    def setUp(self):
        self.allowed_funcs = list(BASE_FUNCS.keys())
        self.validator = FormulaValidator(allowed_functions=self.allowed_funcs)

    def test_valid_simple(self):
        r = self.validator.validate("a + b * 2")
        self.assertTrue(r.ok)

    def test_valid_if(self):
        r = self.validator.validate("IF(a > 0, 1, 0)")
        self.assertTrue(r.ok, msg="; ".join(r.errors))

    def test_valid_nested_if(self):
        r = self.validator.validate("IF(a > 0, IF(b > 0, 1, 2), 0)")
        self.assertTrue(r.ok, msg="; ".join(r.errors))

    def test_empty_formula(self):
        r = self.validator.validate("")
        self.assertFalse(r.ok)
        self.assertTrue(len(r.errors) > 0)

    def test_syntax_error(self):
        r = self.validator.validate("a +* b")
        self.assertFalse(r.ok)

    def test_unknown_function(self):
        r = self.validator.validate("unknown_func(a, b)")
        self.assertFalse(r.ok)
        self.assertTrue(any("không được hỗ trợ" in e for e in r.errors))

    def test_blocks_lambda(self):
        r = self.validator.validate("lambda x: x + 1")
        self.assertFalse(r.ok)

    def test_blocks_assignment(self):
        # x = 5 sau normalize → x == 5 (comparison hợp lệ, không phải assignment)
        # Dùng walrus operator := để test chặn assignment (NamedExpr bị cấm)
        r = self.validator.validate("(x := 5)")
        self.assertFalse(r.ok)

    def test_blocks_import(self):
        r = self.validator.validate("__import__('os').system('ls')")
        self.assertFalse(r.ok)

    def test_warns_no_vars(self):
        r = self.validator.validate("1 + 2")
        self.assertTrue(r.ok)
        self.assertTrue(len(r.warnings) > 0)

    def test_normalize_formula(self):
        r = self.validator.validate("IF(a=1, 2, 3)")
        self.assertTrue(r.ok)
        # normalized version should have ==
        self.assertIn("==", r.normalized)

    def test_validate_batch(self):
        formulas = {
            "a": "1 + 2",
            "b": "x * y",
            "c": "IF(a > b, 1, 0)",
        }
        results = self.validator.validate_batch(formulas)
        self.assertEqual(len(results), 3)
        for r in results.values():
            self.assertTrue(r.ok, msg="; ".join(r.errors))

    def test_known_names_validation(self):
        known = {"qty", "rate", "amount", "vat"}
        r = self.validator.validate("qty * rate", known_names=known)
        self.assertTrue(r.ok)

        r = self.validator.validate("unknown_var * 2", known_names=known)
        self.assertFalse(r.ok)
        self.assertTrue(any("chưa được khai báo" in e for e in r.errors))


class TestFilterExprValidation(FrappeTestCase):
    """Test _validate_filter_expr từ data_source_registry."""

    def setUp(self):
        from formula_builder.api.data_source_registry import _validate_filter_expr
        self.validate = _validate_filter_expr

    def test_valid_comparison(self):
        self.validate("row.qty > 0")  # should not raise

    def test_valid_and_or(self):
        self.validate("row.qty > 0 and row.rate > 1000")

    def test_valid_in(self):
        self.validate("row.status in ('A', 'B')")

    def test_valid_numeric_funcs(self):
        self.validate("len(row.items) > 0")
        self.validate("abs(row.val) > 100")
        self.validate("round(row.val, 2) > 0")
        self.validate("float(row.str_val) > 0")

    def test_valid_literal(self):
        self.validate("True")
        self.validate("row.active == True")

    def test_allows_base_funcs_calls(self):
        """Tất cả hàm trong BASE_FUNCS đều được phép trong filter."""
        self.validate("max(row.val) > 0")       # max ∈ BASE_FUNCS
        self.validate("min(row.a, row.b) > 0")  # min ∈ BASE_FUNCS
        self.validate("sum(row.items) > 0")     # sum ∈ BASE_FUNCS
        self.validate("len(row.items) > 0")     # len ∈ BASE_FUNCS
        self.validate("IF(row.qty > 0, 1, 0)") # IF ∈ BASE_FUNCS
        self.validate("vlookup(row.code, tbl, 2)")  # vlookup ∈ BASE_FUNCS
        self.validate("sumif(row.items, '>0', row.vals)")  # sumif ∈ BASE_FUNCS
        self.validate("safe_div(row.a, row.b, 0) > 0")  # safe_div ∈ BASE_FUNCS

    def test_blocks_complex_call(self):
        """Chỉ chặn method call (obj.method()) và expression call."""
        with self.assertRaises(ValueError):
            self.validate("(lambda x: x)(row.val)")  # expression call

    def test_blocks_import(self):
        with self.assertRaises(ValueError):
            self.validate("__import__('os')")

    def test_blocks_subscript(self):
        with self.assertRaises(ValueError):
            self.validate("row['qty'] > 0")

    def test_blocks_attribute_access(self):
        with self.assertRaises(ValueError):
            self.validate("row.__class__")

    def test_blocks_assignment(self):
        with self.assertRaises(ValueError):
            self.validate("x = 5")

    def test_empty_expression(self):
        self.validate("")  # should not raise
        self.validate("   ")  # should not raise

    def test_syntax_error(self):
        with self.assertRaises(ValueError):
            self.validate("a +* b")

    def test_complex_expression(self):
        """Biểu thức phức tạp với nhiều attribute access + function calls."""
        self.validate("row.qty > 0 and len(row.items) >= 2")
        self.validate("abs(row.a - row.b) > 100")
        self.validate("round(row.amount * row.rate, 2) > 0")
        self.validate("str(row.code) in ('A1', 'B2', 'C3')")

    def test_blocks_dangerous_call(self):
        """Chỉ chặn hàm thực sự nguy hiểm (FORBIDDEN_NAMES hoặc không tồn tại)."""
        # eval, exec, open nằm trong FORBIDDEN_NAMES → bị chặn
        blocked = [
            "eval('1+1')",
            "exec('x=1')",
            "open('/etc/passwd')",
        ]
        for expr in blocked:
            with self.assertRaises(ValueError, msg=f"Should block: {expr}"):
                self.validate(expr)

        # Hàm không tồn tại trong BASE_FUNCS → bị chặn
        with self.assertRaises(ValueError):
            self.validate("nonexistent_func(row.val) > 0")

    def test_allows_base_funcs_complex(self):
        """Các hàm BASE_FUNCS đều được phép: sorted_array, map_key, group_sum..."""
        self.validate("sorted_array(row.items, 'name')")
        self.validate("map_key(row.data, 'value')")
        self.validate("group_sum(row.items, 'cat', 'val')")
        self.validate("count(row.items) > 0")
        self.validate("filter_array(row.items, 'x', 'x > 0')")
        self.validate("date_diff(row.d1, row.d2, 'days') > 30")
        self.validate("isnumber(row.val)")
        self.validate("is_blank(row.name)")
        self.validate("coalesce(row.a, row.b, 0) > 0")

    def test_blocks_method_call(self):
        """Chặn method call kiểu obj.method()."""
        with self.assertRaises(ValueError):
            self.validate("row.items.sort()")

    def test_blocks_lambda(self):
        with self.assertRaises(ValueError):
            self.validate("lambda x: x > 0")


# ═══════════════════════════════════════════════════════════════════════════
# TestSafeEval — security/safe_eval.py (Pivot RCE 2026-08-16)
# ═══════════════════════════════════════════════════════════════════════════

class TestSafeEval(unittest.TestCase):
    """Tests cho security/safe_eval.py — validate 1 lần lúc build, eval nhanh.

    Attack payloads là các vector sandbox-escape đã gặp trong audit RCE:
      - import: __import__('os'), __import__('subprocess')
      - attribute traversal: ().__class__.__mro__, [].__class__.__base__
      - builtin nguy hiểm: eval, exec, open, os.system
      - lambda/class/assign → chặn ở AST hoặc SyntaxError
      - method call, getattr/setattr/delattr traversal
      - subscript khi policy FILTER_POLICY cấm
    """

    # ── Happy path: biểu thức hợp lệ compile + eval đúng ──────────────────

    def test_compile_and_eval_arithmetic(self):
        expr = safe_eval.compile_expression("a + b * 2")
        self.assertEqual(expr.eval({"a": 1, "b": 3}), 7)

    def test_row_attribute_access(self):
        expr = safe_eval.compile_expression("row.qty * row.rate")
        row = SimpleNamespace(qty=3, rate=4.5)
        self.assertEqual(expr.eval({"row": row}), 13.5)

    def test_dict_subscript_allowed_by_default(self):
        expr = safe_eval.compile_expression("data['qty'] + data['rate']")
        self.assertEqual(expr.eval({"data": {"qty": 2, "rate": 5}}), 7)

    def test_boolean_condition(self):
        expr = safe_eval.compile_expression("a > 0 and b < 10")
        self.assertTrue(expr.eval({"a": 5, "b": 3}))
        self.assertFalse(expr.eval({"a": 0, "b": 3}))

    def test_function_whitelist_allows_known(self):
        expr = safe_eval.compile_expression(
            "round(x, 2) + int(y)",
            allowed_functions=("round", "int"),
        )
        # Caller inject hàm vào scope (eval không có builtin thật)
        self.assertEqual(
            expr.eval({"x": 1.234, "y": 3.9, "round": round, "int": int}),
            4.23,  # round(1.234, 2)=1.23 + int(3.9)=3
        )

    def test_if_function_call_with_scope_func(self):
        expr = safe_eval.compile_expression(
            "IF(a > 0, b, c)", allowed_functions=("IF",)
        )
        self.assertEqual(
            expr.eval({"a": 1, "b": 10, "c": 20, "IF": lambda c, t, f: t if c else f}),
            10,
        )

    def test_source_property(self):
        expr = safe_eval.compile_expression("  a + 1  ")
        self.assertEqual(expr.source, "a + 1")

    # ── Attack payloads bị chặn ở compile ─────────────────────────────────

    def test_blocks_import_call(self):
        for payload in ("__import__('os')", "__import__('subprocess')"):
            with self.assertRaises(ValueError, msg=f"Should block: {payload}"):
                safe_eval.compile_expression(payload)

    def test_blocks_eval_and_exec(self):
        for payload in ("eval('1+1')", "exec('x=1')"):
            with self.assertRaises(ValueError, msg=f"Should block: {payload}"):
                safe_eval.compile_expression(payload)

    def test_blocks_open_and_os(self):
        for payload in ("open('/etc/passwd')", "os.system('id')", "sys.exit()"):
            with self.assertRaises(ValueError, msg=f"Should block: {payload}"):
                safe_eval.compile_expression(payload)

    def test_blocks_dunder_attribute_traversal(self):
        payloads = [
            "().__class__.__mro__",
            "[].__class__.__base__",
            "(1).__class__",
            "obj.__globals__",
        ]
        for payload in payloads:
            with self.assertRaises(ValueError, msg=f"Should block: {payload}"):
                safe_eval.compile_expression(payload)

    def test_blocks_getattr_setattr_traversal(self):
        for payload in ("getattr(obj, 'x')", "setattr(obj, 'x', 1)", "delattr(obj, 'x')"):
            with self.assertRaises(ValueError, msg=f"Should block: {payload}"):
                safe_eval.compile_expression(payload)

    def test_blocks_lambda(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("lambda x: x > 0")

    def test_blocks_import_statement(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("import os")

    def test_blocks_assignment(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("a = 1")

    def test_blocks_method_call(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("'abc'.upper()")

    def test_blocks_complex_call(self):
        # call qua subscript / không phải Name hay Attribute
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("funcs[0]('x')")

    def test_blocks_walrus(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("(x := 1)")

    # ── Policy ────────────────────────────────────────────────────────────

    def test_filter_policy_blocks_subscript(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("row['qty'] > 1", policy=safe_eval.FILTER_POLICY)

    def test_filter_policy_allows_attribute(self):
        expr = safe_eval.compile_expression(
            "row.qty > 1 and row.rate < 10", policy=safe_eval.FILTER_POLICY
        )
        self.assertTrue(expr.eval({"row": SimpleNamespace(qty=5, rate=3)}))

    def test_condition_policy_allows_subscript(self):
        expr = safe_eval.compile_expression("data['qty'] > 1", policy=safe_eval.CONDITION_POLICY)
        self.assertTrue(expr.eval({"data": {"qty": 5}}))

    def test_transform_policy_arithmetic(self):
        expr = safe_eval.compile_expression("value * 2 + 1", policy=safe_eval.TRANSFORM_POLICY)
        self.assertEqual(expr.eval({"value": 5}), 11)

    def test_allowed_attributes_whitelist(self):
        pol = safe_eval.ExpressionPolicy(allowed_attributes=("qty",))
        expr = safe_eval.compile_expression("row.qty", policy=pol)
        self.assertEqual(expr.eval({"row": SimpleNamespace(qty=7)}), 7)
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("row.rate", policy=pol)

    def test_forbid_attribute(self):
        pol = safe_eval.ExpressionPolicy(allow_attribute=False)
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("row.qty", policy=pol)

    def test_subscript_depth_limit(self):
        pol = safe_eval.ExpressionPolicy(max_subscript_depth=2)
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("a[0][1][2]", policy=pol)
        # depth 2 chạy được
        expr = safe_eval.compile_expression("a[0][1]", policy=pol)
        self.assertEqual(expr.eval({"a": [[10, 20]]}), 20)

    def test_function_whitelist_blocks_unknown(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression(
                "calc_total(row) + 1", allowed_functions=("round", "int")
            )

    # ── Sandbox isolation lúc eval ────────────────────────────────────────

    def test_eval_scope_has_no_builtins(self):
        # `len` không bị cấm ở compile, nhưng eval KHÔNG có builtin thật
        # (globals cố định {"__builtins__": {}}) → phải inject từ scope.
        expr = safe_eval.compile_expression("len([1, 2, 3])")
        with self.assertRaises(NameError):
            expr.eval({})
        self.assertEqual(expr.eval({"len": len}), 3)

    def test_eval_uses_only_injected_names(self):
        expr = safe_eval.compile_expression("a + b")
        self.assertEqual(expr.eval({"a": 1, "b": 2}), 3)
        with self.assertRaises(NameError):
            expr.eval({"a": 1})  # thiếu b → NameError, không fallback builtin

    # ── Cache ─────────────────────────────────────────────────────────────

    def test_compile_cache_reuse(self):
        safe_eval.clear_cache()
        e1 = safe_eval.compile_expression("a * 2")
        e2 = safe_eval.compile_expression("a * 2")
        self.assertIs(e1, e2)

    def test_clear_cache(self):
        safe_eval.clear_cache()
        e1 = safe_eval.compile_expression("a + 1")
        safe_eval.clear_cache()
        e2 = safe_eval.compile_expression("a + 1")
        self.assertIsNot(e1, e2)

    def test_cache_key_respects_policy_and_functions(self):
        safe_eval.clear_cache()
        e1 = safe_eval.compile_expression("round(x, 1)", allowed_functions=("round",))
        e2 = safe_eval.compile_expression("round(x, 1)")  # không whitelist
        self.assertIsNot(e1, e2)
        e3 = safe_eval.compile_expression("round(x, 1)", allowed_functions=("round",))
        self.assertIs(e1, e3)

    # ── Input validation ──────────────────────────────────────────────────

    def test_none_rejected(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression(None)

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("   ")

    def test_syntax_error_rejected(self):
        with self.assertRaises(ValueError):
            safe_eval.compile_expression("a +* 2")

    def test_validate_expression_no_compile(self):
        # hợp lệ → không raise
        safe_eval.validate_expression("row.qty * row.rate")
        # bất hợp lệ → raise ValueError
        with self.assertRaises(ValueError):
            safe_eval.validate_expression("__import__('os')")

    # ── validate_formula_sources (gate cache-restore) ─────────────────────

    def test_validate_formula_sources_accepts_valid(self):
        safe_eval.validate_formula_sources(
            {
                "a": "1 + 2",
                "b": "a * 3 + IF(a > 0, 10, 0)",
            },
            runtime_env={},
        )

    def test_validate_formula_sources_rejects_malicious(self):
        for expr in ("__import__('os').system('id')", "eval('1+1')", "a + b"):
            with self.subTest(expr=expr):
                if expr == "a + b":
                    continue  # hợp lệ
                with self.assertRaises(Exception):
                    safe_eval.validate_formula_sources({"a": expr}, runtime_env={})
