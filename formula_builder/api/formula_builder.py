from __future__ import annotations
import ast, json, time
from typing import Any, Dict, List
import frappe
import re as _re
from formula_builder.formula_utils import (FormulaEngine, FormulaError,
    FormulaValidationError, BASE_FUNCS, normalize_formula)
from formula_builder.api.variable_resolver import ScopeContext, VariableResolver, SuggestionsBuilder
from formula_builder.api.data_source_registry import (
    resolve_bindings_with_deps,
)
from formula_builder.api.settings_cache import (
    get_allowed_funcs,
    get_max_formula_length,
    get_settings,
    invalidate_cache as _invalidate_settings_cache,
)

# ============================================================================
# CONSTANTS & HELPERS (Bảo mật, Sanitize, Rate Limit, Cache)
# ============================================================================

_SAFE_VALUE_TYPES = (int, float, str, bool, type(None))
_FORBIDDEN_FIELDS = frozenset({
    "owner", "modified_by", "docstatus", "creation", "modified",
    "name", "_liked_by", "_comments", "_assign", "_user_tags"
})

# ── AI System Prompt ────────────────────────────────────────────────────────
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

# Patterns để detect code blocks và dangerous content trong AI response
_AI_CLEANUP_PATTERNS = [
    (_re.compile(r'```[a-zA-Z]*\s*\n'), ''),   # ```python\n → remove
    (_re.compile(r'\n```'),             ''),   # closing ``` → remove
    (_re.compile(r'^```'),              ''),   # standalone ``` → remove
    (_re.compile(r'^`|`$'),             ''),   # wrapping backticks → remove
]

# ── Helpers ────────────────────────────────────────────────────────────────
def _sanitize_frm_doc(raw: dict, doctype: str) -> dict:
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

def _assert_read_perm(doctype: str, docname: str):
    """Kiểm tra quyền đọc document, throw PermissionError nếu không có."""
    if not doctype or not docname or docname.startswith("new-"):
        return
    if not frappe.has_permission(doctype, "read", docname):
        frappe.throw(
            f"Không có quyền truy cập {doctype} {docname}",
            frappe.PermissionError,
        )

def _check_rate_limit(action: str, limit: int = 10, window: int = 60):
    """Kiểm tra rate limit — CHỈ dùng cho ai_suggest (gọi external API).

    evaluate và validate KHÔNG bị rate limit vì:
      - Đã có auth (@frappe.whitelist)
      - Đã có AST sandbox + __builtins__={}
      - Đã có budget guard (max_operations)
      - Là thao tác tương tác của user, read-only, không side effect

    Admin có thể tùy chỉnh limit trong Formula Builder Settings.
    """
    user = frappe.session.user or "Guest"
    key = f"fb_rl:{user}:{action}"
    try:
        new_count = frappe.cache().incr(key, 1)
        if new_count == 1:
            frappe.cache().expire(key, window)

        # Đọc limit từ Settings (fallback về giá trị truyền vào)
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

# ── Settings ── now in api/settings_cache.py (single source of truth) ───────

def _scope(s): return ScopeContext.from_dict(json.loads(s or "{}") if s else {})

def _json(s):
    try: 
        return json.loads(s or "{}") or {}
    except Exception: 
        return {}

def _ok(valid, msg, errors, warnings, markers, normalized=None, circular_detected=False):
    """Trả response validate_formula — bổ sung normalized và circular_detected cho JS."""
    return {
        "valid":             valid,
        "message":           msg,
        "errors":            errors,
        "warnings":          warnings,
        "markers":           markers,
        "normalized":        normalized,        # JS render chip "⇄ Đã chuẩn hóa"
        "circular_detected": circular_detected, # JS render chip "↺ Vòng lặp tròn!"
    }

def _ev(success, result, error, explain, ctx_used, cross_ref, elapsed_ms=None):
    """Trả response evaluate_formula — bổ sung elapsed_ms cho JS render ⏱."""
    return {
        "success":      success,
        "result":       result,
        "error":        error,
        "explain":      explain,
        "context_used": ctx_used,
        "cross_ref":    cross_ref,
        "elapsed_ms":   elapsed_ms,   # JS render: ⏱ ${r.elapsed_ms}ms
    }


# ── Engine Cache ───────────────────────────────────────────────────────────

_ENGINE_CACHE: Dict[str, FormulaEngine] = {}
_ENGINE_CACHE_MAX = 128


def _engine_cache_key(formula: str, allowed_funcs: dict) -> str:
    """Tạo cache key từ formula + fingerprint của allowed functions."""
    import hashlib
    formula_hash = hashlib.sha256(formula.encode("utf-8")).hexdigest()
    func_names = ",".join(sorted(allowed_funcs.keys()))
    func_hash = hashlib.sha256(func_names.encode("utf-8")).hexdigest()
    return f"{formula_hash}:{func_hash}"


def _get_or_create_engine(formula: str, allowed_funcs: dict) -> FormulaEngine:
    """Lấy FormulaEngine từ cache hoặc tạo mới. Giới hạn 128 entries (LRU-style)."""
    key = _engine_cache_key(formula, allowed_funcs)

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


def _invalidate_engine_cache() -> None:
    """Xóa toàn bộ engine cache — gọi khi settings thay đổi."""
    _ENGINE_CACHE.clear()


