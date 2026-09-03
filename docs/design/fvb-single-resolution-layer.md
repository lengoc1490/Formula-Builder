# ADR: FVB — Single Resolution Layer cho Formula Builder

> **Status:** ✅ Approved — Owner duyệt 2026-08-31, không cần chỉnh. Quyết định triển khai:
> **dừng ở design**, chưa triển khai (Phase 0-4 trong §6 chờ kế hoạch/app cụ thể).
> **Date:** 2026-08-31
> **Author:** SA1
> **Reviewer:** Elon + Owner (2026-08-31)
> **Scope:** formula_builder (platform) + alumglass (app tiêu biểu)
> **Liên quan:** `docs/fb_source_type_contract.md`, `alumglass/docs/design/fvb-seed.md`,
> `alumglass/docs/quotation-pricing-flow.md` (§2.2, §6)
> **Trạng thái triển khai:** chưa có code change — design note thuần túy.

---

## 1. Bối cảnh & vấn đề

### 1.1 Ba câu hỏi của Owner (2026-08-31)

1. **Q1 — Formula Builder có cần xây thêm doctype để mapping "biến nào → từ doctype nào →
   giá trị nào" không**, hay để logic hiện tại (app nghiệp vụ tự định nghĩa)?
2. **Q2 — Formula Variable Binding (FVB) dùng như thế nào, các source_type có tác dụng
   gì, đã linh hoạt chưa?**
3. **Q3 — Làm thế nào để không làm đi làm lại nhiều lần** (chống duplication giữa
   platform và app nghiệp vụ)?

### 1.2 Hiện trạng duplication (bằng chứng từ code)

- **AL Variable Library đang giữ 2 vai trò cùng lúc** trong alumglass:
  - *Catalog* (đúng chỗ): `var_label`, `var_type`, `link_doctype`, `select_options`,
    `default_value`, `is_system` — nơi định nghĩa *ý nghĩa* biến.
  - *Resolution* (trùng với FVB): `source_doctype` + `source_field` — nơi định nghĩa
    *cách lấy giá trị*. Engine `bom_orchestrator._resolve_system_variables()` (B1.3)
    đọc 2 field này để resolve runtime; `get_formula_context()` trong
    `alumglass/api/__init__.py` cũng đọc chúng để mô tả biến.
- **Patch D3 `seed_fvb_from_variable_library`** (alumglass/patches/v28_9) phải *bridge*
  2 nơi: đọc `source_doctype/source_field` từ Variable Library, rồi ghi lại thành
  `source_type="linked_doctype_field"` + `source_config={link_field, target_doctype,
  target_field}` vào FVB. Cùng một thông tin "biến X → doctype Y → field Z" tồn tại ở
  2 bảng — đó là duplication.
- **Hai đường runtime song song**: B1.3 (`_resolve_system_variables` — Variable Library)
  và B1.4 (`_resolve_fb_context` — FVB qua `get_live_context`) **đều chạy trong cùng
  một flow**, theo thứ tự merge 1.3 → 1.4. Không phải "dữ liệu trùng" mà là "2 nguồn
  resolve cùng lúc". Đây là lý do lộ trình phải đi từng bước (xem §6).
- **FVB pricing chưa seed**: `quotation-pricing-flow.md` §2.2 ghi rõ dòng
  `Formula Variable Binding | *(D3 — chưa seed)*`. D3 chỉ seed system vars của 2
  doctype (AL Profile System, AL Product Type) + global constants — pricing
  (`composite_key_lookup`/`aluminum_price_composite`) chưa có binding nào, nên B2
  pricing vẫn chạy fallback `_fetch_composite_prices` cũ.

### 1.3 Một gap mới phát hiện khi rà code (chưa từng được ghi nhận)

DocType `Formula Variable Binding` khai báo `source_type` là **Select tĩnh với chỉ
13 option** (10 source type Phase 1 + 3 source type Phase 2), trong khi registry đã có
**17 source type built-in** + **3 source type custom của alumglass**. 4 source type
built-in mới (`matrix_lookup`, `reuse_formula_result`, `composite_key_lookup`,
`aggregate_from_items`) **không có trong dropdown của Form chuẩn** — muốn dùng phải
tạo bằng patch hoặc insert thủ công. Tương tự mọi custom source type của app.
→ Đây là bằng chứng cụ thể nhất cho thấy **thiếu FVB Admin UI / ít nhất là thiếu
dropdown động**, chứ không phải thiếu schema hay thiếu engine.

---

## 2. Trả lời Q1 — KHÔNG cần thêm doctype mapping mới

FVB đã là mapping layer hoàn chỉnh. Mỗi record trả lời đủ 3 câu hỏi của Owner:

