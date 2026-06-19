# formula_utils/engine_audit.py
# Audit engine - extends trace engine with full audit capabilities

import random
import time
from typing import Dict, Any, Optional, Set, List, Tuple, Union, Iterable

from .engine_trace import FormulaEngineTrace
from .engine_core import IncrementalContext
from .types import (
    AuditSession, AuditReport, TraceNode, IncrementalStats,
    AssertionViolation, AuditLevel
)
from .errors import FormulaError, ErrorCode
from .normalize import hash_dict


class FormulaEngineAudit(FormulaEngineTrace):
    """
    Full audit support with trace trees and sessions.
    Extends FormulaEngineTrace with audit logging, sample recording,
    execution tree materialization, and batch calculation with audit reports.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_session: Optional[AuditSession] = None

    def begin_audit_session(
        self,
        force_materialize: bool = False,
        sample_rate: float = 0.001,
    ) -> AuditSession:
        """Start an audit session."""
        input_schema_hash = hash_dict({
            k: {"dtype": f.dtype.__name__}
            for k, f in self._input_schema.items()
        })
        output_schema_hash = hash_dict({
            k: {"unit": f.unit, "bucket": f.bucket, "primary": f.primary}
            for k, f in self._output_schema.items()
        })
        batch_hash = hashlib.sha256(
            (self._hash + self.ENGINE_VERSION + input_schema_hash + output_schema_hash).encode()
        ).hexdigest()

        session = AuditSession(
            formula_set_uid=self._meta.uid() if self._meta else "N/A",
            batch_hash=batch_hash,
            force_materialize=force_materialize,
            sample_rate=sample_rate
        )
        self.current_session = session
        return session

    def calculate(
        self,
        inputs: Dict[str, Any],
        trace_fields: Optional[Set[str]] = None,
        explain_ui: bool = False,
        audit: bool = False,
        strict: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Calculate with optional audit logging."""
        result = super().calculate(inputs, trace_fields=trace_fields, explain_ui=explain_ui, strict=strict)

        if audit and self.current_session:
            session = self.current_session
            session.rows_processed += 1

            # Sample logging
            if random.random() < session.sample_rate:
                session.add_sample(session.rows_processed, {
                    "inputs": dict(inputs),
                    "outputs": {n: result[n] for n in self._topo_order},
                })

            result["_audit_ref"] = session.session_id

        return result

    def materialize_tree(self, log_entry: Dict, target_output: str) -> TraceNode:
        """Build execution tree from log entry."""
        if target_output not in log_entry["outputs"]:
            raise FormulaError(
                f"Target output '{target_output}' not found in log entry",
                code=ErrorCode.TARGET_OUTPUT_NOT_FOUND
            )

        path = set()

        def build(node_name: str, level: int = 0) -> Optional[TraceNode]:
            if node_name in path:
                return None

            path.add(node_name)
            deps = self._deps_cache.get(node_name, set())

            node = TraceNode(
                name=node_name,
                formula=self._original_expr.get(node_name, ""),
                value=log_entry["outputs"].get(node_name),
                deps={d: log_entry["outputs"].get(d, log_entry["inputs"].get(d)) for d in deps},
                level=level,
                is_input=node_name in log_entry["inputs"]
            )

            for dep in sorted(deps):
                child = build(dep, level + 1)
                if child:
                    node.children.append(child)

            path.remove(node_name)
            return node

        root = build(target_output)
        if not root:
            root = TraceNode("ROOT", "No dependencies found", None, {})
        return root

    def end_audit_session(self, target_output: Optional[str] = None) -> AuditReport:
        if not self.current_session:
            raise FormulaError("No active audit session", code=ErrorCode.AUDIT_SESSION_NOT_ACTIVE)

        session = self.current_session
        session.finalize(session.rows_processed)

        rows_count = max(session.rows_processed, 1)
        fields_per_row = len(self._topo_order)

        report = AuditReport(
            calculation_id=session.session_id,
            formula_set_uid=session.formula_set_uid,
            calculated_at=session.started_at,
            executed_by="system",
            scenario="audit_batch",
            fields_calculated=fields_per_row * rows_count,
            rows_processed=session.rows_processed,
            inputs_hash=session.batch_hash,
            outputs_hash="",
            violations=session.violations,
        )

        # Materialize execution tree if target_output and data available
        if target_output and (session.force_materialize or session.violations):
            if session.sample_logs:
                sample = session.sample_logs[0]
                try:
                    report.execution_tree = self.materialize_tree(sample, target_output)
                except FormulaError:
                    pass  # target_output not in sample → skip

        self.current_session = None
        return report

    def calculate_batch(
        self,
        rows: Iterable[Dict[str, Any]],
        trace_fields: Optional[Set[str]] = None,
        explain_ui: bool = False,
        audit: bool = False,
        target_output: str = None,
        strict: Optional[bool] = None
    ) -> Tuple[List[Dict[str, Any]], Optional[AuditReport]]:
        """Batch calculation with optional audit."""
        start = time.perf_counter()
        results = []

        for row in rows:
            res = self.calculate(row, trace_fields=trace_fields, explain_ui=explain_ui, audit=audit, strict=strict)
            results.append(res)

        total_ms = (time.perf_counter() - start) * 1000

        report = None
        if audit:
            report = self.end_audit_session(target_output=target_output)
            report.total_execution_time_ms = total_ms

        return results, report

    def calculate_incremental(
        self,
        ictx: IncrementalContext,
        changed_inputs: Dict[str, Any],
        strict: Optional[bool] = None,
        return_stats: bool = False,
        trace_fields: Optional[Set[str]] = None,
        explain_ui: bool = False,
        audit: bool = False,
    ) -> Union[Dict[str, Any], Tuple[Dict[str, Any], IncrementalStats]]:
        out = super().calculate_incremental(
            ictx, changed_inputs,
            strict=strict,
            return_stats=return_stats,
            trace_fields=trace_fields,
            explain_ui=explain_ui,
        )

        if audit and self.current_session:
            session = self.current_session
            session.rows_processed += 1
            if random.random() < session.sample_rate:
                session.add_sample(session.rows_processed, {
                    "inputs": dict(ictx._inputs),
                    "outputs": dict(ictx._outputs),
                    "changed_inputs": list(changed_inputs.keys()),
                    "mode": "incremental",
                })

            # Inject audit ref into result dict
            if return_stats:
                result, stats = out
                result["_audit_ref"] = session.session_id
                return result, stats
            else:
                out["_audit_ref"] = session.session_id

        return out


# Avoid circular import of hashlib
import hashlib