# ── SECTION 1: Suggestions ─────────────────────────────────────────────────
@frappe.whitelist()
def get_suggestions(current_doctype="", current_docname=None,
                    child_table_field=None, row_index=None, formula_set_code=None):
    ck = f"fb_sugg:{current_doctype}:{current_docname}:{child_table_field}:{row_index}"
    cached = frappe.cache().get_value(ck)
    if cached: 
        return cached
    ctx = ScopeContext(current_doctype=current_doctype or "",
                       current_docname=current_docname,
                       child_table_field=child_table_field,
                       row_index=int(row_index) if row_index is not None else None,
                       formula_set_code=formula_set_code)
    result = SuggestionsBuilder(ctx).build()
    frappe.cache().set_value(ck, result, expires_in_sec=30)
    return result

@frappe.whitelist()
def get_child_rows(doctype, docname, child_field):
    _assert_read_perm(doctype, docname)
    try:
        doc  = frappe.get_doc(doctype, docname)
        rows = doc.get(child_field) or []
        return [{"line_ref":getattr(r,"line_ref",None),"idx":r.idx,
                 "label":getattr(r,"item_code",None) or getattr(r,"item_name",None) or f"Dòng {r.idx}"}
                for r in rows if getattr(r,"line_ref",None)]
    except Exception as e:
        frappe.log_error(str(e),"Formula Builder: get_child_rows")
        return []

@frappe.whitelist()
def get_doctype_fields(doctype):
    if not doctype: 
        return []
    try:
        SKIP = {"Section Break","Column Break","HTML","Button","Fold","Tab Break"}
        return [{"fieldname":f.fieldname,"label":f.label or f.fieldname,"fieldtype":f.fieldtype}
                for f in frappe.get_meta(doctype).fields if f.fieldtype not in SKIP]
    except Exception as e:
        frappe.log_error(str(e),"Formula Builder: get_doctype_fields")
        return []


# ── SECTION 2: Validate ────────────────────────────────────────────────────
@frappe.whitelist()
def validate_formula(formula, scope_context_json=None):
    errors, warnings, markers = [], [], []
    circular_detected = False
    # Permission check
    if scope_context_json:
        try:
            _raw = json.loads(scope_context_json or "{}")
            _assert_read_perm(_raw.get("current_doctype", ""), _raw.get("current_docname", ""))
        except frappe.PermissionError:
            raise
        except Exception:
            pass

    if not formula or not formula.strip():
        return _ok(False, "Công thức trống", ["Không được để trống"], [], [])
    formula = formula.strip()

    if len(formula) > get_max_formula_length():
        errors.append(f"Quá dài: {len(formula)}/{get_max_formula_length()} ký tự")

    allowed, disabled, _ = get_settings()
    known_fns = set(allowed.keys()) | set(BASE_FUNCS.keys())

    try:
        norm_str = normalize_formula(formula, frozenset(known_fns))
        normalized_expr = norm_str if norm_str != formula else None
        tree = ast.parse(norm_str, mode="eval")
    except SyntaxError as e:
        col = e.offset or 1
        errors.append(f"Lỗi cú pháp dòng {e.lineno}, cột {col}: {e.msg}")
        markers.append({"severity":"error","message":f"Cú pháp: {e.msg}",
                        "startLine":e.lineno,"startCol":col,"endLine":e.lineno,"endCol":col+5})
        return _ok(False, errors[0], errors, warnings, markers,
                   normalized=normalized_expr, circular_detected=False)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            col, line = getattr(node,"col_offset",0)+1, getattr(node,"lineno",1)
            if fn in disabled:
                errors.append(f"Hàm '{fn}' đã bị tắt trong Settings")
                markers.append({"severity":"error","message":f"'{fn}' bị tắt",
                                "startLine":line,"startCol":col,"endLine":line,"endCol":col+len(fn)})
            elif fn not in known_fns and fn not in {"True","False","None"}:
                warnings.append(f"Hàm '{fn}' không có trong whitelist")
                markers.append({"severity":"warning","message":f"'{fn}' không có trong whitelist",
                                "startLine":line,"startCol":col,"endLine":line,"endCol":col+len(fn)})

    if scope_context_json:
        try:
            ctx = _scope(scope_context_json)
            full_ctx = VariableResolver().build_full_context(ctx)
            known = set(full_ctx.keys()) | known_fns | {"True","False","None"}
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id not in known:
                    warnings.append(f"Biến '{node.id}' chưa nhận diện trong scope")
        except Exception:
            pass

        try:
            ctx = _scope(scope_context_json)
            full_ctx = VariableResolver().build_full_context(ctx)
            FormulaEngine(
                formulas=[{"name":"__chk__","formula":normalize_formula(formula, frozenset(known_fns))}],
                safe_funcs=allowed,
            )
        except (FormulaError, FormulaValidationError) as e:
            if "circular" in str(e).lower() or "vòng lặp" in str(e).lower():
                circular_detected = True
                errors.append(f"Phát hiện vòng lặp tròn: {e}")
        except Exception:
            pass

    valid = len(errors) == 0
    return _ok(valid,
               "✓ Hợp lệ" if valid else errors[0],
               errors, warnings, markers,
               normalized=normalized_expr,
               circular_detected=circular_detected)


