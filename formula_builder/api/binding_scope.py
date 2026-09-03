# ═══════════════════════════════════════════════════════════════════════════
# FILE: formula_builder/api/binding_scope.py
# Scope semantics chuẩn cho Formula Variable Binding (A5 — Phase 1)
# ═══════════════════════════════════════════════════════════════════════════
"""Chuẩn hoá scope semantics (applies_to_doctype / applies_to_field) giữa các entry.

Bối cảnh (docs/design/fvb-single-resolution-layer.md §3.1 gap #4 + de-xuat §3A A5):
    - ``get_live_context`` (formula_builder.py) lọc binding theo scope TRONG Python
      (global khi cả 2 field rỗng; doctype khi khớp doctype; doctype+field khi khớp field).
    - Một số entry khác (vd alumglass ``bom_orchestrator._get_pricing_bindings`` dùng
      BatchBindingResolver trực tiếp) chỉ lọc theo ``applies_to_doctype``, bỏ qua
      ``applies_to_field`` → preview scope lệch runtime.

Module này là nơi platform định nghĩa MỘT luật filter duy nhất để mọi entry dùng chung:

    global              : applies_to_doctype == ""  và applies_to_field == ""
    theo doctype        : applies_to_doctype == doctype  (field rỗng hoặc field trùng/thiếu)
    theo doctype + field: applies_to_doctype == doctype  và applies_to_field == field

App nghiệp vụ (alumglass DEV1) dùng hàm này cho ``_get_pricing_bindings`` để
tôn trọng ``applies_to_field`` — đọc thêm docs/fb_source_type_contract.md §9.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import frappe

# Field cần thiết khi fetch binding — khớp bộ field mà get_live_context từng fetch.
BINDING_FIELDS: Tuple[str, ...] = (
    "name",
    "variable_name",
    "variable_label",
    "source_type",
    "source_config",
    "resolve_priority",
    "applies_to_doctype",
    "applies_to_field",
    "is_global",
    "data_type",
    "default_value",
)


def binding_matches_scope(
    binding: Dict[str, Any], doctype: str = "", field: str = ""
) -> bool:
    """Binding có áp dụng cho scope (doctype, field) không.

    Luật (bảo toàn nguyên vẹn semantics cũ của ``get_live_context``):
      1. ``applies_to_doctype`` + ``applies_to_field`` đều rỗng → GLOBAL, áp mọi nơi.
      2. ``applies_to_doctype == doctype``:
         - binding không set field → áp cho mọi field của doctype.
         - binding set field → chỉ áp khi khớp ``field`` (hoặc caller không cung cấp field).
      3. Ngoài ra → không áp dụng.

    Args:
        binding: dict binding (từ frappe.get_all) — ít nhất có 2 key trên.
        doctype: doctype scope ("" = không có doctype context).
        field: fieldname scope ("" = không lọc theo field).
    """
    b_doctype = binding.get("applies_to_doctype") or ""
    b_field = binding.get("applies_to_field") or ""

    # Global: áp dụng mọi nơi
    if not b_doctype and not b_field:
        return True
    # Doctype-specific (không khớp doctype → không áp dụng)
    if b_doctype != doctype:
        return False
    # Khớp doctype: không set field / khớp field / caller không đưa field → áp dụng
    if not b_field or b_field == field or not field:
        return True
    return False


def filter_bindings_for_scope(
    bindings: Sequence[Dict[str, Any]], doctype: str = "", field: str = ""
) -> List[Dict[str, Any]]:
    """Lọc danh sách binding theo scope (xem binding_matches_scope)."""
    return [b for b in bindings if binding_matches_scope(b, doctype, field)]


def get_scope_bindings(
    doctype: str = "",
    field: str = "",
    include_inactive: bool = False,
    fields: Optional[Sequence[str]] = None,
    order_by: str = "resolve_priority asc",
) -> List[Dict[str, Any]]:
    """Fetch binding active của một scope từ DB, theo đúng luật filter scope.

    - is_active=1 (trừ khi include_inactive=True).
    - DB prefilter doctype: ``applies_to_doctype in ["", doctype]`` (bỏ qua khi doctype rỗng).
    - Python filter theo field: global + doctype + doctype/field.

    Args:
        doctype: doctype scope.
        field: fieldname scope.
        include_inactive: True → lấy cả binding is_active=0.
        fields: bộ field trả về (mặc định BINDING_FIELDS).
        order_by: order query (None → mặc định).

    Returns:
        List binding dict khớp scope.
    """
    db_filters: List[Any] = []
    if not include_inactive:
        db_filters.append(["is_active", "=", 1])
    if doctype:
        db_filters.append(["applies_to_doctype", "in", ["", doctype]])

    fetch_fields = list(fields) if fields is not None else list(BINDING_FIELDS)

    try:
        rows = (
            frappe.get_all(
                "Formula Variable Binding",
                filters=db_filters,
                fields=fetch_fields,
                order_by=order_by or None,
            )
            or []
        )
    except Exception:
        rows = []

    return filter_bindings_for_scope(rows, doctype, field)
