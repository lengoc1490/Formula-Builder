# Source Type: `composite_key_lookup`

Lookup giá trị từ **ma trận N-chiều** (bảng giá/parameter nhiều chiều) bằng tập key fields động (`item_code`, `color`, `thickness`, `surface`, ...). Nâng cấp tổng quát của `matrix_lookup` (2D) — `matrix_lookup` là trường hợp đặc biệt với 2 chiều + fallback row/col key.

- Registered: `composite_key_lookup`
- Module: `formula_builder/api/data_source_registry.py`
- Decorator: `@register_source` (canonical từ `source_type_registry`) — decorate trực tiếp `_handle_composite_key_lookup`
- Batchable: ✅ (có `resolve_batch` — fetch toàn bộ rows ma trận 1 lần/group, resolve từng binding)
- Cache: ✅ (`supports_cache`, TTL mặc định 300s)
- Transform: ✅ (`supports_transform`)

## Khi nào dùng

- Bảng giá nhôm kính AL: giá = f(item_code, color, thickness, surface) — khách hàng chọn subset đặc tính, giá fallback theo các chiều còn lại.
- Parameter matrix nhiều chiều bất kỳ (thép, gỗ, linh kiện): tra giá/trọng lượng/định mức theo N thuộc tính.
- Cần fallback "rút dần chiều" khi không khớp exact: thử `[item_code, color]` → `[item_code]` → default.
- Cần `multiplier_chain`: base value × hệ số từng chiều không khớp.

## Config

```json
{
  "source_type": "composite_key_lookup",
  "variable_name": "price",
  "source_config": {
    "doctype": "AL Pricing",
    "value_field": "price",
    "key_fields": ["item_code", "color", "thickness", "surface"],
    "key_values": [],
    "fallback_keys": [["item_code", "color"], ["item_code"]],
    "match_mode": "exact",
    "multipliers": {},
    "filters": [],
    "default_value": 0
  }
}
```

| Field | Bắt buộc | Mô tả |
| --- | --- | --- |
| `doctype` | ✅ | DocType chứa các rows ma trận (mỗi row = 1 tổ hợp đặc tính + value). |
| `value_field` | ✅ | Field chứa giá trị cần trả về (vd `price`). |
| `key_fields` | — | Danh sách N tên field key (chiều). Nếu bỏ trống → chỉ khớp exact theo `key_values` (nếu có). |
| `key_values` | — | N giá trị key khớp với `key_fields`. Hỗ trợ template `{{row.field}}`, `{{doc.field}}`, `{{resolved.field}}`. Bỏ trống → auto-map `{{row.<key_field>}}` cho từng chiều. Chiều có value `None`/`''` bị bỏ qua. |
| `fallback_keys` | — | Danh sách có thứ tự các subset key fields để thử khi không khớp exact (rút dần chiều). Mỗi subset phải chứa các field nằm trong `key_fields`. |
| `match_mode` | — | `exact` (mặc định) \| `case_insensitive` \| `multiplier_chain`. |
| `multipliers` | — | Chỉ dùng khi `match_mode=multiplier_chain`: map dim → `{doctype, match_field, match_value, value_field}` để tra multiplier của chiều bị bỏ. |
| `filters` | — | Frappe filters bổ sung giới hạn query ma trận. |
| `default_value` | — | Giá trị trả về khi không khớp (mặc định 0). |

## Resolution order

1. **Exact** — khớp đủ toàn bộ `key_fields` đã resolve.
2. **Fallback subsets** — lần lượt từng subset trong `fallback_keys`:
   - Với subset, chỉ xét các row ứng viên mà chiều **không nằm trong subset** có giá trị `ANY`/`None`/`''` **hoặc bằng giá trị requested**. Row cụ thể có giá trị khác (vd `thickness=1.2` khi đang cần `9.9`) bị loại — đây là ngữ nghĩa đúng của bảng giá fallback (row tổng quát `ANY` thắng row cụ thể mâu thuẫn).
3. **Multiplier chain** — nếu `match_mode=multiplier_chain` và khớp fallback mà còn chiều bỏ: `base_value × ∏(multiplier của từng chiều không khớp)`.
4. **Default** — trả `default_value`.

