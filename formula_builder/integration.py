# formula_builder/integration.py
"""
Public integration surface for other Frappe apps.
Other apps should import from here rather than reaching into internals.
"""
from __future__ import annotations
from typing import Any, Dict, List

import frappe

from formula_builder.flexible_formula_engine import (
    FlexibleFormulaEngine,
    EngineConfig,
    ChildTableConfig,
    ERPNextAdapter,
    CalculationResult,
    build_inputs_from_frappe_doc,
)
from formula_builder.api.variable_resolver import VariableResolver, ScopeContext


class FrappeERPNextAdapter(ERPNextAdapter):
    """Concrete adapter implementation — ready to use by any app."""

    def get_doc(self, doctype: str, docname: str):
        return frappe.get_doc(doctype, docname)

    def get_global_vars(self) -> Dict[str, Any]:
        try:
            resolver = VariableResolver()
            rows = frappe.get_all(
                "Formula Global Variable",
                filters={"is_active": 1, "value_source": "CONSTANT"},
                fields=["var_name", "constant_value", "var_type"],
            )
            return {
                r.var_name: resolver._cast(r.constant_value, r.var_type)
                for r in rows
            }
        except Exception:
            return {}

    def rows_to_dicts(self, doc, child_field: str) -> List[Dict]:
        rows = doc.get(child_field) or []
        return [
            row.as_dict() if hasattr(row, "as_dict") else dict(row)
            for row in rows
        ]


# Re-export common names for convenience
__all__ = [
    "FlexibleFormulaEngine", "EngineConfig", "ChildTableConfig",
    "FrappeERPNextAdapter", "CalculationResult",
    "build_inputs_from_frappe_doc", "VariableResolver", "ScopeContext",
]