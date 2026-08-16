# ═══════════════════════════════════════════════════════════════════════════
# FILE: formula_builder/formula_utils/data_source_registry.py
# Data Source Registry — Formula Builder v2.0
# ═══════════════════════════════════════════════════════════════════════════
"""Registry pattern for resolving variable bindings from any data source.

Each handler is registered via @register_source(source_type) and receives:
  - binding: dict (the Formula Variable Binding row as dict)
  - doc: the current Frappe document object (or None)
  - resolved_so_far: dict of already-resolved variables (for computed deps)
"""
from __future__ import annotations

import ast
import hashlib
import json
import importlib
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Any, Callable, Dict, List, Optional, Tuple

import frappe

# ── Registry storage ─────────────────────────────────────────────────────────
_data_source_handlers: Dict[str, Callable] = {}


# ── Abstract Base Class ──────────────────────────────────────────────────────

class BaseDataSourceHandler(ABC):
    """Abstract base cho tất cả data source handler.

    Mỗi source_type phải implement:
      - resolve(): resolve giá trị từ binding + document context
      - validate_config(): validate source_config JSON (trả về error string hoặc None)
    """

    @abstractmethod
    def resolve(self, binding: dict, doc, resolved_so_far: dict) -> Any:
        """Resolve giá trị cho variable binding."""
        ...

    @abstractmethod
    def validate_config(self, binding: dict) -> Optional[str]:
        """Validate source_config. Trả về error message nếu invalid, None nếu OK."""
        ...


def register_source(source_type: str):
    """Decorator to register a handler for a source_type."""
    def decorator(func: Callable) -> Callable:
        _data_source_handlers[source_type] = func
        return func
    return decorator


def batchable(fingerprint_fn: Optional[Callable] = None):
    """Decorator to mark a handler as supporting batch resolution.

    When marked @batchable, the handler will be grouped by fingerprint
    and resolved via BatchBindingResolver instead of individually.

    Args:
        fingerprint_fn: Optional function(source_config_dict) → fingerprint string.
            Bindings with the same fingerprint are grouped into 1 batch query.
            Default: group by source_type only.
    """
    def decorator(func: Callable) -> Callable:
        func.batchable = True
        if fingerprint_fn is not None:
            func.fingerprint_fn = fingerprint_fn
        return func
    return decorator


def get_handler(source_type: str) -> Optional[Callable]:
    """Return the handler for a given source_type, or None."""
    return _data_source_handlers.get(source_type)


def is_batchable(source_type: str) -> bool:
    """Check if a source_type handler supports batch resolution."""
    handler = get_handler(source_type)
    return handler is not None and getattr(handler, 'batchable', False)


def get_batch_resolver(source_type: str) -> Optional[Callable]:
    """Get the resolve_batch function for a handler, or None."""
    handler = get_handler(source_type)
    if handler is None:
        return None
    return getattr(handler, 'resolve_batch', None)


# ── Whitelist helpers ────────────────────────────────────────────────────────
def _get_custom_function_whitelist() -> List[str]:
    """Read allowed module prefixes from System Settings."""
    try:
        val = frappe.db.get_single_value(
            "Formula Builder Settings", "custom_function_whitelist"
        ) or ""
    except Exception:
        val = ""
    defaults = ["formula_builder.custom_functions", "formula_builder.formula_utils", "frappe.utils"]
    if not val:
        return defaults
    return [p.strip() for p in val.split("\n") if p.strip()] or defaults


def _check_custom_function_allowed(module_path: str) -> None:
    """Raise PermissionError if module_path is not in the whitelist."""
    whitelist = _get_custom_function_whitelist()
    # Dùng == hoặc startswith(prefix + ".") để tránh prefix collision
    # Ví dụ: "formula_builder.custom_functions" match "formula_builder.custom_functions.utils"
    # nhưng KHÔNG match "formula_builder.custom_functions_evil"
    if not any(
        module_path == prefix or module_path.startswith(prefix + ".")
        for prefix in whitelist
    ):
        raise frappe.PermissionError(
            f"Module '{module_path}' not in custom_function whitelist."
        )


# ── Cast helper ──────────────────────────────────────────────────────────────
def _cast(val: Any, dtype: str = "Float") -> Any:
    if val is None:
        return None
    try:
        if dtype in ("Float", "Currency", "Percent"):
            return float(val)
        if dtype == "Int":
            return int(float(val))
        if dtype in ("Check", "Bool"):
            return bool(int(val)) if str(val).isdigit() else bool(val)
        return str(val)
    except Exception:
        return val


# ── Filter expression security validator ──────────────────────────────────────

# AST nodes bị cấm TUYỆT ĐỐI trong filter_expr
# KHÔNG chặn Attribute, Call — người dùng được dùng mọi hàm từ settings
# Bảo mật thực sự: eval(__builtins__={}) + scope bị giới hạn bởi safe_globals
_FILTER_FORBIDDEN_NODES: frozenset = frozenset({
    "Import", "ImportFrom", "Exec", "Eval",
    "FunctionDef", "AsyncFunctionDef", "ClassDef",
    "Delete", "Global", "Nonlocal", "Await", "Yield", "YieldFrom",
    "Lambda", "DictComp", "SetComp",
    "Assign", "AugAssign", "AnnAssign", "NamedExpr",
})

# Tên TUYỆT ĐỐI bị cấm — tất cả tên khác đều được phép
_FILTER_FORBIDDEN_NAMES: frozenset = frozenset({
    "__import__", "globals", "locals", "vars", "dir",
    "__class__", "__bases__", "__mro__", "__subclasses__",
    "__builtins__", "__globals__", "__code__", "__func__",
    "__self__", "__dict__", "__module__", "__qualname__",
    "exec", "eval", "compile", "open", "breakpoint", "input",
})

# Cache lazy — build lần đầu tiên khi cần, sau đó tái sử dụng
_filter_allowed_calls_cache: Optional[frozenset] = None
_filter_safe_globals_cache: Optional[dict] = None


def _get_filter_context() -> tuple:
    """Lazy-build allowed function names + safe_globals từ Formula Builder Settings.

    Gọi get_allowed_funcs() — single source of truth:
      - Có settings: tôn trọng admin config (enable/disable từng hàm)
      - Không có settings: fallback về toàn bộ BASE_FUNCS (~80+ hàm)
      - Có cache Redis TTL 300s

    Returns:
        (allowed_names: frozenset, safe_globals: dict)
    """
    global _filter_allowed_calls_cache, _filter_safe_globals_cache

    if _filter_safe_globals_cache is not None:
        return _filter_allowed_calls_cache, _filter_safe_globals_cache

    try:
        from formula_builder.api.settings_cache import get_allowed_funcs
        allowed = get_allowed_funcs()
    except Exception:
        from formula_builder.formula_utils import BASE_FUNCS
        allowed = dict(BASE_FUNCS)

    _filter_allowed_calls_cache = frozenset(allowed.keys())

    _filter_safe_globals_cache = {
        "row": None,
        "True": True,
        "False": False,
        "None": None,
    }
    _filter_safe_globals_cache.update(allowed)

    return _filter_allowed_calls_cache, _filter_safe_globals_cache


def _invalidate_filter_context_cache() -> None:
    """Xóa cache — gọi khi Formula Builder Settings thay đổi."""
    global _filter_allowed_calls_cache, _filter_safe_globals_cache
    _filter_allowed_calls_cache = None
    _filter_safe_globals_cache = None


def _validate_filter_expr(filter_expr: str) -> None:
    """Validate filter expression cho child_table_aggregate.

    Cho phép TOÀN BỘ hàm từ formula_utils BASE_FUNCS (~80+ hàm):
      - row.field, row.qty > 0, row.rate * row.qty
      - sum(row.items), count(row.items), average(row.values)
      - IF(row.qty > 10, 'big', 'small')
      - vlookup(row.code, table, 2)
      - sumif(row.items, '>0', row.values)
      - len(row.items) > 0, abs(row.val) > 100, round(row.val, 2)
      - Toán tử: == != < > <= >= and or not in is
      - Literal: số, chuỗi, True/False/None

    Chỉ chặn:
      - import, eval, exec, lambda, class/function def
      - Dunder attributes (row.__class__, row.__dict__, ...)
      - Subscript (row['field'] — dùng row.field thay thế)
      - Method calls (obj.method() style)

    Raises:
        ValueError: nếu filter_expr chứa cấu trúc nguy hiểm.
    """
    if not filter_expr or not filter_expr.strip():
        return

    # 1. Parse AST
    try:
        tree = ast.parse(filter_expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Filter expression syntax error: {e.msg}") from e

    # 2. Walk AST — kiểm tra từng node
    allowed_calls, _ = _get_filter_context()

    for node in ast.walk(tree):
        node_type = type(node).__name__

        # --- Chặn forbidden node types ---
        if node_type in _FILTER_FORBIDDEN_NODES:
            raise ValueError(
                f"Forbidden operation '{node_type}' in filter expression."
            )

        # --- Kiểm tra Name (biến, hằng) ---
        if node_type == "Name":
            name = node.id  # type: ignore[attr-defined]
            if name in _FILTER_FORBIDDEN_NAMES:
                raise ValueError(
                    f"Forbidden name '{name}' in filter expression."
                )
            # Tất cả các tên khác đều được phép — eval context đã giới hạn scope

        # --- Kiểm tra Attribute (row.field) ---
        if node_type == "Attribute":
            attr = node.attr  # type: ignore[attr-defined]
            if attr.startswith("__"):
                raise ValueError(
                    f"Dunder attribute '.{attr}' is not allowed in filter. "
                    "Use normal field names like row.qty, row.rate."
                )
            # Attribute hợp lệ — tiếp tục

        # --- Kiểm tra Call (gọi hàm) ---
        if node_type == "Call":
            if isinstance(node.func, ast.Name):  # type: ignore[attr-defined]
                fname = node.func.id  # type: ignore[attr-defined]
                if fname not in allowed_calls:
                    raise ValueError(
                        f"Function '{fname}()' is not available. "
                        "Check Formula Builder Settings for enabled functions."
                    )
            elif isinstance(node.func, ast.Attribute):  # type: ignore[attr-defined]
                raise ValueError(
                    "Method calls (e.g. obj.method()) are not allowed in filter."
                )
            else:
                raise ValueError(
                    "Complex call expressions are not allowed in filter."
                )

        # --- Chặn Subscript (row['field']) ---
        if node_type == "Subscript":
            raise ValueError(
                "Subscript access (e.g. row['field']) is not allowed in filter. "
                "Use row.field_name instead."
            )


# ═══════════════════════════════════════════════════════════════════════════
# HANDLERS — each is registered via @register_source
# ═══════════════════════════════════════════════════════════════════════════

@register_source("constant")
def _handle_constant(binding: dict, doc, resolved_so_far: dict) -> Any:
    cfg = json.loads(binding.get("source_config") or "{}")
    return _cast(cfg.get("value"), binding.get("data_type") or cfg.get("type", "Float"))


@register_source("linked_doctype_field")
@batchable(fingerprint_fn=lambda cfg: "linked:" + cfg.get("target_doctype", "") + ":" + cfg.get("target_field", ""))
def _handle_linked_doctype_field(binding: dict, doc, resolved_so_far: dict) -> Any:
    cfg = json.loads(binding.get("source_config") or "{}")
    link_field = cfg.get("link_field", "")
    target_doctype = cfg.get("target_doctype", "")
    target_field = cfg.get("target_field", "")
    fallback = cfg.get("fallback")

    if not doc or not link_field or not target_field:
        return fallback

    linked_name = doc.get(link_field)
    if not linked_name:
        return fallback

    dt = target_doctype or frappe.get_meta(doc.doctype).get_field(link_field).options
    if not dt:
        return fallback

    try:
        val = frappe.db.get_value(dt, linked_name, target_field)
        return val if val is not None else fallback
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"DataSource: linked_doctype_field ({binding.get('variable_name')})",
        )
        return fallback


