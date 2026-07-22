# ═══════════════════════════════════════════════════════════════════════════
# FILE: formula_builder/api/variable_resolver.py
# Variable Scope Resolver v2 — Formula Builder ERP
# ═══════════════════════════════════════════════════════════════════════════
from __future__ import annotations
import json, re
from typing import Any, Dict, List, Tuple
import frappe
from formula_builder.formula_utils import FormulaEngine, BASE_FUNCS
from formula_builder.api.settings_cache import get_allowed_funcs


# ── ChildTableRows: list-like wrapper cho phép index bằng cả int và slug ────
class ChildTableRows:
    """
    Wrapper cho child table rows, hỗ trợ:
      - items[0]           → row dict tại index (int)
      - items['canh_trai'] → row dict tìm theo slug (str)
      - items.canh_trai    → row dict (attribute access, nhờ DotToSubscriptTransformer)
      - for r in items     → iteration
      - len(items)         → số lượng rows
    """
    def __init__(self, rows, slug_fields=None):
        self._rows = rows
        self._slug_map = {}
        if slug_fields is None:
            # Tự động phát hiện: custom_slug → line_ref → field đuôi _slug → slug
            slug_fields = ["custom_slug", "line_ref"]
            if rows and isinstance(rows[0], dict):
                for k in rows[0]:
                    if k not in slug_fields and (k.endswith("_slug") or k == "slug"):
                        slug_fields.append(k)
        for row in rows:
            for sf in slug_fields:
                val = row.get(sf) if isinstance(row, dict) else None
                if val is not None:
                    self._slug_map[str(val)] = row
                    break  # 1 row chỉ có 1 slug duy nhất, tìm thấy là thoát

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._rows[key]
        if isinstance(key, str):
            # 1. Slug lookup
            row = self._slug_map.get(key)
            if row is not None:
                return row
            # 2. Integer string fallback
            try:
                return self._rows[int(key)]
            except (ValueError, IndexError):
                raise KeyError(f"Row not found by slug or index: {key}")
        raise TypeError(f"ChildTableRows: unsupported key type {type(key).__name__}")

    def __len__(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)

    def __contains__(self, item):
        return item in self._rows

    def __repr__(self):
        return f"<ChildTableRows({len(self._rows)} rows)>"

    def get(self, key, default=None):
        """Dict-like get, hỗ trợ items.get('slug', default)."""
        try:
            return self[key]
        except (KeyError, IndexError, TypeError):
            return default


def _get_allowed_db_query_doctypes() -> set:
    """Lấy danh sách doctype được phép từ Formula Builder Settings."""
    try:
        settings = frappe.get_single("Formula Builder Settings")
        rows = settings.get("db_query_allowed_doctypes") or []
        return {row.doctype_name for row in rows if row.doctype_name}
    except Exception:
        return set()