# ── SECTION 3: Evaluate ────────────────────────────────────────────────────
@frappe.whitelist()
def evaluate_formula(
    formula, scope_context_json=None,
    extra_context_json=None,
    use_cross_ref_dag=0,
    frm_doc_json=None,
    override_vars=None,
):
    if not formula or not formula.strip():
        return _ev(False, None, "Công thức trống", {}, {}, {})
    t0 = time.monotonic()
    try:
        ctx = _scope(scope_context_json)
        # Permission check
        _assert_read_perm(ctx.current_doctype, ctx.current_docname)

        extra = _json(extra_context_json)
        resolver = VariableResolver()
        allowed = get_allowed_funcs()

        # Xử lý override_vars (test với biến)
        if override_vars:
            try:
                ov = json.loads(override_vars) if isinstance(override_vars, str) else override_vars
                if isinstance(ov, dict):
                    for k, v in ov.items():
                        if not isinstance(k, str) or k.startswith("__"):
                            continue
                        try:
                            extra[k] = float(v) if "." in str(v) else int(v)
                        except (ValueError, TypeError):
                            extra[k] = str(v)
            except Exception:
                pass

        # Sanitize frm_doc_json
        if frm_doc_json:
            try:
                frm_doc_raw = json.loads(frm_doc_json) if isinstance(frm_doc_json, str) else frm_doc_json
                if isinstance(frm_doc_raw, dict):
                    extra["__frm_doc__"] = _sanitize_frm_doc(frm_doc_raw, ctx.current_doctype)
            except Exception:
                pass

        if int(use_cross_ref_dag or 0) and ctx.child_table_field:
            try:
                engine = resolver.build_cross_ref_engine(ctx, formula)
            except ValueError as e:
                return _ev(False, None, str(e), {}, {}, {})
            inputs = resolver.build_full_context(ctx, extra)
            results = engine.calculate(inputs)
            cross_ref = {k:v for k,v in results.items() if "__" in k and k!="__target__"}
            explain = _explain(engine, "__target__", inputs)
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            return _ev(True, results.get("__target__"), None, explain,
                       inputs, cross_ref, elapsed_ms=elapsed)
        else:
            full_ctx = resolver.build_full_context(ctx, extra)
            engine = _get_or_create_engine(formula, allowed)
            results = engine.calculate(full_ctx)
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            return _ev(True, results.get("__r__"), None,
                       _explain(engine, "__r__", full_ctx),
                       full_ctx, {}, elapsed_ms=elapsed)

    except (FormulaError, FormulaValidationError) as e:
        elapsed = round((time.monotonic() - t0) * 1000, 1)
        return _ev(False, None, str(e), {}, {}, {}, elapsed_ms=elapsed)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Formula Builder: evaluate_formula")
        elapsed = round((time.monotonic() - t0) * 1000, 1)
        return _ev(False, None, f"Lỗi không mong đợi: {e}", {}, {}, {}, elapsed_ms=elapsed)


def _explain(engine, name, inputs):
    """Gọi engine.explain(name, inputs) đúng API — yêu cầu inputs tường minh."""
    try:
        obj = engine.explain(name, inputs)                            # FIX: explain(name, inputs)
        return obj.to_dict() if hasattr(obj, "to_dict") else {}
    except Exception: 
        return {}


@frappe.whitelist()
def evaluate_formula_set(formula_set_code, extra_context_json=None):
    try:
        name = frappe.db.get_value("Formula Set", {"set_code": formula_set_code}, "name")
        if not name:
            return {"success": False, "error": f"Formula Set '{formula_set_code}' không tồn tại"}
        fs  = frappe.get_doc("Formula Set", name)
        fms = [{"name":ln.var_name,"formula":ln.formula}
               for ln in (fs.get("formulas") or []) if ln.formula and ln.var_name]
        ctx     = ScopeContext(current_doctype=fs.linked_doctype or "")
        inputs  = VariableResolver().build_full_context(ctx, _json(extra_context_json))
        engine  = FormulaEngine(formulas=fms, safe_funcs=get_allowed_funcs())  # FIX: safe_funcs
        return {"success":True,"result":engine.calculate(inputs)}      # FIX: calculate(inputs)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Formula Builder: evaluate_formula_set")
        return {"success":False,"error":str(e)}


