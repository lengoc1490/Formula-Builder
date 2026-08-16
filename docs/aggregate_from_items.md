# Source Type: `aggregate_from_items`

Aggregate một field từ tập rows (snapshot JSON, child table hiện tại, hoặc query doctype) lọc theo `key_field == key_value` — giống **SUMIF**. Hỗ trợ thêm **multi-field `filters`** (Frappe-style) áp dụng cho mọi rows_source — thay được helper python thuần dict `fb_handlers.cost_bucket_aggregate` cho AL Cost Bucket.

- Registered: `aggregate_from_items`
- Module: `formula_builder/api/data_source_registry.py`
- Decorator: `@register_source` (canonical từ `source_type_registry`) — decorate trực tiếp `_handle_aggregate_from_items`
- Batchable: ✅ (có `resolve_batch` — fetch rows nguồn 1 lần/group, aggregate từng binding)
- Cache: ✅ (`supports_cache`, TTL mặc định 300s)
- Transform: ✅ (`supports_transform`)

## Khi nào dùng

- Cộng chi phí theo nhóm: `sum(line_total)` cho các dòng có `cost_bucket == 'NVL'`.
- Khi rows nguồn lấy từ 1 trong 3 chỗ: **snapshot JSON** (cấu hình chốt sẵn), **child table** (dòng hiện tại của doc), hoặc **doctype query** (query doc khác theo template).
- Lọc thêm nhiều field cùng lúc qua `filters` (thay `filter_by` cũ của `cost_bucket_aggregate`): vd sum chỉ các dòng `cost_bucket == 'NVL'` **VÀ** `qty > 1`.
- `key_value` để trống → aggregate trên **toàn bộ** rows (node AGGREGATE thuần).

## Config

```json
{
  "source_type": "aggregate_from_items",
  "variable_name": "nvl_total",
  "source_config": {
    "rows_source": "child_table",
    "child_table_field": "items",
    "filters": [["qty", ">", 1]],
    "key_field": "cost_bucket",
    "key_value": "{{row.cost_bucket}}",
    "value_field": "line_total",
    "aggregate": "sum",
    "default_value": 0
  }
}
```

| Field | Bắt buộc | Mô tả |
| --- | --- | --- |
| `rows_source` | ✅ | `snapshot` \| `child_table` \| `doctype_query`. |
| `snapshot_doctype` | theo `rows_source` | DocType chứa snapshot (`rows_source=snapshot`). |
| `snapshot_name` | theo `rows_source` | Name của snapshot doc; hỗ trợ template `{{doc.field}}`, `{{resolved.field}}`. Nếu trống → fallback `resolved_so_far[snapshot_doctype]` rồi `doc[snapshot_doctype]`. |
| `snapshot_field` | — | Field trên snapshot doc chứa JSON data (mặc định `snapshot`). |
| `rows_path` | — | JSON path trong snapshot data chứa list rows (mặc định `items`). |
| `child_table_field` | theo `rows_source` | Fieldname child-table trên doc hiện tại (`rows_source=child_table`). |
| `doctype` | theo `rows_source` | DocType cần query (`rows_source=doctype_query`). |
| `fields` | — | Fields cần fetch cho doctype_query (mặc định `['name']`). |
| `filters` | — | **Multi-field Frappe-style filters áp dụng cho MỌI rows_source**: `[['field','=','val'], ...]`. Operator: `=`, `==`, `!=`, `<>`, `>`, `<`, `>=`, `<=`, `like`, `in`, `not in`. Value hỗ trợ `{{row.field}}`, `{{doc.field}}`, `{{resolved.field}}`. Kết hợp **AND** với `key_field/key_value`. Với doctype_query, các filter này cũng được đưa vào `get_all` (value dùng `{doc.x}`/`{resolved.x}`). |
| `order_by` | — | Order clause cho doctype_query. |
| `limit` | — | Số rows tối đa cho doctype_query (0 = không giới hạn). |
| `key_field` | — | Field dùng làm key lọc (giống criteria field của SUMIF), vd `cost_bucket`. Bỏ trống → aggregate toàn bộ. |
| `key_value` | — | Giá trị khớp `key_field`; hỗ trợ `{{row.field}}`, `{{doc.field}}`, `{{resolved.field}}`. Trống → toàn bộ rows. |
| `value_field` | ✅ (trừ `count`) | Field cần aggregate, vd `line_total`. Không bắt buộc khi `aggregate=count` (schema dùng `required_unless`). **Ưu tiên hơn `sum_field`** khi cả hai cùng tồn tại. |
| `sum_field` | — | **Alias** của `value_field` (backward-compat với AL Cost Bucket source_config cũ dùng `sum_field`). Chỉ đọc khi `value_field` rỗng. KHÔNG thay đổi schema chuẩn — `value_field` vẫn là key chuẩn. |
| `aggregate` | ✅ | `sum` \| `avg` \| `min` \| `max` \| `count` \| `first` \| `last`. |
| `default_value` | — | Giá trị trả về khi không có row thỏa điều kiện hoặc lỗi đọc rows nguồn (mặc định 0). |