# ───────────────────────────────────────────────────────────────────────────
# ScopeContext
# ───────────────────────────────────────────────────────────────────────────
class ScopeContext:
    """Đóng gói toàn bộ ngữ cảnh của một phiên edit công thức."""

    def __init__(self, current_doctype="", current_docname=None,
                 child_table_field=None, row_index=None, line_ref=None,
                 local_vars=None, formula_set_code=None):
        self.current_doctype   = current_doctype or ""
        self.current_docname   = current_docname
        self.child_table_field = child_table_field
        self.row_index         = int(row_index) if row_index is not None else None
        self.line_ref          = line_ref
        self.local_vars        = local_vars or {}
        self.formula_set_code  = formula_set_code
        # Internal cache — tránh DB calls lặp lại
        self._doc_cache:    Dict[Tuple, Any] = {}
        self._meta_cache:   Dict[str, Any]   = {}
        self._global_cache: Dict             = {}

    @classmethod
    def from_dict(cls, d: dict) -> "ScopeContext":
        return cls(
            current_doctype   = d.get("current_doctype", ""),
            current_docname   = d.get("current_docname"),
            child_table_field = d.get("child_table_field"),
            row_index         = d.get("row_index"),
            line_ref          = d.get("line_ref"),
            local_vars        = d.get("local_vars", {}),
            formula_set_code  = d.get("formula_set_code"),
        )

    def get_doc(self, doctype, docname):
        # Bỏ qua bản ghi tạm (chưa lưu)
        if docname and docname.startswith("new-"):
            return None
        key = (doctype, docname)
        if key not in self._doc_cache:
            try:    
                self._doc_cache[key] = frappe.get_doc(doctype, docname)
            except Exception:
                self._doc_cache[key] = None
        return self._doc_cache[key]

    def get_meta(self, doctype):
        if doctype not in self._meta_cache:
            try:    
                self._meta_cache[doctype] = frappe.get_meta(doctype)
            except Exception:
                self._meta_cache[doctype] = None
        return self._meta_cache[doctype]

    def child_table_fieldnames(self, doctype) -> List[str]:
        meta = self.get_meta(doctype)
        if not meta: 
            return []
        return [f.fieldname for f in meta.fields
                if f.fieldtype in ("Table", "Table MultiSelect")]