def _resolve_linked_doctype_field_batch(
    bindings: List[dict], doc, resolved_so_far: dict
) -> Dict[str, Any]:
    """Batch resolve nhiều linked_doctype_field bindings.

    Gom theo (doctype, target_field) → 1 query WHERE name IN (...).
    """
    if not bindings or not doc:
        return {}

    results: Dict[str, Any] = {}

    # Group by (target_doctype, target_field)
    groups: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for b in bindings:
        cfg = json.loads(b.get("source_config", "{}"))
        link_field = cfg.get("link_field", "")
        target_doctype = cfg.get("target_doctype", "")
        target_field = cfg.get("target_field", "")

        if not link_field or not target_field:
            results[b["variable_name"]] = cfg.get("fallback") or b.get("default_value")
            continue

        linked_name = doc.get(link_field)
        if not linked_name:
            results[b["variable_name"]] = cfg.get("fallback") or b.get("default_value")
            continue

        dt = target_doctype or frappe.get_meta(doc.doctype).get_field(link_field).options
        if not dt:
            results[b["variable_name"]] = cfg.get("fallback") or b.get("default_value")
            continue

        groups[(dt, target_field, linked_name)].append(b)

    # Batch execute each group
    for (dt, target_field, linked_name), group in groups.items():
        try:
            # 1 query lấy tất cả fields từ linked doctype
            full_doc = frappe.db.get_value(dt, linked_name, target_field)
            value = full_doc if full_doc is not None else None
            for b in group:
                results[b["variable_name"]] = (
                    value
                    if value is not None
                    else b.get("default_value")
                )
        except Exception as e:
            frappe.log_error(
                f"Batch linked_doctype_field failed ({dt}/{target_field}): {e}",
                "DataSource Registry",
            )
            for b in group:
                try:
                    val = _handle_linked_doctype_field(b, doc, resolved_so_far)
                    results[b["variable_name"]] = (
                        val if val is not None else b.get("default_value")
                    )
                except Exception:
                    results[b["variable_name"]] = b.get("default_value")

    return results


_handle_linked_doctype_field.resolve_batch = _resolve_linked_doctype_field_batch


@register_source("whole_doctype")
@batchable(fingerprint_fn=lambda cfg: "whole:" + cfg.get("target_doctype", ""))
def _handle_whole_doctype(binding: dict, doc, resolved_so_far: dict) -> Any:
    """Return entire doctype document as dict for object.field access."""
    cfg = json.loads(binding.get("source_config") or "{}")
    link_field = cfg.get("link_field", "")
    target_doctype = cfg.get("target_doctype", "")
    fields = cfg.get("fields") or []
    include_child = cfg.get("include_child_tables", False)

    if not doc or not link_field:
        return {}

    linked_name = doc.get(link_field)
    if not linked_name:
        return {}

    dt = target_doctype or frappe.get_meta(doc.doctype).get_field(link_field).options
    if not dt:
        return {}

    try:
        meta = frappe.get_meta(dt)
        scalar_types = {
            "Data", "Int", "Float", "Currency", "Percent",
            "Check", "Date", "Datetime", "Select", "Small Text",
            "Text", "Long Text", "Link", "Dynamic Link", "Read Only",
        }
        field_set = set(fields) if fields else None
        result = {}
        for f in meta.fields:
            if f.fieldtype not in scalar_types:
                continue
            if field_set is not None and f.fieldname not in field_set:
                continue
            try:
                result[f.fieldname] = frappe.db.get_value(dt, linked_name, f.fieldname)
            except Exception:
                result[f.fieldname] = None
        if include_child:
            for f in meta.fields:
                if f.fieldtype == "Table":
                    try:
                        full_doc = frappe.get_doc(dt, linked_name)
                        result[f.fieldname] = [
                            row.as_dict() for row in (full_doc.get(f.fieldname) or [])
                        ]
                    except Exception:
                        result[f.fieldname] = []
        return result
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"DataSource: whole_doctype ({binding.get('variable_name')})",
        )
        return {}


def _resolve_whole_doctype_batch(
    bindings: List[dict], doc, resolved_so_far: dict
) -> Dict[str, Any]:
    """Batch resolve nhiều whole_doctype bindings.

    Gom theo (doctype) → 1 query WHERE name IN (...).
    Các bindings trỏ tới cùng 1 doctype name sẽ dùng chung kết quả.
    """
    if not bindings or not doc:
        return {}

    results: Dict[str, Any] = {}
    fetched_cache: Dict[Tuple[str, str], Dict] = {}  # (dt, name) → doc dict

    for b in bindings:
        cfg = json.loads(b.get("source_config", "{}"))
        link_field = cfg.get("link_field", "")
        target_doctype = cfg.get("target_doctype", "")
        fields = cfg.get("fields") or []
        include_child = cfg.get("include_child_tables", False)

        if not link_field:
            results[b["variable_name"]] = {}
            continue

        linked_name = doc.get(link_field)
        if not linked_name:
            results[b["variable_name"]] = {}
            continue

        dt = target_doctype or frappe.get_meta(doc.doctype).get_field(link_field).options
        if not dt:
            results[b["variable_name"]] = {}
            continue

        cache_key = (dt, linked_name)
        if cache_key in fetched_cache:
            results[b["variable_name"]] = fetched_cache[cache_key]
            continue

        try:
            meta = frappe.get_meta(dt)
            scalar_types = {
                "Data", "Int", "Float", "Currency", "Percent",
                "Check", "Date", "Datetime", "Select", "Small Text",
                "Text", "Long Text", "Link", "Dynamic Link", "Read Only",
            }
            field_set = set(fields) if fields else None
            result = {}
            for f in meta.fields:
                if f.fieldtype not in scalar_types:
                    continue
                if field_set is not None and f.fieldname not in field_set:
                    continue
                try:
                    result[f.fieldname] = frappe.db.get_value(dt, linked_name, f.fieldname)
                except Exception:
                    result[f.fieldname] = None
            if include_child:
                for f in meta.fields:
                    if f.fieldtype == "Table":
                        try:
                            full_doc = frappe.get_doc(dt, linked_name)
                            result[f.fieldname] = [
                                row.as_dict() for row in (full_doc.get(f.fieldname) or [])
                            ]
                        except Exception:
                            result[f.fieldname] = []

            fetched_cache[cache_key] = result
            results[b["variable_name"]] = result
        except Exception as e:
            frappe.log_error(
                f"Batch whole_doctype failed ({dt}/{linked_name}): {e}",
                "DataSource Registry",
            )
            results[b["variable_name"]] = {}

    return results


_handle_whole_doctype.resolve_batch = _resolve_whole_doctype_batch


@register_source("child_table_aggregate")
def _handle_child_table_aggregate(binding: dict, doc, resolved_so_far: dict) -> Any:
    cfg = json.loads(binding.get("source_config") or "{}")
    child_field = cfg.get("child_table_field", "")
    field = cfg.get("field", "")
    aggregate = cfg.get("aggregate", "sum")
    filter_expr = cfg.get("filter_expr", "")

    if not doc or not child_field:
        return None

    rows = doc.get(child_field) or []
    if not rows:
        return 0 if aggregate == "count" else ([] if aggregate == "list" else None)

    if filter_expr:
        # Validate filter expression AST security trước khi eval
        try:
            _validate_filter_expr(filter_expr)
        except ValueError as e:
            frappe.log_error(
                f"Filter expression rejected for '{binding.get('variable_name')}': {e}",
                "DataSource: child_table_aggregate",
            )
            return None

        # Dùng get_allowed_funcs() từ settings (single source of truth)
        # Mặc định: tất cả BASE_FUNCS (~80+ hàm), admin có thể tùy chỉnh
        _, base_globals = _get_filter_context()
        safe_globals = dict(base_globals)
        filtered = []
        for r in rows:
            safe_globals["row"] = r
            try:
                if eval(filter_expr, {"__builtins__": {}}, safe_globals):
                    filtered.append(r)
            except Exception:
                pass
        rows = filtered

    values = [getattr(r, field, None) for r in rows]
    values = [v for v in values if v is not None]

    if not values:
        return 0 if aggregate == "count" else None

    try:
        if aggregate == "sum":
            return sum(float(v) for v in values)
        elif aggregate == "avg":
            return sum(float(v) for v in values) / len(values)
        elif aggregate == "min":
            return min(float(v) for v in values)
        elif aggregate == "max":
            return max(float(v) for v in values)
        elif aggregate == "count":
            return len(values)
        elif aggregate == "list":
            return values
    except Exception:
        return None
    return None


@register_source("global_default")
def _handle_global_default(binding: dict, doc, resolved_so_far: dict) -> Any:
    cfg = json.loads(binding.get("source_config") or "{}")
    key = cfg.get("key", "")
    company_specific = cfg.get("company_specific", False)
    company_field = cfg.get("company_field", "company")

    if not key:
        return None
    try:
        return frappe.db.get_single_value("Global Defaults", key)
    except Exception:
        return None


@register_source("session_variable")
def _handle_session_variable(binding: dict, doc, resolved_so_far: dict) -> Any:
    cfg = json.loads(binding.get("source_config") or "{}")
    key = cfg.get("key", "")
    session_map = {
        "user": frappe.session.user,
        "user_fullname": frappe.session.user_fullname or frappe.session.user,
        "user_roles": frappe.get_roles(frappe.session.user),
        "lang": frappe.local.lang or "en",
        "now": frappe.utils.now(),
        "today": frappe.utils.today(),
        "company": frappe.defaults.get_user_default("company"),
    }
    return session_map.get(key)


@register_source("doctype_query")
@batchable(fingerprint_fn=lambda cfg: "doctype_query:" + cfg.get("doctype", "") + ":" + cfg.get("fieldname", ""))
def _handle_doctype_query(binding: dict, doc, resolved_so_far: dict) -> Any:
    cfg = json.loads(binding.get("source_config") or "{}")
    target_doctype = cfg.get("doctype", "")
    filters_raw = cfg.get("filters") or []
    fieldname = cfg.get("fieldname", "name")
    aggregate = cfg.get("aggregate", "first")

    if not target_doctype:
        return None

    def _resolve_filter_val(v):
        if isinstance(v, str) and v.startswith("{doc.") and v.endswith("}"):
            return doc.get(v[5:-1]) if doc else None
        return v

    filters = []
    for f in filters_raw:
        if isinstance(f, list) and len(f) == 3:
            filters.append([f[0], f[1], _resolve_filter_val(f[2])])

    try:
        if aggregate == "count":
            return frappe.db.count(target_doctype, filters=filters)
        elif aggregate == "list":
            return frappe.get_all(target_doctype, filters=filters, fields=[fieldname])
        elif aggregate == "sum":
            rows = frappe.get_all(target_doctype, filters=filters, fields=[fieldname])
            return sum(float(r.get(fieldname, 0) or 0) for r in rows)
        else:
            order_by = "modified desc" if aggregate == "last" else None
            rows = frappe.get_all(
                target_doctype, filters=filters, fields=[fieldname],
                limit=1, order_by=order_by,
            )
            return rows[0].get(fieldname) if rows else None
    except Exception as e:
        frappe.log_error(
            f"doctype_query ({binding.get('variable_name')}): {e}",
            "DataSource Registry",
        )
        return None


def _resolve_doctype_query_batch(bindings: List[dict], doc, resolved_so_far: dict) -> Dict[str, Any]:
    """Batch resolve nhiều doctype_query bindings.

    Gom tất cả bindings cùng doctype → 1 query WHERE name IN (...)
    hoặc 1 query với aggregate.

    Chỉ hoạt động cho aggregate="first" (lấy giá trị fieldname cho
    nhiều document name cùng lúc).
    """
    if not bindings:
        return {}

    results: Dict[str, Any] = {}

    # Group by (doctype, fieldname, filters_hash) for sub-grouping
    subgroups: Dict[Tuple[str, str, str], List[dict]] = defaultdict(list)
    for b in bindings:
        cfg = json.loads(b.get("source_config", "{}"))
        doctype = cfg.get("doctype", "")
        fieldname = cfg.get("fieldname", "name")
        aggregate = cfg.get("aggregate", "first")

        # Chỉ batch cho aggregate="first" với các query khác doctype name
        if aggregate == "first":
            filters_raw = cfg.get("filters") or []
            filters_hash = hashlib.md5(
                json.dumps(filters_raw, sort_keys=True).encode()
            ).hexdigest()[:12]
            subgroups[(doctype, fieldname, filters_hash)].append(b)
        else:
            # aggregate != first → gọi handler riêng
            results[b["variable_name"]] = _handle_doctype_query(
                b, doc, resolved_so_far
            )

    # Batch execute each subgroup
    for (doctype, fieldname, _), subgroup in subgroups.items():
        results.update(
            _batch_doctype_query_first(subgroup, doc, doctype, fieldname)
        )

    return results