| Câu hỏi | Field trên FVB | Ghi chú |
| --- | --- | --- |
| **Biến nào** | `variable_name` | Tên duy nhất dùng trong formula |
| **Từ đâu** | `source_type` + `source_config` | Loại nguồn + config (JSON, validated theo `config_schema`) |
| **Giá trị nào** | `data_type` + `default_value` | Kiểu cast + fallback khi resolve fail |
| (Scope) cho ai | `applies_to_doctype` + `applies_to_field` | Global (`""`) hoặc theo doctype + field |
| (Ưu tiên) | `resolve_priority` | Thứ tự resolve (topological sort theo dependency) |
| (Bật/tắt) | `is_active`, `is_global` | Filter khi `get_live_context` đọc DB |
| (Batch) | `batch_group` | Gộp binding vào 1 batch query (fingerprint tường minh) |

Một doctype mapping generic ("biến → doctype → field") chỉ là **tập con của FVB**:
nó không bắt được các nguồn không phải doc-read (constant, query, composite, pipeline,
custom_function...). Xây doctype mới = tái tạo FVB một cách nghèo nàn hơn, rồi lại phải
bridge về FVB ở runtime — đúng kiểu duplication đang muốn tránh.

**Kết luận Q1:** giữ FVB làm mapping layer. Nhiệm vụ đúng của platform không phải là
thêm doctype, mà là (a) làm cho FVB dùng được bằng UI (dropdown source_type động +
form config theo `config_schema`), và (b) thu hồi phần resolution đang nằm rải rác
trong app nghiệp vụ về FVB.

---

## 3. Trả lời Q2 — Toàn bộ 17 source_type built-in

Nguồn chính xác: `formula_builder/api/data_source_registry.py` (`_register_all_to_central_registry`
+ Phase 3 / FB-1 revised). Ngoài 17 built-in, app nghiệp vụ tự đăng ký qua
`@register_source` (alumglass đã đăng ký `aluminum_price_composite`, `glass_master_data`,
`cost_bucket_aggregate` — deprecated). Mọi type đều có `config_schema` (validate),
phần lớn có `batchable` + `fingerprint_fn`, một số có `supports_transform`/`supports_cache`.

### Nhóm A — Literal & System (không cần doc context)

| source_type | Dùng khi nào | Linh hoạt | Hạn chế |
| --- | --- | --- | --- |
| `constant` | Hằng số, hệ số, VAT... | Cao (đơn giản, cast theo data_type) | Không động được theo doc |
| `global_default` | Đọc 1 giá trị từ Global Defaults | Trung bình | Chỉ đọc được settings key |
| `session_variable` | user, roles, company, today, now, lang | Thấp | Enum cố định 7 key |

### Nhóm B — Đọc doc liên kết (cần doc context)

| source_type | Dùng khi nào | Linh hoạt | Hạn chế |
| --- | --- | --- | --- |
| `linked_doctype_field` | Đọc **1 field** từ doc liên kết (workhorse — D3 dùng cho system vars) | **Rất cao**, batchable ✅ | Cần `link_field` tồn tại trên doc scope |
| `whole_doctype` | Trả **toàn bộ** doc liên kết thành Object (multi-field) | Cao, batchable ✅ | Trả dict — chỉ dùng được trong `computed`/formula |
| `child_table_aggregate` | sum/avg/min/max/count/list trên child table + `filter_expr` | Cao | `filter_expr` phụ thuộc whitelist hàm trong Settings |
| `dynamic_link` | Target doctype **động** từ field (Dynamic Link pattern) | Trung bình | Không batch |

### Nhóm C — Query & phái sinh

| source_type | Dùng khi nào | Linh hoạt | Hạn chế |
| --- | --- | --- | --- |
| `doctype_query` | Query bất kỳ doctype + filters (template `{doc.x}`/`{resolved.x}`) + aggregate first/last/count/list/sum | **Rất cao** — "most flexible built-in", batchable ✅ | Batch chỉ tối ưu cho `aggregate="first"` (xem code batch) |
| `computed` | Biến phái sinh = formula dùng resolved vars (DAG, topo sort) | Cao | Không có cache riêng |

### Nhóm D — Composite không cần code (v31 Phase 2)

| source_type | Dùng khi nào | Linh hoạt | Hạn chế |
| --- | --- | --- | --- |
| `pipeline` | Chain nhiều bước: output step N → input step N+1 | Cao, batchable ✅ (outer) | **Inner steps chạy tuần tự, không batch-optimize** |
| `conditional` | Rẽ nhánh theo runtime condition (Python expr, safe_eval) | Cao | **Inner branch source resolve từng binding riêng, không batch** |
| `fallback_chain` | Resilience: primary → fallback → default | Cao | **Inner link resolve từng cái, không batch**; log ồn khi chain exhaust |

### Nhóm E — Ma trận / tra cứu (Phase 3 + FB-1 revised)