# ───────────────────────────────────────────────────────────────────────────
# VariableResolver
# ───────────────────────────────────────────────────────────────────────────
class VariableResolver:
    """
    Resolver chain:
      1. $name / $snap.field  → Formula Global Variable / Snapshot
      2. Tên thuần            → local_vars → field doctype → Global fallback
      3. X.Y                  → child_table.line_ref.Y hoặc DocType.field
      4. X[n].Y               → child[index].Y hoặc DocType["name"].Y
      5. X.Y.Z                → child_table.line_ref.field
      6. FS-CODE.var          → Formula Set output
    """

    def resolve(self, name: str, ctx: ScopeContext) -> Any:
        name = (name or "").strip()
        if not name: 
            return None

        # 1. Global prefix $
        if name.startswith("$"):
            inner = name[1:]
            return self._get_snapshot(inner[5:], ctx) if inner.startswith("snap.") \
                   else self._get_global(inner, ctx)

        # 2. Path với . hoặc [
        if "." in name or "[" in name:
            return self._resolve_path(name, ctx)

        # 3. Tên thuần
        if name in ctx.local_vars:         
            return ctx.local_vars[name]
        if ctx.current_docname:
            v = self._get_field(ctx.current_doctype, ctx.current_docname, name, ctx)
            if v is not None:              
                return v
        return self._get_global(name, ctx)

    def _resolve_path(self, path: str, ctx: ScopeContext) -> Any:
        # X["key"].Y hoặc X[n].Y
        m = re.match(r'^(\w[\w\s-]*)\[([^\]]+)\]\.(\w+)$', path)
        if m:
            prefix, key_raw, field = m.groups()
            key = key_raw.strip().strip('"\'')
            if ctx.current_docname and prefix in ctx.child_table_fieldnames(ctx.current_doctype):
                try:    
                    return self._get_child_by_index(ctx.current_doctype, ctx.current_docname, prefix, int(key), field, ctx)
                except Exception:
                    return self._get_child_by_lineref(ctx.current_doctype, ctx.current_docname, prefix, key, field, ctx)
            return self._get_field(prefix, key, field, ctx)

        # FS-CODE.var
        if re.match(r'^FS-', path, re.I) and "." in path:
            fs_code, _, var_name = path.partition(".")
            return self._get_formula_set_output(fs_code, var_name, ctx)

        parts = path.split(".")
        if len(parts) == 2:
            prefix, field = parts
            if ctx.current_docname and prefix in ctx.child_table_fieldnames(ctx.current_doctype):
                return self._get_child_current_row(ctx.current_doctype, ctx.current_docname, prefix, ctx.row_index, field, ctx)
            return self._get_field(prefix, ctx.current_docname, field, ctx)

        if len(parts) == 3:
            p0, p1, field = parts
            if ctx.current_docname and p0 in ctx.child_table_fieldnames(ctx.current_doctype):
                return self._get_child_by_lineref(ctx.current_doctype, ctx.current_docname, p0, p1, field, ctx)
            doc = ctx.get_doc(p0, ctx.current_docname)
            if doc:
                rows = doc.get(p1) or []
                if rows: 
                    return getattr(rows[0], field, None)
        return None

    # ── Global ─────────────────────────────────────────────────────────────
    def _get_global(self, name: str, ctx: ScopeContext) -> Any:
        if name in ctx._global_cache: 
            return ctx._global_cache[name]
        try:
            row = frappe.db.get_value("Formula Global Variable",
                {"var_name": name, "is_active": 1},
                ["value_source","constant_value","formula_expr",
                 "db_query_doctype","db_query_field","db_query_filters","var_type"],
                as_dict=True)
        except Exception:
            return None
        if not row: 
            return None

        val = None
        if row.value_source == "CONSTANT":
            val = self._cast(row.constant_value, row.var_type)

        elif row.value_source == "FORMULA":
            try:
                others = {r.var_name: self._cast(r.constant_value, r.var_type)
                          for r in frappe.get_all("Formula Global Variable",
                              filters={"is_active":1,"value_source":"CONSTANT"},
                              fields=["var_name","constant_value","var_type"])
                          if r.var_name != name}
                engine = FormulaEngine(
                    formulas=[{"name":"__g__","formula":row.formula_expr}],
                    safe_funcs=get_allowed_funcs(),
                    max_operations=10000,
                )
                val = engine.calculate(others).get("__g__")
            except Exception as e:
                frappe.log_error(f"Global FORMULA ({name}): {e}", "VariableResolver")

        elif row.value_source == "DB_QUERY":
            try:
                query_doctype = row.db_query_doctype or ""
                allowed_doctypes = _get_allowed_db_query_doctypes()
                if not allowed_doctypes or query_doctype not in allowed_doctypes:
                    frappe.log_error(
                        f"DB_QUERY từ chối doctype '{query_doctype}' (whitelist: {allowed_doctypes})",
                        "VariableResolver Security"
                    )
                else:
                    filters = {}
                    if row.db_query_filters:
                        for k, v in json.loads(row.db_query_filters).items():
                            filters[k] = self._get_global(v[1:], ctx) if isinstance(v, str) and v.startswith("$") else v
                    rows_db = frappe.get_all(query_doctype, filters=filters,
                                             fields=[row.db_query_field], limit=1)
                    if rows_db:
                        val = self._cast(rows_db[0].get(row.db_query_field), row.var_type)
            except Exception as e:
                frappe.log_error(f"Global DB_QUERY ({name}): {e}", "VariableResolver")

        ctx._global_cache[name] = val
        return val

    # ── DocType field ──────────────────────────────────────────────────────
    def _get_field(self, doctype, docname, field, ctx):
        if not doctype or not docname: 
            return None
        try:    
            return frappe.db.get_value(doctype, docname, field)
        except Exception:
            return None

    # ── Child table ────────────────────────────────────────────────────────
    def _get_child_by_lineref(self, doctype, docname, child_field, line_ref, field, ctx):
        """Tìm row theo slug/line_ref. 1 vòng lặp duy nhất, tìm thấy là trả về ngay."""
        doc = ctx.get_doc(doctype, docname)
        if not doc:
            return None
        # Tự động phát hiện slug fields: custom_slug → line_ref → *_slug → slug
        meta = ctx.get_meta(doc.doctype)
        child_meta = None
        if meta:
            for f in meta.fields:
                if f.fieldname == child_field and f.options:
                    child_meta = ctx.get_meta(f.options)
                    break
        SLUG_FIELDS = ["line_ref", "custom_slug"]
        if child_meta:
            for cf in child_meta.fields:
                fn = cf.fieldname
                if fn not in SLUG_FIELDS and (fn.endswith("_slug") or fn == "slug"):
                    SLUG_FIELDS.append(fn)
        for row in (doc.get(child_field) or []):
            for sf in SLUG_FIELDS:
                v = getattr(row, sf, None)
                if v is not None and str(v) == line_ref:
                    return getattr(row, field, None)
        return None

    def _get_child_by_index(self, doctype, docname, child_field, idx, field, ctx):
        doc = ctx.get_doc(doctype, docname)
        if not doc: 
            return None
        rows = doc.get(child_field) or []
        return getattr(rows[idx], field, None) if 0 <= idx < len(rows) else None

    def _get_child_current_row(self, doctype, docname, child_field, row_index, field, ctx):
        if row_index is None: 
            return None
        return self._get_child_by_index(doctype, docname, child_field, row_index, field, ctx)

    # ── Snapshot ───────────────────────────────────────────────────────────
    def _get_snapshot(self, field, ctx):
        snap = frappe.cache().get_value(
            f"formula_snapshot:{ctx.current_doctype}:{ctx.current_docname}") or {}
        return snap.get(field)

    # ── Formula Set output ─────────────────────────────────────────────────
    def _get_formula_set_output(self, fs_code, var_name, ctx):
        try:
            name = frappe.db.get_value("Formula Set", {"set_code": fs_code}, "name")
            if not name:
                return None
            fs = frappe.get_doc("Formula Set", name)
            formulas = [{"name": ln.var_name, "formula": ln.formula}
                        for ln in (fs.get("formulas") or []) if ln.formula and ln.var_name]
            inputs = self.build_full_context(ctx)
            engine = FormulaEngine(formulas=formulas,
                                   safe_funcs=get_allowed_funcs())  # FIX: extra_funcs → safe_funcs
            return engine.calculate(inputs).get(var_name)             # FIX: calculate(inputs)
        except Exception as e:
            frappe.log_error(f"Formula Set ({fs_code}.{var_name}): {e}", "VariableResolver")
            return None

    # ── Full context builder ───────────────────────────────────────────────
    def build_full_context(self, ctx: ScopeContext, extra: Dict = None) -> Dict:
        # Request-level cache
        cache_attr = None
        if not extra and ctx.current_docname and not ctx.current_docname.startswith("new-"):
            cache_attr = f"_vr_ctx_{ctx.current_doctype}_{ctx.current_docname}_{ctx.child_table_field}_{ctx.row_index}"
            cached_ctx = getattr(frappe.local, cache_attr, None)
            if cached_ctx is not None:
                return dict(cached_ctx)
            
        context = {}
        SCALAR = {"Int","Float","Currency","Percent","Data","Small Text",
                "Text","Check","Date","Datetime","Select","Link"}

        # 1. Global CONSTANT
        try:
            for r in frappe.get_all("Formula Global Variable",
                    filters={"is_active":1},
                    fields=["var_name","value_source","constant_value","var_type"]):
                if r.value_source == "CONSTANT":
                    context[r.var_name] = self._cast(r.constant_value, r.var_type)
        except Exception:
            pass

        # ── NEW: support unsaved doc passed via extra["__frm_doc__"] ──────────────
        frm_doc_data = None
        if extra and "__frm_doc__" in extra:
            frm_doc_data = extra.pop("__frm_doc__")  # consume, don't leak to context

        # 2. Fields doctype hiện tại
        # Priority: frm_doc_data (unsaved) > DB
        if frm_doc_data:
            # Unsaved doc passed from JS
            meta = ctx.get_meta(ctx.current_doctype)
            if meta:
                for f in meta.fields:
                    if f.fieldtype in SCALAR:
                        v = frm_doc_data.get(f.fieldname)
                        if v is not None:
                            context[f.fieldname] = v
        elif ctx.current_docname and not ctx.current_docname.startswith("new-"):
            try:
                doc = ctx.get_doc(ctx.current_doctype, ctx.current_docname)
                meta = ctx.get_meta(ctx.current_doctype)
                if doc and meta:
                    for f in meta.fields:
                        if f.fieldtype in SCALAR:
                            v = doc.get(f.fieldname)
                            if v is not None:
                                context[f.fieldname] = v
            except Exception as e:
                frappe.log_error(f"Error building context from doc: {e}", "VariableResolver")

        # 3. Fields dòng child (current row)
        if ctx.child_table_field and ctx.row_index is not None:
            if frm_doc_data:
                # Unsaved: get from frm_doc_data
                rows = frm_doc_data.get(ctx.child_table_field) or []
                if ctx.row_index < len(rows):
                    row = rows[ctx.row_index]
                    if isinstance(row, dict):
                        for k, v in row.items():
                            if v is not None and not k.startswith("_"):
                                context[k] = v
                        # Alias custom_ fields
                        for k, v in list(context.items()):
                            if k.startswith("custom_") and k[7:] not in context:
                                context[k[7:]] = v
            elif ctx.current_docname and not ctx.current_docname.startswith("new-"):
                try:
                    doc = ctx.get_doc(ctx.current_doctype, ctx.current_docname)
                    meta = ctx.get_meta(ctx.current_doctype)
                    if doc and meta:
                        rows = doc.get(ctx.child_table_field) or []
                        if ctx.row_index < len(rows):
                            for k, v in rows[ctx.row_index].as_dict().items():
                                if v is not None and not k.startswith("_"):
                                    context[k] = v
                            for k, v in list(context.items()):
                                if k.startswith("custom_") and k[7:] not in context:
                                    context[k[7:]] = v
                except Exception as e:
                    frappe.log_error(f"Error building child context: {e}", "VariableResolver")

        # ── NEW: inject child table rows as lists for items[N].field access ───────
        # This enables: rf(items[0], 'rate'), items[0].rate, sum(r['qty'] for r in items)
        self._inject_child_table_lists(ctx, context, frm_doc_data)

        context.update(ctx.local_vars)
        if extra:
            context.update(extra)

        if cache_attr is not None:
            setattr(frappe.local, cache_attr, context)
        return context


    def _inject_child_table_lists(
        self,
        ctx: ScopeContext,
        context: Dict,
        frm_doc_data: Dict = None,
    ) -> None:
        """
        Inject toàn bộ child table rows vào context dưới dạng list of dict.
        Ví dụ: context['items'] = [{'rate': 100, 'qty': 2, ...}, ...]

        Cho phép dùng trong formula:
            rf(items[0], 'rate')         → rate của dòng đầu tiên
            items[0].get('rate', 0)      → an toàn hơn
            sum(r.get('qty',0) for r in items)  → tổng qty
        """
        meta = ctx.get_meta(ctx.current_doctype)
        if not meta:
            return

        SCALAR_TYPES = {
            "Int", "Float", "Currency", "Percent", "Data",
            "Small Text", "Text", "Check", "Date", "Datetime",
            "Select", "Link", "Dynamic Link", "Read Only",
        }

        for f in meta.fields:
            if f.fieldtype not in ("Table", "Table MultiSelect"):
                continue
            table_field = f.fieldname

            rows_data = []

            if frm_doc_data:
                # Unsaved doc: rows already as list of dicts from JS
                raw_rows = frm_doc_data.get(table_field) or []
                for row in raw_rows:
                    if not isinstance(row, dict):
                        continue
                    clean = {k: v for k, v in row.items() if not k.startswith("__")}
                    # Numeric coercion for known types
                    rows_data.append(clean)
            elif ctx.current_docname and not ctx.current_docname.startswith("new-"):
                try:
                    doc = ctx.get_doc(ctx.current_doctype, ctx.current_docname)
                    if not doc:
                        continue
                    child_meta = ctx.get_meta(f.options) if f.options else None
                    scalar_fields = (
                        {cf.fieldname for cf in child_meta.fields if cf.fieldtype in SCALAR_TYPES}
                        if child_meta else set()
                    )
                    for row in (doc.get(table_field) or []):
                        row_dict = {}
                        if scalar_fields:
                            for fn in scalar_fields:
                                v = getattr(row, fn, None)
                                if v is not None:
                                    row_dict[fn] = v
                        else:
                            # Fallback: as_dict()
                            row_dict = {
                                k: v for k, v in row.as_dict().items()
                                if not k.startswith("_") and v is not None
                            }
                        rows_data.append(row_dict)
                except Exception as e:
                    frappe.log_error(
                        f"_inject_child_table_lists [{table_field}]: {e}",
                        "VariableResolver"
                    )

            # Inject vào context dưới dạng ChildTableRows (hỗ trợ cả index và slug)
            context[table_field] = ChildTableRows(rows_data)


    # ── Cross-ref DAG engine ───────────────────────────────────────────────
    def build_cross_ref_engine(self, ctx: ScopeContext, target_formula: str,
                                formula_fields: List[str] = None) -> FormulaEngine:
        """
        Thu thập tất cả công thức từ các dòng có line_ref trong child table,
        normalize cú pháp, tạo FormulaEngine DAG duy nhất.

        Normalize: items.canh_trai.qty → canh_trai__qty
        """
        formula_fields = formula_fields or self._get_formula_fields_from_settings()
        formulas = []
        inputs   = self.build_full_context(ctx)

        if ctx.current_docname and ctx.child_table_field:
            try:
                doc  = ctx.get_doc(ctx.current_doctype, ctx.current_docname)
                rows = (doc.get(ctx.child_table_field) or []) if doc else []
                for row in rows:
                    lr = getattr(row, "line_ref", None)
                    slug = getattr(row, "custom_slug", None)
                    if not lr and not slug:
                        continue
                    # Đưa fields của dòng vào inputs với prefix lr__ và slug__
                    for k, v in row.as_dict().items():
                        if v is not None and not k.startswith("_"):
                            if lr:
                                inputs[f"{lr}__{k}"] = v
                            if slug and str(slug) != str(lr):
                                inputs[f"{str(slug)}__{k}"] = v
                    # Thu thập công thức dòng
                    for ff in formula_fields:
                        expr = getattr(row, ff, None)
                        if expr and str(expr).strip():
                            norm = self._normalize(str(expr), ctx.child_table_field, rows)
                            formulas.append({
                                "name":    f"{lr or slug}__{ff.replace('_formula','')}",
                                "formula": norm,
                            })
            except Exception as e:
                frappe.log_error(f"build_cross_ref_engine: {e}", "VariableResolver")

        norm_target = self._normalize(target_formula, ctx.child_table_field or "", [])
        formulas.append({"name": "__target__", "formula": norm_target})

        try:
            return FormulaEngine(formulas=formulas,
                                 safe_funcs=get_allowed_funcs())  # FIX: extra_funcs → safe_funcs
        except Exception as e:
            raise ValueError(f"DAG engine error (circular dependency?): {e}") from e

    # Thêm hàm helper:
    def _get_formula_fields_from_settings(self) -> list:
        try:
            settings = frappe.get_single("Formula Builder Settings")
            rows = settings.get("formula_column_names") or []  # child table mới cần tạo
            if rows:
                return [r.fieldname for r in rows if r.fieldname]
        except Exception:
            pass
        # Fallback an toàn (giữ behavior cũ)
        return [
            "custom_qty_formula", "custom_price_formula", "custom_amount_formula",
            "qty_formula", "price_formula", "amount_formula",
        ]


    def _normalize(self, expr: str, child_field: str, rows: list) -> str:
        """items.lr.qty → lr__qty | items[n].qty → rowN_lr__qty"""
        if not child_field or not expr: 
            return expr
        expr = re.compile(rf'\b{re.escape(child_field)}\.(\w+)\.(\w+)\b').sub(r'\1__\2', expr)
        def _idx(m):
            idx   = int(m.group(1))
            field = m.group(2)
            if rows and idx < len(rows):
                lr = getattr(rows[idx], "line_ref", None)
                if lr: 
                    return f"{lr}__{field}"
            return m.group(0)
        return re.compile(rf'\b{re.escape(child_field)}\[(\d+)\]\.(\w+)\b').sub(_idx, expr)

    # ── Static helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _cast(val, dtype="Float"):
        if val is None: 
            return None
        try:
            dtype = dtype or "Float"
            if dtype in ("Float","Currency","Percent"): 
                return float(val)
            if dtype == "Int":   
                return int(float(val))
            if dtype in ("Check","Bool"): 
                return bool(int(val)) if str(val).isdigit() else bool(val)
            return str(val)
        except Exception:
            return val


