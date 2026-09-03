# Source Type Contract — chuẩn khai báo source_type cho app

Chuẩn duy nhất để khai báo một data source type trong Formula Builder (v31+). Mọi source type — built-in lẫn external app — phải tuân theo contract này để được: validate config, group batch, cache, transform, và xuất hiện trong admin UI.

- Module canonical: `formula_builder/api/source_type_registry.py`
- Handler tập trung: `formula_builder/api/data_source_registry.py`

## 1. Decorator canonical: `@register_source`

**Chỉ có MỘT cách đăng ký**: import `register_source` từ `formula_builder.api.source_type_registry` và decorate **trực tiếp hàm `_handle_...`**.

```python
from formula_builder.api.source_type_registry import register_source

@register_source(
    "my_source",
    label="My Data Source",
    description="Fetch dữ liệu từ doctype của app",
    config_schema={
        "type": "object",
        "required": ["doctype", "value_field"],
        "properties": {
            "doctype": {"type": "string", "description": "DocType nguồn"},
            "value_field": {"type": "string", "description": "Field cần đọc"},
            "default_value": {"type": ["number", "string"], "description": "Fallback khi không khớp"},
        },
    },
    app="my_app",                 # app đăng ký — để admin UI phân nhóm
    batchable=True,
    fingerprint_fn=lambda cfg: "my_source:" + cfg.get("doctype", ""),
    supports_transform=True,
    supports_cache=True,
    default_cache_ttl=300,
)
def _handle_my_source(binding, doc, resolved_so_far):
    """Handler nhận binding dict, trả về giá trị (đã cast data_type)."""
    cfg = json.loads(binding.get("source_config") or "{}")
    ...
    return value
```

**Quy tắc bắt buộc:**

| Điểm | Quy tắc |
| --- | --- |
| Tên handler | `_handle_<source_type>` — decorate trực tiếp, **KHÔNG dùng wrapper `_dispatch`**. |
| Import | `from formula_builder.api.source_type_registry import register_source` — không alias `_register_central`. |
| `resolve_batch` | Gán **1 lần** sau khi định nghĩa hàm batch: `_handle_my_source.resolve_batch = _resolve_my_source_batch`. |
| Signature | `handler(binding: dict, doc, resolved_so_far: dict) -> Any`. |
| `source_config` | Luôn là JSON string — parse bằng `json.loads(binding.get("source_config") or "{}")`. |
| Trả về | Giá trị đã `_cast(val, data_type)`; không trả `None` khi có `default_value`. |

## 2. config_schema — lightweight JSON Schema

`SourceTypeRegistry._validate_against_schema` hỗ trợ subset JSON Schema:

- `type`: `object` / `string` / `number` / `integer` / `array` / `boolean`. Nếu cần nhận nhiều kiểu (vd `default_value` number hoặc string) → dùng `"type": ["number", "string"]` (validator bỏ qua → lenient).
- `required`: list field bắt buộc.
- `required_unless`: **conditional required** — bỏ qua field trong `required` khi điều kiện thỏa. Vd `value_field` không bắt buộc khi `aggregate == "count"`:

  ```python
  "required": ["rows_source", "aggregate", "value_field"],
  "required_unless": {
      "value_field": {"if": "aggregate", "equals": "count"},
  },
  ```
- `properties`: mô tả từng field (`type`, `description`, `enum`, `minimum`, `maximum`, `items`).
- `enum`: giới hạn giá trị cho field kiểu string (validator báo lỗi nếu ngoài danh sách).

**Rà soát khi thêm source type:** khai báo đầy đủ mọi field trong config — đặc biệt `default_value`, `filters`, `match_mode`, `fallback_keys` — để admin UI generate form đúng.

## 3. fingerprint_fn — grouping batch

`fingerprint_fn(cfg) -> str` xác định các binding có thể **share một lần fetch** trong batch. Hai binding cùng `(source_type, fingerprint)` → gọi `_resolve_*_batch` 1 lần với cả group.

- Phải bao gồm mọi field ảnh hưởng đến **cách lấy rows** (doctype, filters, rows_source, fields...) — KHÔNG bao gồm field resolve-per-binding (như `key_value` template).
- Dùng `json.dumps(..., sort_keys=True)` để ổn định thứ tự.
- Convention: prefix `"<source_type>:"` + các field nối `|`.

## 4. Dual registry — legacy dict + central registry

`register_source` tự đăng ký vào **CẢ HAI**:

1. `SourceTypeRegistry` (central, v31) — metadata đầy đủ (config_schema, fingerprint, app, cache...) dùng cho validate, batch, admin UI.
2. `_data_source_handlers` (legacy dict trong `data_source_registry`) — backward-compat cho code cũ gọi `get_handler(source_type)`.