| source_type | Dùng khi nào | Linh hoạt | Hạn chế |
| --- | --- | --- | --- |
| `matrix_lookup` | Ma trận 2D (row_key, col_key, fallback row/col, `{{row.x}}` templates) | Cao, batchable ✅ | 2 trục cố định |
| `composite_key_lookup` | Ma trận **N-chiều**: `key_fields` động, `fallback_keys` (rút dần chiều), `match_mode` exact / case_insensitive / **multiplier_chain** | **Rất cao** — `matrix_lookup` là special case | Config phức tạp hơn |
| `aggregate_from_items` | SUMIF-style trên rows từ `snapshot` / `child_table` / `doctype_query` / `resolved` (in-memory) | **Rất cao** — thay thế `cost_bucket_aggregate` (alumglass) | Nhiều `rows_source` → UI cần form conditional |
| `reuse_formula_result` | Dùng lại kết quả từ formula/BOM/config khác (locate theo scope_field, line_match, aggregate) | Cao, batchable ✅ | Phụ thuộc cấu trúc child table của doc nguồn |

### Nhóm F — Escape hatch

| source_type | Dùng khi nào | Linh hoạt | Hạn chế |
| --- | --- | --- | --- |
| `custom_function` | Gọi hàm Python từ module trong whitelist (Settings), args template `{doc.x}`/`{resolved.x}` | **Tối đa** | Cần code; module phải khai báo whitelist |

### 3.1 Đánh giá thẳng

**Đã đủ linh hoạt cho ~80–90% nhu cầu:**
- Đọc doc trực tiếp, query, aggregate, composite N-chiều, pipeline/conditional/fallback
  đều không cần code.
- Registry tự discovery từ `hooks.fb_source_types` — app thêm source type riêng không
  đụng platform.
- Validate `source_config` theo `config_schema` (kể cả `required_unless` — conditional
  required) → nền tảng tốt cho form động.
- Batch + fingerprint + transform + cache là **lợi thế platform** mà app không nên tự
  viết lại (chính alumglass đã chuyển `cost_bucket_aggregate` sang `aggregate_from_items`).

**Gap thực tế:**
1. **Thiếu dropdown động + form tạo `source_config`**: Select tĩnh 13 option, config
   nhập JSON thô — không dùng được trên Form chuẩn (bằng chứng §1.3).
2. **Thiếu test-binding trong UI**: `test_data_source` API có sẵn nhưng chỉ resolve
   với `doc=None` → chỉ test được source type không cần doc (constant, global_default,
   doctype_query không dùng doc...). Cần thêm chế độ test trên doc thật.
3. **Inner steps của pipeline/conditional/fallback_chain không batch**: đúng kết quả,
   nhưng với hàng trăm dòng BOM sẽ thành nhiều query nhỏ. Ghi nhận, chưa giải quyết
   trong đợt này.
4. **Scope semantics không nhất quán giữa 2 entry point**: `get_live_context` tôn trọng
   `applies_to_field`; còn `_get_pricing_bindings` (dùng BatchBindingResolver trực tiếp)
   chỉ lọc theo `applies_to_doctype`, bỏ qua `applies_to_field`. Cần chuẩn hoá khi làm
   admin UI (preview scope phải khớp runtime).

---

## 4. Kiến trúc đề xuất — FVB = single resolution layer

### 4.1 Phân ranh platform vs app nghiệp vụ

```
┌─────────────────────────────────────────────────────────────────────┐
│  FORMULA BUILDER (platform) — "CÁCH resolve" (engine + registry)     │
│                                                                     │
│  • SourceTypeRegistry + @register_source  — đăng ký + metadata       │
│  • 17 source_type built-in + BatchBindingResolver (N+1 → ~5 queries)│
│  • config_schema validate + transform + cache                       │
│  • get_live_context (scope filter theo doctype/field)               │
│  • Formula Variable Binding (FVB) = SINGLE RESOLUTION LAYER         │
│      variable_name + source_type + source_config + data_type +      │
│      default_value + applies_to_doctype/field + resolve_priority    │
│  • API whitelisted: list_source_types / get_source_type_schema /    │
│    validate_binding_source_config / test_data_source /              │
│    get_registry_stats                                               │
└─────────────────────────────────────────────────────────────────────┘
        ▲                          ▲
        │ config (data)           │ custom source type khi có
        │ + source_config seed    │ logic thương mại riêng
┌───────┴──────────────────────────┴──────────────────────────────────┐
│  APP NGHIỆP VỤ (vd alumglass) — "Ý NGHĨA biến" (dữ liệu + catalog)  │
│                                                                     │
│  • Catalog biến: AL Variable Library giữ label/type/options/default │
│    (BỎ phần source_doctype/source_field — dời sang FVB)             │
│  • Custom source type: fb_handlers.py aluminum_price_composite /    │
│    glass_master_data — đăng ký qua @register_source                 │
│  • Dữ liệu seed: FVB seed qua patch idempotent (mở rộng D3)         │
│  • Dữ liệu cấu hình: AL Pricing Dimension / Mapping, Item Price,    │
│    AL Glass Master... (do app quản lý)                              │
└─────────────────────────────────────────────────────────────────────┘
```

