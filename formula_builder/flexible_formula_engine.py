"""
flexible_formula_engine.py  —  v2.0
=====================================
Cầu nối giữa FlexibleFormulaEngine ↔ AlumGlass ERP Formula Builder ecosystem.

Kiến trúc tổng thể AlumGlass ERP:
─────────────────────────────────────────────────────────────────────────────
                        ┌─────────────────────────────────┐
  Frappe Form/Grid      │  formula_builder.js  (Monaco)   │
  (Child Tables)   ───► │  formula_builder_field.js       │  UI Layer
                        │  • Gợi ý biến / hàm             │
                        │  • Validate, Preview realtime   │
                        └──────────────┬──────────────────┘
                                       │ API calls
                        ┌──────────────▼──────────────────┐
                        │  formula_builder.py  (Frappe)   │
                        │  • validate_formula()            │  API Layer
                        │  • evaluate_formula()            │
                        │  • get_suggestions()             │
                        │  • get_live_context()            │
                        └──────────────┬──────────────────┘
                                       │
               ┌───────────────────────┼───────────────────────┐
               │                       │                       │
  ┌────────────▼──────────┐  ┌─────────▼─────────┐  ┌────────▼──────────────┐
  │  variable_resolver.py │  │  formula_utils/   │  │  flexible_formula_    │
  │  • ScopeContext       │  │  __init__.py      │  │  engine.py  (file này) │
  │  • VariableResolver   │  │  • FormulaEngine  │  │  • ChildTableConfig   │
  │  • SuggestionsBuilder │  │  • BASE_FUNCS     │  │  • EngineConfig       │
  │  • build_full_context │  │  • IncrementalCtx │  │  • FlexibleFormulaEng │
  │  • build_cross_ref_   │  │  • FormulaValidat │  │    ine                │
  │    engine()           │  │  • 80+ funcs      │  │  • ERPNextAdapter     │  ◄─ NEW
  └───────────────────────┘  └───────────────────┘  └───────────────────────┘
               │ context                │ engine                │ multi-table
               └───────────────────────┴───────────────────────┘
                                       │
                        ┌──────────────▼──────────────────┐
                        │     Frappe DocType              │
                        │  + Child Tables (items, taxes…) │
                        └─────────────────────────────────┘

Vai trò của FlexibleFormulaEngine trong hệ thống:
  1. Nhận dữ liệu từ nhiều child table cùng lúc (items, taxes, labor_costs…)
  2. Người dùng chỉ nhập công thức đơn giản ("qty * rate") trong Formula Builder UI
  3. FlexibleFormulaEngine tiền xử lý: inject giá trị cột (rate → 0.8)
  4. Gộp tất cả thành 1 FormulaEngine DAG duy nhất → tính 1 lần
  5. ERPNextAdapter tích hợp trực tiếp với Frappe Doc / VariableResolver

FILE NÀY DÙNG ĐỘC LẬP — không phụ thuộc frappe.
Để dùng trong Frappe, xem ERPNextAdapter ở cuối file.
"""

from __future__ import annotations

import re
import warnings
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from formula_builder.formula_utils import (
    FormulaEngine,
    FormulaValidator,
    IncrementalContext,
    FormulaError,
    InputField,
    OutputField,
    BASE_FUNCS,
    html_unescape_formula,
    html_escape_formula,
)
# Dò định danh phải dùng CHUNG một hàm với `DependencyGraph.build_from_exprs()`,
# ⛔ không tự cài lại regex ở đây: hai bản song song sẽ trôi lệch nhau ⇒ thứ tự
# tính theo một bộ cạnh, còn việc phát hiện "cần tính lại" theo bộ khác.
from formula_builder.formula_utils.topo import extract_identifiers


# ─────────────────────────────────────────────────────────────────────────────
# §1  Dataclass: ChildTableConfig
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ChildTableConfig:
    """
    Cấu hình một child table — không hardcode bất kỳ tên trường nào.

    Attributes
    ----------
    table_key : str
        Key của list trong context/inputs dict.
        Ví dụ: ``"items"``, ``"taxes"``, ``"labor_costs"``.

    formula_field : str
        Tên trường chứa công thức do user nhập trong Formula Builder.
        Ví dụ: ``"formula"``, ``"custom_formula"``, ``"custom_price_formula"``.

    id_field : str
        Trường định danh dòng — trở thành tên biến output trong FormulaEngine.
        Thường là ``"line_ref"`` hoặc ``"kyhieu"`` trong AlumGlass ERP.

        Ví dụ nếu id_field="line_ref" và row có line_ref="K1"
        → FormulaEngine sẽ có biến tên "K1" (hoặc "{prefix}K1" nếu có prefix).

    row_fields : List[str]
        Các trường sẽ được inject giá trị vào công thức trước khi gửi vào engine.

        Đây là tính năng cốt lõi "Excel-like": user nhập ``qty * rate``,
        hệ thống tự thay ``rate`` → ``0.8`` dựa trên cột rate của dòng đó.

        Nếu để rỗng ``[]`` → auto-detect toàn bộ trường có giá trị số/bool.

        QUAN TRỌNG: Chỉ inject các trường THUỘC DÒN HIỆN TẠI (per-row).
        Không inject các tên trường là kết quả của dòng khác (line_ref).
        Ví dụ: ["qty", "price", "rate", "discount_pct"] ✓
                ["K1", "K2", "K3"] ✗ — những cái này là biến engine, không inject.

    output_field : Optional[str]
        Tên trường để ghi kết quả trở lại row (mutate in-place).
        Để ``None`` nếu chỉ cần kết quả trong CalculationResult.values.
        Ví dụ: ``"amount"``, ``"tax_amount"``, ``"calculated_value"``.

    prefix : str
        Tiền tố cho biến engine. Dùng khi hai table có id trùng nhau.
        Ví dụ: prefix="TAX_" → biến K1 của bảng taxes thành "TAX_K1".
        Mặc định rỗng "".

    skip_empty_formula : bool
        Bỏ qua dòng không có công thức (True, mặc định).
        False → raise ValueError.

    assertions : List[dict]
        Assertion riêng cho table này — thêm vào global assertions.
        Format: [{"name": "positive", "expr": "K1 > 0",
                  "message": "K1 phải dương", "severity": "ERROR"}].
    """
    table_key          : str
    formula_field      : str
    id_field           : str
    row_fields         : List[str]       = field(default_factory=list)
    output_field       : Optional[str]   = None
    prefix             : str             = ""
    skip_empty_formula : bool            = True
    assertions         : List[dict]      = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# §2  Dataclass: EngineConfig
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EngineConfig:
    """
    Cấu hình toàn cục cho FlexibleFormulaEngine.

    Attributes
    ----------
    child_tables : List[ChildTableConfig]
        Danh sách cấu hình các child table cần tính.

    global_formulas : List[dict]
        Công thức cấp header: subtotal, total_tax, grand_total…

        Lưu ý về cú pháp — 2 cách tham chiếu đến kết quả child table:

        ✅ Cách 1 — Tham chiếu theo id (KHUYẾN NGHỊ):
            ``{"name": "subtotal", "formula": "K1 + K2 + K3"}``
            Tham chiếu trực tiếp tên biến engine (id_field của dòng).
            Engine tự sắp xếp DAG đúng thứ tự.

        ✅ Cách 2 — Dùng list trong context (khi cần sum động):
            ``{"name": "subtotal", "formula": "sum(r['amount'] for r in items)"}``
            Chỉ dùng được khi output_field đã có giá trị trong list trước khi
            gọi calculate(), hoặc khi dùng sau khi đã write-back.
            Thông thường dùng ``sum_by_line_refs`` helper thay thế.

    extra_context : Dict[str, Any]
        Biến mặc định luôn có trong context (inputs ghi đè nếu trùng).
        Ví dụ: ``{"VAT_RATE": 0.1, "USD_RATE": 25000}``.

    on_error : str
        ``"raise"`` | ``"null"`` | ``"default"`` (mặc định ``"default"``).

    default_value : Any
        Giá trị trả về khi lỗi và on_error="default". Mặc định 0.

    deterministic : bool
        Chặn now()/today()/random() (mặc định True).

    max_operations : Optional[int]
        Giới hạn số phép tính. None = không giới hạn.

    rounding_policy : Dict[str, dict]
        Làm tròn theo tên biến.
        Ví dụ: ``{"K1": {"decimals": 0}, "subtotal": {"decimals": 0}}``.

    assertions : List[dict]
        Assertion toàn cục (thêm vào assertions của từng table).

    custom_functions : Dict[str, Callable]
        Hàm tùy chỉnh inject vào engine.
        Ví dụ: ``{"to_vnd": lambda x: round(x / 1000) * 1000}``.

    input_fields : List[InputField]
        Schema đầu vào (tùy chọn).

    output_fields : List[OutputField]
        Schema đầu ra (tùy chọn, metadata).

    strict : bool
        Nếu True, biến ngoài input_fields sẽ gây lỗi.
    """
    child_tables     : List[ChildTableConfig] = field(default_factory=list)
    global_formulas  : List[dict]             = field(default_factory=list)
    extra_context    : Dict[str, Any]         = field(default_factory=dict)
    on_error         : str                    = "default"
    default_value    : Any                    = 0
    deterministic    : bool                   = True
    max_operations   : Optional[int]          = None
    rounding_policy  : Dict[str, dict]        = field(default_factory=dict)
    assertions       : List[dict]             = field(default_factory=list)
    custom_functions : Dict[str, Callable]    = field(default_factory=dict)
    input_fields     : List[InputField]       = field(default_factory=list)
    output_fields    : List[OutputField]      = field(default_factory=list)
    strict           : bool                   = False


    def __post_init__(self):
        # Validate on_error
        _valid_on_error = {"raise", "null", "default"}
        if self.on_error not in _valid_on_error:
            raise ValueError(
                f"[EngineConfig] on_error='{self.on_error}' không hợp lệ. "
                f"Chọn một trong: {_valid_on_error}"
            )

        # Validate global_formulas format
        for i, gf in enumerate(self.global_formulas):
            if not isinstance(gf, dict) or "name" not in gf or "formula" not in gf:
                raise ValueError(
                    f"[EngineConfig] global_formulas[{i}] thiếu key 'name' hoặc 'formula'. "
                    f"Nhận được: {gf}"
                )

        # Check trùng tên biến giữa các tables: biến engine là f"{prefix}{row_id}",
        # nên chỉ TRÙNG THẬT khi trùng CẢ (prefix, id_field).
        # VÌ SAO sửa: trước đây chỉ so `prefix` mà quên `id_field`. Mà prefix mặc
        # định là "" nên MỌI config có ≥2 bảng không đặt prefix đều bị kêu — trong
        # khi câu cảnh báo lại ghi "Đảm bảo id_field của các dòng không trùng nhau"
        # (điều mà mã chưa hề kiểm). Cảnh báo báo oan thì người ta học cách bỏ qua.
        _seen_pairs: Dict[Tuple[str, str], int] = {}
        for tbl in self.child_tables:
            _key = (tbl.prefix, tbl.id_field)
            _seen_pairs[_key] = _seen_pairs.get(_key, 0) + 1
        _dup_pairs = sorted(k for k, n in _seen_pairs.items() if n > 1)
        if _dup_pairs:
            # Cho phép trùng nếu giá trị id của các dòng khác nhau — warn thay vì raise
            warnings.warn(
                "[EngineConfig] Có 2 child tables dùng cùng (prefix, id_field): "
                + ", ".join(f"prefix={p!r}/id_field={d!r}" for p, d in _dup_pairs)
                + ". Đảm bảo giá trị id_field của các dòng không trùng nhau.",
                stacklevel=2,
            )

        # Check global formula names không trùng với prefix của tables
        global_names = {gf["name"] for gf in self.global_formulas}
        for tbl in self.child_tables:
            if tbl.table_key in global_names:
                raise ValueError(
                    f"[EngineConfig] global_formula name '{tbl.table_key}' "
                    f"trùng với table_key. Đặt tên khác để tránh nhầm lẫn."
                )


