# ═══════════════════════════════════════════════════════════════════════════
#  formula_builder/api/formula_table_api.py
#
#  Backend API cho formula_table_dialog_v3.js
#  Tương ứng với _RPC map trong JS:
#    CALC_CELL  → calc_cell
#    CALC_TABLE → calc_table
#    VALIDATE   → validate_formula
#    SCC_CHECK  → scc_check
#
#  Phụ thuộc: formula_utils v29.1.0  (xem __init__.py)
#  Frappe  : @whitelist(), frappe.parse_json(), frappe.log_error()
# ═══════════════════════════════════════════════════════════════════════════

import json
import frappe
from frappe import _

from formula_builder.formula_utils import (
    FormulaEngine,
    FormulaValidator,
    ValidationResult,
    scc_topo_sort,
    scc_topo_sort_with_info,
    FormulaError,
    FormulaBudgetExceeded,
    FormulaComplexityError,
    FormulaRuntimeError,
    FormulaValidationError,
    MODE_NULL,
)
from formula_builder.api.settings_cache import get_allowed_funcs
from formula_builder.api._helpers import parse_json as _parse
from formula_builder.api._logging import timed


# ─────────────────────────────────────────────────────────────────────────────
#  §0  INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _is_formula_error(val) -> bool:
    """Kiểm tra giá trị trả về từ FormulaEngine.calculate() có phải lỗi."""
    return isinstance(val, (Exception, FormulaError))


def _fmt_error(val) -> str:
    """Chuẩn hoá thông báo lỗi thành string ngắn gọn."""
    if val is None:
        return "Lỗi tính toán"
    return str(val)[:200]


def _safe_result(val):
    """
    Chuyển kết quả engine về kiểu JSON-serialisable.
    - float('inf') / float('nan') → None
    - Exception → None  (caller kiểm tra _is_formula_error trước)
    """
    if val is None:
        return None
    if isinstance(val, float):
        import math
        if math.isnan(val) or math.isinf(val):
            return None
    return val


# ── Cache cho _load_formula_set — tránh load DB lặp lại ──────────────────
_fs_cache: dict = {}
_FS_CACHE_MAX = 32


def _invalidate_fs_cache():
    """Xóa cache _load_formula_set + _cell_engine_cache — gọi khi settings thay đổi."""
    _fs_cache.clear()
    _cell_engine_cache.clear()