**Nguyên tắc:** FB sở hữu **cách resolve** (source type nào, batch ra sao, validate,
cache, transform). App sở hữu **ý nghĩa biến** (biến này là gì, từ bảng nào, có logic
thương mại riêng gì). FVB là chỗ hai bên gặp nhau — app đổ config vào FVB, FB chạy.

### 4.2 D3 đã minh hoạ đúng phân ranh

`seed_fvb_from_variable_library` (D3): catalog giữ ở Variable Library (label/type/
default), resolution dời sang FVB (`linked_doctype_field` + source_config). Đúng hướng.
Hạn chế hiện tại: D3 **chưa phủ hết** system vars (chỉ 2 doctype có link_field trong
`_LINK_BY_SOURCE_DOCTYPE`; các source_doctype khác bị skip → engine B1.3 vẫn phải
resolve). Đó là phần việc còn lại của lộ trình §6.

---

## 5. Thiết kế FVB Admin UI (mức thiết kế — KHÔNG code ở note này)

### 5.1 Mục tiêu

Biến FVB từ "bảng cấu hình JSON thô" thành "màn hình khai báo biến data-driven":
chọn source_type từ dropdown động, điền form từ `config_schema`, test kết quả,
xem trước grouping batch, scope theo doctype/field.

### 5.2 Tận dụng API đã có sẵn (không phải viết lại)

| API (đã whitelist) | Dùng làm gì trong UI |
| --- | --- |
| `list_source_types()` | Đổ dropdown `source_type`, **nhóm theo app** (`platform` vs từng app) |
| `get_source_type_schema(source_type)` | Sinh **form động** cho `source_config` theo `config_schema` (type/required/enum/items/description) |
| `validate_binding_source_config(source_type, source_config)` | Validate ngay khi save (real-time) |
| `test_data_source(source_type, source_config)` | Nút Test cho source type không cần doc |
| `get_registry_stats()` | Header thống kê (tổng source type, batchable, theo app) |
| `get_doctype_fields(doctype)` (đã có trong formula_builder.py) | Dropdown field khi chọn `applies_to_doctype` |

### 5.3 Những gì phải THÊM (nhỏ, additive — không đụng engine)

1. **Dropdown `source_type` động**: Doctype hiện khai báo Select tĩnh 13 option → đổi
   thành `Data` (hoặc giữ Select nhưng client script `frm.fields_dict.source_type
   .set_data(list_source_types())` khi form mở). **Bắt buộc** — nếu không, 4 source
   type Phase 3/FB-1 + mọi custom type không dùng được qua UI.
2. **Form động `source_config`**: section hiển thị field theo `config_schema` của
   source_type đang chọn (text/number/select/enum/array/list lồng nhau). Khi save:
   gom về JSON string ghi vào `source_config`. Lưu ý schema có `required_unless`
   (`aggregate_from_items.value_field` không bắt buộc khi `aggregate=count`) — form
   phải tôn trọng.
3. **`test_data_source_with_doc(source_type, source_config, doctype, docname,
   resolved_context_json)`**: mở rộng `test_data_source` — resolve với **doc thật +
   context đã resolve** (pre_resolved) để test được `linked_doctype_field`,
   `composite_key_lookup`, `pipeline`... chứ không chỉ source không cần doc. Nút
   "Test trên record này".
4. **`preview_batch_groups(doctype, docname)`**: trả về danh sách binding active của
   scope + fingerprint grouping (dùng chính logic `fingerprint_fn`/`batch_group`) →
   hiển thị "10 binding → 3 batch query" trước khi deploy.
5. **Scope preview**: một filter nhỏ mô phỏng đúng luật của `get_live_context`
   (global khi cả 2 trống; doctype khi khớp doctype; doctype+field khi khớp field) để
   admin thấy binding này "sẽ chạy ở đâu".

### 5.4 Bố cục UI (khuyến nghị)

- **Tab 1 — Bindings**: grid FVB (filter theo `applies_to_doctype`, `source_type`,
  `is_active`) + nút "New Binding" mở form.
- **Tab 2 — Form Binding** (thay Form chuẩn hoặc overlay): variable_name/label →
  source_type (dropdown động) → form source_config (động) → data_type/default_value →
  scope (doctype/field) → resolve_priority → is_global/is_active/batch_group → nút
  Test (có/thu doc) + Validate.
- **Tab 3 — Batch preview**: chọn scope → xem grouping.
- **Tab 4 — Source Type Explorer**: liệt kê toàn bộ registry (app, batchable, cache,
  transform, config_schema) — giúp DEV/hỗ trợ tra cứu.

Giữ **DocType FVB làm nơi lưu trữ duy nhất** — không tạo bảng mới. Admin UI chỉ là
lớp hiển thị + soạn thảo trên cùng DocType.

---

## 6. Lộ trình loại bỏ duplication (lấy alumglass làm ví dụ)

### Nguyên tắc an toàn: không bao giờ phá golden

Golden hiện tại: `CDMQ-2C = 22,717,289` / `CDMQ-4C = 47,430,808` (§fvb-seed.md).
Mỗi phase phải giữ nguyên golden, tách biệt, có thể revert.

