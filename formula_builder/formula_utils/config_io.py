# config_io.py — F13: Import/Export formula sets (JSON)
#
# Tiện ích THUẦN (pure) — không import frappe, không cần site, không đụng
# formula_utils/engine_*.py hay security.py (DEV1 đang vá RCE).
# Chỉ dùng stdlib: json, datetime, hashlib.
#
# Mục đích: cho phép export một bộ công thức (formula set) kèm variable
# bindings (source_type + source_config) ra JSON canonical để:
#   - Chuyển giữa dev/staging/prod (không phụ thuộc DB/translation)
#   - Backup cấu hình công thức
#   - Diff/audit khi so sánh 2 môi trường
#
# Định dạng payload (schema_version = 1):
# {
#   "schema_version": 1,
#   "exported_at": "ISO-8601",
#   "meta": { ... tuỳ chọn: name, description, app, version, tags ... },
#   "formula_set": [
#       {"name": "gia_thanh", "formula": "tt_nvl + cpc_nvl + vat_nvl",
#        "description": "...", "group": "sp", "order": 1}   # name+formula bắt buộc, còn lại passthrough
#   ],
#   "bindings": [                                   # tuỳ chọn
#       {"source_type": "matrix_lookup",
#        "source_config": {"doctype": "Item Price", "value_field": "price"}},
#       {"source_type": "constant", "source_config": {"value": 5}}
#   ],
#   "checksum": "sha256 của phần canonical (formula_set + bindings)"
# }

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1
_REQUIRED_FORMULA_KEYS = ("name", "formula")
_REQUIRED_BINDING_KEYS = ("source_type", "source_config")


class ConfigIOError(ValueError):
    """Lỗi validate khi import/export cấu hình công thức."""


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_bytes(formula_set: List[dict], bindings: List[dict]) -> bytes:
    """Serialize canonical (sort_keys, ensure_ascii=False) để tính checksum ổn định."""
    payload = {
        "formula_set": formula_set,
        "bindings": bindings,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _validate_formulas(formulas: Any) -> List[dict]:
    if not isinstance(formulas, (list, tuple)):
        raise ConfigIOError("formula_set phải là list các dict {name, formula, ...}")
    out: List[dict] = []
    for i, f in enumerate(formulas):
        if not isinstance(f, dict):
            raise ConfigIOError(f"formula_set[{i}] phải là dict, nhận {type(f).__name__}")
        missing = [k for k in _REQUIRED_FORMULA_KEYS if not f.get(k)]
        if missing:
            raise ConfigIOError(f"formula_set[{i}] thiếu key bắt buộc: {', '.join(missing)}")
        if not isinstance(f["name"], str) or not f["name"].strip():
            raise ConfigIOError(f"formula_set[{i}].name phải là chuỗi không rỗng")
        if not isinstance(f["formula"], str):
            raise ConfigIOError(f"formula_set[{i}].formula phải là chuỗi, nhận {type(f['formula']).__name__}")
        out.append(dict(f))
    if not out:
        raise ConfigIOError("formula_set không được rỗng")
    return out


def _validate_bindings(bindings: Any) -> Optional[List[dict]]:
    if bindings is None:
        return None
    if not isinstance(bindings, (list, tuple)):
        raise ConfigIOError("bindings phải là list các dict {source_type, source_config}")
    out: List[dict] = []
    for i, b in enumerate(bindings):
        if not isinstance(b, dict):
            raise ConfigIOError(f"bindings[{i}] phải là dict, nhận {type(b).__name__}")
        missing = [k for k in _REQUIRED_BINDING_KEYS if b.get(k) in (None, "")]
        if missing:
            raise ConfigIOError(f"bindings[{i}] thiếu key bắt buộc: {', '.join(missing)}")
        if not isinstance(b["source_type"], str) or not b["source_type"].strip():
            raise ConfigIOError(f"bindings[{i}].source_type phải là chuỗi không rỗng")
        sc = b.get("source_config")
        if isinstance(sc, str):
            # Cho phép source_config dạng JSON string từ hệ thống cũ → chuẩn hoá về dict
            try:
                sc = json.loads(sc)
            except json.JSONDecodeError as e:
                raise ConfigIOError(f"bindings[{i}].source_config là JSON string không hợp lệ: {e}") from e
        if not isinstance(sc, dict):
            raise ConfigIOError(f"bindings[{i}].source_config phải là dict hoặc JSON string, nhận {type(sc).__name__}")
        item = dict(b)
        item["source_config"] = sc
        out.append(item)
    return out


def export_config(
    formulas: List[dict],
    bindings: Optional[List[dict]] = None,
    *,
    meta: Optional[Dict[str, Any]] = None,
    include_checksum: bool = True,
) -> str:
    """Export formula set + bindings ra JSON canonical (schema_version=1).

    Args:
        formulas: list các dict {name, formula, ...} — name/formula bắt buộc.
        bindings: list các dict {source_type, source_config, ...} — source_config
            có thể là dict hoặc JSON string; export luôn chuẩn hoá về dict.
        meta: dict tuỳ chọn (name, description, app, version, tags...). Passthrough.
        include_checksum: tính checksum sha256 của phần canonical.

    Returns:
        Chuỗi JSON (pretty, ensure_ascii=False).

    Raises:
        ConfigIOError: nếu formulas/bindings không hợp lệ.
    """
    formulas = _validate_formulas(formulas)
    bindings = _validate_bindings(bindings)
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": _utcnow_iso(),
        "meta": dict(meta) if meta else {},
        "formula_set": formulas,
        "bindings": bindings if bindings is not None else [],
    }
    if include_checksum:
        payload["checksum"] = hashlib.sha256(
            _canonical_bytes(formulas, bindings or [])
        ).hexdigest()
    return json.dumps(payload, ensure_ascii=False, indent=2)