def _load_formula_set(config_doctype: str | None, config_name: str | None) -> dict:
    """
    Load FormulaSet document nếu được chỉ định. Có cache 32 entries.
    Trả về dict với keys:
        safe_funcs  : dict | None
        allowed_fns : list | None
    Nếu không có config → fallback về Formula Builder Settings global.
    """
    # Cache lookup
    cache_key = f"{config_doctype or '__none__'}:{config_name or '__none__'}"
    if cache_key in _fs_cache:
        return _fs_cache[cache_key]

    from formula_builder.formula_utils import BASE_FUNCS

    def _build_from_rows(fn_rows) -> dict:
        """Chuyển child table rows → safe_funcs dict."""
        result = {}
        for r in fn_rows:
            func_name = getattr(r, "func_name", None) or (r.get("func_name") if isinstance(r, dict) else None)
            is_enabled = getattr(r, "is_enabled", True) or (r.get("is_enabled", True) if isinstance(r, dict) else True)
            alias = getattr(r, "alias", None) or (r.get("alias") if isinstance(r, dict) else None)
            if not func_name or not is_enabled:
                continue
            if func_name in BASE_FUNCS:
                result[func_name] = BASE_FUNCS[func_name]
            if alias and alias.strip() and alias in BASE_FUNCS:
                result[alias.strip()] = BASE_FUNCS[alias.strip()]
            elif alias and alias.strip() and func_name in BASE_FUNCS:
                result[alias.strip()] = BASE_FUNCS[func_name]
        return result

    result = None  # type: dict | None

    # ── Không có config → dùng Formula Builder Settings global ──────────────
    if not (config_doctype and config_name):
        try:
            safe_funcs = get_allowed_funcs()
            result = {"safe_funcs": safe_funcs, "allowed_fns": list(safe_funcs.keys())}
        except Exception:
            result = {"safe_funcs": None, "allowed_fns": None}
    else:
        # ── Có config → load từ DocType chỉ định ────────────────────────────
        try:
            doc = frappe.get_doc(config_doctype, config_name)
            fn_rows = doc.get("allowed_functions") or []

            if not fn_rows:
                try:
                    safe_funcs = get_allowed_funcs()
                    result = {"safe_funcs": safe_funcs, "allowed_fns": list(safe_funcs.keys())}
                except Exception:
                    result = {"safe_funcs": None, "allowed_fns": None}
            else:
                safe_funcs = _build_from_rows(fn_rows)
                if not safe_funcs:
                    result = {"safe_funcs": None, "allowed_fns": None}
                else:
                    result = {"safe_funcs": safe_funcs, "allowed_fns": list(safe_funcs.keys())}

        except frappe.DoesNotExistError:
            frappe.log_error(
                f"_load_formula_set: DocType '{config_doctype}' name '{config_name}' không tồn tại",
                "Formula Table API",
            )
            result = {"safe_funcs": None, "allowed_fns": None}
        except Exception as e:
            frappe.log_error(
                f"_load_formula_set({config_doctype!r}, {config_name!r}): {e}",
                "Formula Table API",
            )
            result = {"safe_funcs": None, "allowed_fns": None}

    # Lưu vào cache (chỉ cache kết quả hợp lệ)
    if result and result.get("safe_funcs"):
        if len(_fs_cache) >= _FS_CACHE_MAX:
            oldest = next(iter(_fs_cache))
            del _fs_cache[oldest]
        _fs_cache[cache_key] = result

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  §1  calc_cell
#  Tính một công thức đơn lẻ với context cho sẵn.
#  JS gọi mỗi khi người dùng thay đổi công thức trong một ô formula.
#
#  Params (JSON string từ Frappe whitelist):
#    formula        : str              – chuỗi công thức
#    context        : dict             – biến context ({qty:2, rate:50000, …})
#    config_doctype : str | null
#    config_name    : str | null
#
#  Returns:
#    { result: any | null, error: str | null }
# ─────────────────────────────────────────────────────────────────────────────

# ── Cache cho calc_cell engine — tránh compile lặp lại ────────────────────
_cell_engine_cache: dict = {}
_CELL_CACHE_MAX = 64