# ─────────────────────────────────────────────────────────────────────────────
# §3  Dataclass: CalculationResult
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CalculationResult:
    """
    Kết quả trả về từ ``FlexibleFormulaEngine.calculate()``.

    Attributes
    ----------
    values : Dict[str, Any]
        Toàn bộ kết quả {formula_name: value}.
        Bao gồm cả kết quả từng dòng (K1, K2…) lẫn global (subtotal…).

    row_results : Dict[str, Dict[str, Any]]
        Kết quả nhóm theo table_key.
        ``{"items": {"K1": 800.0, "K2": 200.0}, "taxes": {"T1": 100.0}}``.
        Key bên trong là id_field của dòng (không bao gồm prefix).

    errors : Dict[str, str]
        Các lỗi theo tên formula (khi on_error != "raise").

    warnings : List[str]
        Cảnh báo assertion severity=WARNING.
    """
    values      : Dict[str, Any]            = field(default_factory=dict)
    row_results : Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors      : Dict[str, str]            = field(default_factory=dict)
    warnings    : List[str]                 = field(default_factory=list)

    def get(self, name: str, default: Any = None) -> Any:
        """Lấy giá trị theo tên formula."""
        return self.values.get(name, default)

    def table(self, table_key: str) -> Dict[str, Any]:
        """Kết quả của một child table cụ thể (key = id_field, không có prefix)."""
        return self.row_results.get(table_key, {})

    def to_frappe_update(
        self,
        scalar_fields: List[str] = None,
        exclude_names: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Trả về dict gồm các giá trị global để update lên Frappe Doc.

        Parameters
        ----------
        scalar_fields : List[str], optional
            Danh sách tên field cần lấy. None → lấy tất cả global values.

        exclude_names : list, optional
            Danh sách tên biến cần loại bỏ (thường là row variable names: K1, K2...).
            Lấy từ result.row_results keys nếu không truyền.

        Example
        -------
        ::

            result = engine.calculate(inputs)
            update = result.to_frappe_update(["subtotal", "total_tax", "grand_total"])
            frappe.db.set_value("Sales Order", docname, update)
        """
        _exclude = set(exclude_names or [])
        # Auto-exclude tất cả row-level variable names (có trong row_results)
        for table_dict in self.row_results.values():
            _exclude.update(table_dict.keys())

        if scalar_fields:
            return {k: self.values.get(k) for k in scalar_fields if k in self.values}

        return {
            k: v for k, v in self.values.items()
            if k not in _exclude
        }


# ─────────────────────────────────────────────────────────────────────────────
# §4  FlexibleFormulaEngine
# ─────────────────────────────────────────────────────────────────────────────

class FlexibleFormulaEngine:
    """
    Engine tính toán linh hoạt — cầu nối FormulaEngine ↔ ERPNext child tables.

    Tính năng chính
    ---------------
    ① Người dùng nhập công thức đơn giản trong Formula Builder (Monaco editor)
       Ví dụ: ``qty * price * (1 - discount_pct / 100)``
       Hệ thống tự hiểu qty/price/discount_pct là cột của dòng đó.

    ② Tham chiếu chéo giữa các dòng trong cùng bảng:
       ``K3: K1 + K2`` — engine tự tính K1, K2 trước (DAG).

    ③ Tham chiếu từ bảng này sang bảng khác:
       ``TAX_T1: subtotal * rate`` — subtotal là kết quả của bảng items.

    ④ Tất cả công thức của tất cả bảng → 1 FormulaEngine DAG duy nhất.
       Chỉ 1 lần calculate() → kết quả cho toàn bộ tài liệu.

    ⑤ Ghi kết quả trở lại rows (output_field) — mutate in-place.

    ⑥ Multi-scenario, validate, explain, incremental context.

    Workflow tích hợp với Formula Builder
    ─────────────────────────────────────
    User nhập công thức trong formula_builder.js
         ↓ (Monaco editor với gợi ý biến từ SuggestionsBuilder)
    formula_builder.py::evaluate_formula() — preview realtime
         ↓ (dùng VariableResolver.build_full_context() để test từng dòng)
    Lưu vào Frappe child table row.formula_field
         ↓ (before_save hook)
    ERPNextAdapter.calculate_doc() (hoặc recalculate_quotation_formulas)
         ↓
    FlexibleFormulaEngine.calculate(inputs)
         ↓
    FormulaEngine DAG → kết quả → ghi lại vào doc

    Ví dụ nhanh
    -----------
    ::

        config = EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items",   formula_field="formula",
                    id_field="line_ref", row_fields=["qty", "price", "rate"],
                    output_field="amount",
                ),
                ChildTableConfig(
                    table_key="taxes",   formula_field="formula",
                    id_field="line_ref", row_fields=["rate"],
                    output_field="tax_amount", prefix="TAX_",
                ),
            ],
            global_formulas=[
                {"name": "subtotal",   "formula": "K1 + K2 + K3"},
                {"name": "total_tax",  "formula": "TAX_T1 + TAX_T2"},
                {"name": "grandtotal", "formula": "subtotal + total_tax + shipping_fee"},
            ],
            extra_context={"shipping_fee": 0},
        )
        engine = FlexibleFormulaEngine(config)
        result = engine.calculate(inputs)
    """

    # Regex: khớp toàn từ (không phải một phần của identifier khác)
    # Hỗ trợ: "rate" trong "amount1 * rate" nhưng không phải "rate" trong "discount_rate"

    # Frappe system fields — không inject dù auto-detect
    _FRAPPE_SYSTEM_FIELDS: frozenset = frozenset({
        "idx", "docstatus", "creation", "modified", "modified_by",
        "owner", "name", "parent", "parenttype", "parentfield",
        "doctype", "_liked_by", "_comments", "_assign", "_user_tags",
    })

    _WORD_RE = staticmethod(lambda col: re.compile(
        rf"(?<!['\"\w\.])({re.escape(col)})(?!['\"\w])"
    ))

    def __init__(self, config: EngineConfig):
        self.config = config
        # Khởi tạo validator 1 lần với toàn bộ BASE_FUNCS + custom
        all_funcs = list(BASE_FUNCS.keys()) + list(config.custom_functions.keys())
        self._validator = FormulaValidator(allowed_functions=all_funcs)

    # ─────────────────────────────────────────────────────────────────────
    # §4a′  Tham số khởi tạo FormulaEngine — MỘT bản duy nhất
    # ─────────────────────────────────────────────────────────────────────

    def _collect_assertions(self) -> List[dict]:
        """Assertion toàn cục + assertion của từng child table."""
        all_assertions = list(self.config.assertions)
        for tbl in self.config.child_tables:
            all_assertions.extend(tbl.assertions)
        return all_assertions

    def _engine_kwargs(
        self,
        all_formulas: List[dict],
        *,
        on_error: Optional[str] = None,
        include_assertions: bool = True,
        include_schema: bool = True,
        include_rounding: bool = True,
    ) -> Dict[str, Any]:
        """Bộ tham số để khởi tạo FormulaEngine — dùng CHUNG cho mọi chỗ gọi.

        VÌ SAO phải gom về một chỗ: trước đây 6 chỗ tự liệt kê tay nên
        `create_incremental_context()` chỉ truyền 4/13 tham số, RƠI MẤT
        `rounding_policy`, `default_value`, `max_operations`, `assertions`,
        `input_fields`, `output_fields`, `strict`. Ca đau nhất là
        `rounding_policy`: lõi áp nó vô điều kiện khi có cấu hình, nên cùng input
        mà `calculate()` CÓ làm tròn còn `create_incremental_context()` KHÔNG ⇒
        UI hiện một số, lưu xuống số khác — lỗi im lặng, chỉ lộ ở tiền.

        Thêm tham số mới cho FormulaEngine thì chỉ cần sửa ở đây, không săn lại
        từng chỗ khởi tạo.
        """
        kwargs: Dict[str, Any] = {
            "formulas":       all_formulas,
            "on_error":       on_error if on_error is not None else self.config.on_error,
            "default_value":  self.config.default_value,
            "deterministic":  self.config.deterministic,
            "max_operations": self.config.max_operations,
            "safe_funcs":     self.config.custom_functions or None,
            "strict":         self.config.strict,
        }
        if include_rounding:
            kwargs["rounding_policy"] = self.config.rounding_policy or None
        if include_assertions:
            kwargs["assertions"] = self._collect_assertions() or None
        if include_schema:
            kwargs["input_fields"]  = self.config.input_fields or None
            kwargs["output_fields"] = self.config.output_fields or None
        return kwargs

    # ─────────────────────────────────────────────────────────────────────
    # §4a  Tiền xử lý công thức: inject giá trị cột vào công thức
    # ─────────────────────────────────────────────────────────────────────

    def _inject_row_values(
        self,
        formula: str,
        row: Dict[str, Any],
        row_fields: List[str],
    ) -> str:
        """
        Thay thế các từ khóa trong ``row_fields`` bằng giá trị literal từ row.

        Ví dụ với row = {"qty": 10, "price": 100, "rate": 0.8}:
            "qty * price * rate"  →  "10 * 100 * 0.8"
            "K1 + K2"             →  "K1 + K2"  (K1/K2 không trong row_fields)
            "rate"                →  "0.8"
            "discount_rate"       →  "discount_rate"  (boundary check ✓)

        Nếu row_fields rỗng → auto-detect các trường số/bool trong row.

        Parameters
        ----------
        formula    : str  — công thức gốc từ Formula Builder
        row        : dict — dữ liệu dòng
        row_fields : list — cột cần thay thế (rỗng = auto)
        """
        if not row_fields:
            # Auto-detect: chỉ inject trường có giá trị scalar
            row_fields = [
                k for k, v in row.items()
                if isinstance(v, (int, float, bool)) and not isinstance(v, type)
                and not k.startswith("_")
                and k not in self._FRAPPE_SYSTEM_FIELDS
            ]

        # Gỡ HTML entity TRƯỚC khi thay cột: nếu để sau, "&amp;" tình cờ chứa tên
        # cột "amp" sẽ bị thay thành giá trị số trước khi entity được giải.
        formula = html_unescape_formula(formula)

        expr = formula
        # Sắp xếp dài trước: tránh "discount_pct" bị thay trước "discount"
        for col in sorted(row_fields, key=len, reverse=True):
            if col not in row:
                continue
            pattern = self._WORD_RE(col)
            if pattern.search(expr):
                # repr() đảm bảo: 0.8 → "0.8", "ABC" → "'ABC'", True → "True"
                expr = pattern.sub(repr(row[col]), expr)
        return expr

    # ─────────────────────────────────────────────────────────────────────
    # §4b  Build formulas từ child tables
    # ─────────────────────────────────────────────────────────────────────

    def _build_child_formulas(
        self,
        context: Dict[str, Any],
    ) -> Tuple[List[dict], Dict[str, str]]:
        """
        Duyệt tất cả child tables, tạo danh sách formulas cho FormulaEngine.

        Returns
        -------
        formulas     : list[dict] {"name": var_name, "formula": resolved_expr}
        name_to_table: {var_name: table_key} để phân loại kết quả sau
        """
        formulas: List[dict] = []
        name_to_table: Dict[str, str] = {}

        for tbl in self.config.child_tables:
            rows = context.get(tbl.table_key) or []

            for row in rows:
                # Lấy id định danh dòng
                row_id = row.get(tbl.id_field)
                if not row_id:
                    continue  # skip dòng không có id

                var_name = f"{tbl.prefix}{row_id}"

                # Lấy công thức gốc — gỡ HTML entity trước khi .strip(), vì
                # "&nbsp;" ở đầu/cuối sẽ thành khoảng trắng thường sau khi gỡ.
                raw = html_unescape_formula(row.get(tbl.formula_field) or "").strip()
                if not raw:
                    if tbl.skip_empty_formula:
                        continue
                    raise ValueError(
                        f"[FlexibleFormulaEngine] Dòng '{row_id}' "
                        f"trong '{tbl.table_key}' không có công thức."
                    )

                # Inject giá trị cột: "qty * rate" → "10 * 0.8"
                resolved = self._inject_row_values(raw, row, tbl.row_fields)

                formulas.append({"name": var_name, "formula": resolved})
                name_to_table[var_name] = tbl.table_key

        return formulas, name_to_table

    def _build_all_formulas(
        self,
        context: Dict[str, Any],
    ) -> Tuple[List[dict], Dict[str, str]]:
        """Gộp child formulas + global formulas thành 1 list."""
        child_f, name_to_table = self._build_child_formulas(context)
        all_f = child_f + list(self.config.global_formulas)
        return all_f, name_to_table

    def _build_all_formulas_raw(self, context: Dict[str, Any]) -> List[dict]:
        """
        Build formulas WITHOUT injection (for validation).
        Returns list of {"name": ..., "formula": raw_formula}

        ⛔ Vẫn phải gỡ HTML entity (dù KHÔNG inject): validator và DependencyGraph
        đều đọc chính chuỗi này. "K1 &gt; K2" chưa gỡ sẽ bị validator báo lỗi cú
        pháp OAN và có thể sinh cạnh phụ thuộc ma vào công thức tên "gt".
        """
        formulas: List[dict] = []
        for tbl in self.config.child_tables:
            rows = context.get(tbl.table_key) or []
            for row in rows:
                row_id = row.get(tbl.id_field)
                if not row_id:
                    continue
                raw = html_unescape_formula(row.get(tbl.formula_field) or "").strip()
                if not raw:
                    if tbl.skip_empty_formula:
                        continue
                    raise ValueError(
                        f"[FlexibleFormulaEngine] Dòng '{row_id}' "
                        f"trong '{tbl.table_key}' không có công thức."
                    )
                formulas.append({"name": f"{tbl.prefix}{row_id}", "formula": raw})
        formulas.extend(self.config.global_formulas)
        return formulas

    # ─────────────────────────────────────────────────────────────────────
    # §4c  Write-back: ghi kết quả vào rows
    # ─────────────────────────────────────────────────────────────────────

    def _write_back(
        self,
        inputs: Dict[str, Any],
        raw_results: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Ghi kết quả engine vào output_field của từng row (mutate in-place).
        Trả về row_results nhóm theo table_key.
        """
        row_results: Dict[str, Dict[str, Any]] = {}

        for tbl in self.config.child_tables:
            rows = inputs.get(tbl.table_key) or []
            table_dict: Dict[str, Any] = {}

            for row in rows:
                row_id = row.get(tbl.id_field)
                if not row_id:
                    continue
                var_name = f"{tbl.prefix}{row_id}"
                value = raw_results.get(var_name)
                table_dict[row_id] = value  # key = id không có prefix

                if tbl.output_field and value is not None:
                    row[tbl.output_field] = value

            row_results[tbl.table_key] = table_dict

        return row_results

    # ─────────────────────────────────────────────────────────────────────
    # §4d  PUBLIC: calculate()
    # ─────────────────────────────────────────────────────────────────────

    def calculate(self, inputs: Dict[str, Any]) -> CalculationResult:
        """
        Tính toán toàn bộ: tất cả child tables + global formulas.

        Parameters
        ----------
        inputs : dict
            Context đầu vào bao gồm:
            • Child tables (list of dict): key phải khớp với table_key
            • Biến scalar: ``shipping_fee``, ``base_amount``, v.v.
            • Tất cả biến toàn cục (AL Global Variables đã resolve nếu dùng ERPNextAdapter)

        Returns
        -------
        CalculationResult
            .values      — dict {formula_name: value}
            .row_results — dict {table_key: {row_id: value}}
            .errors      — dict {formula_name: error_message}
            .warnings    — list[str]

        Notes
        -----
        - Rows trong inputs được MUTATE IN-PLACE nếu output_field được cấu hình.
        - Thứ tự tính: FormulaEngine tự xây DAG (topological sort), đảm bảo
          K1/K2 tính trước K3=K1+K2, và K3 tính trước subtotal=K1+K2+K3.
        """
        # Merge extra_context (inputs ghi đè)
        context = {**self.config.extra_context, **inputs}

        # Build toàn bộ formulas
        all_formulas, name_to_table = self._build_all_formulas(context)
        if not all_formulas:
            return CalculationResult()

        # Khởi tạo FormulaEngine — tham số lấy từ helper DÙNG CHUNG để mọi đường
        # vào engine không lệch cấu hình nhau nữa.
        engine = FormulaEngine(**self._engine_kwargs(all_formulas))
        return self._run_engine(engine, all_formulas, context, inputs)

    # ─────────────────────────────────────────────────────────────────────
    # §4d′  Chạy engine đã dựng + gom kết quả/lỗi/cảnh báo
    # ─────────────────────────────────────────────────────────────────────

    def _run_engine(
        self,
        engine: "FormulaEngine",
        all_formulas: List[dict],
        context: Dict[str, Any],
        inputs: Dict[str, Any],
    ) -> CalculationResult:
        """Tính toán 1 lần cho toàn bộ + write-back + phân loại lỗi/cảnh báo.

        Tách khỏi `calculate()` để `multi_scenario()` dùng lại được engine khi
        nhiều kịch bản cho ra CÙNG bộ công thức (kịch bản chỉ đổi biến scalar).
        """
        # ── LƯỢT 1 — nguyên vẹn như trước bản vá ────────────────────────────
        raw_results = engine.calculate(context)

        errors = self._collect_errors(engine, all_formulas, context)
        warnings_out = self._collect_warnings(engine)

        # Write-back + nhóm row_results
        row_results = self._write_back(inputs, raw_results)

        # ── LƯỢT 2 CÓ MỤC TIÊU ──────────────────────────────────────────────
        # VÌ SAO cần lượt 2: `_write_back()` ghi `output_field` vào dòng SAU khi
        # lượt DAG duy nhất đã chạy xong, nên công thức header dạng
        # `sum(r.get('amount',0) for r in items)` đọc phải 0 (lượt đầu) hoặc giá
        # trị CŨ của lần gọi trước (dòng bị mutate in-place) — sai ở TIỀN mà
        # không có exception nào. Chỉ chạy lượt 2 khi cấu hình THẬT SỰ dùng mẫu
        # đọc-dòng, và chỉ cho đúng những công thức bị ảnh hưởng.
        pass2_formulas = self._second_pass_formulas(engine, all_formulas)
        if not pass2_formulas:
            # ⛔ Không có công thức đọc-dòng ⇒ zero-cost, zero-thay-đổi-hành-vi.
            return CalculationResult(
                values      = raw_results,
                row_results = row_results,
                errors      = errors,
                warnings    = warnings_out,
            )

        # `context2` = số liệu lượt 1 + các dòng ĐÃ có `output_field` (write-back
        # ở trên sửa tại chỗ chính các dict nằm trong `context[table_key]`).
        # VÌ SAO nhét cả `raw_results` vào context: công thức lượt 2 vẫn cần các
        # giá trị phía trước (`K1`, `TAX_T1`…). Chúng trở thành HẰNG ⇒ ⛔ không
        # tính lại công thức dòng nào ⇒ không rủi ro công thức không idempotent
        # (ví dụ `output_field` lọt vào `row_fields`).
        # ⛔ Cách này KHÔNG chia DAG thành "bảng trước, header sau": công thức
        # dòng tham chiếu công thức header (`TAX_T1: subtotal * rate`) vẫn đi
        # đúng một lượt như cũ — chia thô sẽ làm vỡ chiều tham chiếu đó.
        context2 = {**context, **raw_results}
        engine2 = FormulaEngine(**self._engine_kwargs(
            pass2_formulas,
            include_assertions=True,   # assertion phải thấy số CUỐI, ⛔ không phải số lượt 1
            include_schema=False,      # ⛔ tránh báo lỗi schema lần thứ hai
            include_rounding=True,     # giữ đúng chính sách làm tròn
        ))
        results2 = engine2.calculate(context2)

        # Gộp: bảng lỗi/cảnh báo phải phản ánh lượt 2 (số cuối), không phải lượt 1.
        errors = self._merge_second_pass_errors(errors, engine2, pass2_formulas)
        warnings_out = self._merge_second_pass_warnings(warnings_out, engine2)

        merged = {**raw_results, **results2}
        # Ghi LẠI: cần khi công thức DÒNG cũng là consumer (giá trị dòng đổi ở
        # lượt 2). Ở ca thường đây là ghi đè idempotent nên vô hại.
        row_results = self._write_back(inputs, merged)

        return CalculationResult(
            values      = merged,
            row_results = row_results,
            errors      = errors,
            warnings    = warnings_out,
        )

    # ─────────────────────────────────────────────────────────────────────
    # §4d″  Lượt hai có mục tiêu: dò consumer + node phía sau
    # ─────────────────────────────────────────────────────────────────────

    def _second_pass_formulas(
        self,
        engine: "FormulaEngine",
        all_formulas: List[dict],
    ) -> List[dict]:
        """Công thức của LƯỢT HAI = consumer ∪ mọi node phía sau chúng.

        Trả về list RỖNG khi cấu hình không dùng mẫu đọc-dòng — nơi gọi dựa vào
        đó để giữ nguyên hành vi cũ (⛔ zero-cost).

        VÌ SAO phải kéo cả node PHÍA SAU: `subtotal` tính lại rồi mà
        `grandtotal = subtotal + shipping_fee` vẫn giữ số cũ thì lỗi chỉ chạy
        từ chỗ này sang chỗ khác. Cạnh lấy từ `engine.dependency_edges()`
        (``{node: [node_phụ_thuộc]}``) rồi ĐẢO CHIỀU thành ``{node: [node_đứng_sau]}``.
        """
        consumers = self._row_output_consumers(all_formulas)
        if not consumers:
            return []

        formula_names = {f["name"] for f in all_formulas}
        dependents: Dict[str, Set[str]] = {}
        for node, parents in engine.dependency_edges().items():
            for parent in parents:
                dependents.setdefault(parent, set()).add(node)

        # BFS từ consumer; ⛔ chỉ đi trong tập TÊN CÔNG THỨC, bỏ qua tên khác
        # (biến input, tên hàm…) để không kéo nhầm node vào lượt 2.
        pass2: Set[str] = {c for c in consumers if c in formula_names}
        queue = deque(pass2)
        while queue:
            for name in dependents.get(queue.popleft(), ()):
                if name in formula_names and name not in pass2:
                    pass2.add(name)
                    queue.append(name)

        # Giữ nguyên thứ tự của `all_formulas` ⇒ kết quả DETERMINISTIC, và bộ
        # công thức gửi vào engine lượt 2 không phụ thuộc thứ tự duyệt set.
        return [f for f in all_formulas if f["name"] in pass2]

    def _row_output_consumers(self, all_formulas: List[dict]) -> Set[str]:
        """Tên các công thức ĐỌC DỮ LIỆU BẢNG DÒNG (consumer).

        Ví dụ ``sum(r.get('amount',0) for r in items)`` — đọc ``items``, mà
        ``items`` là TÊN BẢNG chứ không phải tên công thức, nên
        `DependencyGraph.build_from_exprs()` ⛔ không sinh cạnh nào cho nó: công
        thức này không được xếp sau các dòng bảng. Đó chính là gốc lỗi.

        Dò bằng `extract_identifiers()` — CHÍNH hàm mà `build_from_exprs()` dùng
        để dựng cạnh, để thứ tự tính và việc phát hiện không bao giờ lệch nhau.
        Xét CẢ công thức dòng lẫn công thức header.

        ⚠️ Trùng tên chỉ là trùng TÊN ĐỊNH DANH: công thức dùng biến
        ``items_count`` ⛔ không bị coi là đọc bảng ``items``.
        """
        table_names = {tbl.table_key for tbl in self.config.child_tables}
        if not table_names:
            return set()
        return {
            f["name"] for f in all_formulas
            if extract_identifiers(f["formula"]) & table_names
        }

    def _assertion_names(self) -> Set[str]:
        """Tên các assertion đã cấu hình.

        VÌ SAO cần: assertion được chạy LẠI ở lượt 2 (engine2 có
        `include_assertions=True`), nên phán quyết của lượt 1 là số CŨ.
        """
        return {a.get("name") for a in self._collect_assertions() if a.get("name")}

    def _merge_second_pass_errors(
        self,
        errors: Dict[str, str],
        engine2: "FormulaEngine",
        pass2_formulas: List[dict],
    ) -> Dict[str, str]:
        """Gộp bảng lỗi hai lượt: bỏ phán quyết CŨ của thứ mà lượt 2 đã tính lại.

        ⛔ VÌ SAO phải BỎ chứ không chỉ `update()`: `update()` chỉ thay được khoá
        nào lượt 2 CÓ báo lỗi. Ca thật: assertion ``subtotal > 0`` lượt 1 thấy
        `subtotal = 0` (lỗi đang vá) ⇒ ghi lỗi OAN; lượt 2 thấy 350 ⇒ không ghi
        gì, nên nếu giữ nguyên thì lỗi oan ở lại vĩnh viễn và người dùng bị chặn
        bởi một cảnh báo sai.

        Bỏ được cả khoá assertion vì lượt 2 CHẠY LẠI toàn bộ assertion trên
        `context2` (đã chứa MỌI giá trị công thức của lượt 1), nên phán quyết
        của lượt 2 luôn đầy đủ và đúng hơn lượt 1.
        """
        stale = {f["name"] for f in pass2_formulas} | self._assertion_names()
        out = {name: msg for name, msg in errors.items() if name not in stale}
        out.update(getattr(engine2, "last_errors", None) or {})
        return out

    def _merge_second_pass_warnings(
        self,
        first_pass: List[str],
        engine2: "FormulaEngine",
    ) -> List[str]:
        """Gộp cảnh báo hai lượt, khử trùng theo (tên assertion, thông điệp).

        `_collect_warnings()` đã render mỗi cảnh báo thành chuỗi
        ``"tên: thông điệp"`` nên khử trùng theo CHUỖI chính là khử theo cặp
        (tên, thông điệp). Giữ nguyên thứ tự lượt 1 trước ⇒ danh sách cảnh báo
        của cấu hình không dùng mẫu đọc-dòng không đổi.
        """
        out: List[str] = []
        seen: Set[str] = set()
        for msg in list(first_pass) + self._collect_warnings(engine2):
            if msg in seen:
                continue
            seen.add(msg)
            out.append(msg)
        return out

    def _collect_errors(
        self,
        engine: "FormulaEngine",
        all_formulas: List[dict],
        context: Dict[str, Any],
    ) -> Dict[str, str]:
        """Lấy bảng lỗi của lần calculate vừa rồi."""
        if hasattr(engine, "last_errors"):
            # Lõi hiện tại (ENGINE_VERSION 31.x) LUÔN có property `last_errors`
            # ⇒ lấy TRỰC TIẾP, không chạy lại công thức.
            #
            # ⚠️ VÌ SAO đổi điều kiện (trước đây: `hasattr(...) AND engine.last_errors`):
            # `last_errors` trả dict {tên: lỗi} của lần calculate gần nhất, nên khi
            # MỌI công thức chạy sạch nó là {} — falsy. Điều kiện cũ vì thế rơi vào
            # nhánh dự phòng đúng ở ca phổ biến nhất: KHÔNG có lỗi thì mới dựng
            # FormulaEngine THỨ HAI và eval lại toàn bộ. Ngược hẳn ý đồ, và tốn gấp
            # đôi cho mọi lần tính sạch.
            return engine.last_errors.copy()

        # ── Đường lùi cho lõi CŨ (chưa có `last_errors`) — giữ nguyên, ⛔ không xoá.
        errors: Dict[str, str] = {}
        if self.config.on_error == "raise":
            return errors
        _err_engine = FormulaEngine(**self._engine_kwargs(
            all_formulas,
            on_error="null",
            include_assertions=False,
            include_schema=False,
            include_rounding=False,
        ))
        _err_results = _err_engine.calculate(context)
        _err_map = getattr(_err_engine, "last_errors", None)

        for name, val in _err_results.items():
            if _err_map is not None:
                # Lõi có bảng lỗi ⇒ chỉ báo ĐÚNG công thức đã lỗi.
                # ⛔ KHÔNG suy lỗi từ `val is None`: công thức HỢP LỆ trả None
                # (row.get('x') thiếu khoá, min() trên list rỗng…) sẽ bị báo oan.
                if name in _err_map:
                    errors[name] = _err_map[name]
            elif isinstance(val, FormulaError):
                errors[name] = str(val)
            elif val is None:
                errors[name] = f"Formula '{name}' returned error (on_error=null → None)"
        return errors

    def _collect_warnings(self, engine: "FormulaEngine") -> List[str]:
        """Cảnh báo assertion (severity=WARNING) của lần calculate vừa rồi.

        `getattr` để chạy được với lõi cũ (chưa có `last_warnings`).
        """
        raw_warnings = getattr(engine, "last_warnings", None) or []
        out: List[str] = []
        for w in raw_warnings:
            name = getattr(w, "assertion_name", None)
            msg = getattr(w, "message", None)
            if msg is None:          # lõi khác trả chuỗi thẳng
                out.append(str(w))
            elif name:
                out.append(f"{name}: {msg}")
            else:
                out.append(str(msg))
        return out

    # ─────────────────────────────────────────────────────────────────────
    # §4e  PUBLIC: create_incremental_context() — Reactive UI
    # ─────────────────────────────────────────────────────────────────────

    def create_incremental_context(
        self, inputs: Dict[str, Any]
    ) -> Tuple[Any, "FormulaEngine", Dict[str, str]]:
        """
        Tạo IncrementalContext để dùng với reactive UI.

        QUAN TRỌNG — Khác với calculate():
        Không inject giá trị cột thành literal. Thay vào đó, các trường cột
        được đưa vào context dict dưới dạng biến (vd: qty_K1=10, price_K1=100).
        Công thức giữ nguyên tên biến → IncrementalContext.set() hoạt động đúng.

        Naming convention: {col}_{row_id}  (vd: qty_K1, price_K2, rate_TAX_T1)

        Returns
        -------
        (ctx, engine, name_to_table)
        """
        context = {**self.config.extra_context, **inputs}

        # Build formulas KHÔNG inject — giữ tên cột làm biến
        formulas: List[dict] = []
        name_to_table: Dict[str, str] = {}
        incremental_vars: Dict[str, Any] = {}

        for tbl in self.config.child_tables:
            rows = context.get(tbl.table_key) or []

            # ── Tự dò cột: MỘT LẦN cho cả bảng, HỢP NHẤT mọi dòng ────────────
            # VÌ SAO nâng ra ngoài vòng lặp dòng: trước đây `fields` được gán lại
            # (rebind) BÊN TRONG vòng lặp, nên bộ cột tự dò của DÒNG 1 bị dùng luôn
            # cho các dòng sau. Dòng 2 có thêm cột (vd `vat`) mà dòng 1 không có
            # ⇒ cột đó không được đổi tên thành `vat_K2` ⇒ công thức giữ tên trần
            # `vat`, LẶNG LẼ bám vào biến context ngoài (hoặc thành biến không xác
            # định) → sai số.
            # ⚠️ `fields` chỉ được GÁN LẠI chứ ⛔ không append vào `tbl.row_fields`,
            # nên lỗi cũ chỉ trong phạm vi MỘT lần gọi, một bảng — không rò rỉ.
            fields = tbl.row_fields
            if not fields:
                _union: Dict[str, None] = {}    # dict giữ thứ tự, tự khử trùng
                for _row in rows:
                    for _k, _v in _row.items():
                        if (isinstance(_v, (int, float, bool))
                                and not isinstance(_v, type)
                                and not _k.startswith("_")
                                # Lọc trường hệ thống Frappe cho KHỚP _inject_row_values
                                # (:458). Thiếu bộ lọc này thì name/owner/idx/parent/
                                # docstatus bị đổi thành name_K1, owner_K1… rác.
                                and _k not in self._FRAPPE_SYSTEM_FIELDS):
                            _union[_k] = None
                fields = list(_union)

            for row in rows:
                row_id = row.get(tbl.id_field)
                if not row_id:
                    continue
                var_name = f"{tbl.prefix}{row_id}"
                # Gỡ HTML entity trước khi đổi tên cột — nếu để sau, "&amp;" chứa
                # tên cột "amp" sẽ bị đổi tên oan thành "amp_K1".
                raw = html_unescape_formula(row.get(tbl.formula_field) or "").strip()
                if not raw:
                    if tbl.skip_empty_formula:
                        continue
                    raise ValueError(
                        f"[FlexibleFormulaEngine] Dòng '{row_id}' "
                        f"trong '{tbl.table_key}' không có công thức."
                    )

                # Đổi tên biến cột: qty → qty_{row_id}
                renamed_formula = raw
                for col in sorted(fields, key=len, reverse=True):
                    if col not in row:
                        continue
                    scoped_name = f"{col}_{row_id}"
                    renamed_formula = self._WORD_RE(col).sub(scoped_name, renamed_formula)
                    incremental_vars[scoped_name] = row[col]

                formulas.append({"name": var_name, "formula": renamed_formula})
                name_to_table[var_name] = tbl.table_key

        all_formulas = formulas + list(self.config.global_formulas)

        # Merge incremental_vars vào context (ưu tiên thấp hơn inputs)
        full_context = {**incremental_vars, **context}

        # Dùng chung helper tham số: trước đây chỗ này chỉ truyền 4/13 tham số nên
        # RƠI MẤT rounding_policy, default_value, max_operations, assertions,
        # input_fields, output_fields, strict ⇒ UI hiện một số, lưu xuống số khác.
        engine = FormulaEngine(**self._engine_kwargs(all_formulas))
        ctx = engine.create_context(full_context)
        return ctx, engine, name_to_table

    # ─────────────────────────────────────────────────────────────────────
    # §4f  PUBLIC: validate_formulas() — Kiểm tra trước khi lưu
    # ─────────────────────────────────────────────────────────────────────

    def validate_formulas(
        self,
        inputs: Dict[str, Any],
        extra_known_vars: Optional[List[str]] = None,
    ) -> Dict[str, List[str]]:
        """
        Validate tất cả công thức (AST tĩnh) - dùng công thức GỐC (chưa inject).

        Thường dùng trong ``before_save`` hook hoặc trước khi submit doc.

        Parameters
        ----------
        inputs           : dict  — context mẫu
        extra_known_vars : list  — biến bổ sung để bỏ qua cảnh báo undefined

        Returns
        -------
        Dict[str, List[str]]
            {formula_name: [error_msg, ...]}. Rỗng = tất cả hợp lệ.
        """
        context = {**self.config.extra_context, **inputs}
        all_formulas_raw = self._build_all_formulas_raw(context)

        issues: Dict[str, List[str]] = {}
        for f in all_formulas_raw:
            result = self._validator.validate(f["formula"])
            if not result.ok:
                issues[f["name"]] = result.errors
        return issues

    # ─────────────────────────────────────────────────────────────────────
    # §4g  PUBLIC: explain() / explain_all() — Debug
    # ─────────────────────────────────────────────────────────────────────

    def explain(
        self,
        formula_name: str,
        inputs: Dict[str, Any],
        escape_html: bool = False,
    ) -> Any:
        """
        Trả về ExplainResult cho một formula — từng bước tính chi tiết.

        Hữu ích để hiển thị "Bảng tính chi tiết" trong Frappe form.
        Kết quả có thể dùng ``.to_dict()`` để serialize sang JSON cho JS.

        escape_html : bool = False
            ⛔ MẶC ĐỊNH TẮT (trả bản RAW) — và đây là chủ ý, không phải sót.
            `formula_builder.js::_actExplain` đã escape MỘT lần bằng `_esc()`
            trước khi đổ vào innerHTML; escape thêm ở đây nữa thì người dùng
            ĐỌC THẤY `a &gt; b` thay vì `a > b` — đúng thứ mà lớp gỡ entity ở
            cửa vào vừa dọn. Chuẩn của cả lớp: escape ĐÚNG MỘT LẦN, ở lớp NGOÀI
            CÙNG của đường hiển thị. Template in ấn render thẳng HTML mà không
            tự escape thì truyền True.

        Example
        -------
        ::

            exp = engine.explain("K3", inputs)
            # exp.steps = [ExplainStep(name="K1", value=800, formula="10*80"), ...]
        """
        context = {**self.config.extra_context, **inputs}
        all_formulas, _ = self._build_all_formulas(context)

        # on_error lấy từ config, ⛔ KHÔNG cứng "raise".
        # VÌ SAO: explain() là công cụ GỠ LỖI; cứng on_error="raise" khiến nó ném
        # lỗi ngay khi công thức hỏng — hỏng đúng lúc người ta cần nó nhất. Để
        # theo config (mặc định "default") thì explain() vẫn trả về các bước đã
        # tính được thay vì đổ.
        eng = FormulaEngine(**self._engine_kwargs(all_formulas))
        # escape ở LỚP NGOÀI CÙNG (đây) — tắt escape của lõi để ⛔ không escape 2 lần.
        return eng.explain(formula_name, context, escape_html=escape_html)

    def explain_all(
        self,
        inputs: Dict[str, Any],
        escape_html: bool = False,
    ) -> Dict[str, Any]:
        """Explain tất cả formulas — trả về dict {name: ExplainResult}.

        Xem `explain()` về tham số escape_html.
        """
        context = {**self.config.extra_context, **inputs}
        all_formulas, _ = self._build_all_formulas(context)

        eng = FormulaEngine(**self._engine_kwargs(all_formulas))
        return eng.explain_all(context, escape_html=escape_html)

    # ─────────────────────────────────────────────────────────────────────
    # §4h  PUBLIC: multi_scenario() — So sánh kịch bản
    # ─────────────────────────────────────────────────────────────────────

    def multi_scenario(
        self,
        base_inputs: Dict[str, Any],
        scenarios: Dict[str, Dict[str, Any]],
    ) -> Dict[str, CalculationResult]:
        """
        Tính toán nhiều kịch bản song song.

        Parameters
        ----------
        base_inputs : dict — context cơ sở
        scenarios   : dict — {scenario_name: {field: override_value}}

        Example
        -------
        ::

            results = engine.multi_scenario(
                base_inputs=inputs,
                scenarios={
                    "base":        {},
                    "discount10":  {"shipping_fee": 0},
                    "premium":     {"shipping_fee": 100_000},
                }
            )
            diff = results["premium"].get("grandtotal") - results["base"].get("grandtotal")
        """
        # TÁI DÙNG ENGINE: nhiều kịch bản thường chỉ đổi biến SCALAR, khi đó phần
        # inject giá trị cột cho ra ĐÚNG CÙNG bộ công thức. Dựng lại FormulaEngine
        # (parse + dựng DAG) cho từng kịch bản là làm thừa — cache theo dấu vân
        # tay của bộ công thức trong phạm vi MỘT lần gọi.
        # Kịch bản có đổi dữ liệu dòng ⇒ công thức khác ⇒ tự động dựng engine mới.
        _engines: Dict[tuple, Any] = {}

        output: Dict[str, CalculationResult] = {}
        for name, overrides in scenarios.items():
            merged = self._clone_scenario_inputs(base_inputs, overrides)
            context = {**self.config.extra_context, **merged}
            all_formulas, _ = self._build_all_formulas(context)
            if not all_formulas:
                output[name] = CalculationResult()
                continue

            key = tuple((f["name"], f["formula"]) for f in all_formulas)
            _eng = _engines.get(key)
            if _eng is None:
                _eng = FormulaEngine(**self._engine_kwargs(all_formulas))
                _engines[key] = _eng

            output[name] = self._run_engine(_eng, all_formulas, context, merged)
        return output

    def _clone_scenario_inputs(
        self,
        base_inputs: Dict[str, Any],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Bản sao input cho một kịch bản.

        VÌ SAO không dùng `deepcopy(base_inputs)`: chỉ những dict DÒNG của child
        table có `output_field` mới bị `_write_back()` sửa tại chỗ — nếu dùng
        chung `base_inputs` thì kịch bản sau sẽ nhìn thấy kết quả kịch bản trước
        đã ghi vào. Các giá trị scalar KHÔNG bị ghi nên dùng lại được, khỏi
        deepcopy cả cây (base_inputs có thể chứa list/dict lớn).
        """
        merged = dict(base_inputs)
        _written_keys = {
            tbl.table_key for tbl in self.config.child_tables if tbl.output_field
        }
        for table_key in _written_keys:
            rows = base_inputs.get(table_key)
            if isinstance(rows, list):
                merged[table_key] = [
                    dict(r) if isinstance(r, dict) else r for r in rows
                ]
        for k, v in overrides.items():
            merged[k] = v
        return merged

    # ─────────────────────────────────────────────────────────────────────
    # §4i  PUBLIC: get_dependency_graph() — Hiển thị DAG
    # ─────────────────────────────────────────────────────────────────────

    def get_dependency_graph(self, inputs: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Trả về đồ thị phụ thuộc {formula_name: [dep1, dep2, ...]}.
        Lưu ý: method này tạo engine tạm thời, không ảnh hưởng đến hiệu năng chính.
        """
        context = {**self.config.extra_context, **inputs}
        all_formulas, _ = self._build_all_formulas(context)
        # Tạo engine tạm (không cache)
        eng = FormulaEngine(**self._engine_kwargs(all_formulas))
        # Dùng accessor CÔNG KHAI của lõi thay vì chọc thẳng vào `eng._deps_cache`
        # / `eng._topo_order` (thuộc tính riêng của lớp khác — đổi cấu trúc bên
        # trong là chỗ này vỡ im lặng).
        return eng.dependency_edges()

    # ─────────────────────────────────────────────────────────────────────
    # §4j  PUBLIC: preview_resolved_formulas() — Debug inject
    # ─────────────────────────────────────────────────────────────────────

    def preview_resolved_formulas(
        self, inputs: Dict[str, Any], escape_html: bool = False
    ) -> List[Dict[str, str]]:
        """
        Trả về danh sách công thức SAU KHI inject giá trị cột.

        Dùng để debug: kiểm tra engine thực sự nhận công thức gì. Mặc định trả
        bản RAW (escape_html=True nếu nơi hiển thị không tự escape — ⛔ xem
        `explain()` để hiểu vì sao mặc định phải là RAW).

        Returns
        -------
        [{"name": "K1", "formula": "10 * 100", "original": "qty * price"}, ...]
        """
        context = {**self.config.extra_context, **inputs}
        all_formulas, _ = self._build_all_formulas(context)

        # Thu thập công thức gốc để so sánh
        raw_map: Dict[str, str] = {}
        for tbl in self.config.child_tables:
            rows = context.get(tbl.table_key) or []
            for row in rows:
                row_id = row.get(tbl.id_field)
                if row_id:
                    raw_map[f"{tbl.prefix}{row_id}"] = row.get(tbl.formula_field, "")
        for f in self.config.global_formulas:
            raw_map[f["name"]] = f["formula"]

        # `changed` tính trên bản THÔ, escape chỉ áp cho phần hiển thị —
        # escape trước rồi so sẽ làm mọi công thức có '>' '<' '&' thành "changed".
        _fmt = (lambda s: html_escape_formula(s)) if escape_html else (lambda s: s)
        out: List[Dict[str, str]] = []
        for f in all_formulas:
            # `original` hiển thị công thức NGƯỜI DÙNG nhập (`qty > rate`), ⛔ không
            # phải bản entity đang nằm trong DB (`qty &gt; rate`) — entity là chi
            # tiết lưu trữ, phơi thẳng ra UI chỉ làm người đọc tưởng công thức hỏng.
            # `changed` cũng phải so trên bản ĐÃ gỡ entity: so với bản entity thì
            # mọi công thức chứa '>' '<' '&' đều bị báo "đã đổi" dù chẳng inject gì.
            original = html_unescape_formula(raw_map.get(f["name"], f["formula"]))
            out.append({
                "name":     f["name"],
                "formula":  _fmt(f["formula"]),
                "original": _fmt(original),
                "changed":  f["formula"] != original,
            })
        return out


# ─────────────────────────────────────────────────────────────────────────────
# §5  ERPNextAdapter — Tích hợp trực tiếp với Frappe (không import frappe ở đây)
# ─────────────────────────────────────────────────────────────────────────────

class ERPNextAdapter:
    """
    Adapter tích hợp FlexibleFormulaEngine với Frappe DocType.

    Lý do tách riêng:
    - FlexibleFormulaEngine hoàn toàn độc lập, không import frappe.
    - ERPNextAdapter đóng gói toàn bộ logic Frappe-specific.
    - Dễ test FlexibleFormulaEngine mà không cần Frappe environment.

    Không dùng trực tiếp file này với frappe — xem hướng dẫn tích hợp bên dưới.

    Hướng dẫn tích hợp trong formula_builder/api/
    ─────────────────────────────────────────
    Tạo file ``formula_builder/api/ffe_adapter.py`` với nội dung:

    .. code-block:: python

        # formula_builder/api/ffe_adapter.py
        import frappe
        from formula_builder.flexible_formula_engine import (
            FlexibleFormulaEngine, EngineConfig, ChildTableConfig, ERPNextAdapter
        )
        from formula_builder.api.variable_resolver import VariableResolver, ScopeContext

        class FrappeERPNextAdapter(ERPNextAdapter):
            \"\"\"Concrete implementation cho Frappe.\"\"\"

            def get_doc(self, doctype: str, docname: str):
                return frappe.get_doc(doctype, docname)

            def get_global_vars(self) -> dict:
                \"\"\"Lấy AL Global Variables (CONSTANT) từ DB.\"\"\"
                try:
                    resolver = VariableResolver()
                    ctx = ScopeContext()
                    # Lấy tất cả CONSTANT
                    rows = frappe.get_all(
                        "AL Global Variable",
                        filters={"is_active": 1, "value_source": "CONSTANT"},
                        fields=["var_name", "constant_value", "var_type"],
                    )
                    return {
                        r.var_name: resolver._cast(r.constant_value, r.var_type)
                        for r in rows
                    }
                except Exception:
                    return {}

            def rows_to_dicts(self, doc, child_field: str) -> list:
                \"\"\"Convert Frappe child rows sang list of plain dicts.\"\"\"
                rows = doc.get(child_field) or []
                return [
                    row.as_dict() if hasattr(row, "as_dict") else dict(row)
                    for row in rows
                ]

            def calculate_doc(
                self,
                engine: FlexibleFormulaEngine,
                doc,
                child_table_map: dict,   # {engine_key: frappe_fieldname}
                scalar_fields: list,     # ["shipping_fee", ...]
                output_scalar: dict,     # {"subtotal": "custom_subtotal", ...}
            ) -> dict:
                \"\"\"
                Tính toán và ghi kết quả lại vào Frappe Doc.

                Parameters
                ----------
                engine          : FlexibleFormulaEngine instance
                doc             : document cần tính
                child_table_map : mapping engine_key → frappe_fieldname
                scalar_fields   : trường scalar lấy từ doc cho context
                output_scalar   : {engine_var_name: frappe_fieldname} để ghi lại

                Example
                -------
                ::

                    adapter.calculate_doc(
                        engine=quotation_engine,
                        doc,
                        child_table_map={"items": "items", "taxes": "taxes"},
                        scalar_fields=["shipping_fee"],
                        output_scalar={
                            "subtotal":   "custom_subtotal",
                            "total_tax":  "custom_total_tax",
                            "grandtotal": "custom_grandtotal",
                        },
                    )
                \"\"\"
                # doc đã được truyền vào như tham số, không cần get_doc

                # Build inputs
                inputs = {}
                inputs.update(self.get_global_vars())
                for engine_key, frappe_field in child_table_map.items():
                    inputs[engine_key] = self.rows_to_dicts(doc, frappe_field)
                for f in scalar_fields:
                    v = doc.get(f)
                    if v is not None:
                        inputs[f] = v

                # Tính toán
                result = engine.calculate(inputs)

                # Ghi scalar fields lên doc
                for eng_var, frappe_field in output_scalar.items():
                    val = result.get(eng_var)
                    if val is not None:
                        doc.set(frappe_field, val)

                # Ghi row results (output_field đã được write-back in-place trên dicts)
                # Sync lại vào Frappe rows
                for tbl in engine.config.child_tables:
                    if not tbl.output_field:
                        continue
                    frappe_field = child_table_map.get(tbl.table_key, tbl.table_key)
                    frappe_rows  = doc.get(frappe_field) or []
                    input_rows   = inputs.get(tbl.table_key) or []
                    id_field     = tbl.id_field
                    out_field    = tbl.output_field
                    # Build map: row_id → calculated_value
                    val_map = result.table(tbl.table_key)
                    for frow in frappe_rows:
                        row_id = frow.get(id_field)
                        if row_id and row_id in val_map:
                            frow.set(out_field, val_map[row_id])

                return result.to_frappe_update(list(output_scalar.keys()))

        # ─── Hook trước khi save ────────────────────────────────────────────
        # Dùng trong hooks.py:
        # doc_events = {
        #     "Sales Order": {"before_save": "formula_builder.api.ffe_adapter.recalculate_doc"}
        # }

        # Instance pre-configured (tạo 1 lần, dùng lại)
        _SALES_ORDER_ENGINE = FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items",    formula_field="custom_formula",
                    id_field="line_ref",  row_fields=["qty", "price", "rate", "discount_pct"],
                    output_field="amount",
                ),
                ChildTableConfig(
                    table_key="taxes",    formula_field="formula",
                    id_field="line_ref",  row_fields=["rate"],
                    output_field="tax_amount", prefix="TAX_",
                ),
            ],
            global_formulas=[
                # ⚠️ Mẫu đọc-dòng dưới đây nay CHẠY ĐÚNG (nhờ "lượt hai có mục
                # tiêu": công thức đọc bảng dòng được tính lại SAU khi bảng đã
                # tính xong và đã ghi vào output_field). Nhưng nó vẫn GIÒN:
                #   • chỉ đọc được output_field của bảng ĐÃ tính xong trong cùng
                #     lượt — ⛔ không đọc được output_field của bảng KHÁC nếu
                #     bảng đó chưa tính xong;
                #   • tên cột trong .get('amount', …) phải khớp CHÍNH XÁC
                #     output_field, đổi một trong hai là im lặng trả 0.
                # ✅ Bền hơn: tham chiếu thẳng tên biến dòng do engine sinh ra
                #    ("K1 + K2 + K3") — vừa có cạnh DAG tường minh, vừa không
                #    phụ thuộc tên cột.
                {"name": "subtotal",   "formula": "sum(r.get('amount',0) for r in items)"},
                {"name": "total_tax",  "formula": "sum(r.get('tax_amount',0) for r in taxes)"},
                {"name": "grandtotal", "formula": "subtotal + total_tax + shipping_fee"},
            ],
            extra_context={"shipping_fee": 0},
            on_error="default",
        ))

        _adapter = FrappeERPNextAdapter()

        def recalculate_doc(doc, method):
            if doc.doctype == "Sales Order":
                _adapter.calculate_doc(
                    engine=_SALES_ORDER_ENGINE,
                    doc=doc,
                    child_table_map={"items": "items", "taxes": "taxes"},
                    scalar_fields=["shipping_fee"],
                    output_scalar={
                        "subtotal":   "custom_subtotal",
                        "total_tax":  "custom_total_tax",
                        "grandtotal": "custom_grandtotal",
                    },
                )
    """

    def get_doc(self, doctype: str, docname: str):
        raise NotImplementedError

    def get_global_vars(self) -> Dict[str, Any]:
        raise NotImplementedError

    def rows_to_dicts(self, doc, child_field: str) -> List[Dict]:
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# §6  Helper: build_inputs_from_frappe_doc
# ─────────────────────────────────────────────────────────────────────────────

def build_inputs_from_frappe_doc(
    doc,
    child_table_map: Dict[str, str],
    scalar_fields: List[str],
    global_vars: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Chuyển Frappe Document sang inputs dict cho FlexibleFormulaEngine.

    Dùng trong Frappe context (có ``import frappe`` ở nơi gọi).

    Parameters
    ----------
    doc              : frappe.Document
    child_table_map  : {engine_key: frappe_fieldname}
    scalar_fields    : danh sách trường scalar lấy từ doc
    global_vars      : dict biến toàn cục (AL Global Variables đã resolve)

    Returns
    -------
    dict sẵn sàng truyền vào engine.calculate()

    Example (trong Frappe controller)
    ----------------------------------
    ::

        from formula_builder.flexible_formula_engine import (
            build_inputs_from_frappe_doc, FlexibleFormulaEngine
        )

        def before_save(self):
            inputs = build_inputs_from_frappe_doc(
                doc=self,
                child_table_map={"items": "items", "taxes": "taxes"},
                scalar_fields=["shipping_fee", "discount_amount"],
                global_vars={"VAT_RATE": 0.1},
            )
            result = my_engine.calculate(inputs)
            self.custom_grand_total = result.get("grandtotal", 0)
    """
    inputs: Dict[str, Any] = {}

    # Global vars trước (ưu tiên thấp nhất)
    if global_vars:
        inputs.update(global_vars)

    # Child tables
    for engine_key, frappe_field in child_table_map.items():
        rows = doc.get(frappe_field) or []
        inputs[engine_key] = [
            row.as_dict() if hasattr(row, "as_dict") else dict(row)
            for row in rows
        ]

    # Scalar fields (ưu tiên cao hơn global_vars)
    for f in scalar_fields:
        v = doc.get(f)
        if v is not None:
            inputs[f] = v

    return inputs