Không cần đăng ký thủ công vào legacy dict. Không dùng decorator cũ `@register_source` (local trong `data_source_registry.py`) cho source type mới — decorator đó chỉ dành cho 13 built-in đầu (giữ backward-compat, đăng ký central qua `_register_all_to_central_registry()`).

## 5. Handler contract

```python
def _handle_my_source(binding, doc, resolved_so_far):
    cfg = json.loads(binding.get("source_config") or "{}")
    default_value = cfg.get("default_value", binding.get("default_value"))
    data_type = binding.get("data_type") or cfg.get("type", "Float")

    # Đọc rows nguồn (frappe.get_all / get_doc / doc.get(child_field) ...)
    # Lọc / transform / lookup
    return _cast(value, data_type)
```

Template resolution: dùng `_resolve_template_val(val, doc, resolved_so_far, row)` (hỗ trợ `{{row.x}}`, `{{doc.x}}`, `{{resolved.x}}`). Lấy row context bằng `_binding_row(binding, resolved_so_far)`.

## 6. Batch contract

```python
def _resolve_my_source_batch(bindings, doc, resolved_so_far):
    """Fetch rows 1 lần/group, resolve từng binding."""
    results = {}
    cfg0 = json.loads(bindings[0].get("source_config") or "{}")
    shared = _fetch_shared(cfg0)          # 1 lần cho cả group
    for b in bindings:
        cfg = json.loads(b.get("source_config") or "{}")
        default_value = cfg.get("default_value", b.get("default_value"))
        ...
        results[b["variable_name"]] = _cast(value, data_type)
    return results

_handle_my_source.resolve_batch = _resolve_my_source_batch   # gán 1 lần
```

## 7. Checklist thêm source_type mới

1. Định nghĩa `_handle_<name>` và decorate `@register_source("<name>", ...)` với đủ `config_schema` (kể cả `default_value`).
2. Nếu batchable: viết `_resolve_<name>_batch`, gán `_handle_<name>.resolve_batch = _resolve_<name>_batch`, đặt `batchable=True`, viết `fingerprint_fn`.
3. Test: registration (cả legacy dict + central), schema validate (lỗi required / enum), resolve (single + batch), template, fingerprint (2 binding cùng cfg → 1 group).
4. Docs: `docs/<source_type>.md` theo mẫu các doc hiện có (composite_key_lookup.md / aggregate_from_items.md), kèm ví dụ ứng dụng thực tế.
5. Chạy regression: `python -m unittest formula_builder.tests.test_platform_source_types formula_builder.tests.test_config_io formula_builder.tests.test_fb1_revised`.

## 8. Config user-controlled và safe-eval (bắt buộc từ 2026-08-16)

Mọi config trong `source_config` là **user-controlled** (nhập trên UI Formula
Builder) → KHÔNG bao giờ `eval()` trần chuỗi đó. Phải qua
`formula_builder.security.safe_eval.compile_expression()`:

| Config | Whitelist hàm | Policy |
| --- | --- | --- |
| `filter_expr` (child_table_aggregate) | `get_allowed_funcs()` (settings) | `FILTER_POLICY` (`forbid_subscript=True`) |
| `branches[].condition` (conditional) | `_CONDITION_ALLOWED_FUNCS` | `CONDITION_POLICY` |
| `transform.formula` (mọi source type) | `_TRANSFORM_ALLOWED_FUNCS` | `TRANSFORM_POLICY` |

Chi tiết thiết kế + audit eval sites: [`docs/security_safe_eval.md`](security_safe_eval.md).

## 9. API admin & scope dùng chung (Phase 1 — 2026-09-03)

Các API whitelisted platform phục vụ FVB Admin UI + app nghiệp vụ (source type vừa đăng
ký sẽ tự xuất hiện, không cần sửa thêm):

| API | Module | Mục đích |
| --- | --- | --- |
| `list_source_types()` | `api/source_type_registry.py` | Dropdown Autocomplete trên FVB — 17 built-in + mọi custom (A1). |
| `get_source_type_schema(source_type)` | ditto | Render form soạn `source_config` theo `config_schema` (A2). |
| `validate_binding_source_config(source_type, source_config)` | ditto | Validate config trước khi lưu (đã có từ trước). |
| `test_data_source(source_type, source_config)` | ditto | Test config với `doc=None` (cũ, backward compatible). |
| `test_data_source_with_doc(source_type, source_config, doctype, docname, resolved_context_json="{}", data_type="Float")` | ditto | Test config trên doc thật + pre-resolved context (A3). Từ chối docname `new-*` chưa lưu. |
| `preview_batch_groups(doctype="", applies_to_field="", include_inactive=0)` | `api/batch_binding_resolver.py` | Xem trước nhóm batch + strategy (resolve_batch / resolve_batch_query / execute_individual) trước khi execute (A4). |

Scope semantics (global / doctype / doctype+field) là luật DUY NHẤT đặt tại
`api/binding_scope.py` (A5):