def _batch_doctype_query_first(
    bindings: List[dict], doc, doctype: str, fieldname: str
) -> Dict[str, Any]:
    """Batch: SELECT name, fieldname FROM doctype WHERE name IN (...).

    Returns dict of {variable_name: field_value} for each binding.
    """
    results: Dict[str, Any] = {}

    # Collect all document names needed
    doc_names_by_binding: Dict[str, str] = {}  # name → variable_name
    all_names: List[str] = []

    for b in bindings:
        cfg = json.loads(b.get("source_config", "{}"))
        filters = cfg.get("filters") or []
        name_val = None

        # Try to extract the target name from filters
        for f in filters:
            if isinstance(f, list) and len(f) == 3:
                if f[0] == "name" and f[1] == "=":
                    name_val = str(f[2])
                    break

        if name_val:
            doc_names_by_binding[name_val] = b["variable_name"]
            all_names.append(name_val)
        else:
            # Can't batch: individual resolve
            try:
                val = _handle_doctype_query(b, doc, {})
                results[b["variable_name"]] = val if val is not None else b.get("default_value")
            except Exception:
                results[b["variable_name"]] = b.get("default_value")

    if not all_names:
        return results

    # Execute 1 batch query
    try:
        rows = frappe.db.get_all(
            doctype,
            filters={"name": ["in", all_names]},
            fields=["name", fieldname],
        )
        value_map = {r.name: r.get(fieldname) for r in rows}

        for doc_name, var_name in doc_names_by_binding.items():
            if doc_name in value_map:
                results[var_name] = value_map[doc_name]
            else:
                results[var_name] = bindings[0].get("default_value") if bindings else None
    except Exception as e:
        frappe.log_error(
            f"Batch doctype_query failed ({doctype}/{fieldname}): {e}",
            "DataSource Registry",
        )
        # Fallback: individual
        for b in bindings:
            try:
                val = _handle_doctype_query(b, doc, {})
                results[b["variable_name"]] = val if val is not None else b.get("default_value")
            except Exception:
                results[b["variable_name"]] = b.get("default_value")

    return results


# Attach batch resolver to handler
_handle_doctype_query.resolve_batch = _resolve_doctype_query_batch


@register_source("custom_function")
def _handle_custom_function(binding: dict, doc, resolved_so_far: dict) -> Any:
    cfg = json.loads(binding.get("source_config") or "{}")
    module_path = cfg.get("module", "")
    function_name = cfg.get("function", "")
    args = cfg.get("args") or {}

    if not module_path or not function_name:
        return None

    _check_custom_function_allowed(module_path)

    resolved_args = {}
    for k, v in args.items():
        if isinstance(v, str) and v.startswith("doc."):
            resolved_args[k] = doc.get(v[4:]) if doc else None
        elif isinstance(v, str) and v.startswith("resolved."):
            resolved_args[k] = resolved_so_far.get(v[9:])
        else:
            resolved_args[k] = v

    try:
        mod = importlib.import_module(module_path)
        func = getattr(mod, function_name)
        return func(**resolved_args)
    except frappe.PermissionError:
        raise
    except Exception as e:
        frappe.log_error(
            f"custom_function ({module_path}.{function_name}): {e}",
            "DataSource Registry",
        )
        return binding.get("default_value")


@register_source("dynamic_link")
def _handle_dynamic_link(binding: dict, doc, resolved_so_far: dict) -> Any:
    cfg = json.loads(binding.get("source_config") or "{}")
    doctype_field = cfg.get("doctype_field", "")
    name_field = cfg.get("name_field", "")
    target_field = cfg.get("target_field", "")

    if not doc or not doctype_field or not name_field or not target_field:
        return None

    ref_doctype = doc.get(doctype_field)
    ref_name = doc.get(name_field)
    if not ref_doctype or not ref_name:
        return None

    try:
        return frappe.db.get_value(ref_doctype, ref_name, target_field)
    except Exception:
        return None


@register_source("computed")
def _handle_computed(binding: dict, doc, resolved_so_far: dict) -> Any:
    """Evaluate a formula using already-resolved dependencies."""
    cfg = json.loads(binding.get("source_config") or "{}")
    formula = cfg.get("formula", "")
    if not formula:
        return binding.get("default_value")

    from formula_builder.formula_utils import FormulaEngine, BASE_FUNCS, normalize_formula
    from formula_builder.api.settings_cache import get_allowed_funcs

    try:
        allowed = get_allowed_funcs()
        safe_funcs = dict(allowed) if allowed else dict(BASE_FUNCS)
        known = set(safe_funcs.keys()) | set(BASE_FUNCS.keys())
        norm = normalize_formula(formula, frozenset(known))
        engine = FormulaEngine(
            formulas=[{"name": "__c__", "formula": norm}],
            safe_funcs=safe_funcs,
        )
        return engine.calculate(resolved_so_far).get("__c__")
    except Exception as e:
        frappe.log_error(
            f"computed ({binding.get('variable_name')}): {e}",
            "DataSource Registry",
        )
        return binding.get("default_value")


# ═══════════════════════════════════════════════════════════════════════════
# v31 PHASE 2 — COMPOSITE SOURCE TYPES
# ═══════════════════════════════════════════════════════════════════════════
#
# Three new source types that COMPOSE existing sources:
#
#   pipeline       — Chain sources: output of step N → input of step N+1
#   conditional    — Branch: pick source based on runtime condition
#   fallback_chain — Resilience: try primary → fallback_1 → fallback_2 → default
#
# These are INDUSTRY-AGNOSTIC. Any Frappe app can use them.
# ═══════════════════════════════════════════════════════════════════════════


@register_source("pipeline")
@batchable(fingerprint_fn=lambda cfg: "pipeline:" + hashlib.md5(
    json.dumps(cfg.get("steps", []), sort_keys=True).encode()
).hexdigest()[:12])
def _handle_pipeline(binding: dict, doc, resolved_so_far: dict) -> Any:
    """Chain multiple data sources: output of step N → input of step N+1.

    Pipeline steps execute SEQUENTIALLY. Each step's resolved value is added
    to the context as `step_{N}` and `{output_as}` if specified.

    source_config format:
        {
            "steps": [
                {
                    "source_type": "doctype_query",
                    "source_config": {"doctype": "Item", "fieldname": "weight_per_unit", ...},
                    "output_as": "weight"           // optional: name for this step's output
                },
                {
                    "source_type": "doctype_query",
                    "source_config": {"doctype": "Item Price", ...},
                    "output_as": "price"
                },
                {
                    "source_type": "computed",
                    "source_config": {
                        "formula": "weight * price",
                        "dependencies": ["weight", "price"]
                    },
                    "output_as": "total"            // final step's output is the pipeline result
                }
            ],
            "merge_strategy": "last"  // "last" (default) or "all" (return dict of all outputs)
        }

    Use cases:
        - Fetch raw price → multiply by exchange rate → apply tax
        - Query BOM lines → SUM quantities → multiply by unit cost
        - Fetch glass data → resolve thickness rule → calculate price
    """
    cfg = json.loads(binding.get("source_config") or "{}")
    steps = cfg.get("steps") or []
    merge_strategy = cfg.get("merge_strategy", "last")

    if not steps:
        return binding.get("default_value")

    # Pipeline context: seeded with pre-resolved vars, accumulates step outputs
    pipeline_ctx = dict(resolved_so_far)
    step_outputs: Dict[str, Any] = {}
    last_value = None

    for i, step in enumerate(steps):
        step_source_type = step.get("source_type", "")
        step_config = step.get("source_config", {})
        output_as = step.get("output_as", f"step_{i}")

        if not step_source_type:
            frappe.log_error(
                f"Pipeline step {i}: missing source_type",
                "DataSource: pipeline",
            )
            continue

        handler = get_handler(step_source_type)
        if handler is None:
            frappe.log_error(
                f"Pipeline step {i}: unknown source_type '{step_source_type}'",
                "DataSource: pipeline",
            )
            continue

        # Build a temporary binding for this step
        step_binding = {
            "variable_name": output_as,
            "source_type": step_source_type,
            "source_config": json.dumps(step_config) if isinstance(step_config, dict) else str(step_config),
            "data_type": step.get("data_type", "Float"),
            "default_value": step.get("default_value"),
        }

        try:
            val = handler(step_binding, doc, pipeline_ctx)
            if val is None:
                val = step.get("default_value")
        except Exception as e:
            frappe.log_error(
                f"Pipeline step {i} ('{output_as}' via {step_source_type}): {e}",
                "DataSource: pipeline",
            )
            val = step.get("default_value")

        step_outputs[output_as] = val
        pipeline_ctx[output_as] = val
        last_value = val

    if merge_strategy == "all":
        return step_outputs
    else:
        return last_value


@register_source("conditional")
def _handle_conditional(binding: dict, doc, resolved_so_far: dict) -> Any:
    """Branch to different data sources based on runtime conditions.

    Evaluates condition expressions in order. The FIRST branch whose
    condition evaluates to True is used. If no condition matches,
    the `default` branch is used.

    Condition syntax: Python expression evaluated with resolved_so_far
    as the variable scope. Example: "product_type == 'CUA_DI'"
    or "total_weight > 100".

    source_config format:
        {
            "branches": [
                {
                    "condition": "{resolved.product_type} == 'CUA_DI'",
                    "source_type": "doctype_query",
                    "source_config": {"doctype": "Door Price", ...}
                },
                {
                    "condition": "{resolved.product_type} == 'CUA_SO'",
                    "source_type": "doctype_query",
                    "source_config": {"doctype": "Window Price", ...}
                }
            ],
            "default": {
                "source_type": "constant",
                "source_config": {"value": 0}
            }
        }

    Use cases:
        - Different price tables per product type
        - Different tax rates per region
        - Different calculation methods per brand
    """
    cfg = json.loads(binding.get("source_config") or "{}")
    branches = cfg.get("branches") or []
    default_branch = cfg.get("default")

    # Resolve template variables in condition strings
    from formula_builder.api.batch_binding_resolver import _resolve_template

    for branch in branches:
        condition_raw = branch.get("condition", "True")
        # Resolve templates like {resolved.xxx} in the condition
        if isinstance(condition_raw, str):
            condition = condition_raw
            for key, val in resolved_so_far.items():
                condition = condition.replace(f"{{{{{key}}}}}", repr(val))
            # Also handle {resolved.key} format
            for key, val in resolved_so_far.items():
                condition = condition.replace(f"{{resolved.{key}}}", repr(val))
        else:
            condition = "True"

        try:
            # Evaluate condition in a safe scope
            safe_scope = {"__builtins__": {}}
            safe_scope.update(resolved_so_far)
            safe_scope.update({
                "True": True, "False": False, "None": None,
                "int": int, "float": float, "str": str, "bool": bool,
                "len": len, "abs": abs, "min": min, "max": max,
                "round": round,
            })
            result = eval(condition, {"__builtins__": {}}, safe_scope)
            if result:
                # This branch matches → use its source
                branch_source_type = branch.get("source_type", "")
                branch_config = branch.get("source_config", {})
                handler = get_handler(branch_source_type)
                if handler is None:
                    frappe.log_error(
                        f"Conditional: unknown source_type '{branch_source_type}' in branch",
                        "DataSource: conditional",
                    )
                    continue

                branch_binding = {
                    "variable_name": binding.get("variable_name", "_cond_"),
                    "source_type": branch_source_type,
                    "source_config": json.dumps(branch_config) if isinstance(branch_config, dict) else str(branch_config),
                    "data_type": branch.get("data_type", binding.get("data_type", "Float")),
                    "default_value": branch.get("default_value"),
                }
                return handler(branch_binding, doc, resolved_so_far)
        except Exception as e:
            frappe.log_error(
                f"Conditional: error evaluating condition '{condition_raw}': {e}",
                "DataSource: conditional",
            )
            continue

    # No branch matched → use default
    if default_branch:
        default_source_type = default_branch.get("source_type", "")
        default_config = default_branch.get("source_config", {})
        handler = get_handler(default_source_type)
        if handler:
            default_binding = {
                "variable_name": binding.get("variable_name", "_default_"),
                "source_type": default_source_type,
                "source_config": json.dumps(default_config) if isinstance(default_config, dict) else str(default_config),
                "data_type": default_branch.get("data_type", binding.get("data_type", "Float")),
                "default_value": default_branch.get("default_value"),
            }
            try:
                return handler(default_binding, doc, resolved_so_far)
            except Exception:
                pass

    return binding.get("default_value")


