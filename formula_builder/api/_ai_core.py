"""AI integration — system prompt, response sanitizer, smart suggest logic, AI proxy.

Tách riêng khỏi formula_builder.py để:
  - Dễ maintain AI prompt template
  - Dễ test response sanitizer
  - Không làm phình file API chính

Các @frappe.whitelist() endpoints vẫn nằm trong formula_builder.py
để giữ nguyên path cho JS calls. File này chỉ chứa internal functions.
"""

from __future__ import annotations

import re as _re

import frappe
from formula_builder.formula_utils import (
    FormulaEngine, FormulaError, FormulaValidationError, BASE_FUNCS
)
from formula_builder.api.settings_cache import get_allowed_funcs

# ============================================================================
# AI SYSTEM PROMPT
# ============================================================================

_AI_SYSTEM_PROMPT = (
    "You are a formula assistant for ERPNext Formula Builder. "
    "Your ONLY job is to convert user requests into valid formula expressions "
    "using the syntax and functions listed below.\n\n"
    "RULES:\n"
    "1. Output ONLY the raw formula expression — no markdown, no code blocks, no explanations.\n"
    "2. Only use functions from the allowed list below. Do NOT invent new functions.\n"
    "3. Use Python-like syntax: IF(cond, true_val, false_val), arithmetic (+, -, *, /), "
    "comparisons (==, !=, <, >, <=, >=), and logical operators (and, or, not).\n"
    "4. Variable names may appear as bare identifiers. Do NOT quote them.\n"
    "5. Strings must use single quotes: 'hello', not \"hello\".\n"
    "6. If the request is unclear, respond with: ERROR: [brief reason]\n"
    "7. Max response length: 500 characters.\n\n"
)

_AI_CLEANUP_PATTERNS = [
    (_re.compile(r'```[a-zA-Z]*\s*\n'), ''),
    (_re.compile(r'\n```'),             ''),
    (_re.compile(r'^```'),              ''),
    (_re.compile(r'^`|`$'),             ''),
]


# ============================================================================
# AI HELPERS
# ============================================================================


def build_ai_system_prompt() -> str:
    """Build system prompt từ Formula Builder Settings (single source of truth)."""
    try:
        allowed = get_allowed_funcs()
    except Exception:
        allowed = dict(BASE_FUNCS)
    func_list = ", ".join(sorted(allowed.keys()))
    return _AI_SYSTEM_PROMPT + f"ALLOWED FUNCTIONS: {func_list}"


def sanitize_ai_response(text: str) -> str:
    """Clean AI response: strip markdown fences, trim, basic safety check.

    NOTE: FormulaEngine.parse() + SecurityValidator là gatekeeper chính.
    """
    if not text:
        return ""

    for pattern, replacement in _AI_CLEANUP_PATTERNS:
        text = pattern.sub(replacement, text)

    text = text.strip()

    if len(text) > 500:
        text = text[:500]

    _hard_block = [
        "__import__", "__class__", "__subclasses__", "__builtins__",
        "__globals__", "__code__", "__dict__", "__bases__", "__mro__",
    ]
    for pattern in _hard_block:
        if pattern in text:
            return ""

    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) > 5:
        return ""

    return text


# ============================================================================
# SMART SUGGEST
# ============================================================================