```python
from formula_builder.api.binding_scope import (
    binding_matches_scope,        # 1 binding có áp cho scope (doctype, field)?
    filter_bindings_for_scope,    # filter python-side 1 danh sách (1 doctype)
    get_scope_bindings,           # fetch DB active theo scope (1 doctype) + filter
)
```

- `get_live_context` và `preview_batch_groups` đều đi qua `get_scope_bindings` → app nghiệp
  vụ (ví dụ alumglass `_get_pricing_bindings`) NÊN import các hàm này thay vì tự lọc chỉ
  theo `applies_to_doctype` (tránh lệch preview vs runtime).
- Chi tiết triển khai + lý do chọn Autocomplete: `docs/design/fvb-single-resolution-layer.md`
  §10. Điểm phối hợp DEV1: §11 file đó.

### 9.1 Pricing binding scope — pattern khuyến nghị cho app (alumglass `_get_pricing_bindings`)

**Bối cảnh:** pricing resolve theo **row-context** (item_code / price_base_item /
category) — lúc FETCH không có 1 doc/doctype gốc duy nhất. Scope lịch sử của pricing
binding là **tập doctype** `["", "Quotation Item", "AL Bom Item"]`: binding global
(`COMPOSITE_MATERIAL_PRICE`) + binding có thể khai báo riêng cho Quotation Item hoặc AL
Bom Item. Yêu cầu A5: **tôn trọng `applies_to_field` khi SET; khi KHÔNG set → giữ nguyên
hành vi cũ** (binding áp cho mọi field của doctype đó).

Bộ hàm scope **đa doctype** (additive, `api/binding_scope.py` — Phase 2/3/4):

```python
from formula_builder.api.binding_scope import (
    binding_matches_any_doctype,        # 1 binding áp cho TẬP doctype không?
    filter_bindings_for_scope_multi,    # filter python-side theo tập doctype
    get_scope_bindings_multi,           # fetch DB active theo tập doctype (+ source_type)
)
```

- `binding_matches_any_doctype(binding, doctypes, field="")` — global (cả 2 rỗng) → True;
  `applies_to_doctype` ∈ doctypes → xét field như `binding_matches_scope`; binding
  doctype-rỗng nhưng field-set (field-only, KHÔNG global) → không khớp doctype cụ thể
  nào → False (đồng nhất `get_live_context`).
- `get_scope_bindings_multi(doctypes, field="", source_types=None, ...)` — DB prefilter
  `applies_to_doctype in ["", *doctypes]` + optional `source_type in source_types`, rồi
  python filter `binding_matches_any_doctype`. `doctypes` rỗng → đồng nhất
  `get_scope_bindings("")` (chỉ global).

**Pattern khuyến nghị cho `_get_pricing_bindings`** (fetch 1 lần cho cả run, rồi ép
field theo row context):

```python
PRICING_DOCTYPES = ("Quotation Item", "AL Bom Item")
PRICING_SOURCE_TYPES = ("composite_key_lookup", "aluminum_price_composite")

# 1) Fetch ứng viên pricing binding đúng scope đa doctype (is_active + source_type).
bindings = get_scope_bindings_multi(
    doctypes=PRICING_DOCTYPES,
    source_types=PRICING_SOURCE_TYPES,
    order_by="resolve_priority asc",
)
# 2) Resolve theo row: row thuộc doctype cụ thể → ép applies_to_field
#    bằng filter_bindings_for_scope(bindings, row_doctype, row_field) — KHÔNG
#    tự viết lại luật field ở app. Nếu 1 row có thể thuộc nhiều doctype (vd cùng
#    item vừa là AL Bom Item vừa là Quotation Item) → giữ nguyên bộ ứng viên và
#    để handler/source_config quyết theo context, đừng bóp field ở fetch.
```

Lưu ý semantics (đã unit-test trong `test_platform_phase1` A5 multi-doctype):

| Binding (`applies_to_doctype`/`field`) | Kết quả match scope đa doctype |
|---|---|
| `""` / `""` (global) | Luôn True — áp mọi row, mọi doctype. |
| `"Quotation Item"` / `""` | True khi doctype row = Quotation Item (mọi field). |
| `"Quotation Item"` / `"unit_price"` | True chỉ khi row = Quotation Item + field = unit_price (hoặc caller không đưa field). |
| `"AL Bom Item"` / `""` | True khi doctype row = AL Bom Item. |
| `""` / `"unit_price"` (field-only) | **False** trên scope có doctype cụ thể — không global, không áp. |
| doctype NGOÀI tập (vd `"Sales Order Item"`) | False. |

Khi binding **KHÔNG set** `applies_to_field` → áp mọi field của doctype khớp (không đổi
kết quả so với hành vi cũ). Khi **set** → chỉ khớp đúng field của row. Đây chính là chuẩn
`get_live_context` mà `_get_pricing_bindings` phải theo để preview ≡ runtime.