@register_source("fallback_chain")
def _handle_fallback_chain(binding: dict, doc, resolved_so_far: dict) -> Any:
    """Try sources in order until one succeeds (graceful degradation).

    Each source in the chain is tried sequentially. The FIRST source
    that returns a non-None, non-error value is used. If all sources
    fail, the binding's default_value is returned.

    Each source can specify:
        - timeout_ms: max time to wait (requires handler support)
        - on_failure: "skip" (default) or "raise"

    source_config format:
        {
            "chain": [
                {
                    "source_type": "custom_function",
                    "source_config": {"function": "fetch_lme_price", ...},
                    "timeout_ms": 3000,
                    "on_failure": "skip"
                },
                {
                    "source_type": "doctype_query",
                    "source_config": {"doctype": "Cached Price", ...},
                    "on_failure": "skip"
                },
                {
                    "source_type": "constant",
                    "source_config": {"value": 2500},
                    "label": "Manual fallback price"
                }
            ]
        }

    Use cases:
        - API → cache → manual default (resilience)
        - Primary DB → replica DB → snapshot → default
        - Premium service → free service → cached → hardcoded
    """
    cfg = json.loads(binding.get("source_config") or "{}")
    chain = cfg.get("chain") or []

    if not chain:
        return binding.get("default_value")

    errors = []

    for i, link in enumerate(chain):
        link_source_type = link.get("source_type", "")
        link_config = link.get("source_config", {})
        link_label = link.get("label", f"link_{i}")

        if not link_source_type:
            errors.append(f"{link_label}: missing source_type")
            continue

        handler = get_handler(link_source_type)
        if handler is None:
            errors.append(f"{link_label}: unknown source_type '{link_source_type}'")
            continue

        link_binding = {
            "variable_name": binding.get("variable_name", "_fallback_"),
            "source_type": link_source_type,
            "source_config": json.dumps(link_config) if isinstance(link_config, dict) else str(link_config),
            "data_type": link.get("data_type", binding.get("data_type", "Float")),
            "default_value": None,  # Don't use default — want to detect real failures
        }

        try:
            val = handler(link_binding, doc, resolved_so_far)
            if val is not None:
                # Success! Apply any transform from the fallback link
                if link.get("transform"):
                    from formula_builder.api.batch_binding_resolver import _apply_transform
                    link_binding["source_config"] = json.dumps({
                        **link_config,
                        "transform": link["transform"],
                    })
                    val = _apply_transform(val, link_binding, resolved_so_far)
                return val
            else:
                errors.append(f"{link_label}: returned None")
        except Exception as e:
            errors.append(f"{link_label}: {e}")
            if link.get("on_failure") == "raise":
                frappe.log_error(
                    f"Fallback chain link {i} ('{link_label}') failed with raise: {e}\n"
                    f"Prior errors: {'; '.join(errors)}",
                    "DataSource: fallback_chain",
                )
                return binding.get("default_value")

    # All links failed → log and return default
    frappe.log_error(
        f"Fallback chain exhausted ({len(chain)} links). "
        f"Errors: {'; '.join(errors)}",
        "DataSource: fallback_chain",
    )
    return binding.get("default_value")



# ═══════════════════════════════════════════════════════════════════════════
# DEPENDENCY RESOLVER
# ═══════════════════════════════════════════════════════════════════════════

def _get_dependency_graph(bindings: List[dict]) -> Dict[str, set]:
    """Build adjacency: node -> set of its dependencies."""
    graph: Dict[str, set] = {}
    var_names = {b["variable_name"] for b in bindings}

    for b in bindings:
        name = b["variable_name"]
        graph.setdefault(name, set())
        if b.get("source_type") == "computed":
            cfg = json.loads(b.get("source_config") or "{}")
            deps = cfg.get("dependencies") or []
            for dep in deps:
                if dep in var_names and dep != name:
                    graph[name].add(dep)
    return graph


def _topological_sort(graph: Dict[str, set]) -> List[str]:
    """Kahn's algorithm. graph: node → set of its dependencies.

    Raises ValueError on cycle.
    """
    # Build reverse graph: node → who depends on it
    reverse: Dict[str, set] = {n: set() for n in graph}
    for node, deps in graph.items():
        for dep in deps:
            reverse[dep].add(node)

    # in_degree = số dependencies chưa được resolve
    in_degree = {node: len(deps) for node, deps in graph.items()}

    queue = deque([n for n, d in in_degree.items() if d == 0])
    result = []

    while queue:
        node = queue.popleft()
        result.append(node)
        # Node đã resolve → giảm in_degree của tất cả nodes phụ thuộc vào nó
        for dependent in reverse.get(node, set()):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) != len(graph):
        remaining = sorted(n for n, d in in_degree.items() if d > 0)
        raise ValueError(
            f"Cycle detected among variables: {', '.join(remaining[:5])}"
        )
    return result


def resolve_bindings_with_deps(
    bindings: List[dict], doc=None
) -> Dict[str, Any]:
    """Resolve all bindings in topological order (dependencies first).

    Returns {variable_name: resolved_value}.
    """
    if not bindings:
        return {}

    graph = _get_dependency_graph(bindings)
    try:
        sorted_names = _topological_sort(graph)
    except ValueError as e:
        frappe.log_error(str(e), "DataSource: resolve_bindings")
        sorted_names = sorted(
            bindings, key=lambda b: b.get("resolve_priority", 100)
        )
        sorted_names = [b["variable_name"] for b in sorted_names]

    binding_map = {b["variable_name"]: b for b in bindings}
    resolved: Dict[str, Any] = {}

    for name in sorted_names:
        b = binding_map.get(name)
        if not b:
            continue
        source_type = b.get("source_type", "")
        handler = get_handler(source_type)
        if handler is None:
            frappe.log_error(
                f"No handler for source_type='{source_type}' (binding: {name})",
                "DataSource Registry",
            )
            resolved[name] = b.get("default_value")
            continue

        try:
            val = handler(b, doc, resolved)
            resolved[name] = val if val is not None else b.get("default_value")
        except frappe.PermissionError:
            raise
        except Exception as e:
            frappe.log_error(
                f"Resolve failed for '{name}' ({source_type}): {e}",
                "DataSource Registry",
            )
            resolved[name] = b.get("default_value")

    return resolved


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION — used by DocType hooks
# ═══════════════════════════════════════════════════════════════════════════

def detect_circular_bindings(bindings: List[dict]) -> Optional[str]:
    """Returns error message if bindings contain a cycle, else None."""
    graph = _get_dependency_graph(bindings)
    try:
        _topological_sort(graph)
        return None
    except ValueError as e:
        return str(e)


def validate_binding_source_config(binding: dict) -> Optional[str]:
    """Returns error string if source_config is invalid for the source_type."""
    source_type = binding.get("source_type", "")
    try:
        cfg = json.loads(binding.get("source_config") or "{}")
    except json.JSONDecodeError:
        return "source_config is not valid JSON."

    required_map = {
        "linked_doctype_field": ["link_field", "target_field"],
        "whole_doctype": ["link_field"],
        "child_table_aggregate": ["child_table_field", "field"],
        "custom_function": ["module", "function"],
        "computed": ["formula"],
        "doctype_query": ["doctype", "fieldname"],
        "dynamic_link": ["doctype_field", "name_field", "target_field"],
        # v31 Phase 2
        "pipeline": ["steps"],
        "conditional": ["branches"],
        "fallback_chain": ["chain"],
    }

    required = required_map.get(source_type, [])
    for key in required:
        if not cfg.get(key):
            return f"'{source_type}' requires '{key}' in source_config."

    if source_type == "computed":
        var_name = binding.get("variable_name", "")
        formula = cfg.get("formula", "")
        if var_name and var_name in formula:
            return (
                f"Self-reference detected: '{var_name}' appears in its own formula. "
                "This is not allowed."
            )

    return None


# ═══════════════════════════════════════════════════════════════════════════
# v31 — REGISTER ALL HANDLERS WITH METADATA IN SourceTypeRegistry
# ═══════════════════════════════════════════════════════════════════════════
# This block runs at import time and populates the central SourceTypeRegistry
# with full metadata (label, description, config_schema) for every built-in
# source type. External apps register via @register_source from
# source_type_registry.py which also calls this.

def _register_all_to_central_registry():
    """Register all 10 built-in handlers with SourceTypeRegistry metadata."""
    try:
        from formula_builder.api.source_type_registry import SourceTypeRegistry
        registry = SourceTypeRegistry.get_instance()
    except ImportError:
        return

    # Prevent double registration
    if registry.has("constant") and registry.get("constant").config_schema:
        return

    registry.register(
        "constant",
        _handle_constant,
        label="Constant Value",
        description="A fixed literal value defined in the binding config.",
        config_schema={
            "type": "object",
            "required": ["value"],
            "properties": {
                "value": {"type": "string", "description": "The constant value (will be cast to data_type)"},
            },
        },
        supports_transform=True,
    )

    registry.register(
        "linked_doctype_field",
        _handle_linked_doctype_field,
        label="Linked DocType Field",
        description="Read a single field from a linked document via link_field → target_doctype → target_field.",
        config_schema={
            "type": "object",
            "required": ["link_field", "target_field"],
            "properties": {
                "link_field": {"type": "string", "description": "Field on current doc that links to target doctype"},
                "target_doctype": {"type": "string", "description": "Target doctype (auto-detected from link_field if blank)"},
                "target_field": {"type": "string", "description": "Field to read from the linked document"},
                "fallback": {"type": "string", "description": "Fallback value if not found"},
            },
        },
        batchable=True,
        fingerprint_fn=lambda cfg: "linked:" + cfg.get("target_doctype", "") + ":" + cfg.get("target_field", ""),
        supports_transform=True,
        supports_cache=True,
        default_cache_ttl=300,
    )

    registry.register(
        "whole_doctype",
        _handle_whole_doctype,
        label="Whole DocType",
        description="Return the entire linked document as a dict of all scalar fields, optionally including child tables.",
        config_schema={
            "type": "object",
            "required": ["link_field"],
            "properties": {
                "link_field": {"type": "string", "description": "Field on current doc that links to target doctype"},
                "target_doctype": {"type": "string", "description": "Target doctype (auto-detected from link_field if blank)"},
                "fields": {"type": "array", "items": {"type": "string"}, "description": "Specific fields to include (all scalar fields if blank)"},
                "include_child_tables": {"type": "boolean", "description": "Whether to include child table data"},
            },
        },
        batchable=True,
        fingerprint_fn=lambda cfg: "whole:" + cfg.get("target_doctype", ""),
        supports_cache=True,
        default_cache_ttl=300,
    )

    registry.register(
        "child_table_aggregate",
        _handle_child_table_aggregate,
        label="Child Table Aggregate",
        description="Aggregate values from a child table: sum, avg, min, max, count, list. Supports filter expressions.",
        config_schema={
            "type": "object",
            "required": ["child_table_field", "field"],
            "properties": {
                "child_table_field": {"type": "string", "description": "Fieldname of the child table on the document"},
                "field": {"type": "string", "description": "Field in the child table to aggregate"},
                "aggregate": {"type": "string", "enum": ["sum", "avg", "min", "max", "count", "list"], "description": "Aggregation method"},
                "filter_expr": {"type": "string", "description": "Python expression to filter rows (e.g. 'row.qty > 10'). Uses AST sandbox."},
            },
        },
    )

    registry.register(
        "global_default",
        _handle_global_default,
        label="Global Default",
        description="Read a value from Frappe's Global Defaults settings.",
        config_schema={
            "type": "object",
            "required": ["key"],
            "properties": {
                "key": {"type": "string", "description": "Key in Global Defaults to read"},
                "company_specific": {"type": "boolean", "description": "Whether to scope by company"},
                "company_field": {"type": "string", "description": "Field name for company on the document"},
            },
        },
        supports_cache=True,
        default_cache_ttl=600,
    )

    registry.register(
        "session_variable",
        _handle_session_variable,
        label="Session Variable",
        description="Read from the current user session: user, roles, company, today, now.",
        config_schema={
            "type": "object",
            "required": ["key"],
            "properties": {
                "key": {"type": "string", "enum": ["user", "user_fullname", "user_roles", "lang", "now", "today", "company"], "description": "Session key to read"},
            },
        },
    )

    registry.register(
        "doctype_query",
        _handle_doctype_query,
        label="DocType Query",
        description="Query any doctype with filters and optional aggregation. The most flexible built-in source type.",
        config_schema={
            "type": "object",
            "required": ["doctype", "fieldname"],
            "properties": {
                "doctype": {"type": "string", "description": "Target DocType name"},
                "fieldname": {"type": "string", "description": "Field to read or aggregate"},
                "aggregate": {"type": "string", "enum": ["first", "last", "count", "list", "sum"], "description": "Aggregation mode: first (single value), last, count, list, sum"},
                "filters": {
                    "type": "array",
                    "description": "Frappe-style filters: [['field', '=', 'value'], ...]. Supports {resolved.xxx} and {inputs.xxx} templates.",
                    "items": {
                        "type": "array",
                        "items": [{"type": "string"}, {"type": "string"}, {}],
                    },
                },
                "batch_key": {"type": "string", "description": "Key field to extract value from batch results"},
                "transform": {
                    "type": "object",
                    "description": "Post-resolve transformation",
                    "properties": {
                        "formula": {"type": "string", "description": "Formula to transform value (use 'value' as the input variable)"},
                        "round": {"type": "integer", "description": "Decimal places to round to"},
                        "multiply": {"type": "number", "description": "Multiply value by this factor"},
                    },
                },
            },
        },
        batchable=True,
        fingerprint_fn=lambda cfg: "doctype_query:" + cfg.get("doctype", "") + ":" + cfg.get("fieldname", ""),
        supports_transform=True,
        supports_cache=True,
        default_cache_ttl=300,
    )

    registry.register(
        "custom_function",
        _handle_custom_function,
        label="Custom Function",
        description="Call an arbitrary Python function from a whitelisted module. Args support {resolved.xxx} and {doc.xxx} templates.",
        config_schema={
            "type": "object",
            "required": ["module", "function"],
            "properties": {
                "module": {"type": "string", "description": "Python module path (must be in custom_function_whitelist)"},
                "function": {"type": "string", "description": "Function name to call"},
                "args": {"type": "object", "description": "Keyword arguments. Values can use {resolved.xxx}, {doc.xxx}, {inputs.xxx} templates."},
            },
        },
        supports_transform=True,
        supports_cache=True,
        default_cache_ttl=0,
    )

    registry.register(
        "dynamic_link",
        _handle_dynamic_link,
        label="Dynamic Link",
        description="Resolve a field where the target doctype is itself a field value (Dynamic Link pattern).",
        config_schema={
            "type": "object",
            "required": ["doctype_field", "name_field", "target_field"],
            "properties": {
                "doctype_field": {"type": "string", "description": "Field that contains the target doctype name"},
                "name_field": {"type": "string", "description": "Field that contains the target document name"},
                "target_field": {"type": "string", "description": "Field to read from the target document"},
            },
        },
    )

    registry.register(
        "computed",
        _handle_computed,
        label="Computed Formula",
        description="Evaluate a formula expression using already-resolved variables. Supports DAG-based dependency ordering.",
        config_schema={
            "type": "object",
            "required": ["formula"],
            "properties": {
                "formula": {"type": "string", "description": "Formula expression using resolved variables"},
                "dependencies": {"type": "array", "items": {"type": "string"}, "description": "Variable names this formula depends on (for DAG ordering)"},
            },
        },
        supports_transform=True,
    )

    # ── v31 Phase 2: Composite source types ─────────────────────────

    registry.register(
        "pipeline",
        _handle_pipeline,
        label="Pipeline (Chained Sources)",
        description="Chain multiple data sources sequentially. Output of each step feeds into the next. Use for multi-step data flows without code.",
        config_schema={
            "type": "object",
            "required": ["steps"],
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "Ordered list of source steps to execute",
                    "items": {
                        "type": "object",
                        "required": ["source_type"],
                        "properties": {
                            "source_type": {"type": "string", "description": "Any registered source type"},
                            "source_config": {"type": "object", "description": "Config for this step's source"},
                            "output_as": {"type": "string", "description": "Variable name to store this step's output (accessible in later steps)"},
                            "data_type": {"type": "string", "description": "Data type for this step"},
                            "default_value": {"type": "string", "description": "Fallback if this step fails"},
                        },
                    },
                },
                "merge_strategy": {"type": "string", "enum": ["last", "all"], "description": "'last' returns final step only; 'all' returns dict of all outputs"},
            },
        },
        batchable=True,
        fingerprint_fn=lambda cfg: "pipeline:" + hashlib.md5(
            json.dumps(cfg.get("steps", []), sort_keys=True).encode()
        ).hexdigest()[:12],
        supports_transform=True,
    )

    registry.register(
        "conditional",
        _handle_conditional,
        label="Conditional (Branching)",
        description="Select a data source at runtime based on conditions. First matching branch wins. Use for multi-scenario logic without code.",
        config_schema={
            "type": "object",
            "required": ["branches"],
            "properties": {
                "branches": {
                    "type": "array",
                    "description": "List of conditional branches, evaluated in order",
                    "items": {
                        "type": "object",
                        "required": ["condition", "source_type"],
                        "properties": {
                            "condition": {"type": "string", "description": "Python expression using resolved variables. Example: product_type == 'CUA_DI'"},
                            "source_type": {"type": "string", "description": "Source type to use if condition is True"},
                            "source_config": {"type": "object", "description": "Config for this branch's source"},
                            "data_type": {"type": "string", "description": "Data type"},
                            "default_value": {"type": "string", "description": "Fallback if this branch fails"},
                        },
                    },
                },
                "default": {
                    "type": "object",
                    "description": "Default source if no condition matches",
                    "required": ["source_type"],
                    "properties": {
                        "source_type": {"type": "string"},
                        "source_config": {"type": "object"},
                    },
                },
            },
        },
        supports_transform=True,
    )

    registry.register(
        "fallback_chain",
        _handle_fallback_chain,
        label="Fallback Chain (Resilience)",
        description="Try sources in order until one succeeds. Primary → fallback_1 → fallback_2 → default. Use for API resilience and graceful degradation.",
        config_schema={
            "type": "object",
            "required": ["chain"],
            "properties": {
                "chain": {
                    "type": "array",
                    "description": "Ordered list of sources to try. First success wins.",
                    "items": {
                        "type": "object",
                        "required": ["source_type"],
                        "properties": {
                            "source_type": {"type": "string", "description": "Source type to try"},
                            "source_config": {"type": "object", "description": "Config for this source"},
                            "label": {"type": "string", "description": "Human-readable label for error logging"},
                            "timeout_ms": {"type": "integer", "description": "Max wait time in milliseconds"},
                            "on_failure": {"type": "string", "enum": ["skip", "raise"], "description": "'skip' continues chain; 'raise' stops immediately"},
                            "data_type": {"type": "string"},
                            "transform": {"type": "object", "description": "Transform to apply if this link succeeds"},
                        },
                    },
                },
            },
        },
        supports_transform=False,  # transform is applied per-link, not to the chain as a whole
    )


