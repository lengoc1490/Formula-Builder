# ═══════════════════════════════════════════════════════════════════════════
# settings_cache.py  —  Single Source of Truth cho Formula Builder Settings
# ═══════════════════════════════════════════════════════════════════════════
"""
Module duy nhất chịu trách nhiệm đọc và cache Formula Builder Settings.

Trước đây logic này bị duplicate ở 3 nơi:
  - api/formula_builder.py      (_load_settings / _allowed / _max_len)
  - api/data_source_registry.py (_allowed_funcs)
  - api/variable_resolver.py    (VariableResolver._allowed_funcs)

Sau refactor: tất cả import từ module này.

QUAN TRỌNG: Cache chỉ lưu tên hàm (strings) — KHÔNG lưu function references.
BASE_FUNCS chứa lambda functions không pickle-able, nên phải
reconstruct dict từ tên hàm sau khi đọc cache.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

import frappe
from formula_builder.formula_utils import BASE_FUNCS

_CACHE_KEY = "formula_builder_settings:v3"
_CACHE_TTL = 300  # 5 phút


# ── Internal: DB read (returns JSON-serializable data only) ───────────────────

def _read_db() -> Tuple[List[dict], List[str], int]:
    """
    Đọc Formula Builder Settings từ DB.
    Returns:
        funcs_json: [{"name": "IF", "alias": ""}, ...]  — JSON-safe
        disabled:   ["now", "today", ...]               — JSON-safe
        max_len:    int
    """
    try:
        settings = frappe.get_single("Formula Builder Settings")
        rows = settings.get("allowed_functions") or []
        max_len = settings.max_formula_length or 2000

        funcs_json: List[dict] = []
        disabled: List[str] = []

        for r in rows:
            # JSON field là "enabled" — getattr an toàn với fallback
            is_enabled = bool(getattr(r, "enabled", getattr(r, "is_enabled", True)))
            func_name = getattr(r, "func_name", "") or ""

            if is_enabled:
                alias = getattr(r, "alias", None) or ""
                funcs_json.append({"name": func_name, "alias": alias})
            else:
                disabled.append(func_name)

        return funcs_json, disabled, max_len

    except Exception:
        # Fallback: tất cả BASE_FUNCS được bật
        return (
            [{"name": k, "alias": ""} for k in BASE_FUNCS],
            [],
            2000,
        )


# ── Reconstruct function dict từ tên ──────────────────────────────────────────

def _build_allowed(funcs_json: List[dict]) -> Dict:
    """
    Từ danh sách {"name": ..., "alias": ...}, tạo dict {name: callable}.
    Chỉ include function có trong BASE_FUNCS.
    """
    allowed: Dict = {}
    for rec in funcs_json:
        name = rec.get("name", "")
        alias = rec.get("alias", "")
        if name in BASE_FUNCS:
            allowed[name] = BASE_FUNCS[name]
        if alias and alias.strip() and name in BASE_FUNCS:
            allowed[alias.strip()] = BASE_FUNCS[name]

    if not allowed:
        allowed = dict(BASE_FUNCS)
    return allowed


# ── Public API ────────────────────────────────────────────────────────────────

def get_settings() -> Tuple[Dict, Set, int]:
    """
    Trả về (allowed_funcs_dict, disabled_funcs_set, max_formula_length).
    Cache chỉ lưu tên hàm (strings) để tránh pickle error với lambda.
    """
    cached = frappe.cache().get_value(_CACHE_KEY)
    if cached is not None:
        allowed = _build_allowed(cached["funcs"])
        disabled = set(cached.get("disabled") or [])
        max_len = cached.get("max_len", 2000)
        return allowed, disabled, max_len

    funcs_json, disabled_list, max_len = _read_db()
    allowed = _build_allowed(funcs_json)

    # Cache JSON-serializable data only — no function references
    try:
        frappe.cache().set_value(
            _CACHE_KEY,
            {"funcs": funcs_json, "disabled": disabled_list, "max_len": max_len},
            expires_in_sec=_CACHE_TTL,
        )
    except Exception:
        # Redis có thể unavailable — không crash, trả kết quả không cache
        pass

    return allowed, set(disabled_list), max_len


def get_allowed_funcs() -> Dict:
    """Trả về {func_name: callable} các hàm được phép."""
    return get_settings()[0]


def get_disabled_funcs() -> Set:
    """Trả về set tên các hàm bị tắt."""
    return get_settings()[1]


def get_max_formula_length() -> int:
    """Trả về giới hạn độ dài công thức (ký tự)."""
    return get_settings()[2]


def invalidate_cache() -> None:
    """Xóa cache — gọi khi Formula Builder Settings thay đổi."""
    try:
        frappe.cache().delete_value(_CACHE_KEY)
    except Exception:
        pass
