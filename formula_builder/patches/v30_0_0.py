"""Migration patches for Formula Builder v30.0.0 (Phase 2 → Phase 3).

Chạy tự động khi `bench migrate`.

Patches:
  1. set_default_rate_limits: Cập nhật rate_limit defaults nếu chưa được set
  2. ensure_formula_builder_settings: Đảm bảo Settings singleton tồn tại
"""

import frappe


def set_default_rate_limits():
    """Cập nhật rate_limit defaults cho các site đã cài đặt từ trước.

    Trước Phase 2: hardcode validate=40, evaluate=20, ai=5
    Sau Phase 2:  evaluate/validate KHÔNG rate limit, ai=10 (đọc từ Settings)
    """
    try:
        settings = frappe.get_single("Formula Builder Settings")

        # Chỉ update nếu giá trị là default cũ (40, 20, 5)
        # Nếu admin đã custom thì giữ nguyên
        changed = False

        if settings.rate_limit_ai == 5:
            settings.rate_limit_ai = 10
            changed = True

        if changed:
            settings.save(ignore_permissions=True)
            frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"set_default_rate_limits failed: {e}", "Formula Builder Patch")


def ensure_formula_builder_settings():
    """Đảm bảo Formula Builder Settings singleton tồn tại sau migrate.

    Nếu chưa có → tạo với defaults từ install.py.
    """
    if frappe.db.exists("Formula Builder Settings", "Formula Builder Settings"):
        return

    try:
        from formula_builder.formula_utils import BASE_FUNCS

        settings = frappe.get_doc({
            "doctype": "Formula Builder Settings",
            "max_formula_length": 2000,
            "rate_limit_validate": 120,
            "rate_limit_evaluate": 120,
            "rate_limit_ai": 10,
            "ai_provider": "None",
            "ai_model": "claude-3-5-sonnet-20241022",
        })

        for fn in BASE_FUNCS:
            settings.append("allowed_functions", {
                "func_name": fn,
                "category": "Other",
                "signature": f"{fn}(...)",
                "insert_template": f"{fn}($1)",
                "is_enabled": 1,
            })

        settings.insert(ignore_permissions=True)
        frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"ensure_formula_builder_settings failed: {e}", "Formula Builder Patch")