# Run registration at import time
_register_all_to_central_registry()


# ═══════════════════════════════════════════════════════════════════════════
# v31 PHASE 3 — PLATFORM EXPANSION SOURCE TYPES (2026-08-16)
#   matrix_lookup (S2)        — 2D pricing/parameter matrix lookup
#   reuse_formula_result (S1) — reuse results from another formula/BOM/config
#
# Generic for every app. Registered via the unified @register_source from
# source_type_registry so they carry full metadata (config_schema, fingerprint,
# batchable) in BOTH the central registry and the legacy handler dict.
# ═══════════════════════════════════════════════════════════════════════════
from formula_builder.api.source_type_registry import register_source

# Sentinel: a matched row exists but the value cell is empty → treat as no match
_MISSING = object()


def _fb_row_get(obj, key):
    """Read a field from a dict / frappe Document / any object with .get()."""
    if obj is None or not key:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    getter = getattr(obj, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            pass
    return getattr(obj, key, None)


def _resolve_template_val(val, doc=None, resolved_so_far=None, row=None):
    """Resolve template strings referencing runtime context.

    Supported syntax (double-brace + FB legacy single-brace):
      - {{row.field}}   / {row.field}       → value from the current child-table row
      - {{doc.field}}   / {doc.field}       → value from the parent document
      - {{resolved.x}}  / {resolved.x}      → value from already-resolved variables
      - {{inputs.x}}    / {inputs.x}        → alias of resolved

    If the whole string is one template, the raw value is returned (type preserved).
    If templates are embedded in literal text, they are replaced as strings.
    Strings without templates are returned unchanged (literals).
    """
    import re
    if not isinstance(val, str):
        return val
    resolved_so_far = resolved_so_far or {}
    if row is None:
        row = resolved_so_far.get("row")

    def _scope_value(scope, key):
        if scope == "row":
            return _fb_row_get(row, key)
        if scope in ("resolved", "inputs"):
            return resolved_so_far.get(key)
        if scope == "doc":
            return _fb_row_get(doc, key)
        return None

    full = re.fullmatch(
        r"\s*\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}\s*", val
    )
    if full:
        return _scope_value(full.group(1), full.group(2))
    full = re.fullmatch(
        r"\s*\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\s*", val
    )
    if full:
        return _scope_value(full.group(1), full.group(2))

    out = val
    for m in re.finditer(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", val):
        v = _scope_value(m.group(1), m.group(2))
        out = out.replace(m.group(0), "" if v is None else str(v))
    for m in re.finditer(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}", val):
        v = _scope_value(m.group(1), m.group(2))
        out = out.replace(m.group(0), "" if v is None else str(v))
    return out


def _binding_row(binding, resolved_so_far):
    """Locate the 'current row' from resolved_so_far or the binding itself."""
    if isinstance(resolved_so_far, dict) and resolved_so_far.get("row") is not None:
        return resolved_so_far.get("row")
    if binding and isinstance(binding, dict):
        return binding.get("row")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# matrix_lookup (S2)
# ═══════════════════════════════════════════════════════════════════════════

def _matrix_lookup_value(rows, cfg, row_key, col_key, fb_row_key, fb_col_key, match_mode):
    """Search fetched matrix rows for a matching cell.

    Returns the raw value of the matched cell, or _MISSING if none matched.
    Resolution order:
      1. exact (row_key, col_key)
      2. fallback row key + exact col key
      3. exact row key + fallback col key
      4. fallback row key + fallback col key
    """
    row_key_field = cfg.get("row_key_field", "")
    col_key_field = cfg.get("col_key_field", "")
    value_field = cfg.get("value_field", "")

    def _eq(a, b):
        if a is None or b is None:
            return False
        if match_mode == "case_insensitive":
            return str(a).strip().lower() == str(b).strip().lower()
        return str(a).strip() == str(b).strip()

    def _find(rk, ck):
        # An axis with a configured field but no resolvable lookup value can never match.
        if row_key_field and rk is None:
            return _MISSING
        if col_key_field and ck is None:
            return _MISSING
        for r in rows:
            rv = _fb_row_get(r, row_key_field) if row_key_field else None
            cv = _fb_row_get(r, col_key_field) if col_key_field else None
            row_ok = (not row_key_field) or _eq(rv, rk)
            col_ok = (not col_key_field) or _eq(cv, ck)
            if row_ok and col_ok:
                val = _fb_row_get(r, value_field)
                if val is not None:
                    return val
        return _MISSING

    # Degenerate: matrix has no axes → first row's value
    if not row_key_field and not col_key_field:
        if rows:
            val = _fb_row_get(rows[0], value_field)
            return val if val is not None else _MISSING
        return _MISSING

    val = _find(row_key, col_key)
    if val is not _MISSING:
        return val
    if fb_row_key is not None:
        val = _find(fb_row_key, col_key)
        if val is not _MISSING:
            return val
    if fb_col_key is not None:
        val = _find(row_key, fb_col_key)
        if val is not _MISSING:
            return val
    if fb_row_key is not None and fb_col_key is not None:
        val = _find(fb_row_key, fb_col_key)
        if val is not _MISSING:
            return val
    return _MISSING


@register_source(
    "matrix_lookup",
    label="Matrix Lookup (2D)",
    description=(
        "Look up a value from a two-dimensional pricing/parameter matrix by row key and "
        "column key, with fallback row/col keys and default_value when no cell matches."
    ),
    config_schema={
        "type": "object",
        "required": ["doctype", "value_field"],
        "properties": {
            "doctype": {"type": "string", "description": "DocType storing the matrix rows"},
            "row_key_field": {"type": "string", "description": "Field used as the row key (e.g. size)"},
            "col_key_field": {"type": "string", "description": "Field used as the column key (e.g. thickness)"},
            "value_field": {"type": "string", "description": "Field holding the value to return"},
            "row_key": {"type": "string", "description": "Value to match on the row axis. Supports {{row.field}}, {{doc.field}}, {{resolved.field}} templates."},
            "col_key": {"type": "string", "description": "Value to match on the column axis. Supports templates."},
            "fallback_row_key": {"type": "string", "description": "Row key to fall back to when no exact match (e.g. 'ANY'). Supports templates."},
            "fallback_col_key": {"type": "string", "description": "Column key to fall back to when no exact match (e.g. 'ANY'). Supports templates."},
            "match_mode": {"type": "string", "enum": ["exact", "case_insensitive"], "description": "Key comparison mode"},
            "filters": {"type": "array", "description": "Extra Frappe filters scoping the matrix query (e.g. by currency, region, date)."},
        },
    },
    batchable=True,
    fingerprint_fn=lambda cfg: "matrix_lookup:" + "|".join([
        cfg.get("doctype", ""),
        cfg.get("row_key_field", ""),
        cfg.get("col_key_field", ""),
        cfg.get("value_field", ""),
        cfg.get("match_mode", "exact"),
        hashlib.md5(json.dumps(cfg.get("filters") or [], sort_keys=True).encode()).hexdigest()[:12],
    ]),
    supports_transform=True,
    supports_cache=True,
    default_cache_ttl=300,
)
def _handle_matrix_lookup(binding, doc, resolved_so_far):
    cfg = json.loads(binding.get("source_config") or "{}")
    doctype = cfg.get("doctype", "")
    value_field = cfg.get("value_field", "")
    default_value = cfg.get("default_value", binding.get("default_value"))
    data_type = binding.get("data_type") or cfg.get("type", "Float")

    if not doctype or not value_field:
        return default_value

    row = _binding_row(binding, resolved_so_far)
    row_key = _resolve_template_val(cfg.get("row_key"), doc, resolved_so_far, row)
    col_key = _resolve_template_val(cfg.get("col_key"), doc, resolved_so_far, row)
    fb_row_key = _resolve_template_val(cfg.get("fallback_row_key"), doc, resolved_so_far, row) if cfg.get("fallback_row_key") is not None else None
    fb_col_key = _resolve_template_val(cfg.get("fallback_col_key"), doc, resolved_so_far, row) if cfg.get("fallback_col_key") is not None else None
    match_mode = cfg.get("match_mode", "exact")

    try:
        fields = list(dict.fromkeys(
            f for f in (cfg.get("row_key_field", ""), cfg.get("col_key_field", ""), value_field) if f
        ))
        rows = frappe.get_all(
            doctype,
            filters=cfg.get("filters") or None,
            fields=fields,
            limit_page_length=0,
        ) or []
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"DataSource: matrix_lookup ({binding.get('variable_name')})",
        )
        return default_value

    val = _matrix_lookup_value(rows, cfg, row_key, col_key, fb_row_key, fb_col_key, match_mode)
    if val is _MISSING:
        return default_value
    return _cast(val, data_type)


def _resolve_matrix_lookup_batch(bindings, doc, resolved_so_far):
    """Batch: fetch the matrix rows ONCE per group, reuse across bindings."""
    results = {}
    if not bindings:
        return results
    cfg0 = json.loads(bindings[0].get("source_config") or "{}")
    doctype = cfg0.get("doctype", "")
    value_field = cfg0.get("value_field", "")
    match_mode = cfg0.get("match_mode", "exact")
    fields = list(dict.fromkeys(
        f for f in (cfg0.get("row_key_field", ""), cfg0.get("col_key_field", ""), value_field) if f
    ))
    rows = []
    if doctype and value_field:
        try:
            rows = frappe.get_all(
                doctype,
                filters=cfg0.get("filters") or None,
                fields=fields,
                limit_page_length=0,
            ) or []
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "DataSource: matrix_lookup (batch)",
            )
            rows = []

    for b in bindings:
        cfg = json.loads(b.get("source_config") or "{}")
        default_value = cfg.get("default_value", b.get("default_value"))
        data_type = b.get("data_type") or cfg.get("type", "Float")
        if not doctype or not value_field or not rows:
            results[b["variable_name"]] = default_value
            continue
        row = _binding_row(b, resolved_so_far)
        row_key = _resolve_template_val(cfg.get("row_key"), doc, resolved_so_far, row)
        col_key = _resolve_template_val(cfg.get("col_key"), doc, resolved_so_far, row)
        fb_row_key = _resolve_template_val(cfg.get("fallback_row_key"), doc, resolved_so_far, row) if cfg.get("fallback_row_key") is not None else None
        fb_col_key = _resolve_template_val(cfg.get("fallback_col_key"), doc, resolved_so_far, row) if cfg.get("fallback_col_key") is not None else None
        val = _matrix_lookup_value(rows, cfg, row_key, col_key, fb_row_key, fb_col_key, match_mode)
        results[b["variable_name"]] = default_value if val is _MISSING else _cast(val, data_type)
    return results


