"""Shared helpers for Formula Builder API — sanitize, rate limit, response builders.

Các module API khác (formula_builder.py, formula_table_api.py) import từ đây
để tránh duplicate code.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import frappe

# ============================================================================
# CONSTANTS
# ============================================================================

_SAFE_VALUE_TYPES = (int, float, str, bool, type(None))
_FORBIDDEN_FIELDS = frozenset({
    "owner", "modified_by", "docstatus", "creation", "modified",
    "name", "_liked_by", "_comments", "_assign", "_user_tags"
})

# ============================================================================
# SANITIZE
# ============================================================================


def sanitize_frm_doc(raw: dict, doctype: str) -> dict:
    """Lọc frm_doc từ JS – chỉ giữ field có trong meta, loại system fields."""
    if not doctype:
        return {}
    try:
        meta = frappe.get_meta(doctype)
        allowed_scalars = {
            f.fieldname for f in meta.fields
            if f.fieldtype not in ("Section Break", "Column Break", "Tab Break",
                                   "Heading", "HTML", "Button", "Image",
                                   "Attach", "Attach Image", "Barcode", "Signature")
        }
        allowed_tables = {
            f.fieldname: f.options for f in meta.fields
            if f.fieldtype in ("Table", "Table MultiSelect") and f.options
        }
    except Exception:
        return {}

    result = {}
    for k, v in raw.items():
        if k.startswith("__") or k in _FORBIDDEN_FIELDS:
            continue
        if k in allowed_scalars and isinstance(v, _SAFE_VALUE_TYPES):
            result[k] = v
        elif k in allowed_tables and isinstance(v, list):
            child_doctype = allowed_tables[k]
            try:
                child_meta = frappe.get_meta(child_doctype)
                child_allowed = {f.fieldname for f in child_meta.fields
                                 if f.fieldtype not in ("Section Break", "Column Break", "Tab Break",
                                                        "Heading", "HTML", "Button")}
            except Exception:
                child_allowed = set()
            clean_rows = []
            for row in v:
                if not isinstance(row, dict):
                    continue
                clean_row = {
                    rk: rv for rk, rv in row.items()
                    if not rk.startswith("__")
                    and rk not in _FORBIDDEN_FIELDS
                    and (not child_allowed or rk in child_allowed or rk in ("idx", "name"))
                    and isinstance(rv, _SAFE_VALUE_TYPES)
                }
                clean_rows.append(clean_row)
            result[k] = clean_rows
    return result


# ============================================================================
# PERMISSION
# ============================================================================


def assert_read_perm(doctype: str, docname: str):
    """Kiểm tra quyền đọc document, throw PermissionError nếu không có."""
    if not doctype or not docname or docname.startswith("new-"):
        return
    if not frappe.has_permission(doctype, "read", docname):
        frappe.throw(
            f"Không có quyền truy cập {doctype} {docname}",
            frappe.PermissionError,
        )


# ============================================================================
# RATE LIMIT (chỉ dùng cho ai_suggest)
# ============================================================================


def check_rate_limit(action: str, limit: int = 10, window: int = 60):
    """Kiểm tra rate limit — CHỈ dùng cho ai_suggest (gọi external API).

    evaluate và validate KHÔNG bị rate limit vì:
      - Đã có auth (@frappe.whitelist)
      - Đã có AST sandbox + __builtins__={}
      - Đã có budget guard (max_operations)
      - Là thao tác tương tác của user, read-only, không side effect
    """
    user = frappe.session.user or "Guest"
    key = f"fb_rl:{user}:{action}"
    try:
        new_count = frappe.cache().incr(key, 1)
        if new_count == 1:
            frappe.cache().expire(key, window)

        try:
            setting_limit = frappe.db.get_single_value(
                "Formula Builder Settings", f"rate_limit_{action}"
            )
            if setting_limit and setting_limit > 0:
                limit = int(setting_limit)
        except Exception:
            pass

        if new_count > limit:
            frappe.throw(
                f"⏳ Tạm dừng: đã vượt {limit} yêu cầu ({action}) "
                f"trong {window}s. Vui lòng đợi giây lát rồi thử lại.",
                frappe.TooManyRequestsError,
            )
    except frappe.TooManyRequestsError:
        raise
    except Exception:
        pass


# ============================================================================
# SCOPE & JSON HELPERS
# ============================================================================


def parse_scope(s=None):
    """Parse scope context từ JSON string → ScopeContext."""
    from formula_builder.api.variable_resolver import ScopeContext
    return ScopeContext.from_dict(json.loads(s or "{}") if s else {})


def parse_json(s):
    """Safe JSON parse — trả về dict rỗng khi lỗi."""
    try:
        return json.loads(s or "{}") or {}
    except Exception:
        return {}


# ============================================================================
# RESPONSE BUILDERS
# ============================================================================


def ok_response(valid, msg, errors, warnings, markers,
                normalized=None, circular_detected=False):
    """Trả response validate_formula."""
    return {
        "valid":             valid,
        "message":           msg,
        "errors":            errors,
        "warnings":          warnings,
        "markers":           markers,
        "normalized":        normalized,
        "circular_detected": circular_detected,
    }


def ev_response(success, result, error, explain, ctx_used, cross_ref, elapsed_ms=None):
    """Trả response evaluate_formula."""
    return {
        "success":      success,
        "result":       result,
        "error":        error,
        "explain":      explain,
        "context_used": ctx_used,
        "cross_ref":    cross_ref,
        "elapsed_ms":   elapsed_ms,
    }