# ── SECTION 4: Context ─────────────────────────────────────────────────────
@frappe.whitelist()
def get_live_context(scope_context_json):
    """Read Formula Variable Binding records, resolve them, and return
    {variables, crossTables, objects} for the Formula Builder frontend.

    Filters bindings by applies_to_doctype and applies_to_field.
    Resolves in priority order with dependency-aware topological sort.
    """
    try:
        ctx = _scope(scope_context_json)
        _assert_read_perm(ctx.current_doctype, ctx.current_docname)
        doctype = ctx.current_doctype or ""

        # Extract the actual fieldname from context
        try:
            raw = json.loads(scope_context_json or "{}")
            target_field = raw.get("fieldname", raw.get("current_field", ""))
        except Exception:
            target_field = ""

        # ── 1. Fetch active bindings for this doctype/field ──
        filters = {"is_active": 1}
        bindings = []
        try:
            all_bindings = frappe.get_all(
                "Formula Variable Binding",
                filters={"is_active": 1},
                fields=[
                    "name", "variable_name", "variable_label", "source_type",
                    "source_config", "resolve_priority", "applies_to_doctype",
                    "applies_to_field", "is_global", "data_type", "default_value",
                ],
                order_by="resolve_priority asc",
            ) or []
        except Exception:
            all_bindings = []

        for b in all_bindings:
            b_doctype = b.get("applies_to_doctype") or ""
            b_field = b.get("applies_to_field") or ""

            # Global bindings apply everywhere
            if not b_doctype and not b_field:
                bindings.append(b)
                continue
            # Doctype match
            if b_doctype and b_doctype == doctype:
                if not b_field or b_field == target_field or not target_field:
                    bindings.append(b)

        # ── 2. Get current document ──
        doc = None
        if ctx.current_docname and not ctx.current_docname.startswith("new-"):
            try:
                doc = frappe.get_doc(doctype, ctx.current_docname)
            except Exception:
                pass

        # ── 3. Resolve bindings with dependency ordering ──
        resolved = resolve_bindings_with_deps(bindings, doc)

        # ── 4. Build variables list (scalar + simple values) ──
        variables: List[dict] = []
        objects: Dict[str, dict] = {}

        for b in bindings:
            name = b["variable_name"]
            val = resolved.get(name)
            is_global = bool(b.get("is_global"))
            dtype = b.get("data_type") or (
                "Object" if b["source_type"] == "whole_doctype" else "Float"
            )

            if dtype == "Object" and isinstance(val, dict):
                objects[name] = val
                # Also add as variable so sidebar shows it
                variables.append({
                    "name": name,
                    "label": b.get("variable_label") or name,
                    "value": f"[Object: {len(val)} fields]",
                    "type": "Object",
                    "source": "global" if is_global else "local",
                    "source_type": b["source_type"],
                    "is_global": is_global,
                })
            else:
                variables.append({
                    "name": name,
                    "label": b.get("variable_label") or name,
                    "value": val,
                    "type": type(val).__name__ if val is not None else "NoneType",
                    "source": "global" if is_global else "local",
                    "source_type": b["source_type"],
                    "is_global": is_global,
                })

        # ── 5. Also include current doc scalar fields for convenience ──
        SCALAR = {"Int", "Float", "Currency", "Percent", "Data", "Small Text",
                  "Text", "Check", "Date", "Datetime", "Select", "Link"}
        existing_names = {v["name"] for v in variables}
        try:
            if doc:
                meta = frappe.get_meta(doctype)
                for f in meta.fields:
                    if f.fieldtype in SCALAR and f.fieldname not in existing_names:
                        v = doc.get(f.fieldname)
                        if v is not None:
                            variables.append({
                                "name": f.fieldname,
                                "label": f.label or f.fieldname,
                                "value": v,
                                "type": type(v).__name__,
                                "source": "field",
                                "source_type": "doctype_field",
                                "is_global": False,
                            })
                            existing_names.add(f.fieldname)
        except Exception:
            pass

        # ── 6. Build crossTables from child table meta ──
        crossTables = _build_cross_tables(doctype, doc, ctx)

        # ── 7. Include Global Variables (legacy) ──
        try:
            global_vars = frappe.get_all(
                "Formula Global Variable",
                filters={"is_active": 1, "value_source": "CONSTANT"},
                fields=["var_name", "constant_value", "var_type"],
            )
            for gv in global_vars:
                if gv.var_name not in existing_names:
                    try:
                        gval = float(gv.constant_value) if gv.var_type in ("Float", "Int") else str(gv.constant_value)
                    except Exception:
                        gval = gv.constant_value
                    variables.append({
                        "name": gv.var_name,
                        "label": gv.var_name,
                        "value": gval,
                        "type": gv.var_type or "Float",
                        "source": "global",
                        "source_type": "global_variable",
                        "is_global": True,
                    })
        except Exception:
            pass

        # ── 8. JSON string for widget backward compat ──
        json_str = json.dumps(
            {v["name"]: v["value"] for v in variables
             if isinstance(v["value"], (int, float, str, bool, type(None)))},
            ensure_ascii=False, indent=2,
        )

        return {
            "success": True,
            "variables": variables,
            "crossTables": crossTables,
            "objects": objects,
            "json_str": json_str,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Formula Builder: get_live_context")
        return {
            "success": False,
            "error": str(e),
            "variables": [],
            "crossTables": {},
            "objects": {},
            "json_str": "{}",
        }


def _build_cross_tables(doctype: str, doc, ctx) -> Dict[str, dict]:
    """Build crossTables map from child table meta of current doctype.

    Returns: {child_table_fieldname: {fieldname: "Float", ..., _rows: [{...}]}}
    """
    cross_tables: Dict[str, dict] = {}
    if not doctype:
        return cross_tables
    try:
        meta = frappe.get_meta(doctype)
        for f in meta.fields:
            if f.fieldtype == "Table" and f.options:
                child_meta = frappe.get_meta(f.options)
                fields = {}
                for cf in child_meta.fields:
                    if cf.fieldtype not in ("Section Break", "Column Break", "Tab Break",
                                             "Heading", "HTML", "Button", "Table"):
                        fields[cf.fieldname] = cf.fieldtype or "Data"
                cross_tables[f.fieldname] = fields

                # Add actual row data for line_ref resolution
                if doc:
                    rows = doc.get(f.fieldname) or []
                    rows_data = []
                    for r in rows:
                        row_dict = r.as_dict() if hasattr(r, "as_dict") else {}
                        rows_data.append({
                            "line_ref": getattr(r, "line_ref", None) or f"row_{r.idx}",
                            "idx": r.idx,
                            "label": getattr(r, "item_code", None) or getattr(r, "item_name", None) or f"Dong {r.idx}",
                        })
                    fields["_rows"] = rows_data
    except Exception as e:
        frappe.log_error(f"_build_cross_tables: {e}", "Formula Builder")
    return cross_tables
    

@frappe.whitelist()
def get_global_context_preview():
    try:
        resolver = VariableResolver()
        ctx = ScopeContext(current_doctype="")
        rows = frappe.get_all("Formula Global Variable", filters={"is_active":1},
            fields=["var_name","value_source","constant_value","var_type","label","unit","category"])
        
        variables = []
        for r in rows:
            val = resolver._get_global(r.var_name, ctx)
            variables.append({
                "name": r.var_name,
                "label": r.label or r.var_name,
                "value": val,
                "type": type(val).__name__,
                "source": r.value_source,
                "unit": r.unit or "",
                "category": r.category or "Khác",
            })
        return {"success":True,"variables":variables}
    except Exception as e:
        return {"success":False,"error":str(e),"variables":[]}


# ── SECTION 5: Cache ───────────────────────────────────────────────────────
@frappe.whitelist()
def invalidate_suggestions_cache(doc=None, method=None,
                                  current_doctype=None, current_docname=None):
    try:
        if current_doctype and current_docname:
            try:
                frappe.cache().delete_keys(f"fb_sugg:{current_doctype}:{current_docname}:*")
            except Exception:
                pass
        frappe.cache().delete_value("fb_sugg:*")
        _invalidate_settings_cache()
        _invalidate_engine_cache()
        # Đồng bộ: xóa cache filter context trong data_source_registry
        try:
            from formula_builder.api.data_source_registry import _invalidate_filter_context_cache
            _invalidate_filter_context_cache()
        except Exception:
            pass
    except Exception:
        pass
    return {"ok":True}


# ── SECTION 6: Explain ─────────────────────────────────────────────────────
@frappe.whitelist()
def explain_formula(formula, scope_context_json=None):
    """
    Phân tích công thức, trả về steps, vars_used, debug_info (tokens + ast_summary).
    JS render:
      - r.steps       → bảng chuỗi tính toán
      - r.vars_used   → Variable Resolution panel
      - r.debug_info  → AST Summary + Tokens panel
    """
    try:
        ctx = _scope(scope_context_json)
        _assert_read_perm(ctx.current_doctype, ctx.current_docname)
        resolver = VariableResolver()
        allowed = get_allowed_funcs()
        full_ctx = resolver.build_full_context(ctx)

        engine = _get_or_create_engine(formula, allowed)
        results = engine.calculate(full_ctx)

        explain_obj = engine.explain("__r__", full_ctx)
        explain_dict = explain_obj.to_dict() if hasattr(explain_obj, "to_dict") else {}

        steps = explain_dict.get("steps", [])
        for s in steps:
            s.setdefault("is_input", False)

        # Lấy inputs_used, nếu thiếu thì fallback từ full_ctx dựa trên các biến trong formula
        inputs_used = explain_dict.get("inputs_used")
        if not inputs_used:
            import re
            var_pattern = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b')
            formula_vars = set(var_pattern.findall(formula))
            # Loại bỏ tên hàm (đã có trong allowed) và các keyword Python
            keywords = {"IF","IFS","IIF","SWITCH","and_","or_","not_","True","False","None","in"}
            formula_vars = formula_vars - set(allowed.keys()) - keywords
            inputs_used = {k: v for k, v in full_ctx.items()
                           if k in formula_vars and not callable(v) and not k.startswith("_")}
            # Nếu vẫn rỗng, lấy tất cả scalar fields trong full_ctx (trừ các internal)
            if not inputs_used:
                inputs_used = {k: v for k, v in full_ctx.items()
                               if isinstance(v, (int, float, str, bool, type(None)))
                               and not k.startswith("_")}

        # Prepend input steps
        input_steps = [
            {"name": k, "formula": "", "value": v, "deps": {}, "depth": 0,
             "is_root": False, "is_input": True}
            for k, v in sorted(inputs_used.items())
        ]
        all_steps = input_steps + steps

        vars_used = list({
            s["name"] for s in steps
            if not s.get("is_input") and s.get("name") != "__r__"
        })

        debug_info = _build_debug_info(formula, full_ctx, allowed)

        return {
            "steps": all_steps,
            "vars_used": vars_used,
            "circular_risk": False,
            "debug_info": debug_info,
        }

    except (FormulaError, FormulaValidationError) as e:
        return {"steps": [], "vars_used": [], "circular_risk": False,
                "debug_info": {}, "error": str(e)}
    except Exception as e:
        frappe.log_error(f"explain_formula error: {e}", "Formula Builder")
        return {"steps": [], "vars_used": [], "circular_risk": False,
                "debug_info": {}, "error": str(e)}


def _build_debug_info(formula: str, full_ctx: dict, allowed: dict) -> dict:
    """
    Xây dựng debug_info cho JS render:
      - tokens:      list[{type, value}]  → JS render token pills
      - ast_summary: str                  → JS render AST panel
    """
    debug_info = {}

    # Tokenize đơn giản — JS cũng có _naiveLex nhưng server-side tốt hơn cho AST types
    TOKEN_PATTERNS = [
        (r'\$[a-zA-Z_]\w*',             "var"),
        (r'[a-zA-Z_]\w*',               "name"),
        (r'"([^"\\]|\\.)*"',            "string"),
        (r"'([^'\\]|\\.)*'",            "string"),
        (r'\d+\.?\d*',                  "number"),
        (r'[+\-*/%<>=!&|^~]+',          "op"),
        (r'[()[\],]',                   "paren"),
        (r'\s+',                        "ws"),
        (r'.',                          "other"),
    ]
    KEYWORDS = {"IF","IFS","IIF","SWITCH","True","False","None","and_","or_","not_","in"}
    FUNCS    = set(allowed.keys()) | set(BASE_FUNCS.keys())

    tokens = []
    src    = formula
    while src:
        for pattern, ttype in TOKEN_PATTERNS:
            m = _re.match(pattern, src)
            if m:
                val = m.group(0)
                if ttype == "ws":
                    src = src[len(val):]
                    break
                effective_type = ttype
                if ttype == "name":
                    if val in KEYWORDS:
                        effective_type = "keyword"
                    elif val in FUNCS:
                        effective_type = "func"
                tokens.append({"type": effective_type, "value": val})
                src = src[len(val):]
                break
    debug_info["tokens"] = tokens

    # AST summary
    try:
        from formula_builder.formula_utils import normalize_formula as _nf
        norm = _nf(formula, frozenset(FUNCS))
        tree = ast.parse(norm, mode="eval")
        debug_info["ast_summary"] = ast.dump(tree.body, indent=2)
    except Exception as e:
        debug_info["ast_summary"] = f"(Không parse được AST: {e})"

    return debug_info


# ── AI Helpers ───────────────────────────────────────────────────────────────

def _build_ai_system_prompt() -> str:
    """Build system prompt từ Formula Builder Settings (single source of truth).

    get_allowed_funcs() trả về:
      - Có settings: các hàm admin đã enable
      - Không có settings: toàn bộ BASE_FUNCS (~80+ hàm)
    """
    try:
        allowed = get_allowed_funcs()
    except Exception:
        allowed = dict(BASE_FUNCS)
    func_list = ", ".join(sorted(allowed.keys()))
    return _AI_SYSTEM_PROMPT + f"ALLOWED FUNCTIONS: {func_list}"


def _sanitize_ai_response(text: str) -> str:
    """Clean AI response: strip markdown fences, trim, basic safety check.

    NOTE: FormulaEngine.parse() + SecurityValidator là gatekeeper chính.
    Hàm này chỉ làm sạch formatting, không chặn nội dung — engine sẽ reject
    nếu công thức không hợp lệ hoặc chứa code nguy hiểm.
    """
    if not text:
        return ""

    # Strip markdown code fences (```python ... ```)
    for pattern, replacement in _AI_CLEANUP_PATTERNS:
        text = pattern.sub(replacement, text)

    text = text.strip()

    # Truncate at 500 chars
    if len(text) > 500:
        text = text[:500]

    # Chỉ chặn các chuỗi rõ ràng là code injection — còn lại để engine validate
    _hard_block = [
        "__import__", "__class__", "__subclasses__", "__builtins__",
        "__globals__", "__code__", "__dict__", "__bases__", "__mro__",
    ]
    for pattern in _hard_block:
        if pattern in text:
            return ""

    # Cho phép tối đa 5 dòng (công thức IF lồng phức tạp có thể xuống dòng)
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) > 5:
        return ""

    return text