# ───────────────────────────────────────────────────────────────────────────
# SuggestionsBuilder
# ───────────────────────────────────────────────────────────────────────────
class SuggestionsBuilder:
    SCALAR = {"Int","Float","Currency","Percent","Data","Small Text",
              "Check","Date","Select","Link"}

    def __init__(self, ctx: ScopeContext):
        self.ctx      = ctx
        self.resolver = VariableResolver()

    def build(self) -> Dict:
        return {
            "global_vars":     self._global_vars(),
            "local_fields":    self._local_fields(),
            "child_rows":      self._child_rows(),
            "linked_doctypes": self._linked_doctypes(),
            "formula_sets":    self._formula_sets(),
            "functions":       self._functions(),
            "snippets":        self._snippets(),
        }

    def _global_vars(self):
        try:
            rows = frappe.get_all("Formula Global Variable", filters={"is_active":1},
                fields=["var_name","label","var_type","unit","category",
                        "value_source","constant_value","description"],
                order_by="category,var_name")
        except Exception:
            return []
        return [{
            "name":     r.var_name, "label":    r.label or r.var_name,
            "type":     r.var_type or "Float",  "unit":     r.unit or "",
            "category": r.category or "Khác",   "doc":      r.description or "",
            "live_val": r.constant_value if r.value_source=="CONSTANT" else None,
            "insert":   r.var_name,
        } for r in rows]

    def _local_fields(self):
        result = []
        meta = self.ctx.get_meta(self.ctx.current_doctype)
        if not meta:
            return result

        scalar_fields = [f for f in meta.fields if f.fieldtype in self.SCALAR]

        # Batch get all field values in 1 query
        live_values = {}
        if self.ctx.current_docname and not self.ctx.current_docname.startswith("new-"):
            field_names = [f.fieldname for f in scalar_fields]
            if field_names:
                try:
                    row = frappe.db.get_value(
                        self.ctx.current_doctype,
                        self.ctx.current_docname,
                        field_names,
                        as_dict=True,
                    )
                    if row:
                        live_values = dict(row)
                except Exception:
                    pass

        for f in scalar_fields:
            result.append({
                "name": f.fieldname,
                "label": f.label or f.fieldname,
                "fieldtype": f.fieldtype,
                "live_val": live_values.get(f.fieldname),
                "insert": f.fieldname,
                "from_child": False,
            })

        # Fields child đang edit (giữ nguyên logic cũ)
        if self.ctx.child_table_field and self.ctx.current_docname:
            child_dt = next((f.options for f in meta.fields
                             if f.fieldname==self.ctx.child_table_field and f.options), None)
            if child_dt:
                cm = self.ctx.get_meta(child_dt)
                existing = {r["name"] for r in result}
                if cm:
                    for f in cm.fields:
                        if f.fieldtype in self.SCALAR and f.fieldname not in existing:
                            result.append({
                                "name": f.fieldname,
                                "label": f.label or f.fieldname,
                                "fieldtype": f.fieldtype,
                                "live_val": None,
                                "insert": f.fieldname,
                                "from_child": True,
                            })
        return result

    def _child_rows(self):
        result = {}
        if not self.ctx.current_docname: 
            return result
        meta = self.ctx.get_meta(self.ctx.current_doctype)
        if not meta: 
            return result
        try:
            doc = self.ctx.get_doc(self.ctx.current_doctype, self.ctx.current_docname)
            if not doc: 
                return result
            for f in meta.fields:
                if f.fieldtype != "Table": 
                    continue
                rows = doc.get(f.fieldname) or []
                lst  = [{"line_ref":r.line_ref,"idx":r.idx,
                         "label":getattr(r,"item_code",None) or getattr(r,"item_name",None) or r.line_ref,
                         "prefix":f"{f.fieldname}.{r.line_ref}."}
                        for r in rows if getattr(r,"line_ref",None)]
                if lst: 
                    result[f.fieldname] = lst
        except Exception as e:
            frappe.log_error(f"SuggestionsBuilder._child_rows: {e}", "VariableResolver")
        return result

    def _linked_doctypes(self):
        meta = self.ctx.get_meta(self.ctx.current_doctype)
        if not meta: 
            return []
        return [{"fieldname":f.fieldname,"linked_dt":f.options,
                 "label":f.label or f.fieldname,"prefix":f"{f.options}."}
                for f in meta.fields if f.fieldtype=="Link" and f.options]

    def _formula_sets(self):
        try:
            filters = {"is_active":1}
            if self.ctx.current_doctype:
                filters["linked_doctype"] = self.ctx.current_doctype
            sets = frappe.get_all("Formula Set", filters=filters, fields=["set_code","label"])
            result = []
            for fs in sets:
                lines = frappe.get_all("Formula Set Line", filters={"parent":fs.set_code},
                                       fields=["var_name","description"])
                result.append({"set_code":fs.set_code,"label":fs.label,
                               "vars":[{"name":ln.var_name,"doc":ln.description or "",
                                        "insert":f"{fs.set_code}.{ln.var_name}"} for ln in lines]})
            return result
        except Exception: 
            return []

    def _functions(self):
        try:
            rows = frappe.get_single("Formula Builder Settings").get("allowed_functions") or []
            return [{"name":r.func_name,"alias":r.alias or "","category":r.category or "Khác",
                     "detail":r.signature or f"{r.func_name}(...)","documentation":r.description or "",
                     "example":r.example or "","insert_template":r.insert_template or f"{r.func_name}($1)",
                     "is_enabled":bool(r.is_enabled)} for r in rows]
        except Exception: 
            return []

    def _snippets(self):
        return [
            {"name":"Diện tích cửa",        "insert":"(custom_width_mm/1000)*(custom_height_mm/1000)"},
            {"name":"Thành tiền có VAT",     "insert":"qty * rate * (1 + VAT_RATE)"},
            {"name":"Chia an toàn",          "insert":"safe_div($1, $2, 0)"},
            {"name":"Phân loại dày/mỏng",    "insert":"IF(do_day > 60, 'dày', 'mỏng')"},
            {"name":"Làm tròn VNĐ",          "insert":"round($1, -3)"},
            {"name":"Tham chiếu dòng khác",  "insert":"items.line_ref.qty"},
            {"name":"Biến global",           "insert":"$VAT_RATE"},
            {"name":"Tổng các dòng",         "insert":"items.canh_trai.qty + items.canh_phai.qty"},
            {"name":"Sumif theo loại",       "insert":"sumif($1, '$2', $3)"},
            {"name":"IFS nhiều điều kiện",   "insert":"IFS(do_day>70,'dày',do_day>50,'vừa',True,'mỏng')"},
        ]