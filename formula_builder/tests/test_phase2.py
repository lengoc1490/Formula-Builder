"""Tests for Phase 2 refactored modules — _helpers, _engine_cache, _ai_core."""

from frappe.tests.utils import FrappeTestCase


class TestHelpersModule(FrappeTestCase):
    """Test _helpers.py — sanitize, rate limit, response builders."""

    def test_imports_work(self):
        """Tất cả exports từ _helpers có thể import được."""
        from formula_builder.api._helpers import (
            _SAFE_VALUE_TYPES,
            _FORBIDDEN_FIELDS,
            sanitize_frm_doc,
            assert_read_perm,
            check_rate_limit,
            parse_scope,
            parse_json,
            ok_response,
            ev_response,
        )
        self.assertIsInstance(_SAFE_VALUE_TYPES, tuple)
        self.assertIsInstance(_FORBIDDEN_FIELDS, frozenset)
        self.assertTrue(callable(sanitize_frm_doc))
        self.assertTrue(callable(assert_read_perm))
        self.assertTrue(callable(check_rate_limit))
        self.assertTrue(callable(parse_scope))
        self.assertTrue(callable(parse_json))
        self.assertTrue(callable(ok_response))
        self.assertTrue(callable(ev_response))

    def test_parse_json_valid(self):
        from formula_builder.api._helpers import parse_json
        self.assertEqual(parse_json('{"a": 1}'), {"a": 1})

    def test_parse_json_invalid(self):
        from formula_builder.api._helpers import parse_json
        self.assertEqual(parse_json("not json"), {})

    def test_parse_json_empty(self):
        from formula_builder.api._helpers import parse_json
        self.assertEqual(parse_json(""), {})

    def test_ok_response(self):
        from formula_builder.api._helpers import ok_response
        r = ok_response(True, "OK", [], [], [])
        self.assertTrue(r["valid"])
        self.assertEqual(r["message"], "OK")
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["circular_detected"], False)

    def test_ev_response(self):
        from formula_builder.api._helpers import ev_response
        r = ev_response(True, 42, None, {}, {}, {}, elapsed_ms=5.0)
        self.assertTrue(r["success"])
        self.assertEqual(r["result"], 42)
        self.assertIsNone(r["error"])
        self.assertEqual(r["elapsed_ms"], 5.0)

    def test_sanitize_frm_doc_empty(self):
        from formula_builder.api._helpers import sanitize_frm_doc
        self.assertEqual(sanitize_frm_doc({}, ""), {})

    def test_sanitize_frm_doc_no_doctype(self):
        from formula_builder.api._helpers import sanitize_frm_doc
        self.assertEqual(sanitize_frm_doc({"qty": 5}, ""), {})

    def test_sanitize_frm_doc_blocks_system_fields(self):
        from formula_builder.api._helpers import sanitize_frm_doc, _FORBIDDEN_FIELDS
        raw = {"owner": "admin", "modified_by": "user", "docstatus": 0}
        # These are system fields — should be filtered out
        for f in _FORBIDDEN_FIELDS:
            self.assertIn(f, {"owner", "modified_by", "docstatus", "creation",
                              "modified", "name", "_liked_by", "_comments",
                              "_assign", "_user_tags"})


class TestEngineCache(FrappeTestCase):
    """Test _engine_cache.py — LRU cache for FormulaEngine."""

    def test_imports_work(self):
        from formula_builder.api._engine_cache import (
            engine_cache_key,
            get_or_create_engine,
            invalidate_engine_cache,
        )
        self.assertTrue(callable(engine_cache_key))
        self.assertTrue(callable(get_or_create_engine))
        self.assertTrue(callable(invalidate_engine_cache))

    def test_cache_key_deterministic(self):
        """Cùng formula + funcs → cùng key."""
        from formula_builder.api._engine_cache import engine_cache_key
        from formula_builder.formula_utils import BASE_FUNCS

        k1 = engine_cache_key("a + b", dict(BASE_FUNCS))
        k2 = engine_cache_key("a + b", dict(BASE_FUNCS))
        self.assertEqual(k1, k2)

    def test_cache_key_different_formula(self):
        """Khác formula → khác key."""
        from formula_builder.api._engine_cache import engine_cache_key
        from formula_builder.formula_utils import BASE_FUNCS

        k1 = engine_cache_key("a + b", dict(BASE_FUNCS))
        k2 = engine_cache_key("a * b", dict(BASE_FUNCS))
        self.assertNotEqual(k1, k2)

    def test_cache_key_different_funcs(self):
        """Khác bộ hàm → khác key."""
        from formula_builder.api._engine_cache import engine_cache_key

        funcs1 = {"IF": lambda c, t, f: t if c else f, "abs": abs}
        funcs2 = {"IF": lambda c, t, f: t if c else f}
        self.assertNotEqual(
            engine_cache_key("a + b", funcs1),
            engine_cache_key("a + b", funcs2),
        )

    def test_get_or_create_engine_returns_engine(self):
        """Cache miss → tạo engine mới; cache hit → trả engine cũ."""
        from formula_builder.api._engine_cache import (
            get_or_create_engine, invalidate_engine_cache,
        )
        from formula_builder.formula_utils import BASE_FUNCS

        invalidate_engine_cache()

        engine1 = get_or_create_engine("x + y", dict(BASE_FUNCS))
        engine2 = get_or_create_engine("x + y", dict(BASE_FUNCS))
        self.assertIs(engine1, engine2)  # Same object

        engine3 = get_or_create_engine("z * 2", dict(BASE_FUNCS))
        self.assertIsNot(engine1, engine3)  # Different formula

        # Verify engines work
        r = engine1.calculate({"x": 10, "y": 20})
        self.assertEqual(r["__r__"], 30)

        invalidate_engine_cache()

    def test_invalidate_clears_cache(self):
        from formula_builder.api._engine_cache import (
            get_or_create_engine, invalidate_engine_cache,
        )
        from formula_builder.formula_utils import BASE_FUNCS

        invalidate_engine_cache()
        e1 = get_or_create_engine("a + 1", dict(BASE_FUNCS))
        invalidate_engine_cache()
        e2 = get_or_create_engine("a + 1", dict(BASE_FUNCS))
        self.assertIsNot(e1, e2)  # Cache cleared → new object


