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
