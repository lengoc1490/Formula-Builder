"""Cache dùng chung cho bảng `Formula Global Variable`.

Bảng này là hằng số cấu hình (VAT_RATE, NC_SX_PCT, ...): đọc RẤT nhiều lần
(mỗi dòng BOM tính là 1 lần đọc) nhưng gần như không đổi → cache trong Redis
qua `frappe.cache()` để khỏi full-table-scan mỗi lần đọc.

Invalidate: `FormulaGlobalVariable.on_update`/`on_trash` gọi
`invalidate_global_variable_cache()`.

⚠️ NGOẠI LỆ ĐÃ BIẾT — `frappe.db.set_value()` KHÔNG chạy document event
(xem `frappe/database/database.py`: "will not call Document events"), nên
đường ghi đó (patch, data import, script) KHÔNG xoá được cache này. Vì vậy:
  · `CACHE_TTL_SECONDS` là LƯỚI AN TOÀN chặn cửa sổ đọc giá trị cũ;
  · nơi nào chủ động ghi bằng `frappe.db.set_value` thì nên gọi thẳng
    `invalidate_global_variable_cache()` sau khi commit.
"""
import frappe

GLOBAL_VARIABLE_CACHE_KEY = "formula_builder:global_variables"

# Lưới an toàn cho các đường ghi bỏ qua controller (frappe.db.set_value).
# Bảng rất nhỏ nên hạ TTL gần như không tốn gì; đổi giá trị hằng số mà phải
# chờ 10 phút mới ăn thì giá tính ra sai trong 10 phút — không đánh đổi được.
CACHE_TTL_SECONDS = 60

_FIELDS = ["var_name", "constant_value"]


def get_all_global_variables():
    """Trả list[dict] gồm `var_name`, `constant_value` — đọc qua cache Redis.

    `expires=True`: khoá này có TTL nên KHÔNG được nhớ vào `frappe.local.cache`
    (xem `frappe/utils/redis_wrapper.py::get_value` — khi Redis miss mà
    `expires=False` thì hàm ghi `None` vào cache cục bộ, và vì `set_value` có
    `expires_in_sec` nên nó KHÔNG ghi lại giá trị thật vào đó → cả request giữ
    nguyên `None` và query lại DB mỗi lần gọi).
    """
    cached = frappe.cache().get_value(GLOBAL_VARIABLE_CACHE_KEY, expires=True)
    if cached is not None:
        return cached
    data = frappe.get_all("Formula Global Variable", fields=_FIELDS) or []
    frappe.cache().set_value(
        GLOBAL_VARIABLE_CACHE_KEY, data, expires_in_sec=CACHE_TTL_SECONDS
    )
    return data


def invalidate_global_variable_cache():
    """Xoá cache (cả bản trong Redis và bản trong `frappe.local.cache`)."""
    frappe.cache().delete_value(GLOBAL_VARIABLE_CACHE_KEY)