# ── SECTION 7: Smart Suggest ───────────────────────────────────────────────
@frappe.whitelist()
def smart_suggest_formula(doctype="", fieldname="", field_label="",
                           scope_context_json=None):
    """
    Gợi ý công thức thông minh dựa trên fieldname/label và context.
    JS gọi: formula_builder.api.formula_builder.smart_suggest_formula
    Trả về: { suggestions: [{label, formula, desc}] }
    """
    try:
        ctx      = _scope(scope_context_json)
        ctx.current_doctype = ctx.current_doctype or doctype or ""
        resolver = VariableResolver()
        full_ctx = resolver.build_full_context(ctx)

        # Tìm các field phổ biến trong context
        numeric_fields = [k for k, v in full_ctx.items()
                          if isinstance(v, (int, float)) and not k.startswith("_")]

        suggestions = []
        label_lower = (field_label or fieldname or "").lower()

        # ── Gợi ý theo tên field ──
        if any(kw in label_lower for kw in ("amount","tiền","thành tiền","tổng tiền")):
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

        if any(kw in label_lower for kw in ("area","diện tích","s_","sqm")):
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

        if any(kw in label_lower for kw in ("qty","số lượng","sl","quantity")):
            suggestions.append({
                "label": "Làm tròn 2 chữ số",
                "formula": "round(qty, 2)",
                "desc": "Làm tròn số lượng"
            })

        if any(kw in label_lower for kw in ("price","đơn giá","rate","giá")):
            suggestions.append({
                "label": "Làm tròn đơn giá VNĐ",
                "formula": "round(rate, -3)",
                "desc": "Làm tròn đến hàng nghìn đồng"
            })

        # ── Gợi ý chung dựa trên context ──
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
                # Fallback: gợi ý snippet chung
                suggestions = [
                    {"label": "Điều kiện IF",         "formula": "IF(điều_kiện, giá_trị_đúng, giá_trị_sai)", "desc": "Rẽ nhánh theo điều kiện"},
                    {"label": "Chia an toàn",         "formula": "safe_div(tử_số, mẫu_số, 0)",              "desc": "Tránh lỗi chia cho 0"},
                    {"label": "Tham chiếu dòng khác", "formula": "items.line_ref.qty",                       "desc": "Lấy giá trị từ dòng khác"},
                ]

        return {"suggestions": suggestions[:5]}

    except Exception as e:
        frappe.log_error(f"smart_suggest_formula error: {e}", "Formula Builder")
        return {"suggestions": []}