_handle_matrix_lookup.resolve_batch = _resolve_matrix_lookup_batch


# ═══════════════════════════════════════════════════════════════════════════
# reuse_formula_result (S1)
# ═══════════════════════════════════════════════════════════════════════════

def _detect_line_field(target_doc):
    """Auto-detect the first Table child-table field on the target document."""
    if target_doc is None:
        return None
    try:
        for f in target_doc.meta.fields:
            if f.fieldtype in ("Table", "Table MultiSelect"):
                return f.fieldname
    except Exception:
        pass
    for name in ("lines", "items", "rows", "cost_lines", "details"):
        if target_doc.get(name) is not None:
            return name
    return None


def _infer_line_match_field(line_match):
    """Infer the target-line field from a line_match template/bare field name.

    '{{row.item_code}}'  → 'item_code'
    '{row.item_code}'    → 'item_code'
    'item_code'          → 'item_code'
    '{{doc.quotation}}'  → None (no inferable target-line field → use line_match_field)
    """
    import re
    if not line_match or not isinstance(line_match, str):
        return None
    s = line_match.strip()
    m = re.fullmatch(r"\{\{\s*row\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", s)
    if m:
        return m.group(1)
    m = re.fullmatch(r"\{\s*row\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}", s)
    if m:
        return m.group(1)
    if all(ch.isalnum() or ch == "_" for ch in s) and not s[0].isdigit():
        return s
    return None


def _resolve_reuse_target_name(cfg, doc, resolved_so_far):
    """Locate the formula/BOM/config document instance to reuse results from."""
    formula_document = cfg.get("formula_document", "")
    if cfg.get("document_name"):
        return _resolve_template_val(cfg.get("document_name"), doc, resolved_so_far)

    scope_field = cfg.get("scope_field", "")
    scope_value = cfg.get("scope_value")
    if not formula_document or not scope_field or scope_value is None:
        return None
    sv = _resolve_template_val(scope_value, doc, resolved_so_far)
    if sv is None or sv == "":
        return None
    extra = []
    for f in cfg.get("filters") or []:
        if isinstance(f, list) and len(f) == 3:
            extra.append([f[0], f[1], _resolve_template_val(f[2], doc, resolved_so_far)])
    filters = [[scope_field, "=", sv]] + extra
    order_by = cfg.get("scope_order_by", "modified desc")
    try:
        names = frappe.get_all(
            formula_document,
            filters=filters,
            fields=["name"],
            limit=1,
            order_by=order_by,
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"DataSource: reuse_formula_result (locate {formula_document})",
        )
        return None
    return names[0].get("name") if names else None


def _aggregate_reuse_lines(target_doc, cfg, doc, resolved_so_far, row, default_value, data_type):
    """Select matching lines from the target document and aggregate result_field."""
    line_field = cfg.get("line_field") or _detect_line_field(target_doc)
    lines = []
    if line_field:
        lines = target_doc.get(line_field) or []
    if not lines:
        return default_value

    # Match current row against target lines
    matched = list(lines)
    if cfg.get("line_match"):
        lm_raw = cfg.get("line_match")
        lm_field = cfg.get("line_match_field") or _infer_line_match_field(lm_raw)
        # Bare field name (e.g. "item_code") → resolve the value from the current row
        if lm_field and isinstance(lm_raw, str) and lm_raw.strip() == lm_field:
            match_val = _fb_row_get(row, lm_field) if row is not None else None
        else:
            match_val = _resolve_template_val(lm_raw, doc, resolved_so_far, row)
        if match_val is not None and lm_field:
            matched = [
                ln for ln in lines
                if _fb_row_get(ln, lm_field) is not None
                and str(_fb_row_get(ln, lm_field)).strip() == str(match_val).strip()
            ]

    if not matched:
        return default_value

    aggregation = cfg.get("aggregation", "sum")
    values = [_fb_row_get(ln, cfg.get("result_field", "")) for ln in matched]

    if aggregation in ("first", "last"):
        idx = 0 if aggregation == "first" else len(values) - 1
        return _cast(values[idx], data_type)

    nums = []
    for v in values:
        if v is None:
            continue
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return default_value
    if aggregation == "sum":
        result = sum(nums)
    elif aggregation == "avg":
        result = sum(nums) / len(nums)
    elif aggregation == "min":
        result = min(nums)
    elif aggregation == "max":
        result = max(nums)
    else:
        return default_value
    return _cast(result, data_type)


@register_source(
    "reuse_formula_result",
    label="Reuse Formula Result",
    description=(
        "Reuse results from another formula/BOM/config document (e.g. cost template lines). "
        "Locates the target document by scope_field/scope_value, matches its child lines to the "
        "current row, and aggregates result_field (sum/min/max/avg/first/last)."
    ),
    config_schema={
        "type": "object",
        "required": ["formula_document", "result_field"],
        "properties": {
            "formula_document": {"type": "string", "description": "DocType of the formula/BOM/cost-template document whose results are reused"},
            "scope_field": {"type": "string", "description": "Field on the target document used to locate the right instance (e.g. 'quotation')"},
            "scope_value": {"type": "string", "description": "Value for scope_field; supports {{row.field}}, {{doc.field}}, {{resolved.field}} templates."},
            "document_name": {"type": "string", "description": "Alternative to scope_field/scope_value: exact document name (template supported)."},
            "line_field": {"type": "string", "description": "Child-table fieldname holding the result lines (auto-detected from the first Table field if blank)."},
            "line_match": {"type": "string", "description": "Template/field matching the current row against target lines, e.g. '{{row.item_code}}'."},
            "line_match_field": {"type": "string", "description": "Field on target lines compared to line_match (defaults to line_match when it is a bare field name or a {{row.X}} template)."},
            "result_field": {"type": "string", "description": "Field on matched lines to aggregate/read."},
            "aggregation": {"type": "string", "enum": ["sum", "min", "max", "avg", "first", "last"], "description": "How to combine matched lines."},
            "scope_order_by": {"type": "string", "description": "Order used to pick the target document when scope_field matches several (default 'modified desc')."},
            "filters": {"type": "array", "description": "Extra Frappe filters scoping the target-document lookup."},
        },
    },
    batchable=True,
    fingerprint_fn=lambda cfg: "reuse_formula_result:" + "|".join([
        cfg.get("formula_document", ""),
        cfg.get("scope_field", ""),
        cfg.get("line_field", ""),
        cfg.get("line_match_field", ""),
        cfg.get("result_field", ""),
        cfg.get("aggregation", "sum"),
        hashlib.md5(
            json.dumps(
                [cfg.get("scope_value"), cfg.get("line_match"), cfg.get("document_name"), cfg.get("filters") or []],
                sort_keys=True,
            ).encode()
        ).hexdigest()[:12],
    ]),
    supports_transform=True,
    supports_cache=True,
    default_cache_ttl=300,
)
def _handle_reuse_formula_result(binding, doc, resolved_so_far):
    cfg = json.loads(binding.get("source_config") or "{}")
    formula_document = cfg.get("formula_document", "")
    result_field = cfg.get("result_field", "")
    default_value = cfg.get("default_value", binding.get("default_value"))
    data_type = binding.get("data_type") or cfg.get("type", "Float")

    if not formula_document or not result_field:
        return default_value

    name = _resolve_reuse_target_name(cfg, doc, resolved_so_far)
    if not name:
        return default_value

    try:
        target_doc = frappe.get_doc(formula_document, name)
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"DataSource: reuse_formula_result (get_doc {formula_document}/{name})",
        )
        return default_value

    row = _binding_row(binding, resolved_so_far)
    return _aggregate_reuse_lines(
        target_doc, cfg, doc, resolved_so_far, row, default_value, data_type
    )


def _resolve_reuse_formula_result_batch(bindings, doc, resolved_so_far):
    """Batch: fetch each referenced target document once and reuse across bindings."""
    results = {}
    if not bindings:
        return results
    doc_cache = {}
    for b in bindings:
        cfg = json.loads(b.get("source_config") or "{}")
        formula_document = cfg.get("formula_document", "")
        result_field = cfg.get("result_field", "")
        default_value = cfg.get("default_value", b.get("default_value"))
        data_type = b.get("data_type") or cfg.get("type", "Float")
        if not formula_document or not result_field:
            results[b["variable_name"]] = default_value
            continue
        name = _resolve_reuse_target_name(cfg, doc, resolved_so_far)
        if not name:
            results[b["variable_name"]] = default_value
            continue
        if name not in doc_cache:
            try:
                doc_cache[name] = frappe.get_doc(formula_document, name)
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"DataSource: reuse_formula_result (batch get_doc {formula_document}/{name})",
                )
                doc_cache[name] = None
        target_doc = doc_cache[name]
        if target_doc is None:
            results[b["variable_name"]] = default_value
            continue
        row = _binding_row(b, resolved_so_far)
        results[b["variable_name"]] = _aggregate_reuse_lines(
            target_doc, cfg, doc, resolved_so_far, row, default_value, data_type
        )
    return results


_handle_reuse_formula_result.resolve_batch = _resolve_reuse_formula_result_batch



# ═══════════════════════════════════════════════════════════════════════════
# FB-1 REVISED — MATRIX N-CHIỀU + AGGREGATE_FROM_ITEMS (2026-08-16)
#   composite_key_lookup   — matrix N-chiều (key_fields động + fallback_keys +
#                            match_mode exact/case_insensitive/multiplier_chain)
#   aggregate_from_items   — sum field theo key_field/key_value (giống sumif),
#                            rows_source = snapshot | child_table | doctype_query
#                            (thay py thuần dict fb_handlers.cost_bucket_aggregate)
#
# Backward-compat: matrix_lookup 2 trục = special case — giữ nguyên, không sửa.
# Mọi thứ THÊM ở cuối file. Không đụng dòng 584/1075.
# ═══════════════════════════════════════════════════════════════════════════


# ───────────────────────────────────────────────────────────────────────────
# composite_key_lookup — matrix N-chiều
# ───────────────────────────────────────────────────────────────────────────