def _smart_suggest_formula_impl(doctype="", fieldname="", field_label="",
                                 scope_context_json=None):
    """Gợi ý công thức thông minh dựa trên fieldname/label và context."""
    try:
        from formula_builder.api._helpers import parse_scope
        from formula_builder.api.variable_resolver import VariableResolver

        ctx = parse_scope(scope_context_json)
        ctx.current_doctype = ctx.current_doctype or doctype or ""
        resolver = VariableResolver()
        full_ctx = resolver.build_full_context(ctx)

        numeric_fields = [k for k, v in full_ctx.items()
                          if isinstance(v, (int, float)) and not k.startswith("_")]

        suggestions = []
        label_lower = (field_label or fieldname or "").lower()

        if any(kw in label_lower for kw in ("amount", "tiền", "thành tiền", "tổng tiền")):
            if "qty" in full_ctx and "rate" in full_ctx:
                suggestions.append({
                    "label": "Thành tiền = SL × Đơn giá",
                    "formula": "qty * rate",
                    "desc": "Nhân số lượng với đơn giá"
                })
            if "qty" in full_ctx and "rate" in full_ctx:
                suggestions.append({
                    "label": "Thành tiền có VAT",
                    "formula": "qty * rate * (1 + VAT_RATE)" if "VAT_RATE" in full_ctx else "qty * rate * 1.1",
                    "desc": "Thành tiền bao gồm thuế VAT"
                })

        if any(kw in label_lower for kw in ("area", "diện tích", "s_", "sqm")):
            w_key = next((k for k in full_ctx if "width" in k or "rong" in k), None)
            h_key = next((k for k in full_ctx if "height" in k or "cao" in k), None)
            if w_key and h_key:
                suggestions.append({
                    "label": f"Diện tích ({w_key} × {h_key})",
                    "formula": f"({w_key}/1000) * ({h_key}/1000)",
                    "desc": "Diện tích m² từ kích thước mm"
                })
            suggestions.append({
                "label": "Diện tích cửa (mm → m²)",
                "formula": "(custom_width_mm/1000) * (custom_height_mm/1000)",
                "desc": "Chiều rộng × chiều cao đổi sang m²"
            })

        if any(kw in label_lower for kw in ("qty", "số lượng", "sl", "quantity")):
            suggestions.append({
                "label": "Làm tròn 2 chữ số",
                "formula": "round(qty, 2)",
                "desc": "Làm tròn số lượng"
            })

        if any(kw in label_lower for kw in ("price", "đơn giá", "rate", "giá")):
            suggestions.append({
                "label": "Làm tròn đơn giá VNĐ",
                "formula": "round(rate, -3)",
                "desc": "Làm tròn đến hàng nghìn đồng"
            })

        if not suggestions:
            if len(numeric_fields) >= 2:
                a, b = numeric_fields[:2]
                suggestions.append({
                    "label": f"Tổng {a} + {b}",
                    "formula": f"{a} + {b}",
                    "desc": "Cộng hai trường số"
                })
                suggestions.append({
                    "label": f"Tích {a} × {b}",
                    "formula": f"{a} * {b}",
                    "desc": "Nhân hai trường số"
                })
                suggestions.append({
                    "label": f"Chia an toàn {a} / {b}",
                    "formula": f"safe_div({a}, {b}, 0)",
                    "desc": "Chia với mặc định 0 nếu chia cho 0"
                })
            else:
                suggestions = [
                    {"label": "Điều kiện IF",         "formula": "IF(điều_kiện, giá_trị_đúng, giá_trị_sai)", "desc": "Rẽ nhánh theo điều kiện"},
                    {"label": "Chia an toàn",         "formula": "safe_div(tử_số, mẫu_số, 0)",              "desc": "Tránh lỗi chia cho 0"},
                    {"label": "Tham chiếu dòng khác", "formula": "items.line_ref.qty",                       "desc": "Lấy giá trị từ dòng khác"},
                ]

        return {"suggestions": suggestions[:5]}

    except Exception as e:
        frappe.log_error(f"smart_suggest_formula error: {e}", "Formula Builder")
        return {"suggestions": []}


# ============================================================================
# AI SUGGEST (Anthropic API)
# ============================================================================


def _ai_suggest_formula_impl(prompt):
    """Proxy call tới Anthropic API với system prompt bảo mật — key chỉ ở server."""
    from formula_builder.api._helpers import check_rate_limit
    check_rate_limit("ai")

    user_text = str(prompt).strip() if prompt else ""
    if not user_text:
        return {"text": ""}
    if len(user_text) > 2000:
        return {"text": ""}

    try:
        import anthropic
        api_key = frappe.conf.get("anthropic_api_key") or frappe.get_site_config().get("anthropic_api_key")
        if not api_key:
            frappe.log_error("anthropic_api_key chưa cấu hình", "Formula Builder AI")
            return {"text": ""}

        client = anthropic.Anthropic(api_key=api_key)
        settings = frappe.get_single("Formula Builder Settings")
        system_prompt = build_ai_system_prompt()

        msg = client.messages.create(
            model=settings.ai_model or "claude-3-5-sonnet-20241022",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )

        raw_text = msg.content[0].text if msg.content else ""
        sanitized = sanitize_ai_response(raw_text)

        if sanitized:
            try:
                allowed = get_allowed_funcs()
                FormulaEngine(
                    formulas=[{"name": "__ai__", "formula": sanitized}],
                    safe_funcs=allowed,
                )
            except (FormulaError, FormulaValidationError) as e:
                frappe.log_error(
                    f"AI suggested invalid formula rejected: {sanitized} | Error: {e}",
                    "Formula Builder AI",
                )
                return {"text": ""}
            except Exception:
                pass

        return {"text": sanitized}

    except ImportError:
        frappe.log_error("Thiếu thư viện anthropic: pip install anthropic", "Formula Builder AI")
        return {"text": ""}
    except Exception as e:
        frappe.log_error(f"ai_suggest_formula: {e}", "Formula Builder AI")
        return {"text": ""}