@frappe.whitelist()
def ai_suggest_formula(prompt):
    """Proxy call tới Anthropic API với system prompt bảo mật — key chỉ ở server.

    Prompt được gửi trong system message để ngăn prompt injection.
    Response được sanitize để chỉ trả về công thức thuần.
    """
    _check_rate_limit("ai_suggest")

    # Validate input
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
        system_prompt = _build_ai_system_prompt()

        msg = client.messages.create(
            model=settings.ai_model or "claude-3-5-sonnet-20241022",
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )

        raw_text = msg.content[0].text if msg.content else ""
        sanitized = _sanitize_ai_response(raw_text)

        if sanitized:
            # Validate formula syntax với get_allowed_funcs() (single source of truth)
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
    
# ── SECTION 8: Seed ────────────────────────────────────────────────────────
@frappe.whitelist()
def seed_default_functions():
    META = {
        "IF":        {"cat":"Điều kiện","sig":"IF(đk, đúng, sai)",         "desc":"Điều kiện đơn giản",      "tmpl":"IF($1, $2, $3)"},
        "IFS":       {"cat":"Điều kiện","sig":"IFS(dk1,kq1,...)",           "desc":"Nhiều điều kiện",          "tmpl":"IFS($1,$2,$3,$4)"},
        "IIF":       {"cat":"Điều kiện","sig":"IIF(cond, true, false)",     "desc":"Alias IF",                 "tmpl":"IIF($1,$2,$3)"},
        "SWITCH":    {"cat":"Điều kiện","sig":"SWITCH(val,c1,kq1,...)",     "desc":"Switch-case",              "tmpl":"SWITCH($1,$2,$3)"},
        "and_":      {"cat":"Logic",    "sig":"and_(dk1, dk2, ...)",        "desc":"Tất cả đúng",              "tmpl":"and_($1,$2)"},
        "or_":       {"cat":"Logic",    "sig":"or_(dk1, dk2, ...)",         "desc":"Ít nhất 1 đúng",           "tmpl":"or_($1,$2)"},
        "not_":      {"cat":"Logic",    "sig":"not_(đk)",                   "desc":"Phủ định",                 "tmpl":"not_($1)"},
        "abs":       {"cat":"Toán học", "sig":"abs(x)",                    "desc":"Giá trị tuyệt đối",        "tmpl":"abs($1)"},
        "round":     {"cat":"Toán học", "sig":"round(x, d)",               "desc":"Làm tròn",                 "tmpl":"round($1,$2)"},
        "roundup":   {"cat":"Toán học", "sig":"roundup(x, d)",             "desc":"Làm tròn lên",             "tmpl":"roundup($1,$2)"},
        "rounddown": {"cat":"Toán học", "sig":"rounddown(x, d)",           "desc":"Làm tròn xuống",           "tmpl":"rounddown($1,$2)"},
        "floor":     {"cat":"Toán học", "sig":"floor(x)",                  "desc":"Làm tròn xuống gần nhất",  "tmpl":"floor($1)"},
        "ceil":      {"cat":"Toán học", "sig":"ceil(x)",                   "desc":"Làm tròn lên gần nhất",    "tmpl":"ceil($1)"},
        "power":     {"cat":"Toán học", "sig":"power(x, n)",               "desc":"Lũy thừa",                 "tmpl":"power($1,$2)"},
        "sqrt":      {"cat":"Toán học", "sig":"sqrt(x)",                   "desc":"Căn bậc 2",                "tmpl":"sqrt($1)"},
        "min":       {"cat":"Toán học", "sig":"min(a, b, ...)",            "desc":"Nhỏ nhất",                 "tmpl":"min($1,$2)"},
        "max":       {"cat":"Toán học", "sig":"max(a, b, ...)",            "desc":"Lớn nhất",                 "tmpl":"max($1,$2)"},
        "safe_div":  {"cat":"Toán học", "sig":"safe_div(a, b, def=0)",     "desc":"Chia an toàn",             "tmpl":"safe_div($1,$2,0)"},
        "clamp":     {"cat":"Toán học", "sig":"clamp(x, lo, hi)",          "desc":"Giới hạn [lo,hi]",         "tmpl":"clamp($1,$2,$3)"},
        "between":   {"cat":"Toán học", "sig":"between(x, lo, hi)",        "desc":"lo<=x<=hi",                "tmpl":"between($1,$2,$3)"},
        "sum":       {"cat":"Tổng hợp", "sig":"sum(list)",                 "desc":"Tổng",                     "tmpl":"sum($1)"},
        "count":     {"cat":"Tổng hợp", "sig":"count(list)",               "desc":"Đếm",                      "tmpl":"count($1)"},
        "average":   {"cat":"Tổng hợp", "sig":"average(list)",             "desc":"Trung bình",               "tmpl":"average($1)"},
        "sumif":     {"cat":"Tổng hợp", "sig":"sumif(range,crit,sum)",     "desc":"Tổng có điều kiện",        "tmpl":"sumif($1,'$2',$3)"},
        "sumifs":    {"cat":"Tổng hợp", "sig":"sumifs(sum,r1,c1,...)",     "desc":"Tổng nhiều điều kiện",     "tmpl":"sumifs($1,$2,$3)"},
        "countif":   {"cat":"Tổng hợp", "sig":"countif(range,crit)",       "desc":"Đếm có điều kiện",         "tmpl":"countif($1,'$2')"},
        "averageif": {"cat":"Tổng hợp", "sig":"averageif(range,crit)",     "desc":"Trung bình có điều kiện",  "tmpl":"averageif($1,'$2')"},
        "vlookup":   {"cat":"Tra cứu",  "sig":"vlookup(val,tbl,col,ex)",   "desc":"Tra bảng dọc",             "tmpl":"vlookup($1,$2,$3,True)"},
        "xlookup":   {"cat":"Tra cứu",  "sig":"xlookup(val,look,ret)",     "desc":"Tra bảng linh hoạt",       "tmpl":"xlookup($1,$2,$3)"},
        "index":     {"cat":"Tra cứu",  "sig":"index(arr,row,col)",        "desc":"Lấy theo vị trí",          "tmpl":"index($1,$2,$3)"},
        "match":     {"cat":"Tra cứu",  "sig":"match(val,arr,type)",       "desc":"Tìm vị trí",               "tmpl":"match($1,$2,0)"},
        "choose":    {"cat":"Tra cứu",  "sig":"choose(n,v1,v2,...)",       "desc":"Chọn theo số",             "tmpl":"choose($1,$2,$3)"},
        "coalesce":  {"cat":"Tiện ích", "sig":"coalesce(a,b,...)",         "desc":"Giá trị đầu tiên không null","tmpl":"coalesce($1,$2)"},
        "is_blank":  {"cat":"Tiện ích", "sig":"is_blank(x)",               "desc":"Kiểm tra rỗng",            "tmpl":"is_blank($1)"},
        "not_blank": {"cat":"Tiện ích", "sig":"not_blank(x)",              "desc":"Kiểm tra có giá trị",      "tmpl":"not_blank($1)"},
        "isnumber":  {"cat":"Tiện ích", "sig":"isnumber(x)",               "desc":"Kiểm tra là số",           "tmpl":"isnumber($1)"},
        "to_number": {"cat":"Tiện ích", "sig":"to_number(x,def)",          "desc":"Chuyển thành số",          "tmpl":"to_number($1,0)"},
        "percent_of":{"cat":"Tiện ích", "sig":"percent_of(part,total)",    "desc":"Tính phần trăm",           "tmpl":"percent_of($1,$2)"},
        "concat":    {"cat":"Chuỗi",    "sig":"concat(a,b,...)",           "desc":"Nối chuỗi",                "tmpl":"concat($1,$2)"},
        "upper":     {"cat":"Chuỗi",    "sig":"upper(text)",               "desc":"Viết hoa",                 "tmpl":"upper($1)"},
        "lower":     {"cat":"Chuỗi",    "sig":"lower(text)",               "desc":"Viết thường",              "tmpl":"lower($1)"},
        "trim":      {"cat":"Chuỗi",    "sig":"trim(text)",                "desc":"Xóa khoảng trắng",         "tmpl":"trim($1)"},
        "left":      {"cat":"Chuỗi",    "sig":"left(text,n)",              "desc":"n ký tự bên trái",         "tmpl":"left($1,$2)"},
        "right":     {"cat":"Chuỗi",    "sig":"right(text,n)",             "desc":"n ký tự bên phải",         "tmpl":"right($1,$2)"},
        "mid":       {"cat":"Chuỗi",    "sig":"mid(text,start,len)",       "desc":"Chuỗi con",                "tmpl":"mid($1,$2,$3)"},
        "today":     {"cat":"Ngày",     "sig":"today()",                   "desc":"Ngày hôm nay",             "tmpl":"today()"},
        "now":       {"cat":"Ngày",     "sig":"now()",                     "desc":"Thời điểm hiện tại",       "tmpl":"now()"},
        "date_diff": {"cat":"Ngày",     "sig":"date_diff(d1,d2,unit)",     "desc":"Khoảng cách ngày",         "tmpl":"date_diff($1,$2,'days')"},
        "date_add":  {"cat":"Ngày",     "sig":"date_add(dt,days,mo)",      "desc":"Cộng ngày",                "tmpl":"date_add($1,$2,0)"},
    }
    try:
        s = frappe.get_single("Formula Builder Settings")
        if s.get("allowed_functions"):
            return {"seeded":0,"message":"Đã có cấu hình, bỏ qua seed"}
        n = 0
        for fn in BASE_FUNCS:
            m = META.get(fn, {})
            s.append("allowed_functions",{
                "func_name":fn,"alias":"","category":m.get("cat","Khác"),
                "signature":m.get("sig",f"{fn}(...)"),
                "description":m.get("desc",""),
                "example":"","is_enabled":1,"insert_template":m.get("tmpl",f"{fn}($1)"),
            }); n += 1
        s.save(ignore_permissions=True); frappe.db.commit()
        invalidate_suggestions_cache()
        return {"seeded":n,"message":f"Đã seed {n} hàm từ BASE_FUNCS"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Formula Builder: seed")
        return {"seeded":0,"error":str(e)}

@frappe.whitelist()
def get_all_base_functions():
    return [{"func_name":k} for k in BASE_FUNCS.keys()]