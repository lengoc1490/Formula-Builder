"""Engine LRU cache — tránh khởi tạo FormulaEngine trùng lặp.

Dùng trong evaluate_formula() và explain_formula().
Cache key = SHA-256(formula) + SHA-256(sorted func names).
"""

from __future__ import annotations

import hashlib
from typing import Dict

from formula_builder.formula_utils import FormulaEngine

_ENGINE_CACHE: Dict[str, FormulaEngine] = {}
_ENGINE_CACHE_MAX = 128


def engine_cache_key(formula: str, allowed_funcs: dict) -> str:
    """Tạo cache key từ formula + fingerprint của allowed functions."""
    formula_hash = hashlib.sha256(formula.encode("utf-8")).hexdigest()
    func_names = ",".join(sorted(allowed_funcs.keys()))
    func_hash = hashlib.sha256(func_names.encode("utf-8")).hexdigest()
    return f"{formula_hash}:{func_hash}"


def get_or_create_engine(formula: str, allowed_funcs: dict) -> FormulaEngine:
    """Lấy FormulaEngine từ cache hoặc tạo mới. Giới hạn 128 entries (LRU-style)."""
    key = engine_cache_key(formula, allowed_funcs)

    if key in _ENGINE_CACHE:
        return _ENGINE_CACHE[key]

    # Evict oldest entry nếu cache đầy
    if len(_ENGINE_CACHE) >= _ENGINE_CACHE_MAX:
        oldest_key = next(iter(_ENGINE_CACHE))
        del _ENGINE_CACHE[oldest_key]

    engine = FormulaEngine(
        formulas=[{"name": "__r__", "formula": formula}],
        safe_funcs=allowed_funcs,
    )
    _ENGINE_CACHE[key] = engine
    return engine


def invalidate_engine_cache() -> None:
    """Xóa toàn bộ engine cache — gọi khi settings thay đổi."""
    _ENGINE_CACHE.clear()