@timed("calc_cell")
@frappe.whitelist()
def calc_cell(formula, context=None, config_doctype=None, config_name=None):
    formula  = (formula or "").strip()
    ctx      = _parse(context) or {}

    if not formula:
        return {"result": None, "error": "Công thức rỗng"}

    cfg = _load_formula_set(config_doctype, config_name)

    # Cache engine theo (formula, frozenset(func_names))
    func_key = frozenset(cfg["safe_funcs"].keys()) if cfg["safe_funcs"] else frozenset()
    engine_key = (formula, func_key)

    if engine_key in _cell_engine_cache:
        engine = _cell_engine_cache[engine_key]
    else:
        if len(_cell_engine_cache) >= _CELL_CACHE_MAX:
            oldest = next(iter(_cell_engine_cache))
            del _cell_engine_cache[oldest]
        engine = FormulaEngine(
            formulas  = [{"name": "_cell", "formula": formula}],
            on_error  = MODE_NULL,
            safe_funcs= cfg["safe_funcs"],
        )
        _cell_engine_cache[engine_key] = engine

    try:
        res = engine.calculate(ctx)
        val = res.get("_cell")

        if _is_formula_error(val):
            return {"result": None, "error": _fmt_error(val)}

        return {"result": _safe_result(val), "error": None}

    except (FormulaValidationError, FormulaComplexityError) as e:
        return {"result": None, "error": f"[Validation] {e}"}
    except FormulaBudgetExceeded as e:
        return {"result": None, "error": f"[Budget] {e}"}
    except FormulaRuntimeError as e:
        return {"result": None, "error": f"[Runtime] {e}"}
    except Exception as e:
        frappe.log_error(f"calc_cell: formula={formula!r} error={e}", "Formula Table API")
        return {"result": None, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
#  §2  calc_table
#  Tính batch toàn bộ bảng — được gọi khi nhấn "⟳ Tính lại" hoặc sau khi
#  sửa nhiều hàng liên tiếp (debounce trên JS).
#
#  Params:
#    rows           : list[dict]   – dữ liệu hiện tại của child table
#    columns        : list[dict]   – mô tả cột, mỗi phần tử có:
#                       fieldname      : str   – tên cột
#                       formula_key    : str   – tên key lưu công thức trong row
#                                                (thường "_formula_<fieldname>")
#                       formula_defaults: str  – công thức mặc định
#    globals        : dict         – biến toàn cục (vat_rate, usd_rate…)
#    topo_order     : list[str]    – thứ tự fieldname để tính (Kahn sort từ JS)
#    config_doctype : str | null
#    config_name    : str | null
#    parent_doc     : dict | null  – frm.doc (để công thức dùng parent.field)
#
#  Returns:
#    {
#      rows: [
#        {
#          fieldname: value,          ← kết quả tính
#          _err_fieldname: "msg"      ← chỉ có nếu lỗi
#        }
#      ],
#      error: str | null              ← lỗi ở cấp bảng (engine init fail…)
#    }
#
#  Chiến lược công thức per-row:
#    Mỗi hàng có thể mang công thức riêng (lưu ở row[formula_key]).
#    Nếu thiếu → dùng formula_defaults của cột.
#    Engine được khởi tạo lại cho mỗi hàng để đảm bảo đúng công thức.
#    Nếu tất cả hàng dùng cùng công thức → engine tái sử dụng (cache nhỏ).
# ─────────────────────────────────────────────────────────────────────────────

@timed("calc_table")
@frappe.whitelist()
def calc_table(rows, columns, globals=None, topo_order=None,
               config_doctype=None, config_name=None, parent_doc=None):

    rows       = _parse(rows)       or []
    columns    = _parse(columns)    or []
    glb        = _parse(globals)    or {}
    order      = _parse(topo_order) or []
    parent     = _parse(parent_doc)

    if not rows:
        return {"rows": [], "error": None}

    if not order:
        # Fallback: dùng thứ tự khai báo columns (không topo-sort)
        order = [c["fieldname"] for c in columns if c.get("fieldname")]

    # Index columns theo fieldname để lookup O(1)
    col_map = {c["fieldname"]: c for c in columns if c.get("fieldname")}

    cfg = _load_formula_set(config_doctype, config_name)

    # ── Xây context chung (globals + parent) ────────────────────────────────
    base_ctx: dict = dict(glb)
    if parent:
        base_ctx["parent"] = parent
        base_ctx["doc"]    = parent

    # ── Engine cache: tránh khởi tạo lại khi cùng formula ───────────────────
    _engine_cache: dict = {}   # frozenset(formula_assignments) → FormulaEngine

    def _get_engine(formula_assignments: list[tuple[str, str]]) -> FormulaEngine:
        """formula_assignments: [(fieldname, formula_str), ...]"""
        key = frozenset((fn, f) for fn, f in formula_assignments if f)
        if key not in _engine_cache:
            formulas = [{"name": fn, "formula": f}
                        for fn, f in formula_assignments if f]
            _engine_cache[key] = FormulaEngine(
                formulas  = formulas,
                on_error  = MODE_NULL,
                safe_funcs= cfg["safe_funcs"],
            )
        return _engine_cache[key]

    results: list[dict] = []

    for row_idx, row in enumerate(rows):
        # ── Context cho hàng này ────────────────────────────────────────────
        ctx = {**base_ctx, **row}
        ctx["items"]  = rows       # tham chiếu cross-row: items[0].qty
        ctx["row"]    = row
        ctx["rowIdx"] = row_idx

        # ── Lấy công thức cho từng fieldname trong topo_order ───────────────
        formula_assignments: list[tuple[str, str]] = []
        for fn in order:
            col = col_map.get(fn)
            if not col:
                continue
            fml_key = col.get("formula_key") or f"_formula_{fn}"
            formula = (row.get(fml_key) or col.get("formula_defaults") or "").strip()
            if formula:
                formula_assignments.append((fn, formula))

        if not formula_assignments:
            results.append({})
            continue

        try:
            engine  = _get_engine(formula_assignments)
            raw_res = engine.calculate(ctx)
        except FormulaBudgetExceeded as e:
            # Toàn bộ hàng fail với lỗi budget
            row_result = {}
            for fn, _ in formula_assignments:
                row_result[f"_err_{fn}"] = f"[Budget] {e}"
            results.append(row_result)
            continue
        except Exception as e:
            frappe.log_error(
                f"calc_table engine error row={row_idx}: {e}",
                "Formula Table API",
            )
            row_result = {}
            for fn, _ in formula_assignments:
                row_result[f"_err_{fn}"] = str(e)
            results.append(row_result)
            continue

        # ── Gom kết quả ─────────────────────────────────────────────────────
        row_result: dict = {}
        for fn, _ in formula_assignments:
            val = raw_res.get(fn)
            if _is_formula_error(val):
                row_result[fn]           = None
                row_result[f"_err_{fn}"] = _fmt_error(val)
            else:
                row_result[fn] = _safe_result(val)

        results.append(row_result)

    return {"rows": results, "error": None}


# ─────────────────────────────────────────────────────────────────────────────
#  §3  validate_formula
#  Validate cú pháp + kiểm tra tên hàm cho phép.
#  JS gọi khi người dùng nhấn "✓ Validate" (per-cell badge §IV).
#
#  Params:
#    formula        : str
#    config_doctype : str | null
#    config_name    : str | null
#
#  Returns:
#    { error: str | null }    — null nghĩa là hợp lệ
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def validate_formula(formula, config_doctype=None, config_name=None):
    formula = (formula or "").strip()

    if not formula:
        return {"error": "Công thức rỗng"}

    cfg = _load_formula_set(config_doctype, config_name)

    try:
        validator = FormulaValidator(
            allowed_functions=cfg["allowed_fns"],
        )
        result: ValidationResult = validator.validate(formula)

        if not result.ok:
            # errors là list[str] — nối lại bằng "; "
            msg = "; ".join(result.errors) if result.errors else "Công thức không hợp lệ"
            return {"error": msg}

        return {"error": None}

    except FormulaValidationError as e:
        return {"error": str(e)}
    except Exception as e:
        frappe.log_error(f"validate_formula: {e}", "Formula Table API")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
#  §4  scc_check
#  Phát hiện chu trình trong đồ thị phụ thuộc (§VIII trong v3 dialog).
#  JS gọi khi _rebuildDag() phát hiện cyclic nodes và muốn lấy chi tiết SCC.
#
#  Params:
#    nodes : list[str]         – danh sách node id (cellKey "ti:ri:fieldname")
#    edges : list[[str, str]]  – cạnh [from, to], nghĩa là "to phụ thuộc from"
#
#  Returns:
#    {
#      sccs  : list[list[str]]   – mỗi SCC là list node tham gia chu trình
#      error : str | null
#    }
#
#  Dùng scc_topo_sort_with_info (trả về SccTopoResult) để lấy thêm
#  thông tin cyclic / linear nodes ngoài danh sách SCC thuần.
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def scc_check(nodes, edges):
    nodes = _parse(nodes) or []
    edges = _parse(edges) or []

    if not nodes:
        return {"sccs": [], "error": None}

    try:
        # scc_topo_sort_with_info nhận:
        #   nodes : list[str]
        #   edges : list[(str, str)]   — (from, to)
        # Trả về SccTopoResult có field .sccs : list[list[str]]
        pairs = [tuple(e) for e in edges if len(e) == 2]
        result = scc_topo_sort_with_info(nodes, pairs)

        # Lọc chỉ giữ SCC có > 1 node (chu trình thực sự)
        # hoặc SCC 1 node tự tham chiếu (self-loop)
        cyclic_sccs = []
        node_set    = set(nodes)
        edge_set    = {(a, b) for a, b in pairs}

        for scc in result.sccs:
            if len(scc) > 1:
                cyclic_sccs.append(scc)
            elif len(scc) == 1:
                n = scc[0]
                if (n, n) in edge_set:          # self-loop
                    cyclic_sccs.append(scc)

        return {"sccs": cyclic_sccs, "error": None}

    except Exception as e:
        frappe.log_error(f"scc_check: {e}", "Formula Table API")
        return {"sccs": [], "error": str(e)}