"""Engine LRU cache — tránh khởi tạo FormulaEngine trùng lặp.

v31: Sử dụng engine serialization (to_cache_bytes/from_cache_bytes)
để cache toàn bộ engine state thay vì chỉ cache 1 formula đơn lẻ.
Cho phép khởi tạo engine từ cache trong ~5ms thay vì ~100ms (21x speedup).

Cache key = SHA-256(serialized formulas JSON) + SHA-256(sorted func names).
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Dict, Optional

from formula_builder.formula_utils import FormulaEngine

_LOCK = threading.Lock()
_ENGINE_CACHE: Dict[str, bytes] = {}  # key -> marshalled engine bytes
_ENGINE_CACHE_MAX = 128


def _make_batch_key(formulas: list, allowed_funcs: dict) -> str:
    """Tạo cache key từ toàn bộ formula set + fingerprint của allowed functions."""
    sorted_f = sorted(formulas, key=lambda f: f["name"])
    formula_json = json.dumps(sorted_f, sort_keys=True, ensure_ascii=False)
    formula_hash = hashlib.sha256(formula_json.encode("utf-8")).hexdigest()
    func_names = ",".join(sorted(allowed_funcs.keys()))
    func_hash = hashlib.sha256(func_names.encode("utf-8")).hexdigest()
    return f"{formula_hash}:{func_hash}"


def get_cached_engine(
    formulas: list,
    allowed_funcs: Optional[dict] = None,
) -> Optional[FormulaEngine]:
    """Lấy FormulaEngine từ cache (fast ~5ms) hoặc None nếu chưa có."""
    funcs = allowed_funcs or {}
    key = _make_batch_key(formulas, funcs)

    with _LOCK:
        data = _ENGINE_CACHE.get(key)

    if data is None:
        return None

    try:
        return FormulaEngine.from_cache_bytes(data, safe_funcs=funcs)
    except Exception:
        with _LOCK:
            _ENGINE_CACHE.pop(key, None)
        return None


def set_cached_engine(
    formulas: list,
    engine: FormulaEngine,
    allowed_funcs: Optional[dict] = None,
) -> None:
    """Lưu serialized engine vào cache."""
    funcs = allowed_funcs or {}
    key = _make_batch_key(formulas, funcs)

    try:
        data = engine.to_cache_bytes()
    except Exception:
        return

    with _LOCK:
        if len(_ENGINE_CACHE) >= _ENGINE_CACHE_MAX:
            oldest_key = next(iter(_ENGINE_CACHE))
            _ENGINE_CACHE.pop(oldest_key, None)
        _ENGINE_CACHE[key] = data


def get_or_create_engine(
    formula: str,
    allowed_funcs: Optional[dict] = None,
    *,
    on_error: str = "default",
    default_value=0,
    deterministic: bool = True,
) -> FormulaEngine:
    """Lấy FormulaEngine từ cache hoặc tạo mới.

    Tương thích ngược với API cũ (1 formula đơn lẻ).
    Dùng cache serialization cho fast restore.
    """
    formulas = [{"name": "__r__", "formula": formula}]
    funcs = allowed_funcs or {}

    cached = get_cached_engine(formulas, funcs)
    if cached is not None:
        return cached

    engine = FormulaEngine(
        formulas=formulas,
        safe_funcs=funcs,
        on_error=on_error,
        default_value=default_value,
        deterministic=deterministic,
    )
    set_cached_engine(formulas, engine, funcs)
    return engine


def invalidate_engine_cache() -> None:
    """Xóa toàn bộ engine cache — gọi khi settings thay đổi."""
    with _LOCK:
        _ENGINE_CACHE.clear()
