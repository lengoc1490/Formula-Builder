# Copyright (c) 2026, Lê Ngọc and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# 2026-10 (fix hiệu năng #5): cache + khoá cache nằm ở 1 nguồn duy nhất —
# formula_builder/api/global_variable_cache.py (cả phía đọc dùng chung, vd
# alumglass.engine.bom_orchestrator). Bảng này là hằng số cấu hình, đọc rất
# nhiều lần (mỗi lần tính 1 dòng BOM) nhưng gần như không đổi → cache Redis
# qua frappe.cache(), xoá chủ động ở đây mỗi khi có save/xoá.
#
# ⚠️ `frappe.db.set_value()` KHÔNG chạy document event (xem
# frappe/database/database.py: "will not call Document events"), nên đường
# ghi đó (patch / data import / script) KHÔNG xoá được cache qua đây —
# TTL 60s trong global_variable_cache.py là lưới an toàn cho các đường ghi ấy.
# Re-export tên cũ để nơi khác đang import từ file này không vỡ.
from formula_builder.api.global_variable_cache import (
	GLOBAL_VARIABLE_CACHE_KEY,
	invalidate_global_variable_cache,
)


class FormulaGlobalVariable(Document):
	def on_update(self):
		invalidate_global_variable_cache()

	def on_trash(self):
		invalidate_global_variable_cache()
