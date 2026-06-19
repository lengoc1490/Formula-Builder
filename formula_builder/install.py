# formula_builder/install.py
import frappe


def after_migrate():
    """Seed default Formula Builder Settings with BASE_FUNCS on first migrate."""
    if frappe.db.exists("Formula Builder Settings", "Formula Builder Settings"):
        return

    settings = frappe.get_doc({
        "doctype": "Formula Builder Settings",
        "max_formula_length": 2000,
        "rate_limit_validate": 40,
        "rate_limit_evaluate": 20,
        "rate_limit_ai": 5,
        "ai_provider": "None",
        "ai_model": "claude-3-sonnet-20240229",
    })

    try:
        from formula_builder.formula_utils import BASE_FUNCS
        func_list = list(BASE_FUNCS.keys())
        for fn in func_list:
            settings.append("allowed_functions", {
                "func_name": fn,
                "category": "Other",
                "signature": f"{fn}(...)",
                "insert_template": f"{fn}($1)",
                "is_enabled": 1,
            })
    except Exception as e:
        frappe.log_error(f"Seed allowed functions failed: {e}", "Formula Builder Install")

    settings.insert(ignore_permissions=True)
    frappe.db.commit()