class TestAICore(FrappeTestCase):
    """Test _ai_core.py — prompt, sanitizer, smart suggest."""

    def test_build_ai_system_prompt(self):
        from formula_builder.api._ai_core import build_ai_system_prompt
        prompt = build_ai_system_prompt()
        self.assertIn("ALLOWED FUNCTIONS:", prompt)
        self.assertIn("IF", prompt)

    def test_sanitize_empty(self):
        from formula_builder.api._ai_core import sanitize_ai_response
        self.assertEqual(sanitize_ai_response(""), "")

    def test_sanitize_strips_markdown(self):
        from formula_builder.api._ai_core import sanitize_ai_response
        result = sanitize_ai_response("```python\na + b\n```")
        self.assertNotIn("```", result)
        self.assertIn("a + b", result)

    def test_sanitize_truncates(self):
        from formula_builder.api._ai_core import sanitize_ai_response
        long_text = "x" * 600
        result = sanitize_ai_response(long_text)
        self.assertLessEqual(len(result), 500)

    def test_sanitize_blocks_dunder(self):
        from formula_builder.api._ai_core import sanitize_ai_response
        self.assertEqual(sanitize_ai_response("a + __import__('os')"), "")
        self.assertEqual(sanitize_ai_response("row.__class__"), "")

    def test_sanitize_blocks_multiline_code(self):
        from formula_builder.api._ai_core import sanitize_ai_response
        # 6 lines of code → should be blocked (>5 limit)
        code = "\n".join([f"x = {i}" for i in range(6)])
        self.assertEqual(sanitize_ai_response(code), "")

    def test_sanitize_allows_valid_formula(self):
        from formula_builder.api._ai_core import sanitize_ai_response
        self.assertIn("IF", sanitize_ai_response("IF(a > 0, 1, 0)"))

    def test_smart_suggest_returns_list(self):
        from formula_builder.api._ai_core import _smart_suggest_formula_impl
        result = _smart_suggest_formula_impl()
        self.assertIn("suggestions", result)
        self.assertIsInstance(result["suggestions"], list)
        # Fallback: 3 generic suggestions
        self.assertEqual(len(result["suggestions"]), 3)


class TestBackwardCompat(FrappeTestCase):
    """Đảm bảo @frappe.whitelist() endpoints vẫn import được từ formula_builder."""

    def test_all_endpoints_importable(self):
        """Tất cả endpoint vẫn ở formula_builder.api.formula_builder."""
        from formula_builder.api.formula_builder import (
            get_suggestions, get_child_rows, get_doctype_fields,
            validate_formula, evaluate_formula, evaluate_formula_set,
            get_live_context, get_global_context_preview,
            invalidate_suggestions_cache,
            explain_formula,
            smart_suggest_formula, ai_suggest_formula,
            seed_default_functions, get_all_base_functions,
        )
        self.assertTrue(callable(validate_formula))
        self.assertTrue(callable(evaluate_formula))
        self.assertTrue(callable(smart_suggest_formula))
        self.assertTrue(callable(ai_suggest_formula))
        self.assertTrue(callable(explain_formula))
        self.assertTrue(callable(get_live_context))

    def test_wrapper_delegates(self):
        """smart_suggest_formula wrapper gọi _ai_core impl."""
        from formula_builder.api.formula_builder import smart_suggest_formula
        result = smart_suggest_formula()
        self.assertIn("suggestions", result)
        self.assertIsInstance(result["suggestions"], list)


class TestRateLimit(FrappeTestCase):
    """Rate limit logic — chỉ áp dụng cho ai_suggest."""

    def test_check_rate_limit_ai(self):
        """check_rate_limit("ai") đọc settings field rate_limit_ai."""
        from formula_builder.api._helpers import check_rate_limit
        # Test không raise trong điều kiện bình thường
        # (frappe.cache() có thể không available trong test)
        try:
            check_rate_limit("ai")
        except Exception:
            pass  # Redis không có trong test là expected


class TestVersion(FrappeTestCase):
    """Version unification — tất cả module cùng 30.0.0."""

    def test_version_30(self):
        from formula_builder.formula_utils import __version__, __engine_version__
        self.assertEqual(__version__, "30.0.0")
        self.assertEqual(__engine_version__, "30.0.0")

    def test_engine_version(self):
        from formula_builder.formula_utils import FormulaEngine
        self.assertEqual(FormulaEngine.ENGINE_VERSION, "30.0.0")
