# formula_utils/snapshot.py
# Snapshot management and registry for EnterpriseSnapshot

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from .types import (
    EngineMetaBlock,
    EngineContextBlock,
    DagStateBlock,
    ExecutionTraceBlock,
    AuditTrailBlock,
    EnterpriseSnapshot,
    ImmutableSnapshot,
    SnapshotTag,
    SnapshotStatus,
)


# ============================================================================
# Internal hash helpers
# ============================================================================

def _snap_payload_hash(meta: Dict, dag_state: Dict, inputs: Dict, outputs: Dict) -> str:
    """
    SHA-256 của meta + dag_state + inputs + outputs.
    dag_state (execution_order, edges, dirty_nodes) được đưa vào payload
    để hash bắt được cả trường hợp DAG khác nhau cho cùng inputs/outputs.
    """
    raw = json.dumps(
        {"meta": meta, "dag": dag_state, "inputs": inputs, "outputs": outputs},
        sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _snap_trace_hash(trace: Dict) -> str:
    raw = json.dumps(trace, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _snap_build_meta(engine: Any) -> EngineMetaBlock:
    """Build EngineMetaBlock from engine instance."""
    topo = getattr(engine, '_topo_order', [])
    topo_hash = hashlib.sha256(
        json.dumps(topo, ensure_ascii=False).encode()
    ).hexdigest()
    in_s = {k: str(v) for k, v in getattr(engine, '_input_schema', {}).items()}
    out_s = {k: str(v) for k, v in getattr(engine, '_output_schema', {}).items()}
    schema_hash = hashlib.sha256(
        json.dumps({"in": in_s, "out": out_s}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    meta_obj = getattr(engine, '_meta', None)
    frozen = bool(meta_obj and getattr(meta_obj, 'frozen', False))
    return EngineMetaBlock(
        engine_version=getattr(engine, 'ENGINE_VERSION', 'unknown'),
        formula_hash=getattr(engine, '_hash', ''),
        formula_count=len(getattr(engine, '_formulas', [])),
        topo_order_hash=topo_hash,
        schema_hash=schema_hash,
        frozen=frozen,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )


def _snap_build_context(engine: Any, inputs: Dict, outputs: Dict) -> EngineContextBlock:
    """Build EngineContextBlock from engine instance."""
    _mode_map = {1: 'raise', 2: 'null', 3: 'default'}
    return EngineContextBlock(
        dag_version=getattr(engine, '_hash', ''),
        input_keys=sorted(inputs.keys()),
        output_keys=sorted(outputs.keys()),
        rounding_policy=dict(getattr(engine, '_rounding_policy', None) or {}),
        error_mode=_mode_map.get(getattr(engine, '_mode', 3), 'default'),
    )


def _snap_build_dag_state(
    engine: Any,
    dirty_nodes: Optional[List[str]] = None,
    calc_mode: str = "full",
) -> DagStateBlock:
    """Build DagStateBlock from engine instance."""
    topo_order = list(getattr(engine, '_topo_order', []))
    formula_set = set(topo_order)

    raw_deps = getattr(engine, '_deps_cache', {})   # name → set of parents
    dep_edges: Dict[str, List[str]] = {
        k: sorted(v) for k, v in raw_deps.items() if k in formula_set
    }

    raw_rev = getattr(engine, '_reverse_deps', {})  # name → set of children
    rev_edges: Dict[str, List[str]] = {
        k: sorted(v) for k, v in raw_rev.items()
    }

    all_referenced: set = set()
    for parents in raw_deps.values():
        all_referenced.update(parents)
    input_nodes = sorted(all_referenced - formula_set)

    raw_input_edges = getattr(engine, '_input_edges', {})
    for inp_var in raw_input_edges:
        if inp_var not in formula_set and inp_var not in input_nodes:
            input_nodes.append(inp_var)
    input_nodes = sorted(set(input_nodes))

    return DagStateBlock(
        execution_order=topo_order,
        dependency_edges=dep_edges,
        reverse_edges=rev_edges,
        input_nodes=input_nodes,
        formula_nodes=topo_order,
        dirty_nodes=list(dirty_nodes or []),
        calc_mode=calc_mode,
        input_edges={k: sorted(v) for k, v in raw_input_edges.items()},
    )


# ============================================================================
# SnapshotManager
# ============================================================================

class SnapshotManager:
    """Create, compare, and manage EnterpriseSnapshots."""

    @staticmethod
    def create_snapshot(
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        trace: Optional[Dict] = None
    ) -> ImmutableSnapshot:
        """[v11 compat] Tạo ImmutableSnapshot đơn giản (không cần engine)."""
        timestamp = datetime.now(timezone.utc).isoformat()
        snapshot_id = str(uuid.uuid4())
        hashable = {
            "snapshot_id": snapshot_id,
            "created_at": timestamp,
            "inputs": inputs,
            "outputs": outputs
        }
        # Avoid circular import of hash_dict from normalize
        from .normalize import hash_dict
        return ImmutableSnapshot(
            snapshot_id=snapshot_id,
            created_at=timestamp,
            inputs=dict(inputs),
            outputs=dict(outputs),
            integrity_hash=hash_dict(hashable),
            trace=trace,
        )

    @staticmethod
    def compare_snapshots(
        snap1: ImmutableSnapshot,
        snap2: ImmutableSnapshot,
    ) -> Dict[str, Any]:
        """[v11 compat] So sánh 2 ImmutableSnapshot."""
        diff: Dict[str, Any] = {"inputs_changed": {}, "outputs_changed": {}, "summary": {}}
        for k in set(snap1.inputs) | set(snap2.inputs):
            v1, v2 = snap1.inputs.get(k), snap2.inputs.get(k)
            if v1 != v2:
                diff["inputs_changed"][k] = {"before": v1, "after": v2}
        for k in set(snap1.outputs) | set(snap2.outputs):
            v1, v2 = snap1.outputs.get(k), snap2.outputs.get(k)
            if v1 != v2:
                diff["outputs_changed"][k] = {"before": v1, "after": v2}
        diff["summary"] = {
            "inputs_changed_count": len(diff["inputs_changed"]),
            "outputs_changed_count": len(diff["outputs_changed"]),
            "timestamp_1": snap1.created_at,
            "timestamp_2": snap2.created_at,
        }
        return diff

    # ── v12 Enterprise API ─────────────────────────────────────────────────

    @staticmethod
    def create(
        engine: Any,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        tag: SnapshotTag = SnapshotTag.ESTIMATE,
        status: SnapshotStatus = SnapshotStatus.DRAFT,
        created_by: str = "system",
        exec_trace: Optional[ExecutionTraceBlock] = None,
        dirty_nodes: Optional[List[str]] = None,
        calc_mode: str = "full",
        parent_snapshot: Optional[EnterpriseSnapshot] = None,
        revision_chain: Optional[List[str]] = None,
        notes: Optional[str] = None,
        source_doc: Optional[str] = None,
        approved_by: Optional[str] = None,
    ) -> EnterpriseSnapshot:
        snapshot_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        # Layer 1
        meta = _snap_build_meta(engine)
        # Layer 2a
        engine_context = _snap_build_context(engine, inputs, outputs)
        # Layer 2b — DAG state
        dag_state = _snap_build_dag_state(engine, dirty_nodes=dirty_nodes, calc_mode=calc_mode)
        # Layer 3 — Execution trace
        if exec_trace is None:
            exec_trace = ExecutionTraceBlock(
                fields_evaluated=0,
                fields_skipped=0,
                total_exec_ms=0.0,
                entries=[],
            )
        # Layer 5
        parent_id = parent_snapshot.snapshot_id if parent_snapshot else None
        if parent_snapshot and revision_chain is None:
            chain = list(parent_snapshot.audit_trail.revision_chain or [])
            chain.append(parent_snapshot.snapshot_id)
            revision_chain = chain

        audit_trail = AuditTrailBlock(
            tag=tag.value if isinstance(tag, SnapshotTag) else tag,
            status=status.value if isinstance(status, SnapshotStatus) else status,
            created_by=created_by,
            approved_by=approved_by,
            parent_snapshot_id=parent_id,
            revision_chain=revision_chain or [],
            notes=notes,
            source_doc=source_doc,
        )

        # Dual Hash
        payload_hash = _snap_payload_hash(
            meta.to_dict(), dag_state.to_dict(), inputs, outputs
        )
        trace_hash = _snap_trace_hash(exec_trace.to_dict()) if exec_trace.entries else None

        return EnterpriseSnapshot(
            snapshot_id=snapshot_id,
            created_at=created_at,
            meta=meta,
            engine_context=engine_context,
            dag_state=dag_state,
            exec_trace=exec_trace,
            business_input=dict(inputs),
            outputs=dict(outputs),
            audit_trail=audit_trail,
            payload_hash=payload_hash,
            trace_hash=trace_hash,
        )

    @staticmethod
    def revise(
        engine: Any,
        previous_snapshot: EnterpriseSnapshot,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        tag: SnapshotTag = SnapshotTag.ACTUAL,
        status: SnapshotStatus = SnapshotStatus.DRAFT,
        created_by: str = "system",
        exec_trace: Optional[ExecutionTraceBlock] = None,
        dirty_nodes: Optional[List[str]] = None,
        calc_mode: str = "full",
        notes: Optional[str] = None,
        source_doc: Optional[str] = None,
    ) -> EnterpriseSnapshot:
        return SnapshotManager.create(
            engine=engine,
            inputs=inputs,
            outputs=outputs,
            tag=tag,
            status=status,
            created_by=created_by,
            exec_trace=exec_trace,
            dirty_nodes=dirty_nodes,
            calc_mode=calc_mode,
            parent_snapshot=previous_snapshot,
            notes=notes,
            source_doc=source_doc,
        )

    @staticmethod
    def compare(
        snap1: EnterpriseSnapshot,
        snap2: EnterpriseSnapshot,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "snapshot_1": snap1.snapshot_id,
            "snapshot_2": snap2.snapshot_id,
            "timestamp_1": snap1.created_at,
            "timestamp_2": snap2.created_at,
            "tag_1": snap1.audit_trail.tag,
            "tag_2": snap2.audit_trail.tag,
            "same_engine": snap1.meta.formula_hash == snap2.meta.formula_hash,
            "inputs_changed": {},
            "outputs_changed": {},
            "meta_diff": {},
            "summary": {},
        }
        # Meta diff
        for attr in ('engine_version', 'formula_hash', 'topo_order_hash', 'schema_hash', 'frozen'):
            v1, v2 = getattr(snap1.meta, attr), getattr(snap2.meta, attr)
            if v1 != v2:
                result["meta_diff"][attr] = {"before": v1, "after": v2}
        # Inputs diff
        for k in set(snap1.business_input) | set(snap2.business_input):
            v1, v2 = snap1.business_input.get(k), snap2.business_input.get(k)
            if v1 != v2:
                result["inputs_changed"][k] = {"before": v1, "after": v2}
        # Outputs diff + delta %
        for k in set(snap1.outputs) | set(snap2.outputs):
            v1, v2 = snap1.outputs.get(k), snap2.outputs.get(k)
            if v1 != v2:
                entry: Dict[str, Any] = {"before": v1, "after": v2}
                if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                    delta = v2 - v1
                    entry["delta"] = delta
                    entry["delta_pct"] = round(delta / abs(v1) * 100, 4) if v1 != 0 else None
                result["outputs_changed"][k] = entry
        result["summary"] = {
            "inputs_changed_count": len(result["inputs_changed"]),
            "outputs_changed_count": len(result["outputs_changed"]),
            "meta_changed": bool(result["meta_diff"]),
            "same_engine": result["same_engine"],
        }
        return result

    @staticmethod
    def from_legacy(
        legacy_snapshot: ImmutableSnapshot,
        engine: Any,
        tag: SnapshotTag = SnapshotTag.ESTIMATE,
        created_by: str = "migrated",
    ) -> EnterpriseSnapshot:
        return SnapshotManager.create(
            engine=engine,
            inputs=dict(legacy_snapshot.inputs),
            outputs=dict(legacy_snapshot.outputs),
            tag=tag,
            status=SnapshotStatus.ARCHIVED,
            created_by=created_by,
            notes=f"Migrated from legacy snapshot {legacy_snapshot.snapshot_id}",
        )


# ============================================================================
# SnapshotRegistry
# ============================================================================

class SnapshotRegistry:
    """Registry for storing and querying EnterpriseSnapshots."""

    def __init__(self):
        self._store: Dict[str, EnterpriseSnapshot] = {}

    def register(self, snap: EnterpriseSnapshot) -> None:
        self._store[snap.snapshot_id] = snap

    def get(self, snapshot_id: str) -> Optional[EnterpriseSnapshot]:
        return self._store.get(snapshot_id)

    def query(
        self,
        tag: Optional[SnapshotTag] = None,
        status: Optional[SnapshotStatus] = None,
        created_by: Optional[str] = None,
        source_doc: Optional[str] = None,
    ) -> List[EnterpriseSnapshot]:
        results = list(self._store.values())
        if tag is not None:
            tv = tag.value if isinstance(tag, SnapshotTag) else tag
            results = [s for s in results if s.audit_trail.tag == tv]
        if status is not None:
            sv = status.value if isinstance(status, SnapshotStatus) else status
            results = [s for s in results if s.audit_trail.status == sv]
        if created_by is not None:
            results = [s for s in results if s.audit_trail.created_by == created_by]
        if source_doc is not None:
            results = [s for s in results if s.audit_trail.source_doc == source_doc]
        results.sort(key=lambda s: s.created_at, reverse=True)
        return results

    def revision_history(self, snapshot_id: str) -> List[EnterpriseSnapshot]:
        snap = self.get(snapshot_id)
        if not snap:
            return []
        all_ids = list(snap.audit_trail.revision_chain) + [snap.snapshot_id]
        return [self._store[sid] for sid in all_ids if sid in self._store]

    def lock(self, snapshot_id: str) -> Optional[EnterpriseSnapshot]:
        """Chuyển status → LOCKED. Trả về snapshot đã lock."""
        snap = self.get(snapshot_id)
        if snap is None:
            return None
        new_trail = AuditTrailBlock(
            tag=snap.audit_trail.tag,
            status=SnapshotStatus.LOCKED.value,
            created_by=snap.audit_trail.created_by,
            approved_by=snap.audit_trail.approved_by,
            parent_snapshot_id=snap.audit_trail.parent_snapshot_id,
            revision_chain=snap.audit_trail.revision_chain,
            notes=snap.audit_trail.notes,
            source_doc=snap.audit_trail.source_doc,
        )
        locked = EnterpriseSnapshot(
            snapshot_id=snap.snapshot_id,
            created_at=snap.created_at,
            meta=snap.meta,
            engine_context=snap.engine_context,
            dag_state=snap.dag_state,
            exec_trace=snap.exec_trace,
            business_input=snap.business_input,
            outputs=snap.outputs,
            audit_trail=new_trail,
            payload_hash=snap.payload_hash,
            trace_hash=snap.trace_hash,
        )
        self._store[snapshot_id] = locked
        return locked

    def export_json(self, snapshot_id: str, indent: int = 2) -> Optional[str]:
        snap = self.get(snapshot_id)
        return snap.to_json(indent) if snap else None

    def __len__(self) -> int:
        return len(self._store)

    def __repr__(self) -> str:
        return f"<SnapshotRegistry: {len(self)} snapshots>"