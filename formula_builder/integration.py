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
from formula_builder.table_formula_builder import (
    MultiTableFormulaBuilder,
    normalize_global,
    normalize_scoped,
    synthetic_for_pattern,
    synthetic_simple_total,
    build_engine_from_builder,
)
from formula_builder.api.variable_resolver import VariableResolver, ScopeContext
from formula_builder.api.batch_binding_resolver import (
    BatchBindingResolver,
    resolve_all_bindings_batch,
    _apply_transform,
)
from formula_builder.api.data_source_registry import (
    batchable,
    is_batchable,
    get_batch_resolver,
)
from formula_builder.api.source_type_registry import (
    SourceTypeRegistry,
    SourceTypeDefinition,
    register_source,
    list_source_types,
    get_source_type_schema,
    validate_binding_source_config as _validate_binding_source_config,
    get_registry_stats,
    test_data_source,
)


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
    # Batch resolver (v30.1)
    "BatchBindingResolver", "resolve_all_bindings_batch",
    "batchable", "is_batchable", "get_batch_resolver",
    # Source Type Registry (v31 Phase 1)
    "SourceTypeRegistry", "SourceTypeDefinition", "register_source",
    "list_source_types", "get_source_type_schema",
    "validate_binding_source_config", "get_registry_stats",
    "test_data_source",
    # MultiTableFormulaBuilder (v31 Phase 2) — multi-table formula construction
    "MultiTableFormulaBuilder",
    "normalize_global", "normalize_scoped",
    "synthetic_for_pattern", "synthetic_simple_total",
    "build_engine_from_builder",
]