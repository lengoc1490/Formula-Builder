# Copyright (c) 2026, Lê Ngọc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# 2026-10 (fix hiệu năng #5): khoá cache dùng chung — PHẢI khớp đúng khoá
# phía đọc (vd alumglass.engine.bom_orchestrator._get_global_variables_
# cached). Bảng này là hằng số cấu hình, đọc rất nhiều lần (mỗi lần tính 1
# dòng BOM) nhưng gần như không đổi — cache Redis qua frappe.cache(), clear
# chủ động ở đây mỗi khi có save/xoá để không cần TTL ngắn.
GLOBAL_VARIABLE_CACHE_KEY = "formula_builder:global_variables"


class FormulaGlobalVariable(Document):
	def on_update(self):
		frappe.cache().delete_value(GLOBAL_VARIABLE_CACHE_KEY)

	def on_trash(self):
		frappe.cache().delete_value(GLOBAL_VARIABLE_CACHE_KEY)