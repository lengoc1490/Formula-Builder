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
import json
import importlib
from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Callable, Dict, List, Optional

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


def get_handler(source_type: str) -> Optional[Callable]:
    """Return the handler for a given source_type, or None."""
    return _data_source_handlers.get(source_type)


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
    if not any(module_path.startswith(prefix) for prefix in whitelist):
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


@register_source("whole_doctype")
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
