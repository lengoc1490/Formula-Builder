# VÍ DỤ FULL: SNAPSHOT LIFECYCLE — TỪ ENGINE ĐẾN AUDIT TRAIL PERSISTENT

> **App:** Formula Builder v30.0.0 | **DocType:** Formula Snapshot | **Cơ chế:** Memory-first, Explicit-persist
>
> Tài liệu này minh họa vòng đời đầy đủ của Snapshot: từ lúc engine tính toán, snapshot được tạo **trong memory**, người dùng **submit** để persist vào DB, và sau đó **load lại** để giải trình/compare.
>
> Ví dụ dùng lại bài toán CDMQ-2C-TRANSOM từ AlumGlass để có số liệu thực tế.

---

## MỤC LỤC

1. [Bức tranh tổng thể — Memory vs DB](#1-bức-tranh-tổng-thể)
2. [Cấu trúc dữ liệu EnterpriseSnapshot (5-layer)](#2-cấu-trúc-dữ-liệu-enterprisesnapshot)
3. [Cấu trúc DocType `Formula Snapshot` trong DB](#3-cấu-trúc-doctype-formula-snapshot)
4. [Step-by-step: Tính toán → Snapshot → Submit → Load](#4-step-by-step)
5. [Ví dụ số liệu thật: Báo giá cửa CDMQ-2C](#5-ví-dụ-số-liệu-thật)
6. [Snapshot JSON thực tế được lưu trong DB](#6-snapshot-json-thực-tế)
7. [Khôi phục & Giải trình — Load snapshot cũ để compare](#7-khôi-phục--giải-trình)
8. [Các câu query thường dùng cho audit](#8-câu-query-thường-dùng)
9. [Best Practices & Bẫy cần tránh](#9-best-practices--bẫy-cần-tránh)

---

## 1. BỨC TRANH TỔNG THỂ

### 1.1. Triết lý: Memory-first, Explicit-persist

```
┌─────────────────────────────────────────────────────────────────┐
│  NGUYÊN TẮC CỐT LÕI                                             │
│                                                                 │
│  Snapshot luôn được tạo TRONG MEMORY trước (nhanh, không I/O).  │
│  CHỈ persist vào DB khi user/business logic gọi submit().       │
│  Snapshot không được submit → mất khi restart (bình thường).    │
│                                                                 │
│  LÝ DO:                                                         │
│  • Mỗi lần user gõ công thức và bấm "Validate" → 1 snapshot     │
│  • Mỗi lần thay đổi input và bấm "Calculate" → 1 snapshot       │
│  • 90% snapshot là tạm thời, chỉ để debug/xem kết quả           │
│  • 10% snapshot cần lưu: đã duyệt, baseline kỳ sau, audit       │
│  • Nếu auto-save tất cả → DB đầy trong vài ngày                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2. Dòng chảy dữ liệu tổng quát

```
  ┌──────────┐     ┌─────────────────┐     ┌──────────────────────┐
  │  User    │     │  FormulaEngine  │     │  SnapshotRegistry    │
  │  nhập    │────►│  .evaluate()    │────►│  (IN-MEMORY dict)    │
  │  formula │     │                 │     │                      │
  │  + input │     │  Trả về outputs │     │  SnapshotManager     │
  └──────────┘     └─────────────────┘     │  .create() → snap_1  │
                                           │  .create() → snap_2  │
                                           │  .create() → snap_3  │
                                           └──────────┬───────────┘
                                                      │
                                          User review: "OK, duyệt!"
                                                      │
                                                      ▼
                                           ┌──────────────────────┐
                                           │  SnapshotManager     │
                                           │  .submit(snap_2.id)  │
                                           └──────────┬───────────┘
                                                      │
                                                      ▼
                                           ┌────────────────────────┐
                                           │  Frappe DB             │
                                           │  `tabFormula Snapshot` │
                                           │                        │
                                           │  snapshot_id: "abc"    │
                                           │  engine_meta (JSON)    │
                                           │  dag_structure (JSON)  │
                                           │  formulas (JSON)       │
                                           │  business_input (JSON) │
                                           │  outputs (JSON)        │
                                           │  execution_trace (JSON)│
                                           │  payload_hash: "sha"   │
                                           └────────────────────────┘
```

### 1.3. Snapshot nào được submit?

| Tình huống | Có submit không? | Lý do |
|---|---|---|
| User gõ công thức → Validate | ❌ Không | Chỉ để check syntax, chưa có kết quả thật |
| User bấm Calculate lần 1 | ❌ Không | Đang thử nghiệm, có thể sai |
| User bấm Calculate lần 5 | ❌ Không | Vẫn đang điều chỉnh |
| Kế toán bấm "Duyệt báo giá" | ✅ CÓ | Cần audit trail cho báo giá đã gửi khách |
| Chốt giá thành kỳ này làm baseline | ✅ CÓ | Dùng để so sánh kỳ sau |
| Cuối tháng chốt sổ | ✅ CÓ | Compliance, giải trình với kiểm toán |

---

## 2. CẤU TRÚC DỮ LIỆU ENTERPRISESNAPSHOT (5-LAYER)

Mỗi EnterpriseSnapshot có 5 layer, mỗi layer phục vụ 1 mục đích audit khác nhau:

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: EngineMetaBlock                                       │
│  ─────────────────────────────────────────────────────────────  │
│  "Engine nào đã tính ra kết quả này?"                           │
│                                                                 │
│  engine_version:  "30.0.0"           # Phiên bản engine         │
│  formula_hash:    "a1b2c3d4..."      # SHA-256 của toàn bộ      │
│                                       #   formula set           │
│  formula_count:   17                  # Số công thức đã chạy    │
│  topo_order_hash: "e5f6g7h8..."      # SHA-256 của thứ tự DAG   │
│  schema_hash:     "i9j0k1l2..."      # SHA-256 của input+output │
│                                       #   schema                │
│  frozen:          True                # Deterministic mode?     │
│  captured_at:     "2026-07-26T..."    # UTC ISO timestamp       │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2a: EngineContextBlock                                   │
│  ─────────────────────────────────────────────────────────────  │
│  "Engine được cấu hình như thế nào khi chạy?"                   │
│                                                                 │
│  dag_version:      "a1b2c3d4..."     # = formula_hash           │
│  input_keys:       ["W_mm","H_mm",   # Tất cả input keys        │
│                     "n_canh","mau_nhom",...]                    │
│  output_keys:      ["khung_ngang_tren__thanh_tien",             │
│                     "kinh_tren__so_luong_don_vi",...]           │
│  rounding_policy:  {"thanh_tien":0,   # Rounding rules          │
│                     "tong_so_luong":4}                          │
│  error_mode:       "raise"            # raise | null | default  │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2b: DagStateBlock                                        │
│  ─────────────────────────────────────────────────────────────  │
│  "DAG trông như thế nào? Node nào phụ thuộc node nào?"          │
│                                                                 │
│  execution_order:  ["W_mm", "khung_ngang_tren__width",          │
│                     "khung_ngang_tren__so_luong_don_vi", ...]   │
│  dependency_edges: {"khung_ngang_tren__width": ["W_mm"],        │
│                     "kinh_tren__so_luong_don_vi":               │
│                       ["kinh_tren__width","kinh_tren__height",  │
│                        "kinh_tren__calc_pattern"], ...}         │
│  reverse_edges:    {"W_mm": ["khung_ngang_tren__width",         │
│                              "khung_ngang_duoi__width", ...],   │
│                     ...}                                        │
│  input_nodes:      ["W_mm","H_mm","n_canh",...]                 │
│  formula_nodes:    ["khung_ngang_tren__so_luong_don_vi",...]    │
│  dirty_nodes:      []                   # empty = full calc     │
│  calc_mode:        "full"               # full | incremental    │
│  input_edges:      {"W_mm": ["khung_ngang_tren__width",...],...}│
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3: ExecutionTraceBlock                                   │
│  ─────────────────────────────────────────────────────────────  │
│  "Engine đã tính từng bước như thế nào?"                        │
│                                                                 │
│  fields_evaluated: 93                 # Số field được tính      │
│  fields_skipped:   0                  # Số field skip (incr)    │
│  total_exec_ms:    12.345             # Tổng thời gian chạy     │
│  entries: [                                                     │
│    {                                                            │
│      field: "khung_ngang_tren__so_luong_don_vi",                │
│      formula: "lookup_calc_pattern(calc_pattern, width, height, │
│                trong_luong_rieng)",                             │
│      old_value: null,                  # null = lần đầu         │
│      new_value: 3.0168,                                         │
│      triggered_by: ["width","height","calc_pattern",            │
│                     "trong_luong_rieng"],                       │
│      dep_values: {                                              │
│        "width": 2400, "height": null,                           │
│        "calc_pattern": "LENGTH_TO_WEIGHT",                      │
│        "trong_luong_rieng": 1.257                               │
│      },                                                         │
│      exec_time_ms: 0.124,                                       │
│      skipped: false                                             │
│    },                                                           │
│    ... 92 entries khác                                          │
│  ]                                                              │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 4: Business Input & Outputs                              │
│  ─────────────────────────────────────────────────────────────  │
│  "Dữ liệu nghiệp vụ vào/ra — cái mà kế toán quan tâm"           │
│                                                                 │
│  business_input: {                                              │
│    "W_mm": 2400,                                                │
│    "H_mm": 2600,                                                │
│    "TransomHeight_mm": 600,                                     │
│    "n_canh": 2,                                                 │
│    "mau_nhom": "WHITE",                                         │
│    "xuat_xu_nhom": "IMPORT",                                    │
│    "do_day_nhom": 20,                                           │
│    "be_mat_nhom": "POWDER_COATED",                              │
│    "NC_SX_PCT": 0.08,                                           │
│    "NC_LD_PCT": 0.12,                                           │
│    "OH_VC_PCT": 0.03,                                           │
│    "OH_QLY_PCT": 0.03,                                          │
│    "PROFIT_MARGIN": 0.16,                                       │
│    "VAT_RATE": 0.10                                             │
│  },                                                             │
│                                                                 │
│  outputs: {                                                     │
│    "VL_NHOM": 4895431,                                          │
│    "VL_KINH": 6330980,                                          │
│    "VL_VTP": 836400,                                            │
│    "VL_PK": 2000000,                                            │
│    "TONG_VL": 14062811,                                         │
│    "TONG_NC": 2812562,                                          │
│    "TONG_OH": 928145,                                           │
│    "GIA_THANH": 17803518,                                       │
│    "GIA_BAN": 20652081,                                         │
│    "GIA_VAT": 22717289                                          │
│  }                                                              │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 5: AuditTrailBlock                                       │
│  ─────────────────────────────────────────────────────────────  │
│  "Ai tạo? Ai duyệt? Snapshot này trong chuỗi revision nào?"     │
│                                                                 │
│  tag:                "actual"         # estimate|plan|actual|   │
│                                       #   variance|void         │
│  status:             "approved"       # draft|locked|approved|  │
│                                       #   rejected|archived     │
│  created_by:         "accountant@co.com"                        │
│  approved_by:        "manager@co.com"                           │
│  parent_snapshot_id: "snap-001"       # Snapshot cha (revision) │
│  revision_chain:     ["snap-001"]     # Chuỗi đã thay thế       │
│  notes:              "Giá thành SP001 — Tháng 7/2026"           │
│  source_doc:         "QTN-2026-00042" # ERPNext docname         │
└─────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │  DUAL HASH (tính toàn vẹn)                                   │
  │                                                              │
  │  payload_hash: SHA-256(Layer1 + Layer2b + Layer4)            │
  │    → đảm bảo meta + DAG + input/output không bị sửa          │
  │                                                              │
  │  trace_hash: SHA-256(Layer3)                                 │
  │    → đảm bảo execution trace không bị sửa                    │
  │                                                              │
  │  verify() → kiểm tra payload_hash còn khớp không             │
  └──────────────────────────────────────────────────────────────┘
```

---

## 3. CẤU TRÚC DOCTYPE `FORMULA SNAPSHOT`

### 3.1. DocType JSON fields

```json
{
  "doctype": "DocType",
  "name": "Formula Snapshot",
  "module": "Formula Builder",
  "engine": "InnoDB",
  "istable": 0,
  "track_changes": 0,

  "fields": [
    {"fieldname": "snapshot_id",  "fieldtype": "Data",      "unique": 1, "label": "Snapshot ID"},
    {"fieldname": "title",        "fieldtype": "Data",       "label": "Title"},
    {"fieldname": "column_break_1","fieldtype": "Column Break"},

    {"fieldname": "tag",          "fieldtype": "Select",
     "options": "estimate\nplan\nactual\nvariance\nvoid",   "label": "Tag"},
    {"fieldname": "status",       "fieldtype": "Select",
     "options": "draft\nlocked\napproved\nrejected\narchived","label": "Status"},
    {"fieldname": "column_break_2","fieldtype": "Column Break"},

    {"fieldname": "formula_set",  "fieldtype": "Link",       "options": "Formula Set", "label": "Formula Set"},
    {"fieldname": "source_doctype","fieldtype": "Link",      "options": "DocType",     "label": "Source DocType"},
    {"fieldname": "source_doc",   "fieldtype": "Data",       "label": "Source Document"},
    {"fieldname": "section_break_1","fieldtype": "Section Break"},

    {"fieldname": "created_by",   "fieldtype": "Data",       "label": "Created By"},
    {"fieldname": "approved_by",  "fieldtype": "Data",       "label": "Approved By"},
    {"fieldname": "notes",        "fieldtype": "Small Text", "label": "Notes"},
    {"fieldname": "section_break_2","fieldtype": "Section Break"},

    {"fieldname": "engine_version","fieldtype": "Data",      "label": "Engine Version"},
    {"fieldname": "formula_count", "fieldtype": "Int",       "label": "Formula Count"},
    {"fieldname": "payload_hash",  "fieldtype": "Data",      "label": "Payload Hash"},
    {"fieldname": "trace_hash",    "fieldtype": "Data",      "label": "Trace Hash"},
    {"fieldname": "section_break_3","fieldtype": "Section Break"},

    {"fieldname": "business_input", "fieldtype": "JSON",  "label": "Business Input"},
    {"fieldname": "outputs",        "fieldtype": "JSON",  "label": "Outputs"},
    {"fieldname": "audit_trail",    "fieldtype": "JSON",  "label": "Audit Trail"},
    {"fieldname": "section_break_4","fieldtype": "Section Break"},

    {"fieldname": "execution_trace","fieldtype": "JSON",  "label": "Execution Trace",
     "description": "Full step-by-step evaluation trace"}
  ],

  "index_fields": [
    "snapshot_id", "tag", "status",
    "source_doctype", "source_doc", "formula_set", "creation"
  ]
}
```

> **Lưu ý:** Trong Frappe, `JSON` fieldtype → MariaDB `LONGTEXT` (không giới hạn size).
> Không dùng `Long Text` fieldtype vì nó bị giới hạn như `Small Text`.

### 3.2. Vì sao tách thành nhiều field JSON riêng?

Mỗi layer của EnterpriseSnapshot được lưu trong 1 field JSON riêng biệt:

| Layer | Field (JSON) | Mục đích |
|---|---|---|
| 1 | `engine_meta` | Engine version, formula hash, schema hash — tái lập được engine |
| 2a | `engine_context` | Input/output keys, rounding policy, error mode |
| 2b | `dag_structure` | Execution order, dependency edges — giải trình được thứ tự tính |
| 3 | `execution_trace` | Từng bước tính: field, formula, old→new value, dep_values |
| 4 | `business_input` + `outputs` | Dữ liệu nghiệp vụ vào/ra — query được bằng JSON_EXTRACT |
| 5 | `audit_trail` | Tag, status, created_by, revision_chain |

**Tất cả đều là `JSON` fieldtype** → MariaDB `LONGTEXT` → không giới hạn size, query được sub-field bằng `JSON_EXTRACT`.

| Mục đích | Dùng field nào | Ví dụ query |
|---|---|---|
| Khôi phục nguyên vẹn snapshot | Load tất cả JSON fields → `EnterpriseSnapshot.from_dict()` | `SnapshotManager.load(snapshot_id)` |
| Tìm tất cả báo giá có GIA_VAT > 20tr | `outputs` (JSON) | `JSON_EXTRACT(outputs, '$.GIA_VAT') > 20000000` |
| Trace từng bước tính | `execution_trace` (JSON) | Load detail view → parse entries |
| Tìm snapshot dùng màu WHITE | `business_input` (JSON) | `JSON_EXTRACT(business_input, '$.mau_nhom') = 'WHITE'` |
| Xem DAG topology | `dag_structure` (JSON) | `JSON_EXTRACT(dag_structure, '$.execution_order')` |

---

## 4. STEP-BY-STEP: TÍNH TOÁN → SNAPSHOT → SUBMIT → LOAD

Đây là flow đầy đủ, dùng code Python thực tế chạy trong Frappe:

### Bước 1: Chuẩn bị formulas & inputs

```python
from formula_builder.formula_utils import FormulaEngine, SnapshotManager, SnapshotRegistry
from formula_builder.formula_utils.types import SnapshotTag, SnapshotStatus

# ── Formulas (17 dòng BOM × 3 công thức + 14 Cost Template) ──
bom_formulas = {
    # 3 công thức dùng chung cho mỗi slug
    "khung_ngang_tren__so_luong_don_vi": "lookup_calc_pattern(calc_pattern, width, height, trong_luong_rieng)",
    "khung_ngang_tren__tong_so_luong":    "so_luong_don_vi * qty",
    "khung_ngang_tren__thanh_tien":       "tong_so_luong * don_gia",
    "khung_ngang_duoi__so_luong_don_vi": "...",
    # ... lặp lại cho 17 slug
}

cost_template_formulas = {
    "TONG_VL":   "VL_NHOM + VL_KINH + VL_VTP + VL_PK",
    "NC_SX":     "NC_SX_PCT * TONG_VL",
    "NC_LD":     "NC_LD_PCT * TONG_VL",
    "TONG_NC":   "NC_SX + NC_LD",
    "OH_VC":     "OH_VC_PCT * TONG_VL",
    "OH_QLY":    "OH_QLY_PCT * (TONG_VL + TONG_NC)",
    "TONG_OH":   "OH_VC + OH_QLY",
    "GIA_THANH": "TONG_VL + TONG_NC + TONG_OH",
    "PROFIT":    "PROFIT_MARGIN * GIA_THANH",
    "GIA_BAN":   "GIA_THANH + PROFIT",
    "VAT":       "VAT_RATE * GIA_BAN",
    "GIA_VAT":   "GIA_BAN + VAT",
}

formulas = {**bom_formulas, **cost_template_formulas}

# ── Inputs ──
inputs = {
    "W_mm": 2400, "H_mm": 2600, "TransomHeight_mm": 600, "n_canh": 2,
    "mau_nhom": "WHITE", "xuat_xu_nhom": "IMPORT",
    "do_day_nhom": 20, "be_mat_nhom": "POWDER_COATED",
    # Hằng số offset
    "OFFSET_FRAME": 48, "OFFSET_GLASS": 90,
    "OFFSET_FIXED": 50, "OFFSET_DO_NGANG": 48,
    # Tỷ lệ %
    "NC_SX_PCT": 0.08, "NC_LD_PCT": 0.12,
    "OH_VC_PCT": 0.03, "OH_QLY_PCT": 0.03,
    "PROFIT_MARGIN": 0.16, "VAT_RATE": 0.10,
    # Row literals từ B2 (đã resolve sẵn)
    "khung_ngang_tren__trong_luong_rieng": 1.257,
    "khung_ngang_tren__don_gia": 113000,
    "khung_ngang_tren__calc_pattern": "LENGTH_TO_WEIGHT",
    # ... ~80 row literals khác
}
```

### Bước 2: Chạy engine → Kết quả trong memory

```python
# Khởi tạo engine
engine = FormulaEngine(
    formulas=formulas,
    on_error="raise",
    deterministic=True,
)

# Tính toán
outputs = engine.evaluate(inputs)
# → {"khung_ngang_tren__so_luong_don_vi": 3.0168,
#    "khung_ngang_tren__thanh_tien": 340898,
#    ...,
#    "GIA_VAT": 22717289}
```

### Bước 3: Tạo snapshot TRONG MEMORY

```python
registry = SnapshotRegistry()

# Lần 1: Thử nghiệm → KHÔNG submit
snap_1 = SnapshotManager.create(
    engine, inputs, outputs,
    tag=SnapshotTag.ESTIMATE,
    status=SnapshotStatus.DRAFT,
    created_by="user@company.com",
    source_doc="QTN-2026-00042",
    notes="Thử nghiệm lần 1 — chưa có giá vận chuyển",
)
registry.register(snap_1)
# → snap_1 nằm trong registry._store (dict in-memory)
# → CHƯA có gì trong DB

# Lần 2: Sửa input, tính lại → KHÔNG submit
inputs_2 = {**inputs, "OH_VC_PCT": 0.04}  # Tăng vận chuyển lên 4%
outputs_2 = engine.evaluate(inputs_2)

snap_2 = SnapshotManager.create(
    engine, inputs_2, outputs_2,
    tag=SnapshotTag.ESTIMATE,
    status=SnapshotStatus.DRAFT,
    created_by="user@company.com",
    source_doc="QTN-2026-00042",
    notes="Thử nghiệm lần 2 — tăng VC lên 4%",
)
registry.register(snap_2)

# Lần 3: Chốt final → SUBMIT
inputs_final = {**inputs, "OH_VC_PCT": 0.03}  # Quay lại 3%
outputs_final = engine.evaluate(inputs_final)

snap_final = SnapshotManager.create(
    engine, inputs_final, outputs_final,
    tag=SnapshotTag.ACTUAL,
    status=SnapshotStatus.APPROVED,
    created_by="accountant@company.com",
    approved_by="manager@company.com",
    source_doc="QTN-2026-00042",
    notes="Chốt báo giá gửi khách — 22,717,289đ",
)
registry.register(snap_final)
```

### Bước 4: SUBMIT — Persist vào DB

```python
# Chỉ gọi submit() cho snapshot CẦN LƯU
docname = SnapshotManager.submit(
    snap_final.snapshot_id,
    registry,
    title="Báo giá CDMQ-2C — KH Nguyen Van A — T7/2026",
    notes="Đã duyệt, gửi khách ngày 26/07/2026",
    formula_set="BOM_LINE",
)

# → Lúc này trong DB:
#   tabFormula Snapshot:
#     snapshot_id: "a1b2c3d4-..."
#     engine_meta: {"engine_version": "30.0.0", ...}
#     dag_structure: {"execution_order": [...], ...}
#     formulas: {"TONG_VL": "VL_NHOM + ...", ...}
#     business_input: {"W_mm": 2400, ...}
#     outputs: {"GIA_VAT": 22717289, ...}
#     execution_trace: {"entries": [...], ...}
#     payload_hash: "e5f6g7h8..."
#     status: "approved"
#     source_doc: "QTN-2026-00042"

# snap_1 và snap_2 vẫn trong memory → sẽ mất khi restart (bình thường)
```

### Bước 5: LOAD — Khôi phục snapshot từ DB

```python
# 6 tháng sau, kiểm toán đến hỏi: "Sao hồi tháng 7 báo giá 22.7tr?"
# → Load snapshot từ DB về memory

snap_loaded = SnapshotManager.load("a1b2c3d4-...")
# → Trả về EnterpriseSnapshot object đầy đủ 5 layer

# Verify toàn vẹn dữ liệu
assert snap_loaded.verify() == True
# → True: payload_hash khớp → dữ liệu KHÔNG bị sửa từ lúc submit

# Xem lại input nghiệp vụ
print(snap_loaded.business_input["W_mm"])        # 2400
print(snap_loaded.business_input["mau_nhom"])    # WHITE

# Xem lại kết quả
print(snap_loaded.outputs["GIA_VAT"])            # 22717289
print(snap_loaded.outputs["GIA_THANH"])          # 17803518

# Xem lại engine version lúc đó
print(snap_loaded.meta.engine_version)           # "30.0.0"

# Xem lại từng bước tính (trace)
for entry in snap_loaded.exec_trace.entries:
    if not entry.skipped:
        print(f"{entry.field}: {entry.old_value} → {entry.new_value}")

# Compare với snapshot hiện tại (nếu giá đã thay đổi)
current_snap = SnapshotManager.create(engine, inputs, current_outputs, ...)
diff = SnapshotManager.compare_snapshots(
    snap_loaded,  # snapshot cũ từ DB
    current_snap,  # snapshot mới vừa tính
)
print(diff["outputs_changed"])  # {"GIA_VAT": {"before": 22717289, "after": 24120345}}
```

---

## 5. VÍ DỤ SỐ LIỆU THẬT: BÁO GIÁ CỬA CDMQ-2C

### 5.1. Input nghiệp vụ

```
W_mm = 2400          H_mm = 2600          TransomHeight_mm = 600
n_canh = 2           mau_nhom = WHITE      xuat_xu_nhom = IMPORT
do_day_nhom = 20     be_mat_nhom = POWDER_COATED

Hằng số: OFFSET_FRAME=48, OFFSET_GLASS=90, OFFSET_FIXED=50, OFFSET_DO_NGANG=48
Tỷ lệ: NC_SX=8%, NC_LD=12%, OH_VC=3%, OH_QLY=3%, PROFIT=16%, VAT=10%
```

### 5.2. Engine chạy → Outputs từng bước

**BOM Items (17 dòng)** — chỉ hiển thị các dòng đại diện:

| slug | width (mm) | qty | so_luong_don_vi | don_gia | thanh_tien |
|---|---|---|---|---|---|
| khung_ngang_tren | 2400 | 1 | 3.0168 kg | 113,000 | 340,898 |
| do_ngang | 2304 | 1 | 2.8961 kg | 113,000 | 327,259 |
| canh_ngang | 1152 | 4 | 1.5552 kg | 113,000 | 702,950 |
| kinh_tren | 2300×550 | 1 | 1.265 m² | 1,150,000 | 1,454,750 |
| nep_kinh_tren | 5700 (cross-row) | 2 | 1.7784 kg | 113,000 | 401,918 |
| keo_tren | 5700 (cross-row) | 1 | 5.7 m | 45,000 | 256,500 |
| ban_le | — | 8 | 1 cái | 180,000 | 1,440,000 |

**Cost Buckets (B5):**

| Bucket | Tổng |
|---|---|
| VL_NHOM | 4,895,431 |
| VL_KINH | 6,330,980 |
| VL_VTP | 836,400 |
| VL_PK | 2,000,000 |

**Cost Template (B6):**

| # | Biến | Công thức | Kết quả |
|---|---|---|---|
| 1 | TONG_VL | 4,895,431+6,330,980+836,400+2,000,000 | 14,062,811 |
| 2 | NC_SX | 0.08×14,062,811 | 1,125,025 |
| 3 | NC_LD | 0.12×14,062,811 | 1,687,537 |
| 4 | TONG_NC | 1,125,025+1,687,537 | 2,812,562 |
| 5 | OH_VC | 0.03×14,062,811 | 421,884 |
| 6 | OH_QLY | 0.03×(14,062,811+2,812,562) | 506,261 |
| 7 | TONG_OH | 421,884+506,261 | 928,145 |
| 8 | GIA_THANH | 14,062,811+2,812,562+928,145 | 17,803,518 |
| 9 | PROFIT | 0.16×17,803,518 | 2,848,563 |
| 10 | GIA_BAN | 17,803,518+2,848,563 | 20,652,081 |
| 11 | VAT | 0.10×20,652,081 | 2,065,208 |
| 12 | GIA_VAT | 20,652,081+2,065,208 | **22,717,289** |

### 5.3. Snapshot được submit vào DB

```python
# Code thực tế chạy trong BomOrchestrator B7
snap = SnapshotManager.create(
    engine=engine,
    inputs=inputs_final,
    outputs={"VL_NHOM": 4895431, ..., "GIA_VAT": 22717289},
    tag=SnapshotTag.ACTUAL,
    status=SnapshotStatus.APPROVED,
    created_by="accountant@alumglass.com",
    approved_by="manager@alumglass.com",
    source_doc="QTN-2026-00042",
    notes="Cửa CDMQ-2C — KH Nguyen Van A — 2400×2600, WHITE/IMPORT",
)

registry.register(snap)

# SUBMIT — chỉ dòng này mới ghi DB
SnapshotManager.submit(
    snap.snapshot_id, registry,
    title="Báo giá CDMQ-2C #QTN-2026-00042 (Final)",
    formula_set="BOM_LINE",
)
```

---

## 6. DỮ LIỆU SNAPSHOT THỰC TẾ ĐƯỢC LƯU TRONG DB

Đây là dữ liệu được tái tạo từ các field JSON (`engine_meta`, `dag_structure`, `formulas`, `business_input`, `outputs`, `execution_trace`, `audit_trail`) khi gọi `SnapshotManager.load()`. **Đã rút gọn** (chỉ hiển thị 3 trong 93 trace entries, 3 trong 17 dòng BOM) — cấu trúc đầy đủ giống hệt, chỉ khác số lượng.

```json
{
  "snapshot_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2026-07-26T09:15:30.123456+00:00",

  "meta": {
    "engine_version": "30.0.0",
    "formula_hash": "sha256$7f83b165...",
    "formula_count": 107,
    "topo_order_hash": "sha256$a12b3c4d...",
    "schema_hash": "sha256$e5f6g7h8...",
    "frozen": true,
    "captured_at": "2026-07-26T09:15:30.123456+00:00"
  },

  "engine_context": {
    "dag_version": "sha256$7f83b165...",
    "input_keys": ["H_mm","NC_LD_PCT","NC_SX_PCT","OH_QLY_PCT","OH_VC_PCT",
                   "OFFSET_DO_NGANG","OFFSET_FIXED","OFFSET_FRAME","OFFSET_GLASS",
                   "PROFIT_MARGIN","TransomHeight_mm","VAT_RATE","W_mm","be_mat_nhom",
                   "do_day_nhom","mau_nhom","n_canh","xuat_xu_nhom",
                   "khung_ngang_tren__calc_pattern","khung_ngang_tren__don_gia",
                   "khung_ngang_tren__trong_luong_rieng", "...60 keys more"],
    "output_keys": ["GIA_BAN","GIA_THANH","GIA_VAT","NC_LD","NC_SX","OH_QLY",
                    "OH_VC","PROFIT","TONG_NC","TONG_OH","TONG_VL","VAT",
                    "VL_KINH","VL_NHOM","VL_PK","VL_VTP",
                    "khung_ngang_tren__so_luong_don_vi","khung_ngang_tren__thanh_tien",
                    "khung_ngang_tren__tong_so_luong","khung_ngang_tren__width",
                    "...80 keys more"],
    "rounding_policy": {"thanh_tien": 0, "tong_so_luong": 4},
    "error_mode": "raise"
  },

  "dag_state": {
    "execution_order": [
      "W_mm",
      "khung_ngang_tren__width",
      "khung_ngang_tren__qty",
      "kinh_tren__width",
      "kinh_tren__height",
      "kinh_tren__qty",
      "khung_ngang_tren__so_luong_don_vi",
      "khung_ngang_tren__tong_so_luong",
      "khung_ngang_tren__thanh_tien",
      "...",
      "VL_NHOM",
      "TONG_VL",
      "NC_SX",
      "TONG_NC",
      "GIA_THANH",
      "GIA_BAN",
      "GIA_VAT"
    ],
    "dependency_edges": {
      "khung_ngang_tren__width": ["W_mm"],
      "khung_ngang_tren__so_luong_don_vi": [
        "khung_ngang_tren__width",
        "khung_ngang_tren__height",
        "khung_ngang_tren__calc_pattern",
        "khung_ngang_tren__trong_luong_rieng"
      ],
      "khung_ngang_tren__thanh_tien": [
        "khung_ngang_tren__tong_so_luong",
        "khung_ngang_tren__don_gia"
      ],
      "nep_kinh_tren__width": [
        "kinh_tren__width",
        "kinh_tren__height"
      ],
      "GIA_VAT": ["GIA_BAN", "VAT"]
    },
    "reverse_edges": {
      "W_mm": ["khung_ngang_tren__width","khung_ngang_duoi__width",
               "khung_dung__width","do_ngang__width","canh_ngang__width",
               "kinh_tren__width","kinh_duoi__width"],
      "kinh_tren__width": ["kinh_tren__so_luong_don_vi","nep_kinh_tren__width",
                           "keo_tren__width"],
      "kinh_tren__height": ["kinh_tren__so_luong_don_vi","nep_kinh_tren__width",
                            "keo_tren__width"]
    },
    "input_nodes": ["W_mm","H_mm","n_canh","OFFSET_FRAME","mau_nhom", "...14 more"],
    "formula_nodes": ["khung_ngang_tren__so_luong_don_vi","GIA_VAT", "...91 more"],
    "dirty_nodes": [],
    "calc_mode": "full",
    "input_edges": {
      "W_mm": ["khung_ngang_tren__width","khung_ngang_duoi__width",
               "khung_dung__width","do_ngang__width","canh_ngang__width",
               "kinh_tren__width","kinh_duoi__width"]
    }
  },

  "exec_trace": {
    "fields_evaluated": 93,
    "fields_skipped": 0,
    "total_exec_ms": 12.345,
    "entries": [
      {
        "field": "khung_ngang_tren__so_luong_don_vi",
        "formula": "lookup_calc_pattern(calc_pattern, width, height, trong_luong_rieng)",
        "old_value": null,
        "new_value": 3.0168,
        "triggered_by": ["width","height","calc_pattern","trong_luong_rieng"],
        "dep_values": {
          "width": 2400,
          "height": null,
          "calc_pattern": "LENGTH_TO_WEIGHT",
          "trong_luong_rieng": 1.257
        },
        "exec_time_ms": 0.124,
        "skipped": false
      },
      {
        "field": "nep_kinh_tren__width",
        "formula": "2 * (items.kinh_tren.width + items.kinh_tren.height)",
        "old_value": null,
        "new_value": 5700,
        "triggered_by": ["kinh_tren__width","kinh_tren__height"],
        "dep_values": {
          "kinh_tren__width": 2300,
          "kinh_tren__height": 550
        },
        "exec_time_ms": 0.089,
        "skipped": false
      },
      {
        "field": "GIA_VAT",
        "formula": "GIA_BAN + VAT",
        "old_value": null,
        "new_value": 22717289,
        "triggered_by": ["GIA_BAN","VAT"],
        "dep_values": {
          "GIA_BAN": 20652081,
          "VAT": 2065208
        },
        "exec_time_ms": 0.045,
        "skipped": false
      }
    ]
  },

  "business_input": {
    "W_mm": 2400,
    "H_mm": 2600,
    "TransomHeight_mm": 600,
    "n_canh": 2,
    "mau_nhom": "WHITE",
    "xuat_xu_nhom": "IMPORT",
    "do_day_nhom": 20,
    "be_mat_nhom": "POWDER_COATED",
    "OFFSET_FRAME": 48,
    "OFFSET_GLASS": 90,
    "OFFSET_FIXED": 50,
    "OFFSET_DO_NGANG": 48,
    "NC_SX_PCT": 0.08,
    "NC_LD_PCT": 0.12,
    "OH_VC_PCT": 0.03,
    "OH_QLY_PCT": 0.03,
    "PROFIT_MARGIN": 0.16,
    "VAT_RATE": 0.10
  },

  "outputs": {
    "khung_ngang_tren__thanh_tien": 340898,
    "khung_ngang_duoi__thanh_tien": 340898,
    "khung_dung__thanh_tien": 738613,
    "do_ngang__thanh_tien": 327259,
    "canh_ngang__thanh_tien": 702950,
    "canh_dung__thanh_tien": 1191110,
    "kinh_tren__thanh_tien": 1454750,
    "kinh_duoi__thanh_tien": 4876230,
    "nep_kinh_tren__thanh_tien": 401918,
    "nep_kinh_duoi__thanh_tien": 851785,
    "keo_tren__thanh_tien": 256500,
    "keo_duoi__thanh_tien": 543600,
    "gioang__thanh_tien": 12500,
    "vit__thanh_tien": 23800,
    "tay_nam__thanh_tien": 210000,
    "khoa__thanh_tien": 350000,
    "ban_le__thanh_tien": 1440000,
    "VL_NHOM": 4895431,
    "VL_KINH": 6330980,
    "VL_VTP": 836400,
    "VL_PK": 2000000,
    "TONG_VL": 14062811,
    "NC_SX": 1125025,
    "NC_LD": 1687537,
    "TONG_NC": 2812562,
    "OH_VC": 421884,
    "OH_QLY": 506261,
    "TONG_OH": 928145,
    "GIA_THANH": 17803518,
    "PROFIT": 2848563,
    "GIA_BAN": 20652081,
    "VAT": 2065208,
    "GIA_VAT": 22717289
  },

  "audit_trail": {
    "tag": "actual",
    "status": "approved",
    "created_by": "accountant@alumglass.com",
    "approved_by": "manager@alumglass.com",
    "parent_snapshot_id": null,
    "revision_chain": [],
    "notes": "Cửa CDMQ-2C — KH Nguyen Van A — 2400×2600, WHITE/IMPORT",
    "source_doc": "QTN-2026-00042"
  },

  "payload_hash": "e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2",
  "trace_hash": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
}
```

---

## 7. KHÔI PHỤC & GIẢI TRÌNH — LOAD SNAPSHOT CŨ ĐỂ COMPARE

### 7.1. Scenario: Kiểm toán hỏi "Tại sao tháng 7 báo giá 22.7tr mà tháng 12 báo 25.1tr?"

```python
# ── Load snapshot tháng 7 từ DB ──
snap_july = SnapshotManager.load("a1b2c3d4-...")
assert snap_july.verify()  # True → dữ liệu nguyên vẹn

# ── Tính lại với giá hiện tại ──
inputs_dec = {
    **snap_july.business_input,
    # Giá nhôm thay đổi: 113,000 → 128,000
    "khung_ngang_tren__don_gia": 128000,
    "canh_ngang__don_gia": 128000,
    # ... tất cả dòng nhôm đều tăng giá
}
engine = FormulaEngine(formulas_from_snapshot(snap_july), ...)
outputs_dec = engine.evaluate(inputs_dec)

# ── Compare ──
snap_dec_immutable = SnapshotManager.create_snapshot(
    inputs_dec, outputs_dec
)

diff = SnapshotManager.compare_snapshots(
    snap_july,       # ← ImmutableSnapshot from DB
    snap_dec_immutable,
)

# ── Kết quả diff ──
print(diff["summary"])
# {
#   "inputs_changed_count": 10,    # 10 dòng nhôm đổi giá
#   "outputs_changed_count": 14,   # 10 dòng thanh_tien + TONG_VL, GIA_THANH, GIA_BAN, GIA_VAT
# }

print(diff["outputs_changed"]["GIA_VAT"])
# {"before": 22717289, "after": 25120345}

print(diff["inputs_changed"]["khung_ngang_tren__don_gia"])
# {"before": 113000, "after": 128000}

# ── Giải trình ──
# "Giá nhôm Xingfa WHITE/IMPORT/20micron tăng từ 113,000đ/kg (T7)
#  lên 128,000đ/kg (T12), kéo GIA_VAT từ 22.7tr → 25.1tr"
```

### 7.2. Trace từng bước tính để giải trình chi tiết

```python
# Load snapshot
snap = SnapshotManager.load("a1b2c3d4-...")

# In ra toàn bộ chuỗi tính toán cho dòng "nep_kinh_tren"
for entry in snap.exec_trace.entries:
    if entry.field.startswith("nep_kinh_tren"):
        print(f"\n{'='*60}")
        print(f"Field:    {entry.field}")
        print(f"Formula:  {entry.formula}")
        print(f"Result:   {entry.old_value} → {entry.new_value}")
        print(f"Deps:     {entry.dep_values}")
        print(f"Time:     {entry.exec_time_ms:.3f}ms")

# Output:
# ============================================================
# Field:    nep_kinh_tren__width
# Formula:  2 * (items.kinh_tren.width + items.kinh_tren.height)
# Result:   None → 5700
# Deps:     {'kinh_tren__width': 2300, 'kinh_tren__height': 550}
# Time:     0.089ms
# ============================================================
# Field:    nep_kinh_tren__so_luong_don_vi
# Formula:  lookup_calc_pattern(calc_pattern, width, height, trong_luong_rieng)
# Result:   None → 1.7784
# Deps:     {'width': 5700, 'height': None, 'calc_pattern': 'LENGTH_TO_WEIGHT', 'trong_luong_rieng': 0.312}
# Time:     0.105ms
# ============================================================
# Field:    nep_kinh_tren__tong_so_luong
# Formula:  so_luong_don_vi * qty
# Result:   None → 3.5568
# Deps:     {'so_luong_don_vi': 1.7784, 'qty': 2}
# Time:     0.032ms
# ============================================================
# Field:    nep_kinh_tren__thanh_tien
# Formula:  tong_so_luong * don_gia
# Result:   None → 401918
# Deps:     {'tong_so_luong': 3.5568, 'don_gia': 113000}
# Time:     0.028ms
```

### 7.3. Revision Chain (nếu snapshot bị sửa nhiều lần)

```python
# T7: Báo giá lần đầu → submit
snap_v1 = SnapshotManager.create(..., notes="Báo giá lần 1", ...)
registry.register(snap_v1)
SnapshotManager.submit(snap_v1.snapshot_id, registry, title="CDMQ-2C v1")

# T7: Khách yêu cầu đổi màu DARK → tạo revision
inputs_v2 = {**inputs, "mau_nhom": "DARK"}
outputs_v2 = engine.evaluate(inputs_v2)

snap_v2 = SnapshotManager.create(
    engine, inputs_v2, outputs_v2,
    tag=SnapshotTag.ACTUAL,
    status=SnapshotStatus.APPROVED,
    created_by="accountant@co.com",
    approved_by="manager@co.com",
    parent_snapshot=snap_v1,              # ← Trỏ về bản cũ
    revision_chain=[snap_v1.snapshot_id],  # ← Chuỗi revision
    notes="Đổi màu WHITE→DARK theo yêu cầu KH",
)
registry.register(snap_v2)
SnapshotManager.submit(snap_v2.snapshot_id, registry, title="CDMQ-2C v2 (DARK)")

# ── Xem lịch sử revision ──
history = registry.revision_history(snap_v2.snapshot_id)
# → [snap_v1, snap_v2]

for s in history:
    print(f"{s.snapshot_id[:8]} | {s.audit_trail.notes} | {s.created_at}")
# a1b2c3d4 | Báo giá lần 1                         | 2026-07-26T09:15
# f9e8d7c6 | Đổi màu WHITE→DARK theo yêu cầu KH     | 2026-07-26T14:22
```

---

## 8. CÂU QUERY THƯỜNG DÙNG CHO AUDIT

### 8.1. Tìm tất cả snapshot của 1 báo giá

```sql
SELECT snapshot_id, title, tag, status, engine_version, creation
FROM `tabFormula Snapshot`
WHERE source_doc = 'QTN-2026-00042'
ORDER BY creation DESC;
```

### 8.2. Tìm snapshot có GIA_VAT > 20tr (dùng JSON_EXTRACT trên MySQL)

```sql
SELECT snapshot_id, title,
       JSON_EXTRACT(outputs, '$.GIA_VAT') AS gia_vat,
       JSON_EXTRACT(business_input, '$.mau_nhom') AS mau_nhom,
       creation
FROM `tabFormula Snapshot`
WHERE JSON_EXTRACT(outputs, '$.GIA_VAT') > 20000000
  AND tag = 'actual'
ORDER BY creation DESC;
```

### 8.3. Tìm snapshot dùng màu WHITE, nhập khẩu

```sql
SELECT snapshot_id, title, source_doc,
       JSON_EXTRACT(business_input, '$.mau_nhom') AS mau,
       JSON_EXTRACT(business_input, '$.xuat_xu_nhom') AS xuat_xu
FROM `tabFormula Snapshot`
WHERE JSON_EXTRACT(business_input, '$.mau_nhom') = 'WHITE'
  AND JSON_EXTRACT(business_input, '$.xuat_xu_nhom') = 'IMPORT'
ORDER BY creation DESC;
```

### 8.4. Đếm số snapshot theo tag

```sql
SELECT tag, COUNT(*) AS cnt
FROM `tabFormula Snapshot`
WHERE creation >= '2026-07-01'
GROUP BY tag;
```

### 8.5. Tìm snapshot đã approved nhưng chưa có approved_by

```sql
SELECT snapshot_id, title, created_by, creation
FROM `tabFormula Snapshot`
WHERE status = 'approved'
  AND (approved_by IS NULL OR approved_by = '');
```

### 8.6. Kiểm tra toàn vẹn — payload_hash có khớp không

```python
# Python script định kỳ (cron job) để phát hiện snapshot bị sửa
for doc in frappe.get_all("Formula Snapshot", fields=["snapshot_id"]):
    snap = SnapshotManager.load(doc.snapshot_id)
    if not snap.verify():
        frappe.log_error(
            f"Snapshot {doc.snapshot_id}: PAYLOAD HASH MISMATCH — dữ liệu đã bị sửa!"
        )
```

---

## 9. BEST PRACTICES & BẪY CẦN TRÁNH

| # | Bẫy | Vì sao | Cách tránh |
|---|---|---|---|
| 1 | **Auto-submit mọi snapshot** | Mỗi lần user gõ công thức → 1 snapshot. Nếu auto-save: 1000 snapshot/ngày × 50KB = 50MB/ngày → DB đầy sau 1 tháng | Chỉ gọi `submit()` khi user bấm nút "Duyệt"/"Chốt", hoặc khi business logic xác nhận |
| 2 | **Không gọi verify() sau khi load** | Snapshot có thể bị ai đó sửa trực tiếp trong DB (admin có quyền) → payload_hash không còn khớp → dữ liệu không đáng tin | Luôn `assert snap.verify()` trước khi dùng snapshot để audit/compare |
| 3 | **Chỉ lưu outputs, không lưu inputs** | 6 tháng sau không biết "giá nhôm lúc đó là bao nhiêu" → không giải trình được chênh lệch | Luôn lưu cả `business_input` — đó là bằng chứng cho thấy "với input này, engine ra output kia" |
| 4 | **Không lưu engine_version** | Sau này nâng cấp engine (vd: sửa rounding logic, đổi cách parse DAG) → snapshot cũ load lên tính ra kết quả khác → không giải thích được | `engine_version` trong `meta` cho phép tái lập chính xác: "snapshot này được tính bởi engine v30.0.0" |
| 5 | **Không lưu DAG state (execution_order + edges)** | Khi audit hỏi "sao biến X được tính trước biến Y?" — không có DAG thì không trả lời được | `dag_state` ghi lại toàn bộ topology lúc chạy → giải trình được thứ tự tính |
| 6 | **Chỉ lưu trace mà không lưu dep_values** | Có trace "nep_kinh_tren__width = 5700" nhưng không biết 5700 từ đâu ra | Mỗi TraceEntry có `dep_values` — biết chính xác từng dependency có giá trị bao nhiêu lúc tính |
| 7 | **Snapshot quá lớn vì lưu cả trace 1000 node** | Mỗi TraceEntry ~200 bytes → 1000 entries = 200KB → query chậm | Với BOM lớn, chỉ bật trace ở `AuditLevel.WARNING` trở lên, hoặc sampling trace 10% entries |
| 8 | **Không có unique constraint trên snapshot_id** | 2 lần submit cùng 1 snapshot_id → 2 record → load() không biết lấy cái nào | `snapshot_id` field có `unique: 1` trong DocType |

---

## TÓM TẮT MỘT TRANG (CHEAT-SHEET)

```
╔══════════════════════════════════════════════════════════════════╗
║  SNAPSHOT LIFECYCLE — MEMORY-FIRST, EXPLICIT-PERSIST             ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  CREATE (memory):                                                ║
║    snap = SnapshotManager.create(engine, inputs, outputs,        ║
║           tag=ACTUAL, status=DRAFT, created_by="user", ...)      ║
║    registry.register(snap)                                       ║
║    → NẰM TRONG MEMORY, chưa vào DB                               ║
║                                                                  ║
║  SUBMIT (persist):                                               ║
║    SnapshotManager.submit(snap.snapshot_id, registry,            ║
║           title="Báo giá #042", formula_set="BOM_LINE")        ║
║    → GHI VÀO DB: tabFormula Snapshot                             ║
║                                                                  ║
║  LOAD (restore):                                                 ║
║    snap = SnapshotManager.load("snapshot-id")                    ║
║    assert snap.verify()  # Kiểm tra toàn vẹn                     ║
║    → CÓ ĐẦY ĐỦ 5 LAYER: meta, context, DAG, trace, audit         ║
║                                                                  ║
║  COMPARE (audit):                                                ║
║    diff = SnapshotManager.compare_snapshots(old, new)            ║
║    → INPUTS_CHANGED + OUTPUTS_CHANGED                            ║
║                                                                  ║
║  DB STRUCTURE (tất cả data field là JSON → MariaDB LONGTEXT):    ║
║    tabFormula Snapshot                                           ║
║      snapshot_id       VARCHAR (unique) — PK lookup              ║
║      engine_meta       JSON  — Engine version, hash, frozen      ║
║      engine_context    JSON  — Input/output keys, error mode     ║
║      dag_structure     JSON  — Execution order, edges            ║
║      formulas          JSON  — Full formula dictionary           ║
║      business_input    JSON  — Để query nhanh                    ║
║      outputs           JSON  — Để query nhanh                    ║
║      execution_trace   JSON  — Full step-by-step trace           ║
║      audit_trail       JSON  — Tag, status, revision chain       ║
║      payload_hash      VARCHAR — Integrity check                 ║
║      tag, status, source_doc, ...  — Filter/Sort                 ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

*Tài liệu dựa trên dữ liệu thật từ AlumGlass CDMQ-2C-TRANSOM (xem AlumGlass_Vi_Du_Full_Chi_Tiet.md) và kiến trúc Formula Builder v30.0.0.*