## Alias `sum_field` (AL Cost Bucket backward-compat)

AL Cost Bucket (`alumglass`) validate `aggregate_from_items` bằng config key **`sum_field`** (vd `{"sum_field": "line_total", ...}` — xem `al_cost_bucket.py:40`). FB `aggregate_from_items` chuẩn dùng **`value_field`** (required trong `config_schema`, trừ `aggregate=count`).

Từ 2026-08-16, FB hỗ trợ `sum_field` làm **alias** của `value_field`:

- Trong `_handle_aggregate_from_items` + `_resolve_aggregate_from_items_batch`: `value_field = cfg.get("value_field") or cfg.get("sum_field", "")` — nếu `value_field` rỗng thì đọc `sum_field`.
- `fingerprint_fn` cũng dùng giá trị đã resolve (`value_field or sum_field`) → config `sum_field` và `value_field` cùng field cho **cùng fingerprint** (không miss cache), khác field → fingerprint khác (không cache chéo).
- `value_field` vẫn là key chuẩn trong schema — khi cả hai cùng tồn tại, **`value_field` thắng**.
- `aggregate=count` không cần field nào — alias không ảnh hưởng.

Config AL cũ chuyển sang FB không cần sửa gì:

```json
{
  "source_type": "aggregate_from_items",
  "variable_name": "nvl_total",
  "source_config": {
    "rows_source": "child_table",
    "child_table_field": "items",
    "key_field": "cost_bucket",
    "key_value": "{{row.cost_bucket}}",
    "sum_field": "line_total",
    "aggregate": "sum",
    "default_value": 0
  }
}
```

## Map 8 source_type AL Cost Bucket ↔ FB

Owner yêu cầu: *"ở source_type của AL Cost Bucket có những phần nào mà ở FB chưa có, implement để sử dụng FB, không làm riêng lẻ."* Kết quả verify: **8/8 source_type AL đều đã có ở FB** — AL **không cần** implement source_type mới, chỉ cần map config sang FB.

| AL Cost Bucket source_type | FB source_type | Ghi chú |
| --- | --- | --- |
| `aggregate_from_items` | `aggregate_from_items` | sum field theo key_field/key_value (SUMIF) — dùng alias `sum_field`. |
| `formula` | `computed` | Tính field từ công thức. |
| `doctype_query` | `doctype_query` | Query doc khác theo filter. |
| `custom_function` | `custom_function` | Hàm Python tuỳ biến. |
| `constant` | `constant` | Giá trị cố định. |
| `pipeline` | `pipeline` | Chuỗi bước xử lý tuần tự. |
| `conditional` | `conditional` | Rẽ nhánh theo điều kiện. |
| `fallback_chain` | `fallback_chain` | Thử lần lượt, fallback khi lỗi/không có. |

Điểm khớp duy nhất cần xử lý ở FB là alias `sum_field` (mục trên) — đã implement.

## Template hỗ trợ

- `key_value` & `filters` value (snapshot/child_table): `{{row.cost_bucket}}`, `{{doc.quotation}}`, `{{resolved.price}}` — resolve qua `_resolve_template_val`.
- `snapshot_name`: `{{doc.cost_snapshot}}`; fallback thứ tự `resolved_so_far[snapshot_doctype]` → `doc[snapshot_doctype]`.
- `filters` (doctype_query): `{doc.field}` và `{resolved.field}` trong giá trị filter (replace trước khi query).

## Các rows_source

### snapshot
Đọc JSON từ `frappe.get_doc(snapshot_doctype, snapshot_name)` → `snapshot_field` → `json.loads` → đi theo `rows_path`. Snapshot giữ nguyên trạng thái tại thời điểm chốt — phù hợp khi cần tính lại từ cùng một bộ dữ liệu. `filters` lọc in-memory trên dict rows.