## Template hỗ trợ

- `key_values`: `{{row.item_code}}`, `{{doc.quotation}}`, `{{resolved.price}}` — resolve qua `_resolve_template_val`.
- `multipliers[dim].match_value`: mặc định `{{row.<dim>}}` nếu bỏ trống.

## Batch behavior

`_resolve_composite_key_lookup_batch`:
- Group theo fingerprint → `_fetch_composite_rows(cfg)` 1 lần.
- Với mỗi binding: resolve `default_value = cfg.default_value` (fallback `binding.default_value`), `data_type`, dims từ `_resolve_key_values`, gọi `_resolve_composite_value`.
- Binding có `key_fields` thiếu value / rows rỗng → trả default.

## Ví dụ ứng dụng — bảng giá kính alumglass (size × thickness × màu)

Bảng giá kính: giá = f(size, thickness, color). Khi khách chọn kính, nếu không có đủ size chuẩn → fallback về size ANY, còn color không có → fallback về color ANY, và nếu cần màu đặc biệt → multiplier chain cho màu.

```json
{
  "source_type": "composite_key_lookup",
  "variable_name": "glass_price",
  "data_type": "Currency",
  "source_config": {
    "doctype": "AL Glass Price",
    "value_field": "unit_price",
    "key_fields": ["size", "thickness", "color"],
    "key_values": ["{{row.glass_size}}", "{{row.glass_thickness}}", "{{row.glass_color}}"],
    "fallback_keys": [
      ["size", "thickness"],
      ["size"],
      []
    ],
    "match_mode": "multiplier_chain",
    "multipliers": {
      "color": {
        "doctype": "AL Color Multiplier",
        "match_field": "color",
        "value_field": "multiplier"
      }
    },
    "filters": [["price_list", "=", "{{doc.price_list}}"]],
    "default_value": 0
  }
}
```

- `fallback_keys` bỏ dần chiều: khớp `size+thickness` → chỉ `size` → mọi size (`[]` = row tổng quát toàn ANY).
- `match_mode=multiplier_chain`: khi fallback bỏ chiều `color`, base × multiplier màu (tra từ `AL Color Multiplier`).
- `filters` giới hạn theo `price_list` hiện tại của doc.
- Row có chiều bỏ = `ANY`/`None`/`''` được ưu tiên; row cụ thể mâu thuẫn với giá trị requested bị loại.

## So sánh với `matrix_lookup`

| | `matrix_lookup` | `composite_key_lookup` |
| --- | --- | --- |
| Số chiều | 2 cố định (row_key, col_key) | N chiều động |
| Fallback | `fallback_row_key`/`fallback_col_key` (giá trị ANY) | `fallback_keys` (subset chiều) |
| Multiplier | không | `multiplier_chain` |
| Match mode | `case_insensitive` | `exact` / `case_insensitive` / `multiplier_chain` |

## Quyết định thiết kế

- **Fallback chọn row tổng quát thay vì row đầu tiên:** khi fallback subset khớp nhiều row, ưu tiên row có chiều bỏ là `ANY`/`None`/`''`; row cụ thể mâu thuẫn với requested bị loại khỏi ứng viên. Đảm bảo giá fallback đúng nghiệp vụ (bảng giá: bề dày cụ thể chỉ dùng khi khớp, nếu không thì dùng bề dày ANY).
- **Batch fetch 1 lần cho cả group** (cùng doctype + filters) để giảm query khi nhiều dòng cùng lookup trên một ma trận.
- **Auto-map `key_values` từ `{{row.<key_field>}}`** khi bỏ trống — binding gọn, không lặp template.

## Tests

`formula_builder/tests/test_fb1_revised.py` — `TestCompositeKeyLookupRegistration`, `TestCompositeKeyLookupResolve` (exact / auto-map / explicit override / no-match default / fallback / case_insensitive / multiplier_chain), `TestCompositeKeyLookupSchemaAndFingerprint`, `TestCompositeKeyLookupBatch`.
