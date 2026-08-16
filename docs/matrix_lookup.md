# Source Type: `matrix_lookup` (S2)

Tra bảng **2 chiều**: giá theo (kích thước × số lượng), (độ dày × màu), hệ số theo (vùng × trọng lượng), v.v.

Generic cho mọi ngành — không hardcode bất kỳ field/doctype nào.

- Registered: `matrix_lookup`
- Module: `formula_builder/api/data_source_registry.py`
- Batchable: ✅ (có `resolve_batch` — fetch 1 lần, reuse cho cả nhóm binding)
- Cache: ✅ (`supports_cache`, TTL mặc định 300s)
- Transform: ✅ (`supports_transform`)

## Khi nào dùng

- Bảng giá 2 chiều: size × qty → đơn giá.
- Định mức 2 chiều: độ dày × màu → hệ số chi phí.
- Bất kỳ bảng "hàng × cột → giá trị" nào lưu dạng một dòng / một ô trong DocType.

## Config

```json
{
  "source_type": "matrix_lookup",
  "source_config": {
    "doctype": "AL Pricing Matrix",
    "row_key_field": "size",
    "col_key_field": "thickness",
    "value_field": "price",
    "row_key": "{{row.size}}",
    "col_key": "{{row.thickness}}",
    "default_value": 0,
    "fallback_row_key": "ANY",
    "fallback_col_key": "ANY",
    "match_mode": "exact",
    "filters": []
  }
}
```

| Field | Bắt buộc | Ý nghĩa |
| --- | --- | --- |
| `doctype` | ✅ | DocType chứa các dòng matrix (mỗi dòng = 1 ô). |
| `value_field` | ✅ | Field chứa giá trị trả về. |
| `row_key_field` | Optional | Field làm key hàng (vd `size`). Bỏ trống → bỏ qua trục hàng. |
| `col_key_field` | Optional | Field làm key cột (vd `thickness`). Bỏ trống → bỏ qua trục cột. |
| `row_key` | Optional | Giá trị tra trên trục hàng. Hỗ trợ template. |
| `col_key` | Optional | Giá trị tra trên trục cột. Hỗ trợ template. |
| `default_value` | Optional | Giá trị trả về khi không có ô khớp. |
| `fallback_row_key` | Optional | Key hàng fallback (vd `"ANY"`) khi không khớp chính xác. Hỗ trợ template. |
| `fallback_col_key` | Optional | Key cột fallback. Hỗ trợ template. |
| `match_mode` | Optional | `exact` (mặc định) hoặc `case_insensitive`. |
| `filters` | Optional | Filter Frappe bổ sung để thu hẹp matrix (vd theo currency/region/date). |

### Cú pháp template

| Cú pháp | Nghĩa |
| --- | --- |
| `{{row.size}}` / `{row.size}` | Field trên **dòng hiện tại** (child-table row đang tính). |
| `{{doc.quotation}}` / `{doc.quotation}` | Field trên document cha. |
| `{{resolved.x}}` / `{resolved.x}` / `{inputs.x}` | Biến đã resolve trước đó. |
| `1500` / `"ANY"` | Literal — trả về nguyên giá trị. |

> Row được lấy từ `resolved_so_far["row"]` (hoặc `binding["row"]`). Caller (vd formula table API) đặt `ctx["row"]` trước khi resolve.

## Thứ tự resolve

1. **Exact** — dòng có `row_key_field == row_key` và `col_key_field == col_key`.
2. **Fallback row** — `row_key_field == fallback_row_key` và `col_key_field == col_key`.
3. **Fallback col** — `row_key_field == row_key` và `col_key_field == fallback_col_key`.
4. **Fallback cả hai** — `fallback_row_key` × `fallback_col_key`.
5. Không khớp → `default_value`.

Nếu `value_field` của ô khớp bị rỗng (`None`) → coi như không khớp, tiếp tục fallback.

## Ví dụ dùng

Bảng `AL Pricing Matrix`:

| size | thickness | price |
| --- | --- | --- |
| 1000 | 5 | 120 |
| 1000 | 8 | 150 |
| ANY  | 8 | 210 |
| ANY  | ANY | 99 |

Với config ở trên và dòng `{size: 2000, thickness: 8}`:

1. Exact (2000, 8) → không có.
2. Fallback row: (ANY, 8) → **210**. ✅

Dòng `{size: 2000, thickness: 99}`:

1. Exact → không.
2. Fallback row (ANY, 99) → không.
3. Fallback col (2000, ANY) → không.
4. Fallback cả hai (ANY, ANY) → **99**.

## Edge case

- **Missing key** — nếu `row_key_field` có cấu hình nhưng `row_key` resolve ra `None` → không thể khớp trục đó → nhảy fallback/default (tránh match bừa dòng bất kỳ).
- **Không khai báo trục nào** (`row_key_field` + `col_key_field` đều trống) → trả `value_field` của dòng đầu tiên (lookup 1 ô).
- **So sánh chuỗi** — so sánh theo `str(x).strip()`; dùng `match_mode: "case_insensitive"` nếu cần không phân biệt hoa thường.
- **`filters`** — dùng để giới hạn matrix theo ngữ cảnh (vd `[["currency","=","VND"]]`). Filter value có thể dùng template.

## Batch & fingerprint

- `fingerprint_fn` gồm: doctype + row_key_field + col_key_field + value_field + match_mode + md5(filters).
- Hai binding cùng fingerprint → cùng 1 group → `resolve_batch` fetch toàn bộ matrix **1 lần**, reuse cho tất cả binding trong group.

## Test

`formula_builder/tests/test_platform_source_types.py` — `TestMatrixLookup*` (chạy không cần site, mock `frappe.get_all`).

---

*Design doc theo §12.3 S2 (`al_review.md`), track FB Platform Expansion 2026-08-16.*
