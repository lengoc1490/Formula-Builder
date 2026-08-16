# Source Type: `imported_reference_table` (S3) — Design đề xuất

> **Trạng thái: DESIGN ONLY** (2026-08-16, track FB Platform Expansion). Chưa implement.
> Source_type này cần Owner/SA1 chốt cơ chế lưu file upload trước khi code.

## Mục đích

Đọc bảng tham chiếu từ **file Excel/CSV upload** (bảng giá import, hệ số vận chuyển, định mức ngoài) mà không cần tạo DocType cho từng bảng.

## Config schema mẫu

```json
{
  "source_type": "imported_reference_table",
  "source_config": {
    "file_doctype": "FB Imported Table",       // DocType lưu file + metadata
    "file_field": "file",                      // field Attach chứa file
    "table_name": "transport_coefficients",    // tên bảng đã import (hoặc document name)
    "sheet_index": 0,                          // Excel: sheet number
    "header_row": 0,                           // dòng tiêu đề (0-based)
    "column_map": {                            // map cột file → key chuẩn
      "Khu vực": "region",
      "Trọng lượng": "weight",
      "Hệ số": "factor"
    },
    "row_key": "{{row.region}}",
    "col_key": "{{row.weight}}",
    "value_field": "factor",
    "default_value": 1.0,
    "fallback_row_key": "ANY"
  }
}
```

## Thiết kế

- **Lưu file**: DocType `FB Imported Table` (hoặc app tự lo) giữ file Attach + cột tiêu đề. Tạo mới ở bước triển khai.
- **Parser**: `frappe.utils.xlsxutils.read_xlsx_file_from_attached_file` cho Excel; `frappe.utils.csvutils` cho CSV. Parse 1 lần rồi cache theo (file, mtime) → `fingerprint_fn`.
- **Lookup**: giống `matrix_lookup` (hàng × cột → giá trị), dùng chung helper `_matrix_lookup_value`; hoặc lookup đơn cột theo `row_key` khi chỉ có 1 chiều.
- **Batch**: group theo (file, column_map) → parse 1 lần, reuse cho cả nhóm.

## Edge case

- File thay đổi → fingerprint phải đổi (dùng `modified`/content hash của file).
- Cột tiêu đề thiếu → lỗi rõ ràng khi validate.
- Value rỗng / không parse được number → `default_value`.

## Phụ thuộc

- Không. Nhưng cần quyết định: file do **ai upload** (form admin FB? upload từng app?) và **giữ ở đâu** (DocType chung FB hay app tự lo).