def _resolve_key_values(cfg, doc, resolved_so_far, row):
    """Resolve danh sách (key_field, key_value) từ config.

    key_fields: list N tên field làm chiều.
    key_values: list N giá trị — hỗ trợ template {{row.x}}/{{doc.x}}/{{resolved.x}}.
      Nếu bỏ trống → auto-map '{{row.<key_field>}}' cho từng chiều.
    Trả về list tuple (field, value). Bỏ qua chiều có value None/''.
    """
    key_fields = cfg.get("key_fields") or []
    key_values = cfg.get("key_values") or []
    out = []
    for i, kf in enumerate(key_fields):
        if i < len(key_values) and key_values[i] is not None and str(key_values[i]).strip():
            raw = key_values[i]
        else:
            raw = "{{row." + kf + "}}"
        val = _resolve_template_val(raw, doc, resolved_so_far, row)
        if val is None or val == "":
            continue
        out.append((kf, val))
    return out


def _composite_match_value(rows, cfg, dims, match_mode):
    """Tìm row khớp N chiều trong danh sách rows.

    Trả về (row, set_of_matched_key_fields) hoặc (None, None).
    match_mode exact | case_insensitive ảnh hưởng cách so sánh.
    """
    row_key_fields = [d[0] for d in dims]

    def _eq(a, b):
        if a is None or b is None:
            return False
        if match_mode == "case_insensitive":
            return str(a).strip().lower() == str(b).strip().lower()
        return str(a).strip() == str(b).strip()

    for r in rows:
        if not isinstance(r, dict):
            continue
        ok = True
        for kf, kv in dims:
            if not _eq(_fb_row_get(r, kf), kv):
                ok = False
                break
        if ok:
            return r, set(row_key_fields)
    return None, None


def _apply_multiplier_chain(cfg, doc, resolved_so_far, row, base_value, matched_dims):
    """multiplier_chain: base_value × ∏(multiplier của từng chiều KHÔNG khớp).

    matched_dims: set key_field đã khớp ở row fallback. Các chiều còn lại
    (trong key_fields nhưng không khớp) → tra multipliers[dim] và nhân.
    """
    value = base_value
    try:
        value = float(value)
    except (TypeError, ValueError):
        return base_value
    key_fields = cfg.get("key_fields") or []
    multipliers = cfg.get("multipliers") or {}
    for kf in key_fields:
        if kf in matched_dims:
            continue
        mcfg = multipliers.get(kf)
        if not mcfg:
            continue
        m_doctype = mcfg.get("doctype") or cfg.get("doctype")
        m_match_field = mcfg.get("match_field", kf)
        m_match_value = mcfg.get("match_value")
        m_value_field = mcfg.get("value_field", "multiplier")
        if m_match_value is None:
            m_match_value = "{{row." + kf + "}}"
        mv = _resolve_template_val(m_match_value, doc, resolved_so_far, row)
        if mv is None:
            continue
        try:
            rows_m = frappe.get_all(
                m_doctype,
                filters=[[m_match_field, "=", mv]],
                fields=[m_value_field],
                limit=1,
                limit_page_length=1,
            )
            if not rows_m:
                continue
            mult = rows_m[0].get(m_value_field)
            value = value * float(mult)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"DataSource: composite_key_lookup multiplier ({m_doctype}/{m_match_field})",
            )
    return value


def _fetch_composite_rows(cfg):
    """Fetch toàn bộ rows của ma trận 1 lần (doctype + filters).

    Fields: key_fields + value_field (+ các field multiplier nếu có).
    """
    doctype = cfg.get("doctype", "")
    if not doctype:
        return []
    value_field = cfg.get("value_field", "")
    fields = list(cfg.get("key_fields") or [])
    if value_field and value_field not in fields:
        fields.append(value_field)
    for mcfg in (cfg.get("multipliers") or {}).values():
        vf = mcfg.get("value_field")
        if vf and vf not in fields:
            fields.append(vf)
    try:
        return frappe.get_all(
            doctype,
            filters=cfg.get("filters") or None,
            fields=fields or ["name"],
            limit_page_length=0,
        ) or []
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"DataSource: composite_key_lookup fetch ({doctype})",
        )
        return []


def _resolve_composite_value(rows, cfg, dims, doc, resolved_so_far, row,
                             default_value, data_type):
    """Resolve 1 binding composite trên tập rows đã fetch.

    Resolution order:
      1. exact (toàn bộ dims) → value
      2. fallback_keys: lần lượt thử từng subset (rút bớt chiều)
      3. multiplier_chain: nếu khớp fallback mà còn chiều bỏ → nhân multiplier
      4. default_value
    """
    value_field = cfg.get("value_field", "")
    match_mode = cfg.get("match_mode", "exact")

    # 1. Exact full dims
    matched_row, matched_dims = _composite_match_value(rows, cfg, dims, match_mode)
    if matched_row is not None:
        return _cast(matched_row.get(value_field), data_type)

    # 2. Fallback subsets (rút dần chiều)
    fallback_keys = cfg.get("fallback_keys") or []
    for subset in fallback_keys:
        subset_dims = [d for d in dims if d[0] in subset]
        if not subset_dims:
            continue
        candidates = _composite_fallback_candidates(
            rows, cfg, dims, subset_dims, match_mode
        )
        mrow, mset = _composite_match_value(candidates, cfg, subset_dims, match_mode)
        if mrow is not None:
            base = mrow.get(value_field)
            if match_mode == "multiplier_chain":
                base = _apply_multiplier_chain(
                    cfg, doc, resolved_so_far, row, base, mset
                )
            return _cast(base, data_type)

    return default_value


def _composite_fallback_candidates(rows, cfg, dims, subset_dims, match_mode):
    """Lọc rows cho fallback subset: chỉ giữ row mà các chiều KHÔNG nằm
    trong subset có giá trị ANY/None/'' hoặc bằng giá trị requested.

    Mục đích: khi rút bớt chiều (vd chỉ khớp item_code+color), row ứng viên
    phải là row tổng quát (chiều bỏ = ANY) hoặc không mâu thuẫn với giá trị
    requested — KHÔNG lấy row cụ thể có giá trị khác (vd thickness=1.2 khi
    đang cần 9.9). Đây là ngữ nghĩa đúng của bảng giá fallback.
    """
    subset_fields = {d[0] for d in subset_dims}
    requested = {d[0]: d[1] for d in dims if d[0] not in subset_fields}

    def _eq(a, b):
        if a is None or b is None:
            return False
        if match_mode == "case_insensitive":
            return str(a).strip().lower() == str(b).strip().lower()
        return str(a).strip() == str(b).strip()

    def _is_wild(v):
        if v is None:
            return True
        return str(v).strip() == "" or str(v).strip().lower() == "any"

    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        ok = True
        for kf, kv in requested.items():
            rv = _fb_row_get(r, kf)
            if not (_is_wild(rv) or _eq(rv, kv)):
                ok = False
                break
        if ok:
            out.append(r)
    return out


@register_source(
    "composite_key_lookup",
    label="Composite Key Lookup (N-Dimension Matrix)",
    description=(
        "Look up a value from an N-dimensional pricing/parameter matrix by a dynamic "
        "set of key fields (item_code, color, thickness, surface, ...). Supports "
        "fallback_keys (progressively drop dimensions), match_mode exact / "
        "case_insensitive / multiplier_chain (base value × multipliers for dropped "
        "dimensions), and default_value. matrix_lookup (2D) is a special case."
    ),
    config_schema={
        "type": "object",
        "required": ["doctype", "value_field"],
        "properties": {
            "doctype": {"type": "string", "description": "DocType storing the matrix rows"},
            "value_field": {"type": "string", "description": "Field holding the value to return"},
            "key_fields": {"type": "array", "items": {"type": "string"}, "description": "N key field names (dimensions), e.g. ['item_code','color','thickness','surface']"},
            "key_values": {"type": "array", "items": {"type": "string"}, "description": "N key values aligned with key_fields; supports {{row.field}}, {{doc.field}}, {{resolved.field}} templates. Auto-mapped from {{row.<key_field>}} if blank."},
            "fallback_keys": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "Ordered list of key-field subsets to try when no exact match (progressively drop dimensions), e.g. [['item_code','color'], ['item_code']]."},
            "match_mode": {"type": "string", "enum": ["exact", "case_insensitive", "multiplier_chain"], "description": "Key comparison mode. multiplier_chain applies per-dimension multipliers for dropped dimensions."},
            "multipliers": {"type": "object", "description": "For multiplier_chain: map dim → {doctype, match_field, match_value, value_field} to look up the multiplier for a dropped dimension."},
            "filters": {"type": "array", "description": "Extra Frappe filters scoping the matrix query."},
            "default_value": {"type": ["number", "string"], "description": "Value returned when no matrix row matches (default 0)."},
        },
    },
    batchable=True,
    fingerprint_fn=lambda cfg: "composite_key_lookup:" + "|".join([
        cfg.get("doctype", ""),
        cfg.get("value_field", ""),
        json.dumps(cfg.get("key_fields") or [], sort_keys=True),
        cfg.get("match_mode", "exact"),
        hashlib.md5(
            json.dumps([cfg.get("filters") or [], cfg.get("fallback_keys") or []], sort_keys=True).encode()
        ).hexdigest()[:12],
    ]),
    supports_transform=True,
    supports_cache=True,
    default_cache_ttl=300,
)
def _handle_composite_key_lookup(binding, doc, resolved_so_far):
    cfg = json.loads(binding.get("source_config") or "{}")
    doctype = cfg.get("doctype", "")
    value_field = cfg.get("value_field", "")
    default_value = cfg.get("default_value", binding.get("default_value"))
    data_type = binding.get("data_type") or cfg.get("type", "Float")

    if not doctype or not value_field:
        return default_value

    row = _binding_row(binding, resolved_so_far)
    dims = _resolve_key_values(cfg, doc, resolved_so_far, row)
    if not dims:
        return default_value

    rows = _fetch_composite_rows(cfg)
    if not rows:
        return default_value

    return _resolve_composite_value(
        rows, cfg, dims, doc, resolved_so_far, row, default_value, data_type
    )


def _resolve_composite_key_lookup_batch(bindings, doc, resolved_so_far):
    """Batch: fetch rows ma trận 1 lần/group, resolve từng binding."""
    results = {}
    if not bindings:
        return results
    cfg0 = json.loads(bindings[0].get("source_config") or "{}")
    rows = _fetch_composite_rows(cfg0)
    for b in bindings:
        cfg = json.loads(b.get("source_config") or "{}")
        default_value = cfg.get("default_value", b.get("default_value"))
        data_type = b.get("data_type") or cfg.get("type", "Float")
        value_field = cfg.get("value_field", "")
        if not rows or not value_field:
            results[b["variable_name"]] = default_value
            continue
        row = _binding_row(b, resolved_so_far)
        dims = _resolve_key_values(cfg, doc, resolved_so_far, row)
        if not dims:
            results[b["variable_name"]] = default_value
            continue
        results[b["variable_name"]] = _resolve_composite_value(
            rows, cfg, dims, doc, resolved_so_far, row, default_value, data_type
        )
    return results


_handle_composite_key_lookup.resolve_batch = _resolve_composite_key_lookup_batch


# ───────────────────────────────────────────────────────────────────────────
# aggregate_from_items — sum field theo key_field/key_value (giống sumif)
#   Thay py thuần dict fb_handlers.cost_bucket_aggregate cho AL Cost Bucket.
#   rows_source = snapshot | child_table | doctype_query.
# ───────────────────────────────────────────────────────────────────────────

