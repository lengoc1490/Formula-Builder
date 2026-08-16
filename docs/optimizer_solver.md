# Source Type: `optimizer_solver` (S6) — Design đề xuất

> **Trạng thái: DESIGN ONLY** (2026-08-16, track FB Platform Expansion). Chưa implement.
> Thuật toán (1D FFD / 2D Guillotine / allocation) tách riêng, source type chỉ là **wrapper pluggable**.

## Mục đích

Gọi **thuật toán** (cắt 1D FFD, cắt 2D Guillotine, allocation...) như một source type, đầu vào/ra có schema chuẩn. Dùng cho alumglass cắt S4, thép (cắt thanh), gỗ (cắt tấm).

## Config schema mẫu

```json
{
  "source_type": "optimizer_solver",
  "source_config": {
    "algorithm": "cutting_1d_ffd",        // key đăng ký thuật toán
    "algorithm_module": "alumglass.optimizers",  // module chứa hàm (whitelist như custom_function)
    "input": {
      "items": "{{row.demand_lines}}",     // danh sách (length, qty)
      "stock_length": 6000
    },
    "output_as": "patterns",               // key kết quả (patterns + scrap)
    "result_field": "scrap",               // field lấy từ kết quả nếu cần scalar
    "aggregation": "sum",
    "default_value": 0
  }
}
```

## Thiết kế

- **Registry thuật toán riêng** (nhẹ, map key → callable), app đăng ký qua hook `fb_optimizer_algorithms` — tránh nhét logic ngành vào FB.
- **Schema đầu vào chuẩn**: `items` (list of `{length/width, qty}`), constraints (stock dimension), params.
- **Schema đầu ra chuẩn**: `patterns` (list of `{cuts: [...], qty, waste}`), `scrap_total`, `material_used`.
- **Contract**:
  - `resolve(binding, doc, resolved_so_far)` → chạy solver trên input (resolve template từ row/doc/resolved), trả `result_field` sau `aggregation` (giống `reuse_formula_result`).
  - Không batch được nếu input khác nhau từng row → `batchable: false` (hoặc `resolve_batch` chỉ cache kết quả solver theo fingerprint đầu vào).
- **An toàn**: hàm solver phải nằm trong whitelist (tái dùng `_check_custom_function_allowed`) — không để user gọi hàm tùy ý.

## Edge case

- Input rỗng → `default_value`.
- Solver lỗi (không đủ stock, input sai) → trả lỗi + `default_value`, log qua `frappe.log_error`.
- Kết quả lớn (nhiều pattern) → cân nhắc giới hạn size / trả về dạng tham chiếu thay vì nhúng toàn bộ.

## Phụ thuộc

- Cần chốt: thuật toán **cắt tách riêng** (dự án S4) — source type chỉ là wrapper. Triển khai khi có solver thật.
