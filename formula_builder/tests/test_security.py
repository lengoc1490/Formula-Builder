"""Tests for formula_utils/security.py — AST sandbox, formula validation."""

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
        # x = 5 sau normalize → x == 5 (comparison hợp lệ)
        # Dùng walrus operator := để test chặn assignment
        r1 = self.validator.validate("(x := 5)")
        self.assertFalse(r1.ok)

        r2 = self.validator.validate("(x = 5)")
        self.assertFalse(r2.ok)

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
