# Source Type: `reuse_formula_result` (S1)

Gọi **kết quả** của formula/BOM/cấu hình khác (tính chuyền đa tầng, chi phí lũy kế) — đọc lines kết quả từ một document (vd cost template, BOM, config) và aggregate theo dòng hiện tại.

Generic cho mọi ngành. Phục vụ alumglass B5/B6 (cost từ các dòng) và thép/gỗ (chi phí nhiều tầng).

- Registered: `reuse_formula_result`
- Module: `formula_builder/api/data_source_registry.py`
- Batchable: ✅ (có `resolve_batch` — fetch mỗi target doc 1 lần, reuse qua cache)
- Cache: ✅ (`supports_cache`, TTL mặc định 300s)
- Transform: ✅ (`supports_transform`)

## Khi nào dùng

- Line quotation cần cộng chi phí của nhiều dòng con trong cost template: `sum(line_cost)` theo `item_code`.
- Chi phí lũy kế nhiều tầng: BOM cha đọc tổng chi phí từ BOM con.
- Lấy giá trị đầu/cuối từ một cấu hình tính sẵn.

## Config

```json
{
  "source_type": "reuse_formula_result",
  "source_config": {
    "formula_document": "AL Cost Template",
    "scope_field": "quotation",
    "scope_value": "{{doc.quotation}}",
    "line_field": "cost_lines",
    "line_match": "{{row.item_code}}",
    "result_field": "line_cost",
    "aggregation": "sum",
    "default_value": 0,
    "scope_order_by": "modified desc"
  }
}
```

| Field | Bắt buộc | Ý nghĩa |
| --- | --- | --- |
| `formula_document` | ✅ | DocType của formula/BOM/cost-template chứa kết quả cần đọc. |
| `result_field` | ✅ | Field trên line cần lấy/aggregate. |
| `scope_field` | * | Field dùng để tìm **instance** đúng của target document (vd `quotation`). |
| `scope_value` | * | Giá trị cho `scope_field`; hỗ trợ template. |
| `document_name` | * | Cách thay thế: lấy thẳng document theo name (hỗ trợ template). |
| `line_field` | Optional | Tên child-table field chứa lines. Auto-detect field Table đầu tiên nếu bỏ trống. |
| `line_match` | Optional | Template/field nối dòng cha ↔ dòng con (vd `{{row.item_code}}`). Bỏ trống → dùng toàn bộ lines. |
| `line_match_field` | Optional | Field trên lines đích để so sánh. Mặc định suy ra từ `line_match`. |
| `aggregation` | Optional | `sum` (mặc định) · `min` · `max` · `avg` · `first` · `last`. |
| `default_value` | Optional | Giá trị trả về khi không khớp line nào / lỗi. |
| `scope_order_by` | Optional | Thứ tự chọn target doc khi `scope_field` khớp nhiều (mặc định `modified desc`). |
| `filters` | Optional | Filter Frappe bổ sung cho việc tìm target doc. |

> `scope_field`/`scope_value` hoặc `document_name` — dùng một trong hai cách để định vị target doc.

## Cách hoạt động

1. **Định vị target doc**:
   - Có `document_name` → resolve template → `frappe.get_doc(formula_document, name)`.
   - Ngược lại → resolve `scope_value` → `frappe.get_all(formula_document, filters=[[scope_field, "=", scope_value], ...], limit=1, order_by=scope_order_by)`.
2. **Lấy lines**: `target_doc.get(line_field)` (auto-detect child-table field đầu tiên nếu trống).
3. **Nối dòng** (`line_match`):
   - `{{row.item_code}}` → resolve từ row hiện tại; `line_match_field` suy ra = `item_code`.
   - `item_code` (tên field trần) → lấy giá trị từ row hiện tại; `line_match_field` = `item_code`.
   - `{{doc.quotation}}` → cần khai báo `line_match_field` tường minh; nếu không → dùng toàn bộ lines.
4. **Aggregate** `result_field` của các lines khớp:
   - `sum`/`avg`/`min`/`max`: coerce numeric, bỏ qua `None`.
   - `first`/`last`: giá trị line đầu/cuối (giữ nguyên kiểu, cast theo `data_type`).
5. Không có line khớp / lỗi → `default_value`.

## Ví dụ dùng

Cost template `AL Cost Template` có lines:

| item_code | line_cost |
| --- | --- |
| A | 100 |
| A | 50 |
| B | 30 |

Với config ở trên, dòng quotation `{item_code: "A"}` → **150** (`sum`).
Dòng `{item_code: "B"}` → `min` → 30, `max` → 30, `first` → 30, `last` → 30.

## Edge case

- **Không tìm thấy target doc** → `default_value`.
- **`line_match` không resolve được / không suy ra được `line_match_field`** → dùng toàn bộ lines (aggregate trên tất cả). Cẩn thận khi `scope_field` khớp nhiều doc — đặt `scope_order_by` để chọn doc đúng.
- **Giá trị rỗng** — line có `result_field = None` bị bỏ qua khi tính `sum`/`avg`/`min`/`max`; `first`/`last` trả về giá trị thô.
- **Không numeric** — value không ép được `float` bị bỏ qua trong aggregation numeric.
- **Auto-detect `line_field`** — chọn Table field đầu tiên của target doc; khai báo `line_field` nếu doc có nhiều child table.

## Batch & fingerprint

- `fingerprint_fn` gồm: formula_document + scope_field + line_field + line_match_field + result_field + aggregation + md5(scope_value/line_match/document_name/filters).
- `resolve_batch` fetch mỗi target doc **1 lần** (cache theo name) rồi reuse cho mọi binding trỏ cùng doc → giảm N+1.

## Test

`formula_builder/tests/test_platform_source_types.py` — `TestReuseFormulaResult*` (chạy không cần site, mock `frappe.get_all` / `frappe.get_doc`).

---

*Design doc theo §12.3 S1 (`al_review.md`), track FB Platform Expansion 2026-08-16.*