def import_config(payload: str) -> Dict[str, Any]:
    """Import JSON (tạo bởi export_config hoặc tay) → dict đã validate.

    Returns:
        {
            "schema_version": 1,
            "exported_at": str | None,
            "meta": dict,
            "formula_set": [ {...} ],
            "bindings": [ {"source_type": ..., "source_config": {...}} ] | [],
            "checksum": str | None,
        }

    Raises:
        ConfigIOError: nếu payload không phải JSON, sai schema, thiếu key,
            formula_set rỗng, hoặc checksum không khớp.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ConfigIOError(f"payload không phải JSON hợp lệ: {e}") from e
    if not isinstance(data, dict):
        raise ConfigIOError("payload phải là object JSON")

    sv = data.get("schema_version")
    if sv != SCHEMA_VERSION:
        raise ConfigIOError(f"schema_version không hỗ trợ: {sv!r} (hỗ trợ {SCHEMA_VERSION})")

    formulas = _validate_formulas(data.get("formula_set"))
    bindings = _validate_bindings(data.get("bindings"))

    checksum = data.get("checksum")
    if checksum is not None:
        expected = hashlib.sha256(_canonical_bytes(formulas, bindings or [])).hexdigest()
        if checksum != expected:
            raise ConfigIOError("checksum không khớp — payload có thể bị chỉnh sửa/hỏng")

    meta = data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    exported_at = data.get("exported_at")
    if not isinstance(exported_at, str):
        exported_at = None

    return {
        "schema_version": sv,
        "exported_at": exported_at,
        "meta": meta,
        "formula_set": formulas,
        "bindings": bindings or [],
        "checksum": checksum,
    }


def roundtrip(payload: str) -> str:
    """Tiện ích: import rồi export lại — dùng test idempotency và chuẩn hoá file cũ."""
    data = import_config(payload)
    return export_config(
        data["formula_set"],
        data["bindings"] or None,
        meta=data["meta"],
        include_checksum=data["checksum"] is not None,
    )