### Phase 0 — Platform: FVB Admin UI (§5) + dropdown động source_type

Giao cho DEV (formula_builder). Độc lập với alumglass — app chưa cần đổi gì.
Khi xong: admin có thể tạo `composite_key_lookup`/`aggregate_from_items`/... qua UI.

### Phase 1 — Seed FVB đầy đủ từ Variable Library (mở rộng D3)

- Giữ nguyên D3 (idempotent: check `(variable_name, applies_to_doctype, is_global)`
  trước insert, try/except từng record, commit 1 lần).
- **Mở rộng phạm vi**: thay vì chỉ 2 doctype có trong `_LINK_BY_SOURCE_DOCTYPE`, seed
  cho **mọi system var có `source_doctype` + `source_field`**. Việc này cần giải quyết
  `link_field` (doc nào nối tới `source_doctype`) — với mỗi `source_doctype` mới, khai
  báo `link_field` tương ứng trong map (hoặc cấu hình scope phù hợp). Đây là việc
  **thuộc app** (alumglass biết chuỗi doc của mình) — không phải việc platform.
- Seed thêm pricing binding nếu muốn bật FB-max pricing (xem Decision D1).
- **Không xoá** Variable Library `source_doctype/source_field` ở phase này.

### Phase 2 — Golden regression + giữ song song

- Chạy regression BOM (2C/4C). FVB resolve ra cùng giá trị thật với B1.3 (cùng
  doctype + field nguồn) → inputs B1 không đổi → golden không đổi (đúng như D3 đã
  chứng minh).
- Merge order B1 giữ nguyên: 1.3 (Variable Library) vẫn là fallback, 1.4 (FVB)
  override. Nếu FVB phủ hết → 1.3 resolve ra đúng giá trị giống → không lệch.

### Phase 3 — Chuyển FVB thành nguồn duy nhất (retire path cũ)

- Đảo ưu tiên: engine đọc **FVB trước**, chỉ fallback B1.3 khi biến chưa có FVB
  (guard: `if var not in fb_ctx`). Bỏ qua chuỗi rỗng + coerce số — đã có sẵn trong
  `_resolve_fb_context`.
- Khi không còn system var nào phải resolve bởi B1.3 → đánh dấu `source_doctype`/
  `source_field` trên Variable Library **deprecated** (no-op, giữ dữ liệu cũ cho
  backward-compat đọc cũ), và bỏ nhánh 1.3 (hoặc giữ làm defensive no-op).
- Cập nhật `get_formula_context()`: bỏ mô tả dựa trên `source_doctype/source_field`
  của system vars (thay bằng "FVB · linked_doctype_field") — nguồn biến vẫn từ
  `get_live_context` là chính.

### Phase 4 — Vệ sinh + docs

- Update `quotation-pricing-flow.md` §2.2 (FVB không còn "chưa seed"), §6 (gating
  FB-max), `fvb-seed.md` (ghi nhận mở rộng). Xoá `cost_bucket_aggregate` handler khi
  không còn config cũ tham chiếu.
- Cập nhật `docs/design/` này thành "chấp thuận".

