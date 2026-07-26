"""Formula Snapshot — DocType controller.

Persistence layer for EnterpriseSnapshot.
Memory-first: snapshot is created in-memory via SnapshotManager.create(),
then explicitly persisted to DB via SnapshotManager.submit().
"""

import frappe
from frappe.model.document import Document


class FormulaSnapshot(Document):
    """Persisted snapshot of a Formula Engine evaluation run.

    Chỉ được tạo qua SnapshotManager.submit() — không tạo thủ công.
    Mỗi record lưu toàn bộ 5-layer EnterpriseSnapshot để audit trail.
    """

    def validate(self):
        """Validate required fields and hash integrity."""
        if not self.snapshot_id:
            frappe.throw("Snapshot ID is required")

        # Validate JSON fields parse correctly
        json_fields = [
            "engine_meta", "engine_context", "dag_structure",
            "formulas", "business_input", "outputs",
            "audit_trail", "execution_trace",
        ]
        import json
        for fieldname in json_fields:
            val = self.get(fieldname)
            if val:
                try:
                    if isinstance(val, str):
                        json.loads(val)
                except json.JSONDecodeError:
                    frappe.throw(f"Field '{fieldname}' must be valid JSON")

    def on_trash(self):
        """Prevent deletion of approved/locked snapshots."""
        if self.status in ("approved", "locked"):
            frappe.throw(
                f"Cannot delete snapshot '{self.snapshot_id}' "
                f"with status '{self.status}'. Archive it instead."
            )

    def before_save(self):
        """Auto-set engine_version if not provided."""
        if not self.engine_version:
            from formula_builder.formula_utils import __engine_version__
            self.engine_version = __engine_version__
