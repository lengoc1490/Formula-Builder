# Formula Engine v28 — Hướng Dẫn Toàn Diện A–Z

> **Pure Python · Zero External Dependencies · ENGINE_VERSION = "28.0.0"**  
> File: `formula_utils.py` · Dùng cho: lương, giá thành, dự toán, KPI, phân bổ, BOM, Leontief, và mọi domain tính toán

---

## Mục Lục

1. [Triết lý & Kiến trúc](#1-triết-lý--kiến-trúc)
2. [Changelog v28 — 4 Bug Fixes](#2-changelog-v28--4-bug-fixes)
3. [Import nhanh](#3-import-nhanh)
4. [Các lớp lỗi (Error Hierarchy)](#4-các-lớp-lỗi-error-hierarchy)
5. [FormulaEngine — Tham số khởi tạo đầy đủ](#5-formulaengine--tham-số-khởi-tạo-đầy-đủ)
6. [Cú pháp công thức — Đầy đủ](#6-cú-pháp-công-thức--đầy-đủ)
7. [BASE_FUNCS — 80+ Hàm tích hợp (đầy đủ tham số)](#7-base_funcs--80-hàm-tích-hợp-đầy-đủ-tham-số)
8. [calculate() và các biến thể](#8-calculate-và-các-biến-thể)
9. [IncrementalContext — Tính toán tăng tiến](#9-incrementalcontext--tính-toán-tăng-tiến)
10. [Explain API — Giải thích chuỗi tính toán](#10-explain-api--giải-thích-chuỗi-tính-toán)
11. [Multi-Scenario — So sánh phương án](#11-multi-scenario--so-sánh-phương-án)
12. [Validate Inputs & Diff Inputs](#12-validate-inputs--diff-inputs)
13. [FormulaValidator — Kiểm tra tĩnh AST](#13-formulavalidator--kiểm-tra-tĩnh-ast)
14. [Snapshot & Audit — Chốt số, lưu vết](#14-snapshot--audit--chốt-số-lưu-vết)
15. [TimeBucket v3 — Quản lý kỳ thời gian](#15-timebucket-v3--quản-lý-kỳ-thời-gian)
16. [Allocation Engine — Phân bổ chi phí](#16-allocation-engine--phân-bổ-chi-phí)
17. [TopoSort v2 — Sort DAG data rows](#17-toposort-v2--sort-dag-data-rows)
18. [SCC TopoSort — Sort đồ thị có chu kỳ](#18-scc-toposort--sort-đồ-thị-có-chu-kỳ)
19. [SccLinearSolver — Giải hệ tuyến tính trên graph](#19-scclinearsolver--giải-hệ-tuyến-tính-trên-graph)
20. [Security Model](#20-security-model)
21. [Tích hợp ERPNext/Frappe](#21-tích-hợp-erpnextfrappe)
22. [Hiệu năng & Tối ưu](#22-hiệu-năng--tối-ưu)
23. [Ví dụ thực tế — Lương & TNCN](#23-ví-dụ-thực-tế--lương--tncn)
24. [Ví dụ thực tế — Dự toán xây dựng](#24-ví-dụ-thực-tế--dự-toán-xây-dựng)
25. [Ví dụ thực tế — Giá thành sản xuất](#25-ví-dụ-thực-tế--giá-thành-sản-xuất)
26. [Ví dụ thực tế — BOM nhiều cấp](#26-ví-dụ-thực-tế--bom-nhiều-cấp)
27. [Ví dụ thực tế — KPI phụ thuộc vòng](#27-ví-dụ-thực-tế--kpi-phụ-thuộc-vòng)
28. [Cheat Sheet](#28-cheat-sheet)

---

## 1. Triết lý & Kiến trúc

> **Engine không biết bất kỳ domain nào. Mọi ngữ nghĩa nghiệp vụ do caller cung cấp.**

```
formula_utils.py
│
├── FormulaEngineCore           ← parse AST, DAG, eval, incremental, budget guard
│   └── FormulaEngineTrace      ← + execution trace (old→new, triggered_by, exec_ms)
│       └── FormulaEngineAudit  ← + audit session, batch audit, forensic report
│           └── FormulaEngine   ← PUBLIC API đầy đủ ← DÙNG CLASS NÀY
│
├── TimeBucket v3               ← kỳ thời gian (year/half/quarter/month/week)
├── AllocationEngine            ← 8 phương pháp phân bổ chi phí
├── TopoSorter / topo_sort()    ← sort DAG data rows (cycle = fatal error)
├── SccTopoSorter               ← sort cycle-aware (Tarjan SCC)
├── SccLinearSolver             ← giải (I-A)x=b trên graph
├── EnterpriseSnapshot          ← chốt số, 5-layer, dual-hash, audit trail
├── FormulaValidator            ← validate tĩnh AST (standalone)
└── BASE_FUNCS                  ← 80+ hàm built-in
```

### Chọn tool đúng

| Bài toán                          | Tool                              |
| --------------------------------- | --------------------------------- |
| Công thức phụ thuộc nhau          | `FormulaEngine.calculate()`       |
| Reactive UI (user sửa field)      | `calculate_incremental()`         |
| Sort items DAG, KHÔNG có cycle    | `topo_sort()`                     |
| Sort items CÓ cycle               | `scc_topo_sort_with_info()`       |
| Giải x = Ax + b, có cycle         | `solve_linear_on_graph()`         |
| Phân bổ chi phí nhiều phương pháp | `allocate()`                      |
| Kỳ thời gian (Q1/2025, M3…)       | `generate_time_buckets()`         |
| Chốt số bất biến, lưu vết         | `EnterpriseSnapshot`              |
| Validate formula trước khi lưu    | `FormulaValidator.validate()`     |

---

## 2. Changelog v28 — 4 Bug Fixes

v28 = v27 + đúng 4 bug fixes. **Zero breaking change. Code v24/v27 chạy trên v28 không cần sửa.**

| Fix       | Method                     | Mô tả lỗi v27                                                                    |
| --------- | -------------------------- | -------------------------------------------------------------------------------- |
| **FIX 1** | `explain_all()`            | `ExplainResult(fld=fld)` → `TypeError`. Sửa: `field=fld`                         |
| **FIX 2** | `calculate()`              | `MODE_DEFAULT`/`NULL` không gọi `_consume_op()` → `max_operations` bị ignore     |
| **FIX 3** | `recalculate_full()`       | Không có `_consume_op()` nào → budget bị bỏ qua hoàn toàn                        |
| **FIX 4** | `calculate()`              | `_op_counter` không reset → tích lũy qua các lần gọi liên tiếp → sai lệch budget |

```python
from formula_utils import FormulaEngine, __version__
print(__version__)                    # "28.0.0"
print(FormulaEngine.ENGINE_VERSION)   # "28.0.0"
```

---

## 3. Import nhanh

```python
# ── Core ─────────────────────────────────────────────────────────────────────
from formula_utils import (
    FormulaEngine,
    FormulaEngineCore,      # khi cần subclass nhẹ, không dùng full API
    FormulaEngineTrace,     # khi cần trace execution
    FormulaEngineAudit,     # khi cần audit session
    InputField,
    OutputField,
    FormulaSetMeta,
)

# ── Hệ thống lỗi ─────────────────────────────────────────────────────────────
from formula_utils import (
    FormulaError,
    ErrorCode,
    FormulaBudgetExceeded,
    FormulaComplexityError,
    FormulaLimitError,
    FormulaRuntimeError,
    FormulaValidationError,
    FormulaDeterministicError,
    FormulaAssertionError,
)

# ── Snapshot ──────────────────────────────────────────────────────────────────
from formula_utils import (
    EnterpriseSnapshot,
    ImmutableSnapshot,
    SnapshotTag,
    SnapshotStatus,
    SnapshotManager,
    SnapshotRegistry,
    EngineMetaBlock,
    EngineContextBlock,
    DagStateBlock,
    ExecutionTraceBlock,
    TraceEntry,
    AuditTrailBlock,
)

# ── Explain / Dataclass ───────────────────────────────────────────────────────
from formula_utils import (
    ExplainResult,
    ExplainStep,
    InputIssue,
    ScenarioComparison,
)

# ── Validate ──────────────────────────────────────────────────────────────────
from formula_utils import FormulaValidator, ValidationResult

# ── Incremental ───────────────────────────────────────────────────────────────
from formula_utils import IncrementalContext, IncrementalStats

# ── Graph Solver (v27) ────────────────────────────────────────────────────────
from formula_utils import (
    SccLinearSolver,
    SccLinearSolveResult,
    SccLinearAuditEntry,
    solve_linear_on_graph,
)

# ── SCC Sort (v25) ────────────────────────────────────────────────────────────
from formula_utils import (
    scc_topo_sort,
    scc_topo_sort_with_info,
    scc_topo_sort_data,
    scc_topo_sort_flat,
    SccTopoSorter,
    SccTopoResult,
)

# ── Topo Sort (v24) ───────────────────────────────────────────────────────────
from formula_utils import (
    topo_sort,
    topo_sort_with_info,
    TopoSorter,
    TopoSortResult,
)

# ── Allocation ────────────────────────────────────────────────────────────────
from formula_utils import (
    allocate,
    allocate_inplace,
    allocate_fast,
    AllocationEngine,
    AllocationResult,
    AllocationLine,
)

# ── TimeBucket ────────────────────────────────────────────────────────────────
from formula_utils import (
    generate_time_buckets,
    generate_time_buckets_flat,
    year_buckets,
    get_period,
    get_period_by_date,
    get_period_offset,
    same_period_last_year,
    TimeBucket,
    TB_FORMAT,
)

# ── Tiện ích ──────────────────────────────────────────────────────────────────
from formula_utils import (
    hash_formulas,
    hash_dict,
    normalize_formula,
    match_criteria,
    BASE_FUNCS,
)
```

---

## 4. Các lớp lỗi (Error Hierarchy)

```
Exception
└── ValueError
    └── FormulaError                     ← Base; code=ErrorCode, level=ERROR
        ├── SchemaError                  ← Schema không hợp lệ
        ├── FormulaBudgetExceeded        ← Vượt max_operations; ops, limit
        ├── FormulaComplexityError       ← Quá nhiều formula/dependency; metric, value, limit
        ├── FormulaLimitError            ← Iterable quá lớn; size, limit
        ├── FormulaRuntimeError          ← Lỗi eval runtime
        ├── FormulaValidationError       ← Validate formula AST thất bại; errors: List[str]
        ├── FormulaDeterministicError    ← Gọi now()/today() khi deterministic=True
        └── FormulaAssertionError        ← Assertion vi phạm; violations: List[AssertionViolation]
```

### ErrorCode — Mã lỗi machine-readable

| Code                               | Khi nào xảy ra                                          |
| ---------------------------------- | ------------------------------------------------------- |
| `ENGINE.CIRCULAR_DEPENDENCY`       | Formula A → B → A                                       |
| `ENGINE.INVALID_TYPE`              | Kiểu dữ liệu không hợp lệ                              |
| `ENGINE.SYNTAX_ERROR`              | Cú pháp công thức sai                                   |
| `ENGINE.SECURITY_VIOLATION`        | Dùng `import`, `lambda`, `os`, `eval`…                  |
| `ENGINE.MISSING_REQUIRED_INPUT`    | Thiếu input bắt buộc (strict=True)                      |
| `ENGINE.RANGE_MISMATCH`            | `sumif` range và sum_range khác độ dài                  |
| `ENGINE.INDEX_OUT_OF_RANGE`        | `index()` hoặc `choose()` vượt phạm vi                  |
| `ENGINE.DIVISION_BY_ZERO`          | Chia cho 0                                              |
| `ENGINE.SUBSCRIPT_TOO_DEEP`        | `a[b[c[d[...]]]]` lồng sâu quá `max_subscript_depth`   |
| `ENGINE.LITERAL_LIST_TOO_LARGE`    | Literal list `[1,2,...,N]` > `max_iterable_size`        |
| `ENGINE.NON_DETERMINISTIC_IN_FROZEN` | `now()`/`today()` khi `deterministic=True`           |
| `ENGINE.UNKNOWN_FUNCTION`          | Gọi hàm không có trong `runtime_env`                   |
| `ENGINE.UNSUPPORTED_NODE`          | AST node bị cấm                                         |
| `ENGINE.CONTEXT_NOT_INITIALIZED`   | `calculate_incremental()` trước `create_context()`      |
| `ENGINE.STALE_CONTEXT`             | Formula set thay đổi sau khi tạo `IncrementalContext`   |
| `ENGINE.BUDGET_EXCEEDED`           | Vượt `max_operations`                                   |
| `ENGINE.VALIDATION_ERROR`          | `FormulaValidator.validate()` thất bại                  |

```python
from formula_utils import FormulaError, ErrorCode

try:
    engine.calculate(inputs)
except FormulaError as e:
    print(e.code)           # "ENGINE.MISSING_REQUIRED_INPUT"
    print(e.level)          # "ERROR"
    print(e.field_name)     # "NVL"
    print(e.formula)        # "NVL + NC + CPC"
    print(e.context)        # dict biến có sẵn tại thời điểm lỗi
    # Auto-gợi ý tên biến gần đúng nếu NameError
```

---

## 5. FormulaEngine — Tham số khởi tạo đầy đủ

```python
from formula_utils import FormulaEngine, InputField, OutputField, FormulaSetMeta
from datetime import date

engine = FormulaEngine(
    # ════════════════════════════════════════════════════════════
    # BẮT BUỘC
    # ════════════════════════════════════════════════════════════
    formulas = [
        # name: tên biến (dùng trong công thức khác)
        # formula: chuỗi công thức Python-like
        # group (tùy chọn): nhóm công thức
        # bucket (tùy chọn): nhóm output
        {"name": "TONG_CP",  "formula": "NVL + NC + CPC"},
        {"name": "DON_GIA",  "formula": "TONG_CP / SAN_LUONG",
         "bucket": "gia", "group": "gia_thanh"},
        {"name": "GIA_BAN",  "formula": "DON_GIA * (1 + BIEN_LAI)",
         "bucket": "gia", "group": "gia_thanh"},
        {"name": "THUE_VAT", "formula": "GIA_BAN * 10%"},
        {"name": "TONG_TIEN","formula": "GIA_BAN + THUE_VAT"},
    ],

    # ════════════════════════════════════════════════════════════
    # SCHEMA ĐẦU VÀO (tùy chọn — dùng để validate, default values)
    # ════════════════════════════════════════════════════════════
    input_fields = [
        InputField(
            name        = "NVL",
            dtype       = float,   # kiểu Python: float, int, str, bool, list, dict
            required    = True,
            default     = None,    # mặc định nếu required=False
            description = "Chi phí nguyên vật liệu",
        ),
        InputField(name="NC",        dtype=float, required=True),
        InputField(name="CPC",       dtype=float, required=True),
        InputField(name="SAN_LUONG", dtype=float, required=True),
        InputField(name="BIEN_LAI",  dtype=float, required=False, default=0.15),
    ],

    # ════════════════════════════════════════════════════════════
    # SCHEMA ĐẦU RA (tùy chọn — metadata, không validate output)
    # ════════════════════════════════════════════════════════════
    output_fields = [
        OutputField(
            name        = "DON_GIA",
            unit        = "VND/đv",    # đơn vị (metadata)
            bucket      = "gia",       # nhóm (metadata)
            primary     = True,        # output chính
            description = "Đơn giá sản phẩm",
        ),
        OutputField(name="GIA_BAN",   unit="VND/đv", primary=False),
        OutputField(name="TONG_TIEN", unit="VND",    primary=True),
    ],

    # ════════════════════════════════════════════════════════════
    # XỬ LÝ LỖI
    # ════════════════════════════════════════════════════════════
    on_error      = "default",  # "raise" | "null" | "default"
    default_value = 0,          # giá trị khi on_error="default"

    # ════════════════════════════════════════════════════════════
    # GIỚI HẠN & BẢO VỆ
    # ════════════════════════════════════════════════════════════
    max_operations       = None,   # None=vô hạn; VD: 50_000 → bật budget guard
    max_formula_count    = None,   # None=vô hạn; VD: 500 → báo lỗi nếu vượt
    max_dependency_depth = None,   # None=vô hạn; VD: 20  → báo lỗi nếu DAG sâu hơn
    max_iterable_size    = None,   # None=vô hạn; VD: 50_000 → giới hạn list trong formula
    max_subscript_depth  = 5,      # giới hạn a[b[c[...]]] lồng nhau (default 5)

    # ════════════════════════════════════════════════════════════
    # TÍNH NĂNG
    # ════════════════════════════════════════════════════════════
    deterministic    = True,    # True = chặn now()/today() → reproducible (mặc định)
    strict           = False,   # True = raise nếu thiếu required input
    validate_on_init = False,   # True = validate toàn bộ AST ngay khi khởi tạo

    # ════════════════════════════════════════════════════════════
    # HÀM CUSTOM
    # ════════════════════════════════════════════════════════════
    safe_funcs = {
        "round_vnd":  lambda v: round(float(v or 0) / 1000) * 1000,
        "gia_nhap":   lambda ma: db.get_value("Item", ma, "valuation_rate"),
        "ty_gia":     lambda ma_nt, ngay: get_exchange_rate(ma_nt, ngay),
    },

    # ════════════════════════════════════════════════════════════
    # ASSERTIONS — kiểm tra điều kiện sau khi tính
    # ════════════════════════════════════════════════════════════
    assertions = [
        {
            "name"     : "don_gia_duong",
            "expr"     : "DON_GIA > 0",
            "message"  : "Đơn giá phải dương",
            "severity" : "ERROR",     # "ERROR" | "WARNING"
        },
        {
            "name"     : "ty_le_bien_lai",
            "expr"     : "BIEN_LAI >= 0 and BIEN_LAI <= 1",
            "message"  : "Biên lãi phải trong [0, 1]",
            "severity" : "WARNING",
        },
    ],

    # ════════════════════════════════════════════════════════════
    # LÀM TRÒN — áp dụng SAU khi tính xong
    # ════════════════════════════════════════════════════════════
    rounding_policy = {
        "DON_GIA":   {"decimals": 0},    # làm tròn về số nguyên
        "GIA_BAN":   {"decimals": 0},
        "TONG_TIEN": {"decimals": 0},
        "THUE_VAT":  {"decimals": 2},
    },

    # ════════════════════════════════════════════════════════════
    # META — thông tin formula set
    # ════════════════════════════════════════════════════════════
    meta = FormulaSetMeta(
        id             = "bang_gia_sp_v1",
        version        = "1.0.0",
        name           = "Bảng giá sản phẩm",
        description    = "Tính giá thành và giá bán sản phẩm",
        effective_from = date(2025, 1, 1),
        effective_to   = date(2025, 12, 31),
        frozen         = False,   # True = không sửa được
    ),
)
```

### on_error — 3 chế độ xử lý lỗi

| Giá trị     | Khi formula lỗi                          | Khi nào dùng                        |
| ----------- | ---------------------------------------- | ----------------------------------- |
| `"default"` | Trả `default_value` (0), tiếp tục        | Production — không muốn crash       |
| `"null"`    | Trả `None`, tiếp tục                     | Khi cần phân biệt lỗi và giá trị 0 |
| `"raise"`   | Raise `FormulaError` ngay lập tức        | Debug, validate dữ liệu             |

> **v28 FIX 2+3+4**: `max_operations` giờ hoạt động đúng với `"default"`, `"null"` và `recalculate_full()`.

### register_formula() — Thêm công thức vào engine đang chạy

```python
vr = engine.register_formula(
    name         = "PHU_CAP_THANG",
    formula      = "LUONG_CB * 0.3 + PC_CHUC_VU",
    known_names  = {"LUONG_CB", "PC_CHUC_VU"},   # optional, để validate biến
    validate     = True,    # False = bỏ qua validate
)
# Tự rebuild DAG, cập nhật hash
print(vr.ok)            # True
print(vr.normalized)    # formula đã chuẩn hóa
```

### get_metadata() — Xem thông tin engine

```python
meta = engine.get_metadata()
print(meta["engine_version"])       # "28.0.0"
print(meta["formula_count"])        # 5
print(meta["formula_names"])        # ["TONG_CP", "DON_GIA", ...]
print(meta["input_fields"])         # ["NVL", "NC", "CPC", ...]
print(meta["topo_order"])           # thứ tự tính toán đúng
print(meta["dag_depth"])            # 3 — độ sâu phụ thuộc
print(meta["formula_hash"])         # sha256 của toàn bộ formula set
print(meta["budget"])               # max_operations
print(meta["deterministic"])        # True
print(meta["groups"])               # {"gia_thanh": ["DON_GIA", "GIA_BAN", ...]}
print(meta["meta"])                 # FormulaSetMeta dict
```

---

## 6. Cú pháp công thức — Đầy đủ

Engine tự chuẩn hóa công thức 1 pass trước khi parse AST.

```python
# ── Số học ───────────────────────────────────────────────────────────────────
"A + B * C / D"
"A ** 2"
"(A + B) / 2"
"A % B"          # modulo

# ── So sánh Excel-style (auto chuẩn hóa) ─────────────────────────────────────
"A = B"           # → A == B
"A <> B"          # → A != B
"A >= 100"
"A <= B"

# ── Phần trăm (auto chuẩn hóa) ────────────────────────────────────────────────
"GIA_BAN * 10%"   # → GIA_BAN * (10/100)  → GIA_BAN * 0.1
"A * 0.5%"        # → A * 0.005

# ── Điều kiện ─────────────────────────────────────────────────────────────────
"IF(A > 0, A, 0)"
"A if A > 0 else 0"                         # Python ternary
"IFS(KPI>=100, 0.3, KPI>=80, 0.15, True, 0)"
"SWITCH(LOAI, 'A', 10, 'B', 20, 0)"

# ── Hàm viết hoa/thường đều OK ────────────────────────────────────────────────
"SUM(a, b)"     # → sum(a, b)   (chuẩn hóa về tên trong runtime_env)
"IF(...)"       # → IF(...)     (giữ nguyên IF vì có trong runtime_env)
"Min(x, y)"    # → min(x, y)

# ── List comprehension ────────────────────────────────────────────────────────
# Chỉ được dùng BÊN TRONG sum/min/max/any/all/sorted/list/tuple
"sum(r['qty'] * r['price'] for r in items)"
"sum(x for x in vals if x > 0)"
"max(r['score'] for r in nv if r['phong'] = 'IT')"
"any(r['vi_pham'] for r in ho_so)"
"sorted([r['gia'] for r in lich_su], reverse=True)"

# KHÔNG hợp lệ — standalone generator:
# (x for x in lst)         → SecurityViolation
# {k: v for k,v in d}      → SecurityViolation (DictComp bị cấm)

# ── Attribute access — chỉ .get() .keys() .values() .items() .to_dict() ──────
"ds_pc.get('an_trua', 0)"           # ✅
"result.to_dict()"                   # ✅
"obj.format()"                       # ❌ SecurityViolation

# ── Keyword args (len≥3, không bị convert = thành ==) ─────────────────────────
"sorted_array(rows, sort_by='ngay', reverse=True)"   # ✅ sort_by= giữ =
"safe_div(A, B, default=0)"                          # ✅ default= giữ =
"last(rows, sort_by='ngay', value_key='gia')"        # ✅
"vlookup(MA, bang, col=2)"                           # ✅ col= giữ =

# Biến tên ngắn (x, a, n, lo, hi, dt…) dùng = vẫn bị convert thành ==:
"x = 5"    # → x == 5  (so sánh, không phải gán — công thức là expression, không statement)

# ── Logic keywords trong function call ────────────────────────────────────────
"and_(A > 0, B > 0)"   # and_() thay vì and() vì 'and' là keyword Python
"or_(LOAI='A', LOAI='B')"
"not_(IS_VOID)"

# ── Chuỗi ─────────────────────────────────────────────────────────────────────
"concat(MA, '-', str(NAM))"
"upper(TEN)"
"'prefix_' + lower(MA_SP)"

# ── Dict/List literal ─────────────────────────────────────────────────────────
"{'A': 10, 'B': 20}.get(LOAI, 0)"   # ✅ (dict literal + .get() whitelist)
"[1, 2, 3]"                          # ✅ list literal
```

### Những gì KHÔNG được phép trong formula

```python
# ❌ Import
"import os"
"from datetime import date"

# ❌ Gán
"A = 5"                  # Assignment → SecurityViolation (Assign node)
"A += 1"                 # AugAssign
"A: int = 5"             # AnnAssign
"B := A + 1"             # NamedExpr (walrus)

# ❌ Định nghĩa hàm/class
"lambda x: x + 1"
"def f(): ..."
"class C: ..."

# ❌ Tên nguy hiểm
"os.system('rm -rf /')"
"eval('...')"
"__import__('os')"
"globals()"
"locals()"

# ❌ Generator standalone
"(x for x in lst)"      # phải dùng: list(x for x in lst) hoặc sum(...)

# ❌ Dict/Set comprehension
"{k: v for k,v in d.items()}"   # DictComp bị cấm
"{x for x in lst}"              # SetComp bị cấm
```

---

## 7. BASE_FUNCS — 80+ Hàm tích hợp (đầy đủ tham số)

### 7.1 Toán học

| Hàm & Tham số đầy đủ                    | Mô tả                                | Ví dụ                                  |
| --------------------------------------- | ------------------------------------ | -------------------------------------- |
| `abs(x)`                                | Giá trị tuyệt đối                    | `abs(-5)` → `5`                        |
| `round(x, n=0)`                         | Làm tròn n chữ số                    | `round(3.456, 2)` → `3.46`             |
| `roundup(x, d=0)`                       | Làm tròn lên                         | `roundup(3.21, 1)` → `3.3`             |
| `rounddown(x, d=0)`                     | Làm tròn xuống                       | `rounddown(3.99, 1)` → `3.9`           |
| `ceil(x)`                               | Làm tròn lên số nguyên               | `ceil(3.1)` → `4`                      |
| `floor(x)`                              | Làm tròn xuống số nguyên             | `floor(3.9)` → `3`                     |
| `sqrt(x)`                               | Căn bậc hai                          | `sqrt(9)` → `3.0`                      |
| `power(x, n)`                           | Lũy thừa x^n                         | `power(2, 10)` → `1024.0`              |
| `ln(x)`                                 | Logarithm tự nhiên (base e)          | `ln(2.718)` ≈ `1.0`                    |
| `log(x, base=e)`                        | Logarithm cơ số tùy chọn            | `log(100, 10)` → `2.0`                 |
| `log10(x)`                              | Logarithm cơ số 10                   | `log10(1000)` → `3.0`                  |
| `exp(x)`                                | e mũ x                               | `exp(1)` ≈ `2.718`                     |
| `safe_div(a, b, default=0.0)`           | Chia an toàn, b=0 → default          | `safe_div(10, 0)` → `0.0`              |
| `clamp(x, lo, hi)`                      | Giới hạn x trong [lo, hi]            | `clamp(150, 0, 100)` → `100`           |
| `percent_of(part, total, default=0.0)`  | part/total×100, tránh ZeroDivision   | `percent_of(30, 200)` → `15.0`         |
| `pi`                                    | π ≈ 3.14159                          | `2 * pi * R`                           |
| `sin(x)` / `cos(x)` / `tan(x)`          | Lượng giác (radian)                  | `sin(pi/2)` → `1.0`                    |
| `asin(x)` / `acos(x)` / `atan(x)`       | Lượng giác ngược                     | `degrees(asin(1.0))` → `90.0`          |
| `atan2(y, x)`                           | Góc của vector (y,x)                 | `degrees(atan2(1,1))` → `45.0`         |
| `degrees(x)`                            | Radian → độ                          | `degrees(pi)` → `180.0`                |
| `radians(x)`                            | Độ → radian                          | `radians(180)` → `3.14159`             |

> `math` module object **không** được expose để phòng DoS (`math.factorial(99999)`).

### 7.2 Tổng hợp

| Hàm & Tham số đầy đủ        | Mô tả                                                        | Ví dụ                                            |
| --------------------------- | ------------------------------------------------------------ | ------------------------------------------------ |
| `sum(*args, key=None)`      | Tổng — list, *args, dict.values(), generator, list[dict]    | `sum(rows, key='amount')`                        |
| `min(*args, key=None)`      | Giá trị nhỏ nhất                                            | `min(5,3,8)` → `3`                               |
| `max(*args, key=None)`      | Giá trị lớn nhất                                            | `max(rows, key='score')`                         |
| `average(*args, key=None)`  | Trung bình — bỏ qua None và non-numeric                     | `average([10,20,30])` → `20.0`                   |
| `count(*args, key=None)`    | Đếm phần tử không None/rỗng                                 | `count(rows, key='value')`                       |
| `counta(*args, key=None)`   | Alias của `count`                                            | `counta(lst)`                                    |
| `countnum(data)`            | Đếm phần tử là số (int/float)                               | `countnum([1,'a',None,2])` → `2`                 |

**Lưu ý `key` parameter với `list[dict]`**:

```python
rows = [
    {"sp": "A", "sl": 100, "dg": 50_000},
    {"sp": "B", "sl": 200, "dg": 30_000},
]
sum(rows, key='sl')      # → 300
average(rows, key='dg')  # → 40_000.0
min(rows, key='dg')      # → 30_000
max(rows, key='sl')      # → 200
count(rows, key='sl')    # → 2  (không None)

# sum với generator — phổ biến nhất
"sum(r['sl'] * r['dg'] for r in rows)"   # → 100×50_000 + 200×30_000 = 11_000_000
```

### 7.3 Logic & Điều kiện

| Hàm & Tham số đầy đủ                   | Mô tả                                                   | Ví dụ                                          |
| -------------------------------------- | ------------------------------------------------------- | ---------------------------------------------- |
| `IF(cond, true_val, false_val)`        | Điều kiện đơn — Excel-style                             | `IF(KPI >= 100, 1_000_000, 0)`                 |
| `IIF(condition, true_val, false_val)`  | Alias của IF                                             | `IIF(A > 0, A, 0)`                             |
| `IFS(c1, v1, c2, v2, ...)`             | Multi-condition — trả v đầu tiên có c=True              | `IFS(DIEM>=9,'A', DIEM>=7,'B', True,'C')`      |
| `SWITCH(expr, v1, r1, ..., default)`   | Switch-case; default = arg cuối nếu lẻ                  | `SWITCH(LOAI,'A',10,'B',20,0)`                 |
| `coalesce(a, b, c, ...)`               | Giá trị không-None, không-rỗng đầu tiên                 | `coalesce(GIA_NHK, GIA_SD, 0)`                 |
| `is_blank(x)`                          | True nếu x là None, `''`, 0, hoặc 0.0                   | `is_blank(GIA_VON)` → True nếu GIA_VON=0       |
| `not_blank(x)`                         | Ngược `is_blank`                                         | `not_blank(MA_HANG)`                           |
| `between(x, lo, hi)`                   | `lo <= x <= hi` — True/False                             | `between(DIEM, 5, 10)`                         |
| `isnumber(x)`                          | True nếu int hoặc float                                  | `isnumber(GIA_TRI)`                            |
| `and_(*args)`                          | `all(args)` — dùng vì `and` là keyword Python            | `and_(A>0, B>0, C>0)`                          |
| `or_(*args)`                           | `any(args)`                                              | `or_(LOAI='A', LOAI='B')`                      |
| `not_(x)`                              | `not x`                                                  | `not_(IS_VOID)`                                |

```python
# IFS — thuế TNCN bậc lũy tiến
{"name": "THUE_TNCN", "formula": """
IFS(
    TNT <= 5_000_000,   TNT * 5%,
    TNT <= 10_000_000,  TNT * 10% - 250_000,
    TNT <= 18_000_000,  TNT * 15% - 750_000,
    TNT <= 32_000_000,  TNT * 20% - 1_650_000,
    TNT <= 52_000_000,  TNT * 25% - 3_250_000,
    TNT <= 80_000_000,  TNT * 30% - 5_850_000,
    True,               TNT * 35% - 9_850_000
)
"""}

# SWITCH — hệ số lương theo hạng nhân viên
{"name": "HE_SO_PC", "formula": "SWITCH(HANG_NV, 'A', 1.5, 'B', 1.2, 'C', 1.0, 0.8)"}
```

### 7.4 Tổng hợp có điều kiện

| Hàm & Tham số đầy đủ                                             | Mô tả                       |
| ---------------------------------------------------------------- | --------------------------- |
| `sumif(range_vals, criteria, sum_range=None, key=None)`          | Tổng theo 1 điều kiện       |
| `sumifs(sum_range, *criteria_pairs, key=None, **kwargs)`         | Tổng nhiều điều kiện        |
| `countif(range_vals, criteria, key=None)`                        | Đếm theo 1 điều kiện        |
| `countifs(*criteria_pairs, **kwargs)`                            | Đếm nhiều điều kiện         |
| `averageif(range_vals, criteria, average_range=None, key=None)`  | Trung bình theo điều kiện   |

**Cú pháp criteria** (giống Excel):

| Criteria               | Ý nghĩa                         |
| ---------------------- | ------------------------------- |
| `">100"`               | lớn hơn 100                     |
| `">=100"`              | lớn hơn hoặc bằng 100           |
| `"<50"`                | nhỏ hơn 50                      |
| `"<>0"` hoặc `"!=0"`   | khác 0                          |
| `"=SP_A"` hoặc `"SP_A"` | bằng "SP_A"                  |
| `"*SP*"`               | wildcard — chứa "SP"            |
| `100` (số)             | bằng 100                        |
| `None`                 | là None                         |

```python
rows = [
    {"phong": "IT",  "loai": "CT", "luong": 20_000_000},
    {"phong": "IT",  "loai": "HĐ", "luong": 15_000_000},
    {"phong": "KT",  "loai": "CT", "luong": 18_000_000},
    {"phong": "KT",  "loai": "CT", "luong": 22_000_000},
]

# Cú pháp 1: key=(crit_key, sum_key) — cùng dict, khác field
sumif(rows, "IT", key=("phong", "luong"))          # → 35_000_000

# Cú pháp 2: sumifs với list[dict] + kwargs
sumifs(rows, "phong", "KT", "loai", "CT", key="luong")  # → 40_000_000
# Hoặc kwargs style:
sumifs(rows, key="luong", phong="KT", loai="CT")   # → 40_000_000

# Đếm
countif(rows, ">18000000", key="luong")             # → 2
countifs(rows, phong="IT", loai="CT")               # → 1

# averageif
averageif(rows, "IT", key=("phong", "luong"))       # → 17_500_000

# ── Cú pháp Excel thuần (2 list riêng) ─────────────────────────────────────
phong_list = ["IT",  "IT",  "KT",  "KT"]
luong_list = [20e6, 15e6, 18e6, 22e6]
sumif(phong_list, "IT", sum_range=luong_list)       # → 35_000_000
```

### 7.5 Array / Collection

| Hàm & Tham số đầy đủ                                                                                                                                                   | Mô tả                             |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| `filter_array(data, operator=None, threshold=None, key=None, value=None)`                                                                                              | Lọc list theo điều kiện           |
| `sorted_array(data, key=None, reverse=False)` / `sort(data, key=None, reverse=False)`                                                                                  | Sắp xếp                           |
| `map_key(rows, key)`                                                                                                                                                   | Lấy list 1 field từ list[dict]    |
| `group_sum(rows, group_key, sum_key)`                                                                                                                                  | Tổng theo nhóm → dict             |
| `group_count(rows, group_key)`                                                                                                                                         | Đếm theo nhóm → dict              |
| `group_avg(rows, group_key, avg_key)`                                                                                                                                  | Trung bình theo nhóm → dict       |
| `flatten(data)`                                                                                                                                                        | Làm phẳng list lồng nhau          |
| `unique(iterable, key=None)`                                                                                                                                           | Loại bỏ trùng lặp                 |
| `count_unique(data, key=None)`                                                                                                                                         | Đếm unique                        |
| `unique_sum(rows, key_index, value_index)`                                                                                                                             | Tổng theo unique key (list[list]) |
| `unique_key_sum_by_type(items, type_key, key_index, value_key, target, trace_mode=False)` | Tổng unique key theo loại         |
| `sum_by_type(items, type_key, value_key, target, trace_mode=False)`                      | Tổng theo loại (list[list])       |
| `last(data, sort_by=None, n=1, reverse=True, value_key=None, group_by=None, default=None, missing_value=None, error_on_missing_sort_key=False, preserve_order=False)` | Giá trị mới nhất / top N          |
| `first(data, sort_by=None, n=1, value_key=None, default=None, **kwargs)`                                                                                               | Giá trị cũ nhất / bottom N        |
| `nth(data, n, sort_by=None, reverse=True, value_key=None, default=None, **kwargs)`                                                                                     | Phần tử thứ n                     |
| `zip(*lists)`                                                                                                                                                          | Ghép lists — trả `list[tuple]`    |
| `index(array, row_num, col_num=0)`                                                                                                                                     | Phần tử thứ row_num (1-based)     |
| `match(lookup_value, lookup_array, match_type=1)`                                                                                                                      | Vị trí của giá trị (1-based)      |
| `choose(index_num, *values)`                                                                                                                                           | Chọn theo index (1-based)         |
| `sum_dict(d)`                                                                                                                                                          | Tổng values trong dict            |

**Chi tiết `filter_array`**:

```python
rows = [
    {"loai": "A", "so_luong": 150, "gia": 10_000},
    {"loai": "B", "so_luong": 80,  "gia": 20_000},
    {"loai": "A", "so_luong": 200, "gia": 15_000},
]

# Chế độ key=value (exact match)
filter_array(rows, key="loai", value="A")
# → [row1, row3]

# Chế độ operator+threshold+key (numeric)
filter_array(rows, ">", 100, key="so_luong")
# → [row1, row3]  (so_luong > 100)

# Chế độ operator không có key (list số)
filter_array([10, 5, 20, 3], ">=", 10)
# → [10, 20]
```

**Chi tiết `last` — hàm mạnh nhất**:

```python
lich_su_gia = [
    {"ma_sp": "A", "ngay": "2025-01-01", "gia": 100_000},
    {"ma_sp": "A", "ngay": "2025-03-15", "gia": 110_000},
    {"ma_sp": "B", "ngay": "2025-02-10", "gia": 200_000},
    {"ma_sp": "B", "ngay": "2025-04-01", "gia": 190_000},
]

# Giá mới nhất của SP A
last(lich_su_gia, sort_by="ngay", value_key="gia",
     filter_array=None)    # còn phải filter trước
# Tốt hơn:
data_a = filter_array(lich_su_gia, key="ma_sp", value="A")
last(data_a, sort_by="ngay", value_key="gia")   # → 110_000

# Lấy top 2 mới nhất (n=2)
last(lich_su_gia, sort_by="ngay", n=2, value_key="gia")
# → [110_000, 200_000]  (list khi n>1)

# Giá mới nhất THEO TỪNG SẢN PHẨM (group_by)
last(lich_su_gia, sort_by="ngay", group_by="ma_sp", value_key="gia")
# → {"A": 110_000, "B": 190_000}

# Plain list — lấy n phần tử cuối, giữ thứ tự gốc
last([3, 1, 4, 1, 5], n=2, preserve_order=True)
# → [1, 5]  (2 phần tử cuối)
last([3, 1, 4, 1, 5], n=2, preserve_order=False)
# → [4, 5]  (sort rồi lấy top 2)
```

**Chi tiết `match`**:

| `match_type` | Ý nghĩa                                       |
| ------------ | --------------------------------------------- |
| `0`          | Tìm chính xác — raise nếu không tìm thấy      |
| `1` (mặc định) | Tìm vị trí ≤ lookup_value (array tăng dần) |
| `-1`         | Tìm vị trí ≥ lookup_value (array giảm dần)   |

### 7.6 Lookup

| Hàm & Tham số đầy đủ                                                 | Mô tả                              | Ví dụ                                    |
| -------------------------------------------------------------------- | ---------------------------------- | ---------------------------------------- |
| `vlookup(key, table, col=1, default=0)`                              | Tra cứu dọc — list[list] hoặc dict | `vlookup("SP_A", bang_gia, 3)`           |
| `xlookup(lookup_value, lookup_array, return_array, if_not_found=0)`  | Tra cứu linh hoạt                  | `xlookup("H002", ma_list, gia_list, 0)`  |

```python
# vlookup với list of lists
bang_gia = [
    ["SP_A", "Sản phẩm A", 100_000],
    ["SP_B", "Sản phẩm B", 150_000],
    ["SP_C", "Sản phẩm C", 200_000],
]
vlookup("SP_B", bang_gia, 3)          # → 150_000  (col=3: giá)
vlookup("SP_B", bang_gia, 2)          # → "Sản phẩm B"  (col=2: tên)
vlookup("SP_X", bang_gia, 3, -1)      # → -1  (không tìm thấy)

# vlookup với dict
gia_dict = {"SP_A": 100_000, "SP_B": 150_000}
vlookup("SP_A", gia_dict)             # → 100_000  (col=1 với dict scalar)

# xlookup
ma_hang = ["H001", "H002", "H003"]
gia_nhap = [50_000, 75_000, 60_000]
xlookup("H002", ma_hang, gia_nhap, 0) # → 75_000

# xlookup với dict
xlookup("SP_A", {"SP_A": 100, "SP_B": 200}, {}, 0)  # dict mode: lookup_array=dict
```

### 7.7 Chuỗi

| Hàm & Tham số đầy đủ                   | Mô tả                                         | Ví dụ                                               |
| -------------------------------------- | --------------------------------------------- | --------------------------------------------------- |
| `concat(*args)`                         | Nối chuỗi, bỏ qua None                         | `concat('HD-', NAM, '-', STT)`                      |
| `concatenate(*args)`                    | Alias concat (Excel compat)                    | `concatenate(MA, '-', TEN)`                         |
| `text_join(delimiter, *vals)`           | Nối với dấu phân cách                          | `text_join('/', NAM, THANG, NGAY)`                  |
| `textjoin(delimiter, ignore_empty, *t)` | Nối với tùy chọn bỏ empty                     | `textjoin(', ', True, A, B, C)`                     |
| `left(s, n=1)`                          | n ký tự đầu                                   | `left('HD-2025', 2)` → `'HD'`                       |
| `right(s, n=1)`                         | n ký tự cuối                                   | `right('HD-001', 3)` → `'001'`                      |
| `mid(s, start, length)`                 | Cắt giữa (1-based start)                       | `mid('HD-2025-001', 4, 4)` → `'2025'`               |
| `upper(s)`                              | Viết hoa                                       | `upper('abc')` → `'ABC'`                            |
| `lower(s)`                              | Viết thường                                    | `lower('ABC')` → `'abc'`                            |
| `trim(s)`                               | Xóa khoảng trắng 2 đầu                         | `trim('  abc  ')` → `'abc'`                         |
| `replace(s, old, new)`                  | Thay thế tất cả                                | `replace('a-b-c', '-', '/')` → `'a/b/c'`            |
| `substitute(s, old, new, nth=None)`     | Thay thế lần thứ nth (None=tất cả)             | `substitute('a-b-a', 'a', 'x', 1)` → `'x-b-a'`     |
| `find(search, text, start=1)`           | Vị trí chuỗi con (1-based, 0 nếu không có)    | `find('2025', 'HD-2025-001')` → `4`                 |
| `len(s)` / `len_text(s)` / `length(s)` | Độ dài chuỗi                                   | `len('Hello')` → `5`                               |
| `to_number(x, default=0.0)`             | Parse số từ chuỗi, bỏ ký tự không phải số     | `to_number('1,234.5')` → `1234.5`                   |
| `safe_str(x)`                           | Chuyển sang chuỗi, None → `''`                 | `safe_str(None)` → `''`                             |
| `str(x)`                                | Python str()                                   | `str(12345)` → `'12345'`                            |
| `int(x)`                                | Python int()                                   | `int(3.7)` → `3`                                    |
| `float(x)`                              | Python float()                                 | `float('3.14')` → `3.14`                            |
| `bool(x)`                               | Python bool()                                  | `bool(0)` → `False`                                 |

### 7.8 Ngày tháng

| Hàm & Tham số đầy đủ                       | Mô tả                                                                    | Ví dụ                                                |
| ------------------------------------------ | ------------------------------------------------------------------------ | ---------------------------------------------------- |
| `now()`                                     | Datetime UTC hiện tại _(chặn khi `deterministic=True`)_                  | cần `deterministic=False`                            |
| `today()`                                   | Date hôm nay _(chặn khi `deterministic=True`)_                           | cần `deterministic=False`                            |
| `year(dt)`                                  | Năm — nhận `date`, `datetime`, ISO string                                | `year('2025-07-15')` → `2025`                        |
| `month(dt)`                                 | Tháng 1-12                                                               | `month('2025-07-15')` → `7`                          |
| `day(dt)`                                   | Ngày 1-31                                                                | `day('2025-07-15')` → `15`                           |
| `quarter(dt)`                               | Quý 1-4                                                                  | `quarter('2025-07-15')` → `3`                        |
| `date_diff(d1, d2, unit='days')`            | Khoảng cách. unit: `'days'`/`'months'`/`'years'`/`'hours'`/`'seconds'`  | `date_diff(NGAY_KT, NGAY_BD, 'months')`              |
| `date_add(dt, days=0, months=0, years=0)`   | Cộng thêm — xử lý cuối tháng đúng (31/1+1m=28/2)                         | `date_add('2025-01-31', months=1)` → `date(2025,2,28)` |
| `date_format(dt, fmt='%d/%m/%Y')`           | Định dạng ngày thành chuỗi                                                | `date_format(NGAY, '%Y-%m')`                         |
| `workdays(d1, d2)`                          | Số ngày làm việc T2–T6 giữa 2 ngày                                        | `workdays('2025-01-01', '2025-01-31')` → `23`        |

**Định dạng ngày được chấp nhận**:

```python
# Các format tự động nhận dạng:
"2025-01-15"          # ISO
"15/01/2025"          # VN style
"2025/01/15"
"2025-01-15T08:30:00" # datetime
"2025-01-15 08:30:00"
```

### 7.9 TimeBucket trong formula

| Hàm                                                        | Mô tả                                         | Ví dụ                                            |
| ---------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------ |
| `time_buckets(year, bucket_type='all', label_format=None)` | Danh sách kỳ của năm                          | `time_buckets(2025, 'quarter')`                  |
| `get_period(period_type, index, year, label_format=None)`  | TimeBucket theo loại và index                 | `get_period('quarter', 3, 2025)`                 |
| `get_bucket_label(dt, bucket_type, label_type='short')`    | Label kỳ chứa ngày. label_type: short/full/name | `get_bucket_label(NGAY, 'quarter')` → `'Q3'`   |
| `in_time_bucket(dt, bucket)`                               | True nếu dt nằm trong bucket                  | `in_time_bucket(NGAY_GHI, BUCKET_Q3)`           |
| `period_offset(bucket, offset)`                            | Dịch kỳ ±n                                    | `period_offset(KY_HIEN_TAI, -1)`                |
| `same_period_last_year(bucket, years_back=1)`              | Cùng kỳ năm trước                             | `same_period_last_year(KY)`                      |
| `year_buckets(year=None, offset=0, types=None)`            | Tất cả kỳ của năm, offset để lấy năm khác     | `year_buckets(offset=-1)` # năm ngoái            |
| `TB_FORMAT`                                                | Dict các preset label format                  | `TB_FORMAT['short']` → `'{type_short}{index}'`  |

### 7.10 Graph & Allocation trong formula string

| Hàm                                                              | Mô tả                         |
| ---------------------------------------------------------------- | ----------------------------- |
| `solve_linear_on_graph(...)`                                     | Giải `(I-A)x=b` trên graph    |
| `SccLinearSolver`                                                | Class solver                  |
| `topo_sort_data(items, id_key, deps_list_key, dep_id_key)`       | DAG sort (nested deps)        |
| `topo_sort_flat(items, id_key, dep_ids_key)`                     | DAG sort (flat dep list)      |
| `scc_topo_sort_data(items, id_key, deps_list_key, dep_id_key)`   | SCC sort (nested deps)        |
| `scc_topo_sort_flat(items, id_key, dep_ids_key)`                 | SCC sort (flat dep list)      |
| `allocate(sources, targets, method, ...)`                        | Phân bổ chi phí → dict        |
| `AllocationEngine`                                               | Class engine phân bổ          |

### 7.11 Thêm hàm custom

```python
from formula_utils import BASE_FUNCS, FormulaEngine

# ✅ Cách 1: Thêm vào BASE_FUNCS — ảnh hưởng tất cả engine mới khởi tạo sau đó
BASE_FUNCS["round_vnd"]    = lambda v: round(float(v or 0) / 1000) * 1000
BASE_FUNCS["to_int"]       = lambda v: int(float(v or 0))
BASE_FUNCS["vat_10"]       = lambda v: float(v or 0) * 0.1

# ✅ Cách 2: safe_funcs khi khởi tạo — chỉ ảnh hưởng engine này
engine = FormulaEngine(
    formulas=[...],
    safe_funcs={
        "gia_nhap": lambda ma: db_lookup(ma),
        "ty_gia":   lambda ma_nt, ngay: get_rate(ma_nt, ngay),
    }
)

# ❌ KHÔNG expose module, object nguy hiểm
# BASE_FUNCS["db"]   = frappe.db       # SQL injection
# BASE_FUNCS["math"] = math            # DoS: math.factorial(9999)
# BASE_FUNCS["os"]   = os              # shell execution
```

---

## 8. calculate() và các biến thể

```python
# ── Cơ bản ───────────────────────────────────────────────────────────────────
result = engine.calculate(inputs)
# → {tên_formula: value, ...}  — CHỈ trả formulas, không trả inputs

# ── Strict mode — validate input tại runtime ─────────────────────────────────
result = engine.calculate(inputs, strict=True)
# Raise FormulaError(MISSING_REQUIRED_INPUT) nếu thiếu required input

# ── An toàn — không bao giờ raise ────────────────────────────────────────────
result = engine.calculate_safe(inputs)
# Luôn trả dict kể cả khi có lỗi:
# {
#   "TONG_CP": 0,         ← default_value nếu lỗi
#   "DON_GIA": 80_000,    ← bình thường
#   "_ok":         True/False,
#   "_error":      "chi tiết lỗi nếu có",
#   "_error_type": "formula_error" | "budget_exceeded" | "runtime_error" | ...
# }

# ── Batch ─────────────────────────────────────────────────────────────────────
rows = [{"NVL": 5e6, "NC": 2e6, "CPC": 1e6, "SAN_LUONG": 100},
        {"NVL": 6e6, "NC": 2.5e6, "CPC": 1.2e6, "SAN_LUONG": 120}]
results = engine.calculate_batch(rows)
# → [{"TONG_CP": 8e6, "DON_GIA": 80_000, ...}, ...]

# ── Batch với memory — carry-forward giữa các rows ───────────────────────────
# Ứng dụng: sổ kế toán, tồn kho lũy kế, dư nợ tích lũy
results = engine.calculate_batch_with_memory(
    rows           = data_rows,
    memory_keys    = ["SO_DU_DAU", "LUY_KE"],  # keys cần carry forward
    initial_memory = {"SO_DU_DAU": 0, "LUY_KE": 0},
)
# Mỗi row nhận thêm: prev_SO_DU_DAU, prev_LUY_KE từ row trước
# result có thêm 'row_index'

# ── Async ─────────────────────────────────────────────────────────────────────
result = await engine.calculate_async(inputs)

# ── Cache engine — tái dùng bytecode giữa requests ───────────────────────────
# (tiết kiệm thời gian parse/compile khi restart server)
cache_data = engine.to_cache_dict()
# → dict chứa: formulas, topo_order, compiled bytecodes, settings

engine2 = FormulaEngine.from_cache_dict(cache_data)
# Validate version và Python version tự động
# Raise nếu cache_version không khớp "v17"
# Raise nếu Python version khác (bytecode không portable)

# Override settings khi restore:
engine2 = FormulaEngine.from_cache_dict(cache_data,
    max_operations=100_000,
    on_error="null",
)

# diff_inputs — tìm inputs thay đổi
changed_keys = engine.diff_inputs(old_inputs, new_inputs)
# → set of field names đã thay đổi

changed_detail = engine.diff_inputs_values(old_inputs, new_inputs)
# → {"NVL": (5_000_000, 6_000_000), "BIEN_LAI": (0.15, 0.20)}

# get_affected_nodes — biết node nào bị ảnh hưởng khi inputs thay đổi
affected = engine.get_affected_nodes({"NVL", "NC"})
# → set of formula names cần recalculate
```

---

## 9. IncrementalContext — Tính toán tăng tiến

Dùng khi người dùng sửa 1-2 field: **chỉ eval đúng các công thức bị ảnh hưởng**, bỏ qua nhánh độc lập → tiết kiệm CPU đáng kể cho DAG lớn.

```python
# ════════════════════════════════════════════════════════════════════
# Bước 1: Tạo context — full calc lần đầu
# ════════════════════════════════════════════════════════════════════
ctx = engine.create_context(
    initial_inputs = {"NVL": 5_000_000, "NC": 2_000_000,
                      "CPC": 1_000_000, "SAN_LUONG": 100},
    doc_id         = "BG-2025-001",   # tùy chọn — để trace
    strict         = None,             # None = dùng engine.strict
)
print(ctx.outputs["DON_GIA"])    # 80_000
print(ctx.initialized)            # True
print(ctx.doc_id)                 # "BG-2025-001"
print(ctx.inputs)                 # snapshot inputs hiện tại
print(ctx.outputs)                # snapshot outputs hiện tại

# ════════════════════════════════════════════════════════════════════
# Bước 2: Sửa 1 field — chỉ recalc chain phụ thuộc
# ════════════════════════════════════════════════════════════════════
result = engine.calculate_incremental(
    ictx           = ctx,
    changed_inputs = {"NVL": 6_000_000},
    strict         = None,
    return_stats   = False,
)
print(result["DON_GIA"])    # 90_000

# ── Với stats ─────────────────────────────────────────────────────
result, stats = engine.calculate_incremental(
    ctx, {"NVL": 7_000_000}, return_stats=True
)
# IncrementalStats:
print(stats.total_nodes)         # 5 — tổng formula nodes
print(stats.recalculated_nodes)  # 3 — chỉ phụ thuộc NVL
print(stats.skipped_nodes)       # 2 — nhánh không liên quan
print(stats.skip_ratio)          # 0.4 = 40% tiết kiệm
print(stats.elapsed_ms)          # 0.08 ms
print(stats.changed_inputs)      # 1 — NVL thay đổi
print(stats.affected_nodes)      # 3 — công thức bị ảnh hưởng
print(str(stats))                # human-readable summary

# ════════════════════════════════════════════════════════════════════
# Recalculate toàn bộ — khi muốn reset với inputs mới hoàn toàn
# ════════════════════════════════════════════════════════════════════
engine.recalculate_full(ctx, new_inputs={"NVL": 8_000_000, "NC": 2_500_000,
                                          "CPC": 1_200_000, "SAN_LUONG": 120})
# Hoặc giữ inputs cũ, chỉ recalc lại tất cả:
engine.recalculate_full(ctx, new_inputs=None)

# ════════════════════════════════════════════════════════════════════
# Patch thủ công — không trigger recalc ngay
# ════════════════════════════════════════════════════════════════════
ctx.patch("BIEN_LAI", 0.20)   # chỉ cập nhật giá trị trong ctx
# sau đó gọi calculate_incremental để apply

# ════════════════════════════════════════════════════════════════════
# Serialize → Redis / Frappe cache → Khôi phục
# ════════════════════════════════════════════════════════════════════
import json

# Lưu
ctx_dict = ctx.to_dict()
# {
#   "engine_hash": "abc123...",   ← detect stale context
#   "inputs": {...},
#   "outputs": {...},
#   "dirty": [],
#   "initialized": True,
#   "created_at": "2025-...",
#   "last_updated_at": "2025-...",
#   "doc_id": "BG-2025-001"
# }
frappe.cache().set_value(f"eng_ctx_{doc.name}", json.dumps(ctx_dict), 3600)

# Khôi phục
from formula_utils import IncrementalContext
raw = json.loads(frappe.cache().get_value(f"eng_ctx_{doc.name}"))
ctx2 = IncrementalContext.from_dict(engine, raw)
# Tự validate engine_hash — raise STALE_CONTEXT nếu formula set thay đổi

# Tiếp tục sử dụng
result = engine.calculate_incremental(ctx2, {"SAN_LUONG": 150})
```

---

## 10. Explain API — Giải thích chuỗi tính toán

```python
# ════════════════════════════════════════════════════════════════════
# explain() — 1 field
# ════════════════════════════════════════════════════════════════════
expl = engine.explain("GIA_BAN", inputs)
# → ExplainResult

print(expl.field)         # "GIA_BAN"
print(expl.value)         # 92_000
print(expl.inputs_used)   # {"NVL": 5_000_000, "NC": 2_000_000, ...}

# Cây giải thích dạng text
print(expl.to_text())
# Giải thích: GIA_BAN = 92000
#
# Inputs sử dụng:
#   BIEN_LAI    = 0.15
#   CPC         = 1000000
#   NC          = 2000000
#   NVL         = 5000000
#   SAN_LUONG   = 100
#
# Chuỗi tính toán:
#   TONG_CP = NVL + NC + CPC  →  8000000  (dùng: CPC=1000000, NC=2000000, NVL=5000000)
#     DON_GIA = TONG_CP / SAN_LUONG  →  80000  (dùng: SAN_LUONG=100, TONG_CP=8000000)
#       GIA_BAN = DON_GIA * (1 + BIEN_LAI)  →  92000

# Chi tiết từng bước (ExplainStep)
for step in expl.steps:
    print(f"depth={step.depth}  {step.name} = {step.formula}")
    print(f"  → value: {step.value}")
    print(f"  → deps: {step.deps}")     # {dep_name: dep_value}
    print(f"  → is_root: {step.is_root}")

# JSON-safe
import json
data = expl.to_dict()
# {
#   "field": "GIA_BAN",
#   "value": 92000,
#   "inputs_used": {...},
#   "steps": [
#     {"name": "TONG_CP", "formula": "...", "value": 8000000,
#      "deps": {...}, "depth": 2, "is_root": False},
#     ...
#   ]
# }
json.dumps(data, ensure_ascii=False)

# ════════════════════════════════════════════════════════════════════
# explain_all() — tất cả fields (v28 FIX 1: không còn TypeError)
# ════════════════════════════════════════════════════════════════════
all_explains = engine.explain_all(inputs)
# → Dict[str, ExplainResult]

for field_name, e in all_explains.items():
    print(f"{field_name} = {e.value}")
    # e.field, e.value, e.steps, e.inputs_used đều đúng
```

---

## 11. Multi-Scenario — So sánh phương án

```python
# ════════════════════════════════════════════════════════════════════
# calculate_scenarios — chỉ tính, không so sánh
# ════════════════════════════════════════════════════════════════════
all_results = engine.calculate_scenarios(
    scenarios = {
        "Gốc"     : base_inputs,
        "PA_NVL"  : {**base_inputs, "NVL": base_inputs["NVL"] * 1.1},
        "PA_SL"   : {**base_inputs, "SAN_LUONG": base_inputs["SAN_LUONG"] * 1.2},
        "PA_Combo": {**base_inputs,
                     "NVL": base_inputs["NVL"] * 1.1,
                     "SAN_LUONG": base_inputs["SAN_LUONG"] * 1.2},
    },
    strict = None,
)
# → {"Gốc": {"TONG_CP": ..., "DON_GIA": ..., ...}, "PA_NVL": {...}, ...}

# ════════════════════════════════════════════════════════════════════
# compare_scenarios — tính + so sánh + delta
# ════════════════════════════════════════════════════════════════════
cmp = engine.compare_scenarios(
    scenarios     = { "Gốc": base_inputs, "PA_NVL": pa_nvl_inputs, "PA_SL": pa_sl_inputs },
    fields        = ["DON_GIA", "GIA_BAN", "THUE_VAT"],  # None = tất cả
    base_scenario = "Gốc",    # None = scenario đầu tiên
    strict        = None,
)
# → ScenarioComparison

# ── Bảng text ──────────────────────────────────────────────────────
print(cmp.to_table())
# Field             Gốc             PA_NVL          PA_SL
# ------------------------------------------------------------------
# DON_GIA           80,000.00       86,000.00       66,667.00
# GIA_BAN           92,000.00       98,900.00       76,667.00
# THUE_VAT           9,200.00        9,890.00        7,667.00
#
# Delta so với 'Gốc':
# DON_GIA                           +6,000.00 (+7.5%)  -13,333.00 (-16.7%)
# GIA_BAN                           +6,900.00 (+7.5%)  -15,333.00 (-16.7%)

# ── Truy cập kết quả ───────────────────────────────────────────────
cmp.scenarios            # ["Gốc", "PA_NVL", "PA_SL"]
cmp.fields               # ["DON_GIA", "GIA_BAN", "THUE_VAT"]
cmp.base_scenario        # "Gốc"
cmp.results["PA_NVL"]["DON_GIA"]        # 86_000
cmp.delta["DON_GIA"]["PA_NVL"]          # {"delta": 6000, "pct": 7.5}

# ── JSON ───────────────────────────────────────────────────────────
import json
json.dumps(cmp.to_dict(), ensure_ascii=False)
```

---

## 12. Validate Inputs & Diff Inputs

```python
# ════════════════════════════════════════════════════════════════════
# validate_inputs — kiểm tra inputs trước khi tính
# ════════════════════════════════════════════════════════════════════
issues = engine.validate_inputs(inputs, strict_types=False)
# → List[InputIssue]

for issue in issues:
    print(f"[{issue.severity}] {issue.field}: {issue.issue}")
    # issue.field:    tên field
    # issue.issue:    mô tả lỗi
    # issue.value:    giá trị thực tế
    # issue.severity: "error" | "warning"
    # issue.expected: giá trị/type/range mong đợi
    print(f"  Value: {issue.value}, Expected: {issue.expected}")

# JSON
[i.to_dict() for i in issues]

# ════════════════════════════════════════════════════════════════════
# diff_inputs — tìm thay đổi giữa 2 bộ inputs
# ════════════════════════════════════════════════════════════════════
# Chỉ trả tên fields
changed = engine.diff_inputs(old_inputs, new_inputs)
# → {"NVL", "BIEN_LAI"}  (set)

# Trả cả giá trị cũ/mới
changed_detail = engine.diff_inputs_values(old_inputs, new_inputs)
# → {"NVL": (5_000_000, 6_000_000), "BIEN_LAI": (0.15, 0.20)}

# Dùng với incremental:
changed_keys = engine.diff_inputs(old_inputs, new_inputs)
result = engine.calculate_incremental(ctx, {k: new_inputs[k] for k in changed_keys})
```

---

## 13. FormulaValidator — Kiểm tra tĩnh AST

Validate công thức trước khi lưu vào DB — không cần tính thật.

```python
from formula_utils import FormulaValidator

# ── Standalone validator ───────────────────────────────────────────
validator = FormulaValidator(
    allowed_functions = list(BASE_FUNCS.keys()),  # hàm được phép
    forbidden_nodes   = None,  # None = dùng default
)

# ── validate() — 1 công thức ─────────────────────────────────────
vr = validator.validate(
    formula     = "NVL + NC * TY_LE_CPC",
    known_names = {"NVL", "NC", "TY_LE_CPC"},  # biến được phép
)
# → ValidationResult
print(vr.ok)          # True
print(vr.normalized)  # công thức đã chuẩn hóa
print(vr.errors)      # []
print(vr.warnings)    # [] hoặc ["IF thiếu nhánh else ..."]
bool(vr)              # True nếu ok
vr.raise_if_invalid("ten_field")  # raise FormulaError nếu !ok
print(vr.summary())   # human-readable

# ── validate_batch() — nhiều công thức cùng lúc ────────────────────
results = validator.validate_batch(
    formulas    = {"F1": "A + B", "F2": "F1 * C"},
    known_names = {"A", "B", "C"},  # cross-reference tự động
)
# → Dict[str, ValidationResult]
for name, vr in results.items():
    if not vr.ok:
        print(f"{name}: {vr.errors}")

# ── Qua FormulaEngine ──────────────────────────────────────────────
# Validate 1 công thức (có cross-reference với formulas trong engine)
vr = engine.validate_formula(
    "NVL + NC + PC_THEM",
    known_names={"NVL", "NC", "PC_THEM"}
)

# Validate tất cả công thức hiện có trong engine
all_vr = engine.validate_all(known_names={"NVL", "NC", "CPC", "SAN_LUONG", "BIEN_LAI"})

# validate_on_init=True trong FormulaEngine constructor
# → validate ngay khi khởi tạo, raise FormulaValidationError nếu có lỗi
```

### 4 lớp kiểm tra của FormulaValidator

| Lớp | Kiểm tra | Ví dụ lỗi |
| --- | -------- | --------- |
| **1. Syntax** | Cú pháp Python có parse được không | `"A ++ B"` |
| **2. Security** | AST node bị cấm, tên nguy hiểm, attr không whitelist | `import`, `lambda`, `os` |
| **2b. GeneratorExp** | Generator standalone vs trong sum/min/max | `(x for x in lst)` standalone |
| **3. Function whitelist** | Hàm có trong `allowed_functions` không | `my_func(A, B)` |
| **4. Variable whitelist** | Biến có trong `known_names` không (optional) | `UNKNOWN_VAR + A` |

---

## 14. Snapshot & Audit — Chốt số, lưu vết

### 14.1 EnterpriseSnapshot — 5 lớp kiến trúc

```
EnterpriseSnapshot (immutable frozen dataclass)
├── Layer 1: EngineMetaBlock       engine_version, formula_hash, frozen, ...
├── Layer 2a: EngineContextBlock   dag_version, input_keys, output_keys, rounding_policy, error_mode
├── Layer 2b: DagStateBlock        execution_order, dependency_edges, dirty_nodes, calc_mode, ...
├── Layer 3: ExecutionTraceBlock   fields_evaluated, entries: List[TraceEntry]
│            TraceEntry:           field, formula, old_value, new_value, triggered_by, dep_values, exec_time_ms
├── Layer 4: business_input + outputs
└── Layer 5: AuditTrailBlock       tag, status, created_by, approved_by, parent_snapshot_id, revision_chain
```

### 14.2 Chốt số với full trace

```python
from formula_utils import SnapshotTag, SnapshotStatus

# ── snapshot_with_trace — tính + chốt + trace ────────────────────
outputs, snap = engine.snapshot_with_trace(
    inputs          = raw_inputs,          # inputs để tính
    business_inputs = {                    # inputs ghi vào snapshot (có thể khác)
        "so_bao_gia": "BG-2025-001",
        "khach_hang": "Cty ABC Hà Nội",
    },
    tag             = SnapshotTag.ESTIMATE,   # ESTIMATE|PLAN|ACTUAL|VARIANCE|VOID
    status          = SnapshotStatus.DRAFT,   # DRAFT|LOCKED|APPROVED|REJECTED|ARCHIVED
    created_by      = "user@company.com",
    source_doc      = "BG-2025-001",          # ERPNext docname
    notes           = "Báo giá lần 1, chờ khách duyệt",
    approved_by     = None,
    previous_values = None,   # dict output cũ — để trace old_value vs new_value
    dirty_nodes     = None,   # None = full calc (tất cả nodes dirty)
    calc_mode       = "full",
    parent_snapshot = None,
)

# outputs = {"TONG_CP": 8_000_000, "DON_GIA": 80_000, ...}
# snap = EnterpriseSnapshot — immutable

# ── Lưu vào DB ─────────────────────────────────────────────────────
import json
doc.gia_thanh_json = snap.to_json(indent=2)  # hoặc json.dumps(snap.to_dict())
doc.snap_id        = snap.snapshot_id

# ── Chốt số đơn giản (không cần trace) ─────────────────────────────
snap_simple = engine.snapshot(
    inputs      = inputs,
    outputs     = engine.calculate(inputs),
    tag         = SnapshotTag.PLAN,
    created_by  = "system",
    notes       = "Kế hoạch Q1/2025",
)
```

### 14.3 Đọc lại và audit

```python
import json
from formula_utils import EnterpriseSnapshot

# ── Khôi phục từ JSON ──────────────────────────────────────────────
data = json.loads(doc.gia_thanh_json)
snap = EnterpriseSnapshot(**data)  # hoặc SnapshotManager.from_json(...)

# ── Đọc thông tin ──────────────────────────────────────────────────
print(snap.snapshot_id)            # UUID
print(snap.created_at)             # UTC ISO string
print(snap.outputs["DON_GIA"])     # 80_000
print(snap.business_input)         # inputs ghi lúc chốt

# ── Kiểm tra tính toàn vẹn (tamper detection) ──────────────────────
print(snap.verify())               # True = OK, False = bị can thiệp
print(snap.payload_hash)           # SHA-256(meta+dag+inputs+outputs)
print(snap.trace_hash)             # SHA-256(exec_trace) hoặc None

# ── Xem thông tin engine tại thời điểm chốt ────────────────────────
print(snap.meta.engine_version)    # "28.0.0"
print(snap.meta.formula_hash)      # SHA-256 formula set lúc chốt
print(snap.meta.formula_count)     # 5
print(snap.meta.frozen)            # False
print(snap.dag_state.execution_order)   # thứ tự tính lúc đó
print(snap.dag_state.calc_mode)         # "full" | "incremental"

# ── Execution trace chi tiết ───────────────────────────────────────
for entry in snap.exec_trace.entries:
    if not entry.skipped:
        print(f"{entry.field}: {entry.old_value} → {entry.new_value}")
        print(f"  formula:      {entry.formula}")
        print(f"  triggered_by: {entry.triggered_by}")
        print(f"  dep_values:   {entry.dep_values}")
        print(f"  exec_time_ms: {entry.exec_time_ms:.3f}")

# ── Báo cáo forensic đầy đủ ────────────────────────────────────────
print(snap.to_audit_report())
# ════════════════════════════════════════════════════════════════════
#   ENTERPRISE SNAPSHOT — FORENSIC AUDIT REPORT  (engine_v12)
# ════════════════════════════════════════════════════════════════════
#   Snapshot ID  : abc123-...
#   Created At   : 2025-07-15T08:30:00+00:00
#   Created By   : user@company.com
#   Tag          : ESTIMATE
#   Status       : DRAFT
# ── Engine Meta ──────────────────────────────────────────────────────
# ...
```

### 14.4 Revision — cập nhật snapshot

```python
# ── snapshot_revise — tạo version mới từ snapshot cũ ──────────────
snap2 = engine.snapshot_revise(
    previous_snapshot = snap,
    inputs            = new_inputs,
    outputs           = engine.calculate(new_inputs),
    tag               = SnapshotTag.ACTUAL,
    status            = SnapshotStatus.APPROVED,
    created_by        = "manager@company.com",
    notes             = "Cập nhật giá NVL thực tế Q1/2025",
)
# snap2.audit_trail.parent_snapshot_id = snap.snapshot_id
# snap2.audit_trail.revision_chain = [snap.snapshot_id]

# ── So sánh 2 snapshot ─────────────────────────────────────────────
diff = engine.compare_snapshots(snap, snap2)
# hoặc: SnapshotManager.compare(snap, snap2)

print(diff["same_engine"])              # True — cùng formula hash
print(diff["inputs_changed"])           # {"NVL": {"before": 5M, "after": 5.5M}}
print(diff["outputs_changed"]["GIA_BAN"])
# {"before": 92_000, "after": 97_000, "delta": 5_000, "delta_pct": 5.43}
print(diff["summary"]["outputs_changed_count"])  # 5
```

### 14.5 SnapshotRegistry — quản lý nhiều snapshot

```python
from formula_utils import SnapshotRegistry, SnapshotTag, SnapshotStatus

registry = SnapshotRegistry()
registry.register(snap1)
registry.register(snap2)

# Truy vấn
results = registry.query(
    tag        = SnapshotTag.ESTIMATE,
    status     = SnapshotStatus.DRAFT,
    created_by = "user@company.com",
    source_doc = "BG-2025-001",
)

# Lấy theo ID
s = registry.get("abc-123")

# Revision history
history = registry.revision_history("abc-123")

# Khóa snapshot
locked = registry.lock("abc-123")

# Export JSON
json_str = registry.export_json("abc-123", indent=2)

print(len(registry))  # số lượng snapshots
```

### 14.6 ImmutableSnapshot — Legacy (v11 compat)

```python
from formula_utils import SnapshotManager, ImmutableSnapshot

# Tạo (không cần engine)
snap = SnapshotManager.create_snapshot(
    inputs  = {"NVL": 5e6},
    outputs = {"DON_GIA": 80_000},
    trace   = None,
)
print(snap.snapshot_id)
print(snap.integrity_hash)
print(snap.to_dict())

# So sánh 2 legacy snapshot
diff = SnapshotManager.compare_snapshots(snap1, snap2)
# {"inputs_changed": {...}, "outputs_changed": {...}, "summary": {...}}

# Nâng cấp lên EnterpriseSnapshot
enterprise_snap = SnapshotManager.from_legacy(
    legacy_snapshot = snap,
    engine          = engine,
    tag             = SnapshotTag.ESTIMATE,
    created_by      = "migrated",
)
```

---

## 15. TimeBucket v3 — Quản lý kỳ thời gian

### 15.1 Tạo kỳ

```python
from formula_utils import generate_time_buckets, generate_time_buckets_flat

# ── generate_time_buckets — trả dict phân loại ────────────────────
buckets = generate_time_buckets(
    year         = 2025,
    types        = ["year", "half", "quarter", "month", "week"],  # None = tất cả
    week_start   = "monday",   # "monday" | "sunday"

    # label_format: "short"|"short_year"|"short_year2"|"full"|"slash_year"|
    #               "slash_year2"|"padded"|"padded_year"|"date_range"|custom
    label_format = "short",        # Q1, M3, W12, H1, Y2025
    # "short_year":  Q1-2025, M3-2025
    # "short_year2": Q1-25
    # "full":        Quarter 1 2025
    # "slash_year":  Q1/2025
    # "padded":      Q01, M03
    # "date_range":  2025-01-01 → 2025-03-31

    full_format  = "{type_full} {index} {year}",   # cho full_label
    name_format  = "short",                         # cho name (stable key)
)

# Cấu trúc trả về:
buckets["year"]      # TimeBucket object (1)
buckets["halves"]    # List[TimeBucket] (2 phần tử)
buckets["quarters"]  # List[TimeBucket] (4 phần tử)
buckets["months"]    # List[TimeBucket] (12 phần tử)
buckets["weeks"]     # List[TimeBucket] (52-53 phần tử)

# Duyệt
for q in buckets["quarters"]:
    print(f"{q.label}  {q.from_date} → {q.to_date}  prev={q.prev_name} next={q.next_name}")
# Q1  2025-01-01 → 2025-03-31  prev=Q4@2024 next=Q2
# Q2  2025-04-01 → 2025-06-30  prev=Q1 next=Q3
# Q3  2025-07-01 → 2025-09-30
# Q4  2025-10-01 → 2025-12-31  next=Q1@2026

# ── generate_time_buckets_flat — list phẳng ───────────────────────
flat = generate_time_buckets_flat(
    year         = 2025,
    types        = ["quarter", "month"],

    # Chọn 1 output mode:
    as_dict      = True,   # → List[dict] đầy đủ (mặc định nếu không chọn)
    # as_ui      = True,   # → [{"value","label","short_label","full_label","from_date","to_date"}]
    # as_filter  = True,   # → [{"period","from_date","to_date"}]
    # as_entry   = True,   # → [{"period","period_label","period_full","from_date","to_date","year","index"}]
)

# year_buckets — shortcut
from formula_utils import year_buckets
this_year = year_buckets()           # năm hiện tại
last_year = year_buckets(offset=-1)  # năm trước
next_year = year_buckets(offset=+1)  # năm sau
y2024     = year_buckets(2024, types=["quarter", "month"])
```

### 15.2 TimeBucket properties

```python
from formula_utils import get_period

q3 = get_period("quarter", 3, 2025)

# ── Properties ─────────────────────────────────────────────────────
q3.name          # "Q3"          — stable key
q3.label         # "Q3"          — alias short_label
q3.short_label   # "Q3"
q3.full_label    # "Quarter 3 2025"
q3.value         # "Q3"          — alias name (HTML select value)
q3.type          # "quarter"
q3.index         # 3
q3.year          # 2025
q3.from_date     # "2025-07-01"
q3.to_date       # "2025-09-30"
q3.prev_name     # "Q2"
q3.next_name     # "Q4"

# ── Navigation (lazy — không generate toàn bộ năm) ────────────────
q3.prev_period   # TimeBucket Q2/2025
q3.next_period   # TimeBucket Q4/2025

# ── Kiểm tra ngày trong kỳ ───────────────────────────────────────
"2025-08-15" in q3    # True
"2025-11-01" in q3    # False

# ── Serialization ──────────────────────────────────────────────────
q3.to_dict()      # đầy đủ
q3.to_dict(full=False)  # bỏ prev/next names
q3.to_ui()        # {value, label, short_label, full_label, from_date, to_date}
q3.to_filter()    # {period, from_date, to_date}  — dùng với query
q3.to_entry()     # {period, period_label, period_full, from_date, to_date, year, index}

# ── Operators ──────────────────────────────────────────────────────
q3 == "Q3"        # True (so sánh với string)
q3 == other_q3    # True nếu cùng name và year
hash(q3)          # hashable
repr(q3)          # "TimeBucket('Q3', 2025-07-01 → 2025-09-30)"
```

### 15.3 Tìm kiếm kỳ

```python
from formula_utils import get_period, get_period_by_date, get_period_offset, same_period_last_year

# Lấy theo loại và index
q3 = get_period("quarter", 3, 2025)
m7 = get_period("month",   7, 2025)
w30 = get_period("week",   30, 2025,
                 week_start="monday",
                 label_format="short")

# Tìm kỳ chứa một ngày
q = get_period_by_date("2025-08-15", "quarter")   # → Q3/2025
m = get_period_by_date("2025-08-15", "month")     # → M8/2025
w = get_period_by_date("2025-08-15", "week")      # → W33/2025

# Dịch kỳ ±n
q2   = get_period_offset(q3, -1)    # → Q2/2025
q4   = get_period_offset(q3, +1)    # → Q4/2025
q1_2026 = get_period_offset(q3, +2) # → Q1/2026  (cross year)
m3_2024 = get_period_offset(m7, -16) # → M3/2024  (16 tháng trước)

# Cùng kỳ năm trước
q3_2024  = same_period_last_year(q3)              # → Q3/2024
q3_2023  = same_period_last_year(q3, years_back=2) # → Q3/2023
m7_prev  = same_period_last_year(m7)              # → M7/2024

# Qua FormulaEngine static methods — dùng trong API handler
FormulaEngine.get_time_buckets(2025, types=["quarter"])
FormulaEngine.get_period("quarter", 3, 2025)
FormulaEngine.get_period_by_date("2025-08-15", "quarter")
FormulaEngine.get_period_offset(q3, -1)
FormulaEngine.same_period_last_year(q3)
FormulaEngine.year_buckets(2025)
FormulaEngine.get_time_buckets_flat(2025, as_ui=True)
```

### 15.4 Label format tokens

```python
# Tokens có thể dùng trong format string:
# {year}        = 2025
# {year2}       = 25
# {index}       = 3
# {index02}     = 03  (zero-padded)
# {type_short}  = Q/M/W/H/Y
# {type_full}   = Quarter/Month/Week/Half/Year
# {from_date}   = 2025-07-01
# {to_date}     = 2025-09-30

# Preset names (TB_FORMAT dict):
"short"        → "{type_short}{index}"            # Q3
"short_year"   → "{type_short}{index}-{year}"     # Q3-2025
"short_year2"  → "{type_short}{index}-{year2}"    # Q3-25
"full"         → "{type_full} {index} {year}"     # Quarter 3 2025
"slash_year"   → "{type_short}{index}/{year}"     # Q3/2025
"slash_year2"  → "{type_short}{index}/{year2}"    # Q3/25
"padded"       → "{type_short}{index02}"           # Q03
"padded_year"  → "{type_short}{index02}-{year}"   # Q03-2025
"date_range"   → "{from_date} → {to_date}"        # 2025-07-01 → 2025-09-30

# Custom format
get_period("month", 7, 2025, label_format="Tháng {index} năm {year}")
# → short_label = "Tháng 7 năm 2025"
```

---

## 16. Allocation Engine — Phân bổ chi phí

### 16.1 allocate() — API chính

```python
from formula_utils import allocate

result = allocate(
    # ── BẮT BUỘC ─────────────────────────────────────────────────
    sources = [
        {"id": "CPC_XUONG_A", "amount": 50_000_000},
        {"id": "CPC_XUONG_B", "amount": 30_000_000},
    ],
    targets = [
        {"id": "SP_X", "qty": 500, "amount": 150_000_000,
         "weight": 1.5, "alloc_pct": 50, "alloc_amount": 20_000_000,
         "manual_pct": 45},
        {"id": "SP_Y", "qty": 300, "amount": 80_000_000,
         "weight": 1.0, "alloc_pct": 30, "alloc_amount": 15_000_000,
         "manual_pct": 35},
        {"id": "SP_Z", "qty": 200, "amount": 40_000_000,
         "weight": 0.8, "alloc_pct": 20,
         "manual_pct": 20},  # alloc_amount=None → residual trong mixed
    ],

    # ── PHƯƠNG PHÁP ───────────────────────────────────────────────
    method = "qty",   # xem bảng bên dưới

    # ── KEY MAPPING (đổi nếu field có tên khác trong data của bạn)
    source_id_key            = "id",
    source_amount_key        = "amount",
    target_id_key            = "id",
    target_qty_key           = "qty",
    target_amount_key        = "amount",
    target_weight_key        = "weight",      # dùng bởi method="weight"
    target_pct_key           = "alloc_pct",   # dùng bởi method="pct"
    target_manual_amount_key = "alloc_amount",# dùng bởi method="manual_amount" / "mixed" pass1
    target_manual_pct_key    = "manual_pct",  # dùng bởi method="manual_pct" / "mixed" pass2

    # ── NHÓM ─────────────────────────────────────────────────────
    # Mỗi nhóm phân bổ độc lập — chỉ source cùng group mới phân bổ cho target cùng group
    group_key = None,   # "phong_ban" → phân bổ riêng từng phòng

    # ── LÀM TRÒN ─────────────────────────────────────────────────
    rounding_policy       = "last",     # "last"|"largest"|"none"
    round_digits          = 2,
    mixed_residual_method = "qty",      # method cho phần dư trong "mixed"
)
# → AllocationResult
```

### 16.2 8 Phương pháp phân bổ

| method            | Phân bổ theo                                           | Field target cần có       |
| ----------------- | ------------------------------------------------------ | ------------------------- |
| `"equal"`         | Chia đều số targets                                    | (không cần)               |
| `"qty"`           | Tỷ lệ số lượng                                         | `target_qty_key`          |
| `"amount"`        | Tỷ lệ doanh thu/giá trị                                | `target_amount_key`       |
| `"weight"`        | Trọng số tùy chọn                                      | `target_weight_key`       |
| `"pct"`           | % cố định, tổng phải ≈ 100 (engine normalize nếu lệch) | `target_pct_key`          |
| `"manual_amount"` | Số tiền cố định tuyệt đối                              | `target_manual_amount_key`|
| `"manual_pct"`    | % nhập tay (tính trên tổng source)                     | `target_manual_pct_key`   |
| `"mixed"`         | Pass1=manual_amount → Pass2=manual_pct → Pass3=residual | tùy pass                 |

**Mixed — logic 3 pass**:
1. **Pass 1**: target có `alloc_amount` → số tiền cố định
2. **Pass 2**: target còn lại có `manual_pct` → % tính trên phần còn lại sau pass 1
3. **Pass 3**: target còn lại → `mixed_residual_method` (mặc định qty) trên phần còn lại

### 16.3 AllocationResult — API đầy đủ

```python
# ── Fields cơ bản ──────────────────────────────────────────────────
result.ok              # True/False
result.lines           # List[AllocationLine]
result.source_totals   # {"CPC_XUONG_A": 50_000_000, ...}
result.target_totals   # {"SP_X": ..., "SP_Y": ..., "SP_Z": ...}
result.unallocated     # {} — empty nếu phân bổ đủ
result.warnings        # ["Nguồn '...': tổng pct != 100. Normalize."]
result.summary()       # str overview

# ── Chi tiết từng dòng AllocationLine ─────────────────────────────
for line in result.lines:
    line.source_id       # "CPC_XUONG_A"
    line.source_amount   # 50_000_000
    line.target_id       # "SP_X"
    line.allocated       # 25_000_000
    line.ratio           # 0.5 (50%)
    line.method          # "qty" hoặc "mixed:pass1_manual_amount"
    line.weight          # trọng số dùng để tính
    line.meta            # {} hoặc {"mixed_stage": "pass1_manual_amount"}
    line.to_dict()       # dict

# ── to_line_map — lookup O(1) theo target_id ─────────────────────
ln_map = result.to_line_map()
# {target_id → AllocationLine}
ln = ln_map.get("SP_X")

# ── apply_to — ghi vào rows ───────────────────────────────────────
result.apply_to(
    rows    = self.items,           # list[dict] hoặc list[Frappe child row]
    id_key  = "voucher_detail_no",  # field để match
    out_key = "amount",             # field để ghi allocated
)

# ── Xem theo nguồn / đích ─────────────────────────────────────────
by_source = result.group_by_source(sources, source_id_key="id")
# → {source_id: {"allocated_total": ..., "unallocated": ..., "allocated_to": [...]}}

by_target = result.group_by_target(targets, target_id_key="id")
# → {target_id: {"received_total": ..., "received_from": [...]}}

# ── Flat rows — dùng để import vào DB ─────────────────────────────
rows = result.to_flat_rows(ratio_as_pct=True)
# → [{"source_id":..., "target_id":..., "allocated":..., "ratio":6.25, ...}, ...]

# ── Full dict ─────────────────────────────────────────────────────
result.to_full_dict(sources, targets)

# ── Print đẹp ─────────────────────────────────────────────────────
result.print_by_source(sources, label_key="ten_nguon")
result.print_by_target(targets, label_key="ten_san_pham")
```

### 16.4 Output modes — 3 cách dùng AllocationEngine

```python
from formula_utils import AllocationEngine

engine_alloc = AllocationEngine(
    sources, targets, method="qty",
    source_id_key="id", target_id_key="id",
)

# Mode 1: to_result() — đầy đủ, tạo AllocationResult
result = engine_alloc.to_result()

# Mode 2: to_inplace() — ghi thẳng vào targets[i][out_key], nhanh nhất
src_totals, tgt_totals, warns = engine_alloc.to_inplace(
    out_key      = "allocated",
    reset_before = True,   # set targets[i]["allocated"]=0 trước
)
# Không tạo AllocationLine object → dùng cho batch lớn

# Mode 3: to_lines() — pipeline, list of tuples
lines, src_totals, tgt_totals, warns = engine_alloc.to_lines()
# lines: List[AllocTuple] = (source_id, source_amount, target_id, allocated, ratio, method, weight)
```

### 16.5 Alias functions nhanh

```python
from formula_utils import allocate, allocate_inplace, allocate_fast

# allocate() → AllocationResult (Mode 1)
result = allocate(sources, targets, "qty", round_digits=0)

# allocate_inplace() → ghi vào targets dict/object (Mode 2)
src_totals, tgt_totals, warns = allocate_inplace(
    sources, targets, out_key="allocated_amount",
    method="qty", reset_before=True,
)

# allocate_fast() → list tuples (Mode 3)
lines, src_totals, tgt_totals, warns = allocate_fast(sources, targets, "equal")
```

---

## 17. TopoSort v2 — Sort DAG data rows

```python
from formula_utils import topo_sort, topo_sort_with_info, TopoSorter

tasks = [
    {"id": "D", "deps": ["B", "C"]},
    {"id": "C", "deps": ["A"]},
    {"id": "B", "deps": ["A"]},
    {"id": "A", "deps": []},
]

# ── Cơ bản — chỉ trả list đã sort ────────────────────────────────
sorted_items = topo_sort(
    items   = tasks,
    id_fn   = lambda x: x["id"],
    deps_fn = lambda x: x["deps"],
)
# → [task_A, task_B, task_C, task_D]

# ── Đầy đủ — TopoSortResult ──────────────────────────────────────
info = topo_sort_with_info(tasks, lambda x: x["id"], lambda x: x["deps"])

info.items           # [task_A, task_B, task_C, task_D]
info.order           # ["A", "B", "C", "D"]
info.has_cycle       # False  (True nếu có cycle → không crash, append cuối)
info.cycle_nodes     # []
info.levels          # {"A":0, "B":1, "C":1, "D":2}
info.edges           # {"A":[], "B":["A"], "C":["A"], "D":["B","C"]}
info.summary()       # human-readable với level, deps
info.to_dict()       # dict

# ── Reusable TopoSorter ────────────────────────────────────────────
sorter = TopoSorter(lambda x: x["id"], lambda x: x["deps"])
sorted_items  = sorter.sort(tasks)              # fast path
info          = sorter.sort_with_info(tasks)   # với metadata

# ── Sort data rows (nested deps dạng list[dict]) ──────────────────
from formula_utils import topo_sort_data, topo_sort_flat

# deps_list_key chứa list[dict] (hoặc JSON string của list[dict])
sorted_wo = topo_sort_data(
    items         = work_orders,
    id_key        = "name",
    deps_list_key = "required_items",   # [{dep_id_key: "WO-001"}, ...]
    dep_id_key    = "item_code",
)

# dep_ids_key chứa list trực tiếp
sorted_items = topo_sort_flat(
    items       = items,
    id_key      = "id",
    dep_ids_key = "dep_ids",   # ["id1", "id2"]
)
```

### Hành vi khi có cycle

- `topo_sort()`: append cycle nodes vào cuối, **không raise**
- `topo_sort_with_info()`: `has_cycle=True`, `cycle_nodes=["A","B","C"]`, `levels[cycle_node]=-1`
- `FormulaEngine()`: **raise FormulaError(CIRCULAR_DEPENDENCY)** khi parse

---

## 18. SCC TopoSort — Sort đồ thị có chu kỳ

Dùng Tarjan SCC → Kahn's Algorithm trên condensation graph. Cycle nodes được nhóm liền nhau.

```python
from formula_utils import scc_topo_sort, scc_topo_sort_with_info, SccTopoSorter

# A→B→C→A (cycle), D phụ thuộc A (không cycle)
items = [
    {"id": "A", "deps": ["C"]},
    {"id": "B", "deps": ["A"]},
    {"id": "C", "deps": ["B"]},
    {"id": "D", "deps": ["A"]},   # D phụ thuộc SCC(A,B,C)
]

sorted_items = scc_topo_sort(
    items,
    id_fn   = lambda x: x["id"],
    deps_fn = lambda x: x["deps"],
)
# → [A, B, C, D]  — cycle nodes nhóm trước, D sau

info = scc_topo_sort_with_info(items, lambda x: x["id"], lambda x: x["deps"])
# → SccTopoResult

info.items              # [A, B, C, D]
info.order              # ["A", "B", "C", "D"]
info.sccs               # [["A","B","C"], ["D"]]  (Tarjan SCCs)
info.has_cycle          # True
info.cycle_groups       # [["A","B","C"]]  (SCC có >1 node)
info.levels             # {"A":-1, "B":-1, "C":-1, "D":1}  (-1 = cycle)
info.condensation_order # [0, 1]  (SCC index theo topo order)
info.node_to_scc        # {"A":0, "B":0, "C":0, "D":1}
info.edges              # {"A":["C"], "B":["A"], ...}
info.summary()          # human-readable
info.to_dict()

# ── Reusable SccTopoSorter ────────────────────────────────────────
sorter = SccTopoSorter(lambda x: x["id"], lambda x: x["deps"])
sorted_items = sorter.sort(items)
info         = sorter.sort_with_info(items)

# ── Sort data rows ────────────────────────────────────────────────
from formula_utils import scc_topo_sort_data, scc_topo_sort_flat

scc_topo_sort_data(
    items         = cost_centers,
    id_key        = "name",
    deps_list_key = "allocations",       # [{dep_id_key: "CC-001"}, ...]
    dep_id_key    = "to_cost_center",
)

scc_topo_sort_flat(
    items       = nodes,
    id_key      = "id",
    dep_ids_key = "input_ids",
)
```

---

## 19. SccLinearSolver — Giải hệ tuyến tính trên graph

Dùng cho BOM có phế liệu, chi phí reciprocal giữa bộ phận, Leontief I-O model.

**Bài toán**: Với đồ thị có cycle, giải `x_i = b_i + Σ_j(A_ij × x_j)` tương đương `(I-A)x = b`.

- **Không cycle** → direct solve (x_i = b_i + Ax đã biết)
- **Có cycle** → Gaussian elimination trên ma trận SCC

```python
from formula_utils import SccLinearSolver, solve_linear_on_graph

# ── Ví dụ: Chi phí reciprocal ─────────────────────────────────────
# Xưởng A phân bổ 10% cho B, Xưởng B phân bổ 5% cho A
# x_A = b_A + 0.05 * x_B
# x_B = b_B + 0.10 * x_A

items = [
    {"id": "A", "direct_cost": 500_000, "allocs": [{"to": "B", "pct": 0.10}]},
    {"id": "B", "direct_cost": 300_000, "allocs": [{"to": "A", "pct": 0.05}]},
    {"id": "C", "direct_cost": 100_000, "allocs": []},   # không cycle
]

result = solve_linear_on_graph(
    items   = items,

    # id_fn: lấy node ID từ item
    id_fn   = lambda item: item["id"],

    # deps_fn: trả List[(dep_id, edge_data)] — các node mà node này nhận từ
    deps_fn = lambda item: [(a["to"], a) for a in item.get("allocs", [])],

    # b_fn: giá trị hằng số b_i của node
    #   node_id: tên node
    #   item:    data dict
    #   resolved: dict {id: x} của các node đã giải (outside SCC)
    b_fn    = lambda node_id, item, resolved: item["direct_cost"],

    # coeff_fn: lấy hệ số A_ij từ edge_data (trả về từ deps_fn)
    coeff_fn = lambda edge_data: edge_data["pct"],

    # output_fn: ghi x vào item sau khi giải xong
    output_fn = lambda node_id, x_value, item, resolved: item.update({"total_cost": x_value}),

    # Optional:
    feasibility_fn    = None,   # fn(scc_nodes, data_map) → List[str] warnings
    epsilon           = 1e-9,   # ngưỡng singular matrix
    max_iter_fallback = 0,      # 0=không fallback; >0 = Gauss-Seidel iterations
)

# ── SccLinearSolveResult ──────────────────────────────────────────
result.has_cycle      # True — A,B tạo cycle
result.cycle_groups   # [["A","B"]]
result.values         # {"A": 521_276.6, "B": 352_127.66, "C": 100_000}
result.warnings       # []
result.solve_order    # ["A", "B", "C"]

# items đã được ghi total_cost qua output_fn
for item in items:
    print(f"{item['id']}: {item['total_cost']:,.2f}")

# ── Audit chi tiết ────────────────────────────────────────────────
for node_id, entry in result.audit.items():
    print(entry.explain())
    # ━━ A [CYCLE]  [SCC #0, method=gaussian]
    #    b (constant)   :          500,000.000000
    #    deps (A·x):
    #      ← B  coeff=0.050000  x_dep=352,127.66  contrib=17,606.38
    #    x (solution)   :          517,606.383

print(result.summary())      # bảng đầy đủ
print(result.summary_cycle()) # chỉ cycle groups

# ── Dùng SccLinearSolver class trực tiếp ─────────────────────────
solver = SccLinearSolver(
    items             = items,
    id_fn             = ...,
    deps_fn           = ...,
    b_fn              = ...,
    coeff_fn          = ...,
    output_fn         = ...,
    feasibility_fn    = None,
    epsilon           = 1e-9,
    max_iter_fallback = 100,  # Gauss-Seidel fallback nếu Gaussian thất bại
)
result = solver.solve()

# ── Qua FormulaEngine ─────────────────────────────────────────────
result = engine.solve_linear_on_graph(items, id_fn, deps_fn, b_fn, coeff_fn, output_fn)
```

---

## 20. Security Model

Engine dùng `ast.parse(mode='eval')` — chỉ cho phép **expression**, không phải **statement**. Điều này đảm bảo không có gán, vòng lặp, hay side effect nào.

### Bảo vệ nhiều lớp

| Lớp | Cơ chế | Ví dụ bị chặn |
| --- | ------- | ------------- |
| **AST blacklist** | Forbidden node types | `import`, `lambda`, `FunctionDef`, `ClassDef`, `Assign`, `Delete` |
| **Name blacklist** | Forbidden identifiers | `os`, `sys`, `eval`, `exec`, `globals`, `locals`, `__import__` |
| **Attribute whitelist** | Chỉ `.get()`, `.keys()`, `.values()`, `.items()`, `.to_dict()` | `obj.format()`, `obj.__class__` |
| **Function whitelist** | Chỉ hàm trong `runtime_env` | Hàm không có trong `safe_funcs` |
| **Variable whitelist** | (optional) `known_names` | Tên biến không khai báo |
| **Budget guard** | `max_operations` | Vòng lặp vô hạn qua generator |
| **Iterable guard** | `max_iterable_size` | `[1]*100_000_000` |
| **Depth guard** | `max_subscript_depth` | `a[b[c[d[e[...]]]]]` |
| **Deterministic** | Chặn `now()`/`today()` | Time-based non-determinism |
| **__builtins__={}** | Không có builtin Python | `print`, `open`, `input` |

### Chính sách keyword `=` vs `==`

Engine tự phân biệt `=` (gán keyword arg) và `==` (so sánh) theo quy tắc:
- Nếu `ident` trước `=` có len ≥ 3 **và** có trong `_KNOWN_KWARGS` → giữ `=`
- Ngược lại → convert thành `==`

Ví dụ:
```python
"sorted_array(rows, sort_by='ngay', reverse=True)"   # sort_by=, reverse= giữ nguyên
"filter_array(rows, key='loai', value='A')"           # key=, value= giữ nguyên
"A = 5"                                               # A==5 (so sánh)
"x = y"                                               # x==y (so sánh)
```

---

## 21. Tích hợp ERPNext/Frappe

```python
# ── Khởi tạo engine một lần, cache nhiều lần dùng ────────────────
import frappe, json
from formula_utils import FormulaEngine

def get_formula_engine(formula_set_name: str) -> FormulaEngine:
    cache_key = f"formula_engine_{formula_set_name}"
    
    # Thử lấy từ Frappe cache
    cached = frappe.cache().get_value(cache_key)
    if cached:
        try:
            return FormulaEngine.from_cache_dict(json.loads(cached))
        except Exception:
            pass  # cache stale hoặc Python version khác → rebuild
    
    # Tải formula set từ DB
    formula_set = frappe.get_doc("Formula Set", formula_set_name)
    
    formulas = []
    for row in formula_set.formulas:
        formulas.append({
            "name":    row.field_name,
            "formula": row.formula,
            "group":   row.group or "",
            "bucket":  row.bucket or "",
        })
    
    engine = FormulaEngine(
        formulas      = formulas,
        on_error      = "null",
        deterministic = True,
    )
    
    # Lưu vào cache (5 phút)
    frappe.cache().set_value(cache_key, json.dumps(engine.to_cache_dict()), 300)
    return engine


# ── Sử dụng trong doctype ─────────────────────────────────────────
@frappe.whitelist()
def calculate_costs(docname: str):
    doc = frappe.get_doc("BOM", docname)
    engine = get_formula_engine("BOM Cost Engine")
    
    inputs = {
        "nvl":      doc.nvl_amount,
        "nc":       doc.labor_amount,
        "cpc":      doc.overhead,
        "qty":      doc.qty,
    }
    
    results = engine.calculate(inputs)
    
    # Cập nhật doc
    doc.don_gia    = results.get("don_gia", 0)
    doc.gia_ban    = results.get("gia_ban", 0)
    doc.tong_tien  = results.get("tong_tien", 0)
    doc.save()
    
    return results


# ── Allocation trong Frappe child table ───────────────────────────
from formula_utils import allocate_inplace

def allocate_overhead_to_items(doc):
    sources = [{"id": doc.name, "amount": doc.total_overhead}]
    targets = [
        {"id": row.name, "qty": row.qty, "amount": row.amount}
        for row in doc.items
    ]
    
    src_totals, tgt_totals, warns = allocate_inplace(
        sources  = sources,
        targets  = targets,
        out_key  = "overhead",
        method   = "qty",
    )
    # targets[i]["overhead"] đã được ghi
    
    for row in doc.items:
        item_data = next(t for t in targets if t["id"] == row.name)
        row.overhead = item_data["overhead"]


# ── IncrementalContext với Frappe request ──────────────────────────
from formula_utils import IncrementalContext

@frappe.whitelist()
def on_field_change(docname: str, changed_field: str, new_value: float):
    engine = get_formula_engine("BOM Cost Engine")
    cache_key = f"eng_ctx_{docname}"
    
    # Khôi phục context
    raw = frappe.cache().get_value(cache_key)
    if raw:
        try:
            ctx = IncrementalContext.from_dict(engine, json.loads(raw))
        except Exception:
            ctx = None
    else:
        ctx = None
    
    if ctx is None:
        # Lần đầu — tạo mới
        doc = frappe.get_doc("BOM", docname)
        ctx = engine.create_context(get_inputs_from_doc(doc))
    
    # Chỉ recalc fields bị ảnh hưởng
    result = engine.calculate_incremental(ctx, {changed_field: new_value})
    
    # Lưu context
    frappe.cache().set_value(cache_key, json.dumps(ctx.to_dict()), 600)
    
    return result
```

---

## 22. Hiệu năng & Tối ưu

### Cache bytecode — khởi động nhanh

```python
# Parse + compile AST tốn thời gian → cache bytecode
cache = engine.to_cache_dict()
# Lưu vào Redis/DB

# Restore — bỏ qua parse/compile (chỉ exec marshal.loads)
engine2 = FormulaEngine.from_cache_dict(cache)
# Nhanh hơn ~10x so với tạo mới từ formulas list
```

### IncrementalContext — tiết kiệm CPU

```python
# Thay vì: engine.calculate(inputs) mỗi lần user sửa field
# Dùng: engine.calculate_incremental(ctx, {changed_field: value})

# Tiết kiệm: skip_ratio * 100%  CPU
# Ví dụ: 80 formula, user sửa 1 input → chỉ recalc 15 formula = tiết kiệm 81%
```

### on_error mode

```python
# on_error="raise" chậm hơn vì Python exception overhead
# on_error="default" nhanh nhất cho batch processing
engine = FormulaEngine(formulas=..., on_error="default", default_value=0)
```

### max_operations — bảo vệ

```python
# Tắt hoàn toàn (production với dữ liệu đã validate)
engine = FormulaEngine(formulas=..., max_operations=None)

# Bật budget guard (untrusted data)
engine = FormulaEngine(formulas=..., max_operations=50_000)
```

### Batch lớn

```python
# calculate_batch — đơn giản nhất
results = engine.calculate_batch(rows)

# allocate_inplace — không tạo object trung gian
allocate_inplace(sources, targets, "qty")  # nhanh hơn allocate() 30-50%

# to_lines() — pipeline không tạo dataclass
lines, src, tgt, warns = allocate_fast(sources, targets, "qty")
```

### NUMERIC_TYPES — tương thích Frappe/MariaDB

```python
# Frappe trả Decimal từ MariaDB queries
# _safe_sum(), _safe_min(), _safe_max() đều handle Decimal tự động
# Không cần float() thủ công
```

---

## 23. Ví dụ thực tế — Lương & TNCN

```python
from formula_utils import FormulaEngine, InputField, OutputField

engine = FormulaEngine(
    formulas = [
        # Lương tổng hợp
        {"name": "LUONG_GROSS", "formula": "LUONG_CB + PC_TRACH_NHIEM + PC_THAM_NIEN + THU_NHAP_KHAC"},
        # Các khoản giảm trừ bảo hiểm NLĐ
        {"name": "BHXH_NLD",   "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 8%"},
        {"name": "BHYT_NLD",   "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 1.5%"},
        {"name": "BHTN_NLD",   "formula": "min(LUONG_GROSS, 20 * LUONG_CSTT) * 1%"},
        {"name": "TONG_BH_NLD","formula": "BHXH_NLD + BHYT_NLD + BHTN_NLD"},
        # Thu nhập trước thuế
        {"name": "TNT",   "formula": "LUONG_GROSS - TONG_BH_NLD - GIAM_TRU_THAN_NHAN"},
        # TNCN lũy tiến
        {"name": "THUE_TNCN", "formula": """
IFS(
    TNT <= 0,           0,
    TNT <= 5_000_000,   TNT * 5%,
    TNT <= 10_000_000,  TNT * 10% - 250_000,
    TNT <= 18_000_000,  TNT * 15% - 750_000,
    TNT <= 32_000_000,  TNT * 20% - 1_650_000,
    TNT <= 52_000_000,  TNT * 25% - 3_250_000,
    TNT <= 80_000_000,  TNT * 30% - 5_850_000,
    True,               TNT * 35% - 9_850_000
)"""},
        # Lương thực nhận
        {"name": "LUONG_THUC_NHAN", "formula": "LUONG_GROSS - TONG_BH_NLD - THUE_TNCN"},
        # Phần NSDLĐ đóng
        {"name": "BHXH_NSLD",  "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 17%"},
        {"name": "BHYT_NSLD",  "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 3%"},
        {"name": "BHTN_NSLD",  "formula": "min(LUONG_GROSS, 20 * LUONG_CSTT) * 1%"},
        {"name": "TONG_BH_NSLD","formula": "BHXH_NSLD + BHYT_NSLD + BHTN_NSLD"},
        # Chi phí nhân sự thực tế
        {"name": "CHI_PHI_NHAN_SU", "formula": "LUONG_GROSS + TONG_BH_NSLD"},
    ],
    input_fields = [
        InputField("LUONG_CB",           float, True),
        InputField("PC_TRACH_NHIEM",     float, False, 0),
        InputField("PC_THAM_NIEN",       float, False, 0),
        InputField("THU_NHAP_KHAC",      float, False, 0),
        InputField("GIAM_TRU_THAN_NHAN", float, False, 0),
        InputField("LUONG_CSTT",         float, False, 2_340_000),  # Lương cơ sở tháng
    ],
    on_error = "default",
    deterministic = True,
    rounding_policy = {
        "THUE_TNCN":        {"decimals": 0},
        "LUONG_THUC_NHAN":  {"decimals": 0},
        "CHI_PHI_NHAN_SU":  {"decimals": 0},
    },
)

# Tính lương 1 nhân viên
result = engine.calculate({
    "LUONG_CB":           15_000_000,
    "PC_TRACH_NHIEM":      3_000_000,
    "PC_THAM_NIEN":        1_500_000,
    "GIAM_TRU_THAN_NHAN":  4_400_000,  # 2 người phụ thuộc × 2.2M
})

print(f"Lương gross:      {result['LUONG_GROSS']:>15,.0f} VNĐ")
print(f"BH nhân viên:     {result['TONG_BH_NLD']:>15,.0f} VNĐ")
print(f"Thu nhập tính thuế:{result['TNT']:>14,.0f} VNĐ")
print(f"Thuế TNCN:        {result['THUE_TNCN']:>15,.0f} VNĐ")
print(f"Lương thực nhận:  {result['LUONG_THUC_NHAN']:>15,.0f} VNĐ")
print(f"Chi phí nhân sự:  {result['CHI_PHI_NHAN_SU']:>15,.0f} VNĐ")

# Batch — tính lương toàn bộ nhân sự
import csv
with open("nhan_su.csv") as f:
    nhan_su = list(csv.DictReader(f))

results = engine.calculate_batch([
    {k: float(r.get(k, 0)) for k in ["LUONG_CB","PC_TRACH_NHIEM","PC_THAM_NIEN","GIAM_TRU_THAN_NHAN"]}
    for r in nhan_su
])
```

---

## 24. Ví dụ thực tế — Dự toán xây dựng

```python
from formula_utils import FormulaEngine, BASE_FUNCS

# Giả sử: ds_hang_muc là list các hạng mục xây dựng
# Mỗi hạng mục: {ten, khoi_luong, don_vi, don_gia_vl, don_gia_nc, he_so_may}

engine = FormulaEngine(
    formulas = [
        # Tổng giá trị từng loại
        {"name": "TONG_GIA_TRI_VL",  "formula": "sum(r['khoi_luong'] * r['don_gia_vl'] for r in ds_hang_muc)"},
        {"name": "TONG_GIA_TRI_NC",  "formula": "sum(r['khoi_luong'] * r['don_gia_nc'] for r in ds_hang_muc)"},
        {"name": "TONG_GIA_TRI_MAY", "formula": "sum(r['khoi_luong'] * r['don_gia_nc'] * r['he_so_may'] for r in ds_hang_muc)"},
        # Chi phí trực tiếp
        {"name": "CHI_PHI_TRUC_TIEP","formula": "TONG_GIA_TRI_VL + TONG_GIA_TRI_NC + TONG_GIA_TRI_MAY"},
        # Chi phí gián tiếp
        {"name": "CHI_PHI_CHUNG",    "formula": "CHI_PHI_TRUC_TIEP * TY_LE_CPC"},
        {"name": "LNCTT",            "formula": "CHI_PHI_TRUC_TIEP * TY_LE_LNCTT"},
        # Giá trước thuế
        {"name": "GIA_DT_THUE",      "formula": "CHI_PHI_TRUC_TIEP + CHI_PHI_CHUNG + LNCTT"},
        # Thuế VAT đầu ra
        {"name": "THUE_GTGT",        "formula": "GIA_DT_THUE * 10%"},
        {"name": "GIA_SAU_THUE",     "formula": "GIA_DT_THUE + THUE_GTGT"},
        # Thống kê
        {"name": "SO_HANG_MUC",      "formula": "len(ds_hang_muc)"},
        {"name": "GIA_BINH_QUAN",    "formula": "safe_div(GIA_DT_THUE, SO_HANG_MUC)"},
    ],
    safe_funcs = {
        "round_vnd": lambda v: round(float(v or 0) / 1000) * 1000,
    },
    on_error = "default",
    rounding_policy = {
        "GIA_SAU_THUE": {"decimals": 0},
        "THUE_GTGT":    {"decimals": 0},
    },
)

ds_hang_muc = [
    {"ten": "Đào đất",    "khoi_luong": 500, "don_gia_vl": 0,      "don_gia_nc": 85_000,  "he_so_may": 0.3},
    {"ten": "Bê tông M200","khoi_luong": 120, "don_gia_vl": 1_200_000,"don_gia_nc": 250_000,"he_so_may": 0.5},
    {"ten": "Cốt thép",   "khoi_luong": 8,   "don_gia_vl": 18_000_000,"don_gia_nc":500_000,"he_so_may": 0.2},
    {"ten": "Xây gạch",   "khoi_luong": 200, "don_gia_vl": 600_000, "don_gia_nc": 150_000, "he_so_may": 0.1},
]

result = engine.calculate({
    "ds_hang_muc": ds_hang_muc,
    "TY_LE_CPC":   0.065,  # 6.5% chi phí chung
    "TY_LE_LNCTT": 0.06,   # 6% lãi trước thuế
})

print(f"Tổng VL:           {result['TONG_GIA_TRI_VL']:>20,.0f}")
print(f"Tổng NC:           {result['TONG_GIA_TRI_NC']:>20,.0f}")
print(f"Giá DT trước thuế: {result['GIA_DT_THUE']:>20,.0f}")
print(f"VAT 10%:           {result['THUE_GTGT']:>20,.0f}")
print(f"Giá sau thuế:      {result['GIA_SAU_THUE']:>20,.0f}")
```

---

## 25. Ví dụ thực tế — Giá thành sản xuất

```python
from formula_utils import FormulaEngine, allocate

# Bước 1: Phân bổ chi phí chung xưởng cho các sản phẩm
sources = [
    {"id": "XUONG_A", "amount": 200_000_000},
    {"id": "XUONG_B", "amount": 150_000_000},
]
targets = [
    {"id": "SP_001", "qty": 1000, "gio_may": 500},
    {"id": "SP_002", "qty": 800,  "gio_may": 700},
    {"id": "SP_003", "qty": 500,  "gio_may": 300},
]

# Phân bổ theo giờ máy
result = allocate(sources, targets, "weight",
                  target_weight_key="gio_may",
                  round_digits=0)

# Đưa kết quả phân bổ vào dict
cpc_by_sp = {line.target_id: line.allocated for line in result.lines}
# Cộng dồn nếu nhiều nguồn
cpc_total = {}
for line in result.lines:
    cpc_total[line.target_id] = cpc_total.get(line.target_id, 0) + line.allocated

# Bước 2: Tính giá thành từng sản phẩm
engine = FormulaEngine(
    formulas = [
        {"name": "NVL_DON_VI",  "formula": "NVL_TONG / SAN_LUONG"},
        {"name": "NC_DON_VI",   "formula": "NC_TONG  / SAN_LUONG"},
        {"name": "CPC_DON_VI",  "formula": "CPC_PHAN_BO / SAN_LUONG"},
        {"name": "GIA_THANH",   "formula": "NVL_DON_VI + NC_DON_VI + CPC_DON_VI"},
        {"name": "GIA_BAN",     "formula": "GIA_THANH * (1 + BIEN_LAI)"},
        {"name": "DOANH_THU",   "formula": "GIA_BAN * SAN_LUONG"},
        {"name": "LOI_NHUAN",   "formula": "DOANH_THU - (GIA_THANH * SAN_LUONG)"},
    ],
    on_error = "default",
)

san_pham_data = [
    {"id": "SP_001", "NVL_TONG": 80_000_000, "NC_TONG": 20_000_000, "SAN_LUONG": 1000},
    {"id": "SP_002", "NVL_TONG": 60_000_000, "NC_TONG": 25_000_000, "SAN_LUONG": 800},
    {"id": "SP_003", "NVL_TONG": 30_000_000, "NC_TONG": 15_000_000, "SAN_LUONG": 500},
]

BIEN_LAI = 0.20  # 20%

for sp in san_pham_data:
    r = engine.calculate({
        **sp,
        "CPC_PHAN_BO": cpc_total.get(sp["id"], 0),
        "BIEN_LAI":    BIEN_LAI,
    })
    print(f"\n{sp['id']}:")
    print(f"  Giá thành đơn vị: {r['GIA_THANH']:>12,.0f} VNĐ")
    print(f"  Giá bán:          {r['GIA_BAN']:>12,.0f} VNĐ")
    print(f"  Lợi nhuận:        {r['LOI_NHUAN']:>12,.0f} VNĐ")
```

---

## 26. Ví dụ thực tế — BOM nhiều cấp

```python
from formula_utils import topo_sort_data, FormulaEngine

# BOM: SP_A cần SP_B và VT_01; SP_B cần VT_02 và VT_03
bom_items = [
    {"name": "SP_A", "unit_cost": 0, "qty": 1, "components": [
        {"item": "SP_B", "qty": 2},
        {"item": "VT_01", "qty": 3},
    ]},
    {"name": "SP_B", "unit_cost": 0, "qty": 1, "components": [
        {"item": "VT_02", "qty": 1.5},
        {"item": "VT_03", "qty": 0.5},
    ]},
    {"name": "VT_01", "unit_cost": 50_000,  "qty": 1, "components": []},
    {"name": "VT_02", "unit_cost": 30_000,  "qty": 1, "components": []},
    {"name": "VT_03", "unit_cost": 80_000,  "qty": 1, "components": []},
]

# Sort theo thứ tự tính (raw materials trước, finished goods sau)
sorted_bom = topo_sort_data(
    items         = bom_items,
    id_key        = "name",
    deps_list_key = "components",  # list[{item, qty}]
    dep_id_key    = "item",
)

# Tính unit cost theo thứ tự topological
unit_costs = {}
for item in sorted_bom:
    if item["components"]:
        # Semi-finished: tổng cost từ components
        unit_costs[item["name"]] = sum(
            comp["qty"] * unit_costs.get(comp["item"], 0)
            for comp in item["components"]
        )
    else:
        # Raw material: lấy unit_cost trực tiếp
        unit_costs[item["name"]] = item["unit_cost"]

for name, cost in unit_costs.items():
    print(f"{name}: {cost:>12,.0f} VNĐ/đv")
# VT_01:       50,000 VNĐ/đv
# VT_02:       30,000 VNĐ/đv
# VT_03:       80,000 VNĐ/đv
# SP_B:        85,000 VNĐ/đv  (1.5×30K + 0.5×80K)
# SP_A:       320,000 VNĐ/đv  (2×85K + 3×50K)
```

---

## 27. Ví dụ thực tế — KPI phụ thuộc vòng

```python
from formula_utils import solve_linear_on_graph

# Bài toán: Chi phí dịch vụ nội bộ
# - Bộ phận IT cung cấp 20% dịch vụ cho HR, 10% cho Finance
# - Bộ phận HR cung cấp 5% dịch vụ cho IT
# - Finance không cung cấp cho ai

# x_IT  = 500M + 0.05 * x_HR
# x_HR  = 200M + 0.20 * x_IT
# x_Fin = 100M + 0.10 * x_IT

dept = [
    {"id": "IT",  "direct": 500_000_000,
     "serves": [{"to": "HR",  "pct": 0.20}, {"to": "Fin", "pct": 0.10}],
     "receives": [{"from": "HR", "pct": 0.05}]},
    {"id": "HR",  "direct": 200_000_000,
     "serves": [{"to": "IT", "pct": 0.05}],
     "receives": [{"from": "IT", "pct": 0.20}]},
    {"id": "Fin", "direct": 100_000_000,
     "serves": [],
     "receives": [{"from": "IT", "pct": 0.10}]},
]

def deps_fn(item):
    # node này NHẬN từ ai: [(from_id, {pct})]
    return [(r["from"], {"pct": r["pct"]}) for r in item.get("receives", [])]

def b_fn(node_id, item, resolved):
    return float(item["direct"])

def coeff_fn(edge_data):
    return float(edge_data["pct"])

def output_fn(node_id, x_val, item, resolved):
    item["total_cost"] = x_val

result = solve_linear_on_graph(
    items    = dept,
    id_fn    = lambda x: x["id"],
    deps_fn  = deps_fn,
    b_fn     = b_fn,
    coeff_fn = coeff_fn,
    output_fn= output_fn,
    max_iter_fallback = 100,
)

for d in dept:
    print(f"{d['id']:5}: {d['total_cost']:>18,.2f}")

print(f"\nHas cycle: {result.has_cycle}")
print(f"Cycle groups: {result.cycle_groups}")
# IT và HR tạo thành cycle → giải bằng Gaussian elimination
```

---

## 28. Cheat Sheet

### Khởi tạo nhanh

```python
from formula_utils import FormulaEngine

engine = FormulaEngine([
    {"name": "B", "formula": "A * 2"},
    {"name": "C", "formula": "A + B"},
])
result = engine.calculate({"A": 10})
# → {"B": 20, "C": 30}
```

### Các lỗi thường gặp

| Lỗi | Nguyên nhân | Sửa |
| --- | ----------- | ---- |
| `CIRCULAR_DEPENDENCY` | Formula A → B → A | Xem lại dependency |
| `MISSING_REQUIRED_INPUT` | Thiếu field bắt buộc | Thêm field hoặc `strict=False` |
| `SECURITY_VIOLATION` | Dùng `import`, `lambda`, `.format()` | Dùng hàm trong BASE_FUNCS |
| `UNKNOWN_FUNCTION` | Gọi hàm không có trong runtime | Thêm vào `safe_funcs` |
| `CONTEXT_NOT_INITIALIZED` | `calculate_incremental` trước `create_context` | Gọi `create_context` trước |
| `STALE_CONTEXT` | Formula set thay đổi sau khi tạo context | Tạo context mới |
| `BUDGET_EXCEEDED` | Vượt `max_operations` | Tăng limit hoặc tối ưu formula |

### Bảng hàm thường dùng nhất

```python
# Tổng hợp
sum(rows, key='amount')
average(rows, key='score')
count(rows, key='value')

# Điều kiện
IF(A > 0, A, 0)
IFS(A>100,'Cao', A>50,'TB', True,'Thấp')
SWITCH(LOAI, 'A', 10, 'B', 20, 0)
coalesce(GIA1, GIA2, 0)

# Tổng có điều kiện
sumif(rows, "IT", key=("phong","luong"))
sumifs(rows, "phong","IT","loai","CT", key="luong")
countif(rows, ">18000000", key="luong")

# Array
filter_array(rows, key='loai', value='A')
sorted_array(rows, key='ngay', reverse=True)
group_sum(rows, 'phong', 'chi_phi')
last(rows, sort_by='ngay', group_by='ma_sp', value_key='gia')

# Lookup
vlookup(MA, bang_gia, 3)
xlookup(MA, ma_list, gia_list, 0)

# Ngày
date_diff(NGAY_KT, NGAY_BD, 'days')
date_add(NGAY, months=3)
quarter(NGAY)

# Tiện ích
safe_div(A, B, 0)
clamp(X, 0, 100)
between(DIEM, 5, 10)
to_number('1,234.5')
```

### Pattern hay dùng trong formula

```python
# Tổng giá trị list[dict]
"sum(r['sl'] * r['dg'] for r in items)"

# Lọc rồi tính
"sum(r['gia'] for r in items if r['loai'] = 'A')"

# Giá mới nhất
"last(lich_su, sort_by='ngay', value_key='gia')"

# Giá mới nhất theo từng sản phẩm (group_by)
"last(lich_su, sort_by='ngay', group_by='ma_sp', value_key='gia')"

# Tra bảng giá
"vlookup(MA_HANG, BANG_GIA, 3, 0)"

# Tổng lương theo phòng IT
"sumifs(nhan_su, 'phong', 'IT', key='luong')"

# % phân phối theo nhóm
"percent_of(CHI_PHI_IT, TONG_CHI_PHI)"

# Đơn giá an toàn
"safe_div(TONG_CP, SO_LUONG)"

# Giá trị trong khoảng
"clamp(DIEM_KPI * TY_LE, 0, MAX_THUONG)"

# Label kỳ hiện tại
"get_bucket_label(NGAY_LAP, 'quarter', 'short')"

# Kiểm tra ngày trong kỳ
"in_time_bucket(NGAY_GHI, KY_BAO_CAO)"
```

---

*Tài liệu này được tạo từ mã nguồn `formula_utils.py` v28.0.0 — Engine Version: 28.0.0*