**Thứ tự tối quan trọng:** Phase 0 → 1 → 2 (regression) → 3 (retire) → 4. Không nhảy
tắt Phase 3 trước khi FVB phủ 100% system vars có source — nếu không sẽ phá golden
đúng kiểu mà fvb-seed.md cảnh báo (""" override OFFSET_FRAME=48").

---

## 7. Decisions & trade-offs

### D1 — Giữ `aluminum_price_composite` ở app hay dời sang built-in `composite_key_lookup`?

**Quyết định: GIỮ custom handler ở app (alumglass).**

- `aluminum_price_composite` mã hoá **logic thương mại data-driven riêng của AL**:
  "variable_name → AL Variable Dimension Mapping → pricing_dimension →
  custom_fieldname trên Item Price", và `multiplier_chain` đọc
  `AL Color Standard.price_multiplier`. Điểm khác biệt then chốt: **tập dimension
  được xác định động theo `material_category` lúc resolve**, còn `composite_key_lookup`
  yêu cầu `key_fields` tĩnh trong config.
- Hệ quả: 1 đoạn code app (~150 dòng) đổi lấy sự linh hoạt thêm dimension không cần
  sửa binding. Chi phí: platform không tự phục vụ được case này.
- **Ghi chú cho tương lai:** `exact_match` mode của handler ≈ `composite_key_lookup`
  với `key_fields` = các `custom_pd_*`. Nếu sau này AL muốn bỏ lớp Mapping (dimension
  cố định), có thể chuyển binding sang built-in mà không mất gì. Khi đó mới nên xoá
  handler — nhưng **không phải trong đợt này**.

### D2 — Có build FVB Admin UI ngay không?

**Quyết định: CÓ — nhưng scope giới hạn (§5).**

- Lý do: bằng chứng §1.3 — 4 source type built-in + mọi custom type **không chọn
  được** trên Form chuẩn. Không có UI thì 17 source type về mặt thực dụng chỉ là 13.
  Đây là gap chặn hết mọi app khác muốn dùng FB.
- Trade-off: chi phí build (form động từ config_schema là phần khó nhất — các type
  array lồng nhau như `pipeline.steps`, `fallback_chain.chain` cần editor từng phần).
  Giới hạn v1: hỗ trợ đầy đủ các type config phẳng; type composite (pipeline/
  conditional/fallback_chain) v1 có thể dùng editor JSON trợ giúp trước, form hoá
  theo `config_schema` đầy đủ ở v2. **Nêu rõ trong AC để không over-engineer.**

### D3 — Có tách resolution khỏi AL Variable Library ngay không?

**Quyết định: CÓ — nhưng theo lộ trình §6, KHÔNG phải trong 1 commit.**

- Lý do: 2 đường runtime song song (B1.3 + B1.4) đang chạy cùng lúc — cắt B1.3 trước
  khi FVB phủ 100% = phá golden. Lộ trình 4 phase đảo ngược an toàn.
- Hệ quả: giai đoạn chuyển tiếp vẫn tồn tại duplication (đã biết, chấp nhận) cho tới
  khi Phase 3 hoàn tất. Đây là cái giá đúng đắn của "không làm hỏng số".

### D4 — Có gộp `applies_to_doctype/field` thành scope linh hoạt hơn không?

**Quyết định: GIỮ nguyên 2 field, KHÔNG thêm khái niệm scope mới trong đợt này.**

- Hiện tại đủ cho nhu cầu: global (`""`) / theo doctype / theo doctype+field. Hệ
  quả phụ: `_get_pricing_bindings` bỏ qua `applies_to_field` là một lệch nhỏ (gap #4
  §3.1) — chuẩn hoá trong Phase 0 (thêm filter `applies_to_field` cho luồng pricing
  khi cần), thay vì thiết kế scope phức tạp.
- Khi nào xem lại: khi có app thứ 2 dùng FVB với nhu cầu "cùng biến, khác scope tuỳ
  context" (vd khác company/role) — lúc đó mới cần bảng scope riêng.

### D5 — `source_type` Select tĩnh → dropdown động: làm ngay hay đợi Admin UI?

**Quyết định: làm NGAY cùng Admin UI (Phase 0).** Không thể tách — dropdown tĩnh 13
option là lý do Admin UI tồn tại. Cách nhẹ nhất: đổi field sang `Data` + client script
set options từ `list_source_types()`, hoặc custom form trong Admin Page. Chọn phương
án nào tuỳ DEV, nhưng AC phải cover "chọn được mọi source type đã đăng ký".

### D6 — Batch-optimize inner steps của pipeline/conditional/fallback_chain?

**Quyết định: KHÔNG trong đợt này — Out of scope (xem §8).** Trigger để làm sau:
report hiệu năng BOM > ~150 dòng cho thấy inner-step query là bottleneck. Ghi nhận
trong docs là "known limitation", không phải bug.

---

## 8. Out of scope

- **Batch-optimize inner steps** của `pipeline`/`conditional`/`fallback_chain` (D6).
- **Monaco / formula workspace**: công thức vẫn soạn trong Formula Builder hiện có;
  Admin UI FVB chỉ quản lý *biến*, không phải *công thức*.
- **RBAC chi tiết**: FVB hiện chỉ `System Manager` — đủ cho giai đoạn này. Khi có
  khách triển khai nhiều site, mới xét role/tenant phân quyền binding.
- **Merge legacy `Formula Global Variable` vào FVB**: section 7 của `get_live_context`
  vẫn đọc DocType cũ; gộp sang FVB là việc khác, làm sau khi FVB admin ổn định.
- **Cache dashboard / invalidation UI**: cache TTL đã có trong registry metadata;
  chưa cần màn hình quản lý cache.
- **Migrate `matrix_lookup` → `composite_key_lookup`**: giữ backward-compat, không
  xoá (config cũ vẫn chạy).
- **Scope đa chiều (company/role/context)**: chỉ làm khi có app thứ 2 có nhu cầu (D4).

---

## 9. File map cho DEV triển khai (tham chiếu nhanh)

| Việc | File/API liên quan |
| --- | --- |
| Dropdown động source_type | `doctype/formula_variable_binding/formula_variable_binding.json` (đổi Select→Data + mô tả), `...formula_variable_binding.js` (hiện rỗng) |
| API test có doc | `api/source_type_registry.py` (thêm `test_data_source_with_doc` cạnh `test_data_source`) |
| API preview batch groups | `api/batch_binding_resolver.py` (lộ `_group_by_fingerprint` thành API preview) |
| Scope preview | `api/formula_builder.py` `get_live_context` (luật filter §2 của hàm) |
| Nơi đăng ký custom source type của app | `alumglass/fb_handlers.py` + `alumglass/hooks.py` `fb_source_types` |
| Seed FVB mở rộng | `alumglass/patches/v28_9/seed_fvb_from_variable_library.py` (pattern idempotent: check `(variable_name, applies_to_doctype, is_global)`) |
| Engine resolve cũ (retire Phase 3) | `alumglass/engine/bom_orchestrator.py` `_resolve_system_variables` (B1.3), `_resolve_fb_context` (B1.4), `_get_pricing_bindings` (B2) |
| Catalog hiển thị cần vệ sinh | `alumglass/api/__init__.py` `get_formula_context` (bỏ mô tả theo `source_doctype/source_field`) |
| Docs cần cập nhật sau khi code | `alumglass/docs/design/fvb-seed.md`, `alumglass/docs/quotation-pricing-flow.md` §2.2/§6, `formula_builder/docs/design/` này |

---

## Phụ lục A — Bằng chứng verify (đã rà code 2026-08-31)

- Số source type built-in = **17** (đếm trực tiếp từ `data_source_registry.py`:
  10 Phase 1 + 3 Phase 2 composite + 2 Phase 3 + 2 FB-1 revised).
- Select tĩnh trên DocType FVB = **13 option** — thiếu `matrix_lookup`,
  `reuse_formula_result`, `composite_key_lookup`, `aggregate_from_items` + mọi custom.
- Controller/JS FVB **rỗng** (không có validate, không dropdown động, không test).
- `test_data_source` build binding với `doc=None`, `resolved_so_far={}` → chỉ test được
  source không phụ thuộc doc.
- `_get_pricing_bindings` filter `applies_to_doctype in ["", "Quotation Item",
  "AL Bom Item"]`, KHÔNG đọc `applies_to_field`.
- D3 skip system var có `source_doctype` ngoài 2 doctype có trong `_LINK_BY_SOURCE_DOCTYPE`.

---

## 10. Phase 1 platform — đã triển khai (2026-09-03)

> Trạng thái: **delivered (code + docs + test)** theo `docs/design/de-xuat-cai-tien-quotation-pricing.md`
> §3A (A1–A5, platform-side). Scope: repo `formula_builder` thuần — không đụng alumglass
> (DEV1 đang làm Phase 0/seed FVB ở alumglass song song, §11). **KHÔNG** thay đổi output
> của bất kỳ source type hiện hữu; binding cũ (13 option Select) đọc bình thường.

### 10.1 A1 — source_type dropdown động

| Quyết định | Giải thích |
| --- | --- |
| Đổi `source_type` fieldtype **Select → Autocomplete**, bỏ `options` tĩnh | Autocomplete map `varchar` trong MySQL (cùng cột với Select/Data) → **không cần migrate dữ liệu**, giá trị 13 cũ vẫn đọc được. |
| JS nạp options từ `list_source_types()` (đã whitelist sẵn) | 17 built-in + mọi custom đăng ký qua hooks `fb_source_types` luôn xuất hiện đúng trạng thái registry. |
| Giá trị cũ không còn trong registry → vẫn giữ trong dropdown | Không làm mất binding cũ / không force migrate dữ liệu. |
| **Không** chọn Data + dropdown thủ công | ControlData KHÔNG có `set_data`; phải plumbing Awesomplete tay → rủi ro + bảo trì cao hơn Autocomplete (ControlAutocomplete.extend ControlData, có `set_data([{value,label,description}])` + `format_for_input` tra `_data` theo value). |

Files: `doctype/formula_variable_binding/formula_variable_binding.json`,
`.../formula_variable_binding.js` (`FB_ADMIN.loadSourceTypeOptions`).

### 10.2 A2 — Form động soạn `source_config`

- FVB form có thêm HTML field **`source_config_editor_html`** ("Source Config Editor") —
  khi user chọn `source_type`, JS gọi `get_source_type_schema(source_type)` rồi render form
  theo `config_schema.properties` (checkbox/select/number/text/JSON textarea), ghi ngược về
  field JSON native `source_config` (source of truth, submit-safe).
- **required_unless** hiển thị dưới dạng ghi chú "(bắt buộc trừ khi X = Y)" và được tôn trọng
  khi tính trạng thái "đủ required" — ví dụ `aggregate_from_items.value_field` bỏ trống khi
  `aggregate = count` là hợp lệ (khớp `_validate_against_schema`).
- Source type phức tạp (pipeline/conditional/fallback_chain, `args`, `multipliers`...) →
  prop array/object render thành **JSON textarea inline**; vẫn soạn được thẳng trong
  `source_config` native nếu muốn (ADR D2 — v1 giữ nguyên).
- Nút tiện ích (group "Data Source"): **Validate Config**, **Test Source (no doc)**,
  **Test With Doc…**, **Preview Batch Groups**.

### 10.3 A3 — `test_data_source_with_doc`

- Tách executor dùng chung `_execute_source_test(definition, cfg, doc, resolved_so_far,
  data_type)`; `test_data_source` (cũ, `doc=None`) gọi nó → **backward compatible**.
- Whitelisted mới: `test_data_source_with_doc(source_type, source_config, doctype, docname,
  resolved_context_json="{}", data_type="Float")`.
  - Load doc thật (từ chối docname `new-*` chưa lưu bằng lỗi rõ ràng).
  - `resolved_context_json` → pre-resolved `resolved_so_far` (test source phụ thuộc biến
    đã resolve, ví dụ aggregate `rows_source='resolved'`).
  - Trả shape giống `test_data_source`; khi có doc → kèm `doc_context`.

### 10.4 A4 — `preview_batch_groups`

- `BatchBindingResolver.preview_groups(bindings)` — mô phỏng pipeline thật của
  `resolve_all_batch` nhưng **không execute handler**: `_split_batchable` →
  `_group_by_fingerprint` → mỗi nhóm phân loại strategy đúng thứ tự ưu tiên của
  `_execute_one_group` (`resolve_batch` / `resolve_batch_query` / `execute_individual`).
- Whitelisted: `preview_batch_groups(doctype, applies_to_field, include_inactive)` — scope
  lấy qua `binding_scope.get_scope_bindings` (cùng semantics `get_live_context`).
- Output: `{scope, summary:{total_bindings, total_groups, batch_groups,
  individual_bindings, estimated_queries, potential_query_reduction}, groups:[{...}],
  individual_bindings:[{variable_name, source_type, reason}]}`. Nhóm rơi vào
  `execute_individual` và binding non-batchable được liệt kê đầy đủ → FVB admin thấy N+1
  trước khi chạy thật.

### 10.5 A5 — Scope semantics tập trung (`binding_scope`)

- New module `api/binding_scope.py`:
  - `binding_matches_scope(binding, doctype, field)` — luật scope DUY NHẤT.
  - `filter_bindings_for_scope(bindings, doctype, field)` — filter python-side.
  - `get_scope_bindings(doctype, field, include_inactive, fields, order_by)` — fetch + filter
    DB, dùng chung cho `get_live_context` và `preview_batch_groups`.
- `get_live_context` refactor gọn về `get_scope_bindings(...)` — **hành vi filter giữ
  nguyên 100%** (global / doctype / doctype+field; `applies_to_doctype in ["", doctype]`
  prefilter khi có doctype; order `resolve_priority asc`).
- Vì sao: `_get_pricing_bindings` (alumglass) filter chỉ theo doctype, bỏ qua
  `applies_to_field` → preview scope lệch runtime. App nghiệp vụ giờ import 3 hàm này để
  dùng chung 1 luật (xem §11).

### 10.6 Test & gate (Phase 1)

- Test file mới: `formula_builder/tests/test_platform_phase1.py` — **pure-Python, không cần
  site/DB**:
  `python -m unittest formula_builder.tests.test_platform_phase1` (23 tests pass).
  Coverage: registry metadata/A1, required_unless/A2, test_data_source doc=None/A3,
  preview_groups grouping+strategy/A4, binding_scope semantics/A5.
- Smoke no-site: import + `test_data_source`/`validate_binding_source_config` trên
  `constant`, `session_variable`, `aggregate_from_items`; import đủ module; py_compile cả 4
  file py; `node --check` JS; `json.tool` doctype JSON.
- Chưa verify được trên site (formula_builder chưa cài ở site nào; **không migrate** theo
  job scope) → mọi bài DB-driven chờ khi app được cài/sync trên site dev.

---

## 11. Giao diện phối hợp DEV1 (alumglass Phase 0/seed — song song)

DEV2 chỉ làm platform (repo formula_builder). Các điểm DEV1 cần nối khi làm alumglass:

1. **`_get_pricing_bindings` phải tôn trọng `applies_to_field`.** Thay vì tự lọc theo
   `applies_to_doctype in ["", "Quotation Item", "AL Bom Item"]`, import dùng chung:
   `from formula_builder.api.binding_scope import get_scope_bindings, filter_bindings_for_scope,
   binding_matches_scope` — giữ đúng field semantics như `get_live_context`. KHÔNG duplicate
   logic filter ở app.
2. **Scope preview batch** dùng chung `formula_builder.api.batch_binding_resolver.preview_batch_groups`
   (đã trả theo scope semantics trên) → dev BOM item/Quotation nhìn trước được nhóm nào N+1.
3. **Test config có doc** của app dùng `test_data_source_with_doc` (không tự đẻ API tương tự).
4. Import order (nếu app test trong env không có site): phải `import
   formula_builder.api.data_source_registry` trước khi đọc central registry (module-level
   `_register_all_to_central_registry()` nạp 17 built-in); import `source_type_registry`
   đơn lẻ → registry rỗng.

Chưa thấy việc cần đụng code alumglass ở phía platform; nếu DEV1 gặp thiếu contract nào
trong 3 hàm scope → báo lại Elon để bổ sung tại `binding_scope.py` (không sửa ở app).