def _resolve_aggregate_rows(cfg, doc, resolved_so_far):
    """Lấy rows nguồn theo rows_source.

    Returns:
        list rows (mỗi row là dict), hoặc None nếu không lấy được.
    """
    rows_source = cfg.get("rows_source", "snapshot")

    if rows_source == "child_table":
        child_field = cfg.get("child_table_field", "")
        if not doc or not child_field:
            return None
        rows = doc.get(child_field) or []
        if not isinstance(rows, (list, tuple)):
            rows = list(rows)
        return [r for r in rows if r is not None]

    if rows_source == "doctype_query":
        doctype = cfg.get("doctype", "")
        if not doctype:
            return None
        fields = cfg.get("fields") or ["name"]
        filters_raw = cfg.get("filters") or []
        order_by = cfg.get("order_by") or ""
        limit = cfg.get("limit") or 0

        def _resolve_filter_val(v):
            if isinstance(v, str) and v.startswith("{doc.") and v.endswith("}"):
                return doc.get(v[5:-1]) if doc else None
            if isinstance(v, str) and v.startswith("{resolved.") and v.endswith("}"):
                return resolved_so_far.get(v[10:-1]) if isinstance(resolved_so_far, dict) else None
            return v

        filters = []
        for f in filters_raw:
            if isinstance(f, list) and len(f) == 3:
                filters.append([f[0], f[1], _resolve_filter_val(f[2])])
        try:
            return frappe.get_all(
                doctype,
                filters=filters or None,
                fields=fields,
                order_by=order_by or None,
                limit_page_length=limit if limit else 0,
            ) or []
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"DataSource: aggregate_from_items (doctype_query {doctype})",
            )
            return None

    # snapshot (default): load doc snapshot_doctype → đọc field snapshot_field
    # (JSON string) → lấy rows tại rows_path.
    snapshot_doctype = cfg.get("snapshot_doctype", "")
    snapshot_name = cfg.get("snapshot_name") or ""
    snapshot_field = cfg.get("snapshot_field", "snapshot")
    rows_path = cfg.get("rows_path", "items")

    if not snapshot_doctype:
        return None

    # snapshot_name có thể là template {{doc.field}} / {{resolved.field}}
    snap_name = _resolve_template_val(snapshot_name, doc, resolved_so_far) if snapshot_name else None
    if not snap_name:
        # Fallback: lấy từ resolved_so_far / doc field
        snap_name = (resolved_so_far or {}).get(snapshot_doctype) or doc.get(snapshot_doctype) if doc else None
    if not snap_name:
        return None

    try:
        snap_doc = frappe.get_doc(snapshot_doctype, snap_name)
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"DataSource: aggregate_from_items (snapshot get_doc {snapshot_doctype}/{snap_name})",
        )
        return None

    raw = snap_doc.get(snapshot_field) if snap_doc else None
    if raw is None:
        return None
    # snapshot_field có thể là JSON string hoặc dict (từ frappe)
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
    elif isinstance(raw, dict):
        data = raw
    else:
        return None
    rows = data.get(rows_path) if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    return [r for r in rows if isinstance(r, dict)]


def _match_filter_value(row_val, op, target):
    """So sánh row_val với target theo op (Frappe-style filter operator).

    Hỗ trợ =, ==, !=, <>, >, <, >=, <=, like, in, not in.
    """
    if row_val is None:
        return False
    op = (op or "=").strip().lower()
    if op in ("=", "=="):
        return str(row_val).strip() == str(target).strip()
    if op in ("!=", "<>"):
        return str(row_val).strip() != str(target).strip()
    if op == "like":
        return str(target).lower() in str(row_val).lower()
    if op == "in":
        tlist = target if isinstance(target, (list, tuple)) else [target]
        return str(row_val).strip() in {str(t).strip() for t in tlist}
    if op == "not in":
        tlist = target if isinstance(target, (list, tuple)) else [target]
        return str(row_val).strip() not in {str(t).strip() for t in tlist}
    try:
        rv, tv = float(row_val), float(target)
    except (TypeError, ValueError):
        return False
    return {"<": rv < tv, "<=": rv <= tv, ">": rv > tv, ">=": rv >= tv}.get(op, False)


def _apply_aggregate_filters(rows, cfg, doc, resolved_so_far, row):
    """Áp dụng multi-field filters (Frappe-style list) lên rows dict.

    Mỗi filter: ["field", "op", "value"] với op ∈ =, !=, >, <, >=, <=, like, in, not in.
    Value hỗ trợ template {{row.field}}, {{doc.field}}, {{resolved.field}}.
    Dùng cho MỌI rows_source (snapshot, child_table, doctype_query) — thay được
    filter_by cũ của fb_handlers.cost_bucket_aggregate. Kết hợp AND với
    key_field/key_value.
    """
    filters = cfg.get("filters") or []
    if not filters:
        return rows
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        ok = True
        for f in filters:
            if not (isinstance(f, (list, tuple)) and len(f) == 3):
                continue
            field, op, val = f[0], f[1], f[2]
            if isinstance(val, str):
                val = _resolve_template_val(val, doc, resolved_so_far, row)
            if not _match_filter_value(_fb_row_get(r, field), op, val):
                ok = False
                break
        if ok:
            out.append(r)
    return out


@register_source(
    "aggregate_from_items",
    label="Aggregate From Items (sumif-style)",
    description=(
        "Sum/aggregate a field from a set of rows (snapshot JSON, current child table, "
        "or a doctype query) filtered by key_field == key_value — like SUMIF. "
        "Optional multi-field `filters` (Frappe-style list) apply to every rows_source "
        "and combine AND with key_field/key_value. Replaces the pure-Python dict helper "
        "fb_handlers.cost_bucket_aggregate for AL Cost Bucket. When key_value is empty, "
        "aggregates over all rows (AGGREGATE node)."
    ),
    config_schema={
        "type": "object",
        "required": ["rows_source", "aggregate", "value_field"],
        "required_unless": {
            "value_field": {"if": "aggregate", "equals": "count"},
        },
        "properties": {
            "rows_source": {"type": "string", "enum": ["snapshot", "child_table", "doctype_query"], "description": "Where to read the source rows from."},
            "snapshot_doctype": {"type": "string", "description": "DocType holding the snapshot (rows_source=snapshot)."},
            "snapshot_name": {"type": "string", "description": "Name of the snapshot doc; supports {{doc.field}}, {{resolved.field}} templates. Falls back to resolved_so_far[snapshot_doctype] or doc[snapshot_doctype]."},
            "snapshot_field": {"type": "string", "description": "Field on the snapshot doc holding the JSON data (default 'snapshot')."},
            "rows_path": {"type": "string", "description": "JSON path inside snapshot data where the rows list lives (default 'items')."},
            "child_table_field": {"type": "string", "description": "Child-table fieldname on the current doc (rows_source=child_table)."},
            "doctype": {"type": "string", "description": "Target DocType to query (rows_source=doctype_query)."},
            "fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to fetch for doctype_query (default ['name'])."},
            "filters": {"type": "array", "description": "Multi-field Frappe-style filters applied to EVERY rows_source: [['field','=','val'], ...]. Operators: =, !=, >, <, >=, <=, like, in, not in. Values support {{row.field}}, {{doc.field}}, {{resolved.field}} templates. For doctype_query these are also passed to get_all. Combines AND with key_field/key_value."},
            "order_by": {"type": "string", "description": "Order clause for doctype_query."},
            "limit": {"type": "integer", "description": "Max rows for doctype_query (0 = unlimited)."},
            "key_field": {"type": "string", "description": "Field used as the filter key (like SUMIF criteria field), e.g. 'cost_bucket'."},
            "key_value": {"type": "string", "description": "Value to match on key_field; supports {{row.field}}, {{doc.field}}, {{resolved.field}} templates. Empty → aggregate over all rows."},
            "value_field": {"type": "string", "description": "Field to aggregate, e.g. 'line_total'. Required except when aggregate=count. Preferred over sum_field when both present."},
            "sum_field": {"type": "string", "description": "ALIAS của value_field (backward-compat với AL Cost Bucket source_config cũ dùng sum_field). Chỉ đọc khi value_field rỗng. KHÔNG thay đổi schema chuẩn — value_field vẫn required (trừ count)."},
            "aggregate": {"type": "string", "enum": ["sum", "avg", "min", "max", "count", "first", "last"], "description": "Aggregation function."},
            "default_value": {"type": ["number", "string"], "description": "Value returned when no rows match or the rows source fails (default 0)."},
        },
    },
    batchable=True,
    fingerprint_fn=lambda cfg: "aggregate_from_items:" + "|".join([
        cfg.get("rows_source", "snapshot"),
        cfg.get("snapshot_doctype", ""),
        cfg.get("snapshot_field", "snapshot"),
        cfg.get("rows_path", "items"),
        cfg.get("child_table_field", ""),
        cfg.get("doctype", ""),
        json.dumps(cfg.get("filters") or [], sort_keys=True),
        cfg.get("key_field", ""),
        cfg.get("value_field") or cfg.get("sum_field", ""),
        cfg.get("aggregate", "sum"),
    ]),
    supports_transform=True,
    supports_cache=True,
    default_cache_ttl=300,
)
def _handle_aggregate_from_items(binding, doc, resolved_so_far):
    cfg = json.loads(binding.get("source_config") or "{}")
    default_value = cfg.get("default_value", binding.get("default_value"))
    data_type = binding.get("data_type") or cfg.get("type", "Float")
    key_field = cfg.get("key_field", "")
    key_value = cfg.get("key_value", "")
    value_field = cfg.get("value_field") or cfg.get("sum_field", "")
    aggregate = cfg.get("aggregate", "sum")

    rows = _resolve_aggregate_rows(cfg, doc, resolved_so_far)
    if rows is None:
        return default_value

    # Multi-field filters (Frappe-style) — snapshot/child_table lọc in-memory;
    # doctype_query đã lọc ở get_all (filter value dùng {doc.x}/{resolved.x}).
    if cfg.get("rows_source") != "doctype_query":
        row = _binding_row(binding, resolved_so_far)
        rows = _apply_aggregate_filters(rows, cfg, doc, resolved_so_far, row)
    else:
        row = _binding_row(binding, resolved_so_far)

    # Lọc theo key_field == key_value (key_value rỗng → giữ toàn bộ)
    if key_field and key_value not in (None, ""):
        kv = _resolve_template_val(key_value, doc, resolved_so_far, row)
        if kv is not None and kv != "":
            rows = [
                r for r in rows
                if _fb_row_get(r, key_field) is not None
                and str(_fb_row_get(r, key_field)).strip() == str(kv).strip()
            ]

    if not rows:
        return default_value if aggregate != "count" else 0

    if aggregate == "count":
        return len(rows)

    if not value_field:
        return default_value

    values = [_fb_row_get(r, value_field) for r in rows]

    if aggregate in ("first", "last"):
        vals = [v for v in values if v is not None]
        if not vals:
            return default_value
        return _cast(vals[0] if aggregate == "first" else vals[-1], data_type)

    nums = []
    for v in values:
        if v is None:
            continue
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return default_value
    if aggregate == "sum":
        result = sum(nums)
    elif aggregate == "avg":
        result = sum(nums) / len(nums)
    elif aggregate == "min":
        result = min(nums)
    elif aggregate == "max":
        result = max(nums)
    else:
        return default_value
    return _cast(result, data_type)


def _resolve_aggregate_from_items_batch(bindings, doc, resolved_so_far):
    """Batch: gom rows nguồn 1 lần per fingerprint, resolve key_value per-binding."""
    results = {}
    if not bindings:
        return results
    # Group configs chia sẻ rows nguồn → chỉ resolve rows 1 lần.
    # key_value là template per-binding nên không thể gộp theo fingerprint hoàn toàn;
    # ta resolve rows theo cfg đầu group rồi reuse cho các binding cùng rows_source.
    cfg0 = json.loads(bindings[0].get("source_config") or "{}")
    shared_rows = _resolve_aggregate_rows(cfg0, doc, resolved_so_far)

    for b in bindings:
        cfg = json.loads(b.get("source_config") or "{}")
        default_value = cfg.get("default_value", b.get("default_value"))
        data_type = b.get("data_type") or cfg.get("type", "Float")
        key_field = cfg.get("key_field", "")
        key_value = cfg.get("key_value", "")
        value_field = cfg.get("value_field") or cfg.get("sum_field", "")
        aggregate = cfg.get("aggregate", "sum")

        rows = shared_rows
        if rows is None:
            results[b["variable_name"]] = default_value
            continue

        # Multi-field filters (Frappe-style) — snapshot/child_table lọc in-memory;
        # doctype_query đã lọc ở get_all.
        row = _binding_row(b, resolved_so_far)
        if cfg.get("rows_source") != "doctype_query":
            rows = _apply_aggregate_filters(rows, cfg, doc, resolved_so_far, row)

        if key_field and key_value not in (None, ""):
            kv = _resolve_template_val(key_value, doc, resolved_so_far, row)
            if kv is not None and kv != "":
                rows = [
                    r for r in rows
                    if _fb_row_get(r, key_field) is not None
                    and str(_fb_row_get(r, key_field)).strip() == str(kv).strip()
                ]

        if not rows:
            results[b["variable_name"]] = default_value if aggregate != "count" else 0
            continue

        if aggregate == "count":
            results[b["variable_name"]] = len(rows)
            continue

        if not value_field:
            results[b["variable_name"]] = default_value
            continue

        values = [_fb_row_get(r, value_field) for r in rows]
        if aggregate in ("first", "last"):
            vals = [v for v in values if v is not None]
            results[b["variable_name"]] = (
                default_value if not vals else _cast(vals[0] if aggregate == "first" else vals[-1], data_type)
            )
            continue

        nums = []
        for v in values:
            if v is None:
                continue
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
                continue
        if not nums:
            results[b["variable_name"]] = default_value
            continue
        if aggregate == "sum":
            result = sum(nums)
        elif aggregate == "avg":
            result = sum(nums) / len(nums)
        elif aggregate == "min":
            result = min(nums)
        elif aggregate == "max":
            result = max(nums)
        else:
            results[b["variable_name"]] = default_value
            continue
        results[b["variable_name"]] = _cast(result, data_type)

    return results


_handle_aggregate_from_items.resolve_batch = _resolve_aggregate_from_items_batch