### child_table
`doc.get(child_table_field)` → list rows hiện tại trên doc. Luôn đồng bộ với dữ liệu mới nhất đang soạn. `filters` lọc in-memory.

### doctype_query
`frappe.get_all(doctype, filters=..., fields=..., order_by=..., limit_page_length=...)`. `filters` được đưa thẳng vào `get_all` (lọc ở DB — value dùng `{doc.x}`/`{resolved.x}`); không lọc lại in-memory. Phù hợp khi rows nằm ở doc khác.

## Ví dụ ứng dụng — AL Cost Bucket (alumglass)

Thay `fb_handlers.cost_bucket_aggregate` (py thuần dict) bằng source_type FB. Chỉ cần config, không cần code alumglass.

### 1. Sum line_total theo cost_bucket từ bom_set_snapshot (snapshot)

```json
{
  "source_type": "aggregate_from_items",
  "variable_name": "nvl_cost",
  "data_type": "Currency",
  "source_config": {
    "rows_source": "snapshot",
    "snapshot_doctype": "AL BOM Version",
    "snapshot_name": "{{doc.bom_version}}",
    "snapshot_field": "bom_set_snapshot",
    "rows_path": "items",
    "key_field": "cost_bucket",
    "key_value": "{{row.cost_bucket}}",
    "value_field": "line_total",
    "aggregate": "sum",
    "default_value": 0
  }
}
```

Với mỗi dòng quotation đang tính (`row.cost_bucket` = `NVL`, `PHU_KIEN`, ...) → cộng tổng `line_total` của các item cùng `cost_bucket` trong snapshot đã chốt. Giữ nguyên hành vi `cost_bucket_aggregate` cũ nhưng chạy trong engine FB (batch, cache, transform).

### 2. Multi-field filter — sum theo cost_bucket VÀ chỉ lấy item còn hiệu lực

```json
{
  "source_type": "aggregate_from_items",
  "variable_name": "nvl_active_cost",
  "data_type": "Currency",
  "source_config": {
    "rows_source": "snapshot",
    "snapshot_doctype": "AL BOM Version",
    "snapshot_name": "{{doc.bom_version}}",
    "snapshot_field": "bom_set_snapshot",
    "rows_path": "items",
    "filters": [
      ["is_active", "=", "1"],
      ["qty", ">", 0]
    ],
    "key_field": "cost_bucket",
    "key_value": "{{resolved.bucket_code}}",
    "value_field": "line_total",
    "aggregate": "sum"
  }
}
```

`filters` thay hoàn toàn `filter_by` cũ của `cost_bucket_aggregate` — lọc nhiều field cùng lúc (AND), không cần viết hàm Python riêng.

## Batch behavior

`_resolve_aggregate_from_items_batch`:
- Group theo fingerprint → `_resolve_aggregate_rows(cfg)` 1 lần/group.
- Với mỗi binding: áp dụng `filters` (trừ doctype_query — đã lọc ở DB) → lọc `key_field==key_value` (resolve template; trống → tất cả) → tính aggregate → cast theo `data_type`.
- Lỗi đọc rows nguồn → log_error + trả default.

## So sánh với `reuse_formula_result`

| | `reuse_formula_result` | `aggregate_from_items` |
| --- | --- | --- |
| Nguồn rows | Lines kết quả của 1 document cụ thể (qua formula đã tính) | snapshot / child table / doctype query (thô) |
| Filter | `line_match` (1 field đối chiếu) | `key_field == key_value` + multi-field `filters` (Frappe-style) |
| Aggregate | `sum` / `min` / `max` / `avg` / `first` / `last` | + `count` |

## Tests

`formula_builder/tests/test_fb1_revised.py` — `TestAggregateFromItemsRegistration` (schema required + `required_unless` cho count), `TestAggregateFromItemsChildTable` (sum PK / all / count / **multi-field filter** / `in` op), `TestAggregateFromItemsDoctypeQuery` (sum NVL / template filter), `TestAggregateFromItemsSnapshot` (sum theo bucket / **multi-field filter** / JSON path / missing snapshot default), `TestAggregateFromItemsBatch` (dùng chung rows nguồn), `TestAggregateFromItemsSumFieldAlias` (alias `sum_field` — sum, template key, count, ưu tiên `value_field`, batch, fingerprint resolve).
