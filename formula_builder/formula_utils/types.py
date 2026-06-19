# formula_utils/types.py
# Dataclasses, enums, and type definitions for Formula Engine

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, date, timezone
from enum import Enum
import uuid


# ============================================================================
# Enums
# ============================================================================

class AuditLevel(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SnapshotTag(str, Enum):
    """Loại snapshot theo giai đoạn nghiệp vụ"""
    ESTIMATE = "estimate"   # Báo giá / ước tính ban đầu
    PLAN     = "plan"       # Kế hoạch (sau khi confirm estimate)
    ACTUAL   = "actual"     # Chi phí thực tế phát sinh
    VARIANCE = "variance"   # Phân tích chênh lệch
    VOID     = "void"       # Đã hủy / không dùng


class SnapshotStatus(str, Enum):
    """Trạng thái xử lý của snapshot"""
    DRAFT    = "draft"      # Đang tạo
    LOCKED   = "locked"     # Đã khóa, không sửa được
    APPROVED = "approved"   # Đã duyệt
    REJECTED = "rejected"   # Bị từ chối
    ARCHIVED = "archived"   # Lưu trữ


# ============================================================================
# Explain & Validation
# ============================================================================

@dataclass
class ExplainStep:
    """Một bước trong chuỗi tính toán của explain()."""
    name: str               # tên formula
    formula: str            # công thức gốc
    value: Any              # kết quả tính
    deps: Dict[str, Any]    # {dep_name: dep_value}
    depth: int              # độ sâu trong DAG (0 = không phụ thuộc formula nào)
    is_root: bool = False   # True nếu đây là field được explain

    def to_line(self) -> str:
        """Một dòng human-readable."""
        dep_str = ", ".join(f"{k}={v}" for k, v in self.deps.items()) if self.deps else "—"
        indent = "  " * self.depth
        return f"{indent}{self.name} = {self.formula}  →  {self.value}  (dùng: {dep_str})"


@dataclass
class ExplainResult:
    """Kết quả explain() cho một field."""
    field: str              # field được giải thích
    value: Any              # giá trị cuối cùng
    steps: List[ExplainStep]  # các bước theo thứ tự tính
    inputs_used: Dict[str, Any]  # inputs trực tiếp ảnh hưởng đến field này

    def to_text(self) -> str:
        """Human-readable text dạng cây."""
        lines = [f"Giải thích: {self.field} = {self.value}", ""]
        if self.inputs_used:
            lines.append("Inputs sử dụng:")
            for k, v in sorted(self.inputs_used.items()):
                lines.append(f"  {k} = {v}")
            lines.append("")
        lines.append("Chuỗi tính toán:")
        for step in self.steps:
            lines.append(step.to_line())
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize thành dict — tiện cho API/JSON response."""
        return {
            "field": self.field,
            "value": self.value,
            "inputs_used": self.inputs_used,
            "steps": [
                {
                    "name": s.name,
                    "formula": s.formula,
                    "value": s.value,
                    "deps": s.deps,
                    "depth": s.depth,
                    "is_root": s.is_root,
                }
                for s in self.steps
            ],
        }


@dataclass
class InputIssue:
    """Một vấn đề phát hiện khi validate inputs."""
    field: str
    issue: str      # mô tả lỗi human-readable
    value: Any      # giá trị thực tế
    severity: str = "error"   # "error" | "warning"
    expected: Any = None      # giá trị/type/range mong đợi

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "issue": self.issue,
            "value": self.value,
            "severity": self.severity,
            "expected": self.expected,
        }


@dataclass
class ScenarioComparison:
    """Kết quả so sánh nhiều scenario."""
    scenarios: List[str]        # tên các scenario
    fields: List[str]           # fields được so sánh
    results: Dict[str, Dict[str, Any]]   # {scenario: {field: value}}
    delta: Dict[str, Dict[str, Any]]     # {field: {scenario_b_vs_a: delta}}
    base_scenario: str = ""     # scenario làm gốc so sánh

    def to_table(self) -> str:
        """Text table dễ đọc."""
        if not self.scenarios or not self.fields:
            return "(không có dữ liệu)"
        col_w = 18
        header = "Field".ljust(col_w) + "".join(s[:col_w].ljust(col_w) for s in self.scenarios)
        sep = "-" * len(header)
        lines = [header, sep]
        for fld in self.fields:
            row = fld[:col_w].ljust(col_w)
            for sc in self.scenarios:
                val = self.results.get(sc, {}).get(fld, "N/A")
                cell = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
                row += cell[:col_w].ljust(col_w)
            lines.append(row)
        # Delta section
        if self.delta and self.base_scenario:
            lines += ["", f"Delta so với '{self.base_scenario}':"]
            other_scenarios = [s for s in self.scenarios if s != self.base_scenario]
            for fld in self.fields:
                row = fld[:col_w].ljust(col_w)
                for sc in other_scenarios:
                    d = self.delta.get(fld, {}).get(sc, {})
                    dv = d.get("delta", "N/A")
                    pct = d.get("pct", None)
                    if isinstance(dv, (int, float)):
                        pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
                        cell = f"{dv:+,.2f}{pct_str}"
                    else:
                        cell = str(dv)
                    row += cell[:col_w].ljust(col_w)
                lines.append(row)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenarios": self.scenarios,
            "fields": self.fields,
            "results": self.results,
            "delta": self.delta,
            "base_scenario": self.base_scenario,
        }


# ============================================================================
# Assertion & Audit
# ============================================================================

@dataclass
class Assertion:
    name: str
    expr: str
    message: str
    severity: AuditLevel = AuditLevel.ERROR
    depends_on: Optional[List[str]] = None
    _compiled: Optional[Any] = field(default=None)


@dataclass
class AssertionViolation:
    assertion_name: str
    expr: str
    message: str
    severity: AuditLevel
    row_index: Optional[int] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceNode:
    name: str
    formula: str
    value: Any
    deps: Dict[str, Any]
    children: List['TraceNode'] = field(default_factory=list)
    level: int = 0
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    execution_time_ms: float = 0.0
    is_input: bool = False

    def to_tree_string(self, indent=0, show_values=True, show_formula=True) -> str:
        prefix = " " * indent
        symbol = "📥" if self.is_input else "🔢"
        parts = [f"{symbol} {self.name}"]
        if show_formula and not self.is_input:
            parts.append(f"= {self.formula}")
        if show_values:
            parts.append(f"→ {self.value}")
        result = f"{prefix}├─ {' '.join(parts)}\n"
        for child in self.children:
            result += child.to_tree_string(indent + 1, show_values, show_formula)
        return result

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "formula": self.formula,
            "value": self.value,
            "deps": self.deps,
            "children": [c.to_dict() for c in self.children],
            "level": self.level,
            "executed_at": self.executed_at,
            "execution_time_ms": self.execution_time_ms,
            "is_input": self.is_input
        }


@dataclass
class AuditSession:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    formula_set_uid: str = ""
    started_at: datetime = field(default_factory=datetime.utcnow)
    rows_processed: int = 0
    sample_logs: List[Dict] = field(default_factory=list)
    violations: List[AssertionViolation] = field(default_factory=list)
    batch_hash: str = ""
    force_materialize: bool = False
    sample_rate: float = 0.001

    def add_sample(self, row_index: int, log_entry: Dict):
        self.sample_logs.append({"row_index": row_index, **log_entry})

    def finalize(self, total_rows: int):
        self.rows_processed = total_rows


@dataclass
class AuditReport:
    calculation_id: str
    formula_set_uid: str
    calculated_at: datetime
    executed_by: str
    scenario: str
    execution_tree: Optional[TraceNode] = None
    total_execution_time_ms: float = 0.0
    fields_calculated: int = 0
    rows_processed: int = 0
    inputs_hash: str = ""
    outputs_hash: str = ""
    violations: List[AssertionViolation] = field(default_factory=list)

    def summary(self) -> str:
        status = "✅ PASSED" if not self.violations else f"❌ FAILED ({len(self.violations)} violations)"
        lines = [
            "AUDIT SUMMARY",
            f"Status            : {status}",
            f"Rows processed    : {self.rows_processed}",
            f"Fields calculated : {self.fields_calculated}",
            f"Total time (ms)   : {self.total_execution_time_ms:.2f}",
            f"Violations        : {len(self.violations)}",
        ]
        return "\n".join(lines)


# ============================================================================
# Snapshot (v11 legacy)
# ============================================================================

@dataclass(frozen=True)
class ImmutableSnapshot:
    """
    Legacy snapshot (v11). Vẫn giữ nguyên để không break code cũ.
    Khuyến nghị dùng EnterpriseSnapshot (v12) cho code mới.
    """
    snapshot_id: str
    created_at: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    integrity_hash: str
    trace: Optional[Dict] = None

    def to_dict(self):
        return asdict(self)


# ============================================================================
# Enterprise Snapshot Layers
# ============================================================================

@dataclass(frozen=True)
class EngineMetaBlock:
    engine_version:   str   # FormulaEngineCore.ENGINE_VERSION
    formula_hash:     str   # SHA-256 của toàn bộ formula set
    formula_count:    int   # Số công thức
    topo_order_hash:  str   # SHA-256 của thứ tự DAG (fingerprint topology)
    schema_hash:      str   # SHA-256 của input+output schema
    frozen:           bool  # Engine có ở frozen/deterministic mode không
    captured_at:      str   # UTC ISO timestamp lúc capture

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class EngineContextBlock:
    dag_version:     str        # = formula_hash (shorthand)
    input_keys:      List[str]  # Sorted keys của inputs
    output_keys:     List[str]  # Sorted keys của outputs
    rounding_policy: Dict       # Chính sách làm tròn
    error_mode:      str        # 'raise' | 'null' | 'default'

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class DagStateBlock:
    execution_order:   List[str]             # Thứ tự eval thực tế
    dependency_edges:  Dict[str, List[str]]  # node → parents (deps)
    reverse_edges:     Dict[str, List[str]]  # node → children (affected)
    input_nodes:       List[str]             # Pure input variables
    formula_nodes:     List[str]             # Nodes có công thức
    dirty_nodes:       List[str]             # Nodes được recalculate lần này
    calc_mode:         str                   # "full" | "incremental" | "dirty"
    input_edges:       Dict[str, List[str]]  # input_var → [formula nodes dùng nó trực tiếp]

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class TraceEntry:
    field:          str              # Tên field/formula
    formula:        str              # Công thức gốc (text)
    old_value:      Any              # Giá trị trước khi tính (None nếu là lần đầu)
    new_value:      Any              # Giá trị sau khi tính
    triggered_by:   List[str]        # Các dep đã kích hoạt việc tính lại field này
    dep_values:     Dict[str, Any]   # Snapshot giá trị của các deps tại thời điểm tính
    exec_time_ms:   float            # Thời gian eval (milliseconds)
    skipped:        bool             # True nếu node bị skip (incremental, không dirty)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionTraceBlock:
    fields_evaluated: int
    fields_skipped:   int
    total_exec_ms:    float
    entries:          List[TraceEntry]

    def to_dict(self) -> Dict:
        return {
            "fields_evaluated": self.fields_evaluated,
            "fields_skipped":   self.fields_skipped,
            "total_exec_ms":    self.total_exec_ms,
            "entries":          [e.to_dict() for e in self.entries],
        }

    def get(self, field: str) -> Optional[TraceEntry]:
        """Lấy TraceEntry của 1 field theo tên."""
        for e in self.entries:
            if e.field == field:
                return e
        return None

    def changed_fields(self) -> List[TraceEntry]:
        """Các field có old_value ≠ new_value."""
        return [e for e in self.entries if e.old_value != e.new_value and not e.skipped]

    def to_report(self) -> str:
        """Human-readable execution trace report."""
        lines = [
            f"  Evaluated : {self.fields_evaluated} fields",
            f"  Skipped   : {self.fields_skipped} fields (incremental)",
            f"  Total ms  : {self.total_exec_ms:.3f}",
            "",
        ]
        for e in self.entries:
            if e.skipped:
                lines.append(f"  ⏭ {e.field:<20} [SKIP]")
            else:
                changed = "✏" if e.old_value != e.new_value else "="
                old_fmt = f"{e.old_value:,.2f}" if isinstance(e.old_value, (int, float)) else str(e.old_value)
                new_fmt = f"{e.new_value:,.2f}" if isinstance(e.new_value, (int, float)) else str(e.new_value)
                lines.append(f"  {changed} {e.field:<20} {old_fmt:>14} → {new_fmt:<14}  [{e.formula}]")
                if e.triggered_by:
                    lines.append(f"    triggered_by: {', '.join(e.triggered_by)}")
                dep_str = ", ".join(
                    f"{k}={v:,.2f}" if isinstance(v, (int, float)) else f"{k}={v}"
                    for k, v in e.dep_values.items()
                )
                if dep_str:
                    lines.append(f"    deps: {dep_str}")
        return "\n".join(lines)


@dataclass(frozen=True)
class AuditTrailBlock:
    """Lifecycle, provenance, và revision history của snapshot."""
    tag:                str            # SnapshotTag value
    status:             str            # SnapshotStatus value
    created_by:         str            # User / process tạo snapshot
    approved_by:        Optional[str]  # User duyệt (nếu có)
    parent_snapshot_id: Optional[str]  # Snapshot cha (nếu là revision)
    revision_chain:     List[str]      # Danh sách snapshot_id đã thay thế (cũ → mới)
    notes:              Optional[str]  # Ghi chú tự do
    source_doc:         Optional[str]  # ERPNext docname / external ref

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class EnterpriseSnapshot:
    # Identifiers
    snapshot_id: str
    created_at:  str   # UTC ISO

    # Layer 1
    meta: EngineMetaBlock
    # Layer 2a
    engine_context: EngineContextBlock
    # Layer 2b — DAG State
    dag_state: DagStateBlock
    # Layer 3 — Execution Trace
    exec_trace: ExecutionTraceBlock
    # Layer 4
    business_input: Dict[str, Any]
    outputs:        Dict[str, Any]
    # Layer 5
    audit_trail: AuditTrailBlock

    # Dual Hash
    payload_hash: str            # SHA-256(meta + dag_state + inputs + outputs)
    trace_hash:   Optional[str]  # SHA-256(exec_trace) — None nếu không capture

    def to_dict(self) -> Dict:
        return {
            "snapshot_id":    self.snapshot_id,
            "created_at":     self.created_at,
            "meta":           self.meta.to_dict(),
            "engine_context": self.engine_context.to_dict(),
            "dag_state":      self.dag_state.to_dict(),
            "exec_trace":     self.exec_trace.to_dict(),
            "business_input": self.business_input,
            "outputs":        self.outputs,
            "audit_trail":    self.audit_trail.to_dict(),
            "payload_hash":   self.payload_hash,
            "trace_hash":     self.trace_hash,
        }

    def to_json(self, indent: int = 2) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)

    def verify(self) -> bool:
        # Import here to avoid circular import
        from .snapshot import _snap_payload_hash
        expected = _snap_payload_hash(
            self.meta.to_dict(),
            self.dag_state.to_dict(),
            self.business_input,
            self.outputs,
        )
        return expected == self.payload_hash

    def to_audit_report(self) -> str:
        """Sinh báo cáo audit đầy đủ forensic-grade (human-readable)."""
        t  = self.audit_trail
        m  = self.meta
        ds = self.dag_state
        et = self.exec_trace
        lines = [
            "=" * 72,
            "  ENTERPRISE SNAPSHOT — FORENSIC AUDIT REPORT  (engine_v12)",
            "=" * 72,
            f"  Snapshot ID  : {self.snapshot_id}",
            f"  Created At   : {self.created_at}",
            f"  Created By   : {t.created_by}",
            f"  Tag          : {t.tag.upper()}",
            f"  Status       : {t.status.upper()}",
            "",
            "── Engine Meta ──────────────────────────────────────────────────",
            f"  Version      : {m.engine_version}",
            f"  Formula #    : {m.formula_count}",
            f"  Formula Hash : {m.formula_hash[:32]}...",
            f"  DAG Hash     : {m.topo_order_hash[:32]}...",
            f"  Schema Hash  : {m.schema_hash[:32]}...",
            f"  Frozen       : {m.frozen}",
            "",
            "── DAG State ────────────────────────────────────────────────────",
            f"  Calc Mode    : {ds.calc_mode.upper()}",
            f"  Exec Order   : {' → '.join(ds.execution_order)}",
            f"  Formula Nodes: {len(ds.formula_nodes)}",
            f"  Input Nodes  : {', '.join(ds.input_nodes) or '(none)'}",
            f"  Dirty Nodes  : {', '.join(ds.dirty_nodes) or '(all — full calc)'}",
            "",
        ]
        # Dependency edges — show cả formula←formula và formula←input
        lines.append("── Dependency Edges ─────────────────────────────────────────────")
        for node in ds.execution_order:
            formula_parents = ds.dependency_edges.get(node, [])
            # Input deps: input_edges[inp_var] chứa formula nodes dùng inp_var trực tiếp
            input_parents = [
                inp for inp in ds.input_nodes
                if node in ds.input_edges.get(inp, [])
            ]
            all_parents = sorted(set(formula_parents + input_parents))
            if all_parents:
                lines.append(f"  {node:<18} ← {', '.join(all_parents)}")
            else:
                lines.append(f"  {node:<18} ← (no tracked deps)")
        lines.append("")
        lines += [
            "── Integrity ────────────────────────────────────────────────────",
            f"  Payload Hash : {self.payload_hash[:40]}...",
            f"  Trace Hash   : {(self.trace_hash or 'N/A')[:40]}",
            f"  Verified     : {'✅ OK' if self.verify() else '❌ TAMPERED'}",
            "",
            "── Inputs ───────────────────────────────────────────────────────",
        ]
        for k, v in self.business_input.items():
            lines.append(f"  {k:<24} = {v}")
        lines.append("")
        lines.append("── Outputs ──────────────────────────────────────────────────────")
        for k, v in self.outputs.items():
            fmt = f"{v:>20,.2f}" if isinstance(v, (int, float)) else f"{v}"
            lines.append(f"  {k:<24} = {fmt}")
        lines.append("")
        lines.append("── Execution Trace ──────────────────────────────────────────────")
        lines.append(et.to_report())
        lines.append("")
        if t.parent_snapshot_id:
            lines.append("── Revision Chain ───────────────────────────────────────────────")
            lines.append(f"  Parent       : {t.parent_snapshot_id}")
            if t.revision_chain:
                lines.append(f"  History      : {' → '.join(t.revision_chain[:8])}")
            lines.append("")
        if t.notes:
            lines.append("── Notes ────────────────────────────────────────────────────────")
            lines.append(f"  {t.notes}")
            lines.append("")
        if t.source_doc:
            lines.append(f"  Source Doc   : {t.source_doc}")
        lines.append("=" * 72)
        return "\n".join(lines)


# ============================================================================
# Formula Metadata
# ============================================================================

@dataclass
class FormulaSetMeta:
    id: str
    version: str
    name: str
    description: str = ""
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    frozen: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def uid(self) -> str:
        return f"{self.id}@{self.version}"
    
    def is_effective(self, calc_date: date) -> bool:
        if self.effective_from and calc_date < self.effective_from:
            return False
        if self.effective_to and calc_date > self.effective_to:
            return False
        return True


@dataclass
class InputField:
    name: str
    dtype: type
    required: bool = True
    default: Any = None
    description: str = ""


@dataclass
class OutputField:
    name: str
    unit: str = ""
    bucket: str = ""
    primary: bool = False
    description: str = ""


# ============================================================================
# Topo Sort Results
# ============================================================================

@dataclass
class TopoSortResult:
    items:       List[Any]   # (was: sorted — renamed to avoid shadowing built-in)
    order:       List[Any]
    has_cycle:   bool
    cycle_nodes: List[Any]
    levels:      Dict[Any, int]
    edges:       Dict[Any, List[Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items":       self.items,
            "order":       self.order,
            "has_cycle":   self.has_cycle,
            "cycle_nodes": self.cycle_nodes,
            "levels":      self.levels,
            "edges":       self.edges,
        }

    def summary(self) -> str:
        lines = [
            f"TopoSortResult: {len(self.items)} items",
            f"  Levels     : 0–{max(self.levels.values(), default=0)} "
            f"({len(set(self.levels.values()))} distinct)",
            f"  Has cycle  : {self.has_cycle}"
            + (f"  → {self.cycle_nodes}" if self.has_cycle else ""),
        ]
        for item_id in self.order:
            lvl = self.levels.get(item_id, "?")
            deps = self.edges.get(item_id, [])
            dep_str = f" ← {deps}" if deps else " (độc lập)"
            lines.append(f"  [{lvl}] {item_id}{dep_str}")
        return "\n".join(lines)


# ============================================================================
# SCC Linear Solver Results
# ============================================================================

@dataclass
class SccTopoResult:
    items             : List[Any]
    order             : List[Any]
    sccs              : List[List[Any]]
    node_to_scc       : Dict[Any, int]
    condensation_order: List[int]
    has_cycle         : bool
    cycle_groups      : List[List[Any]]
    levels            : Dict[Any, int]
    edges             : Dict[Any, List[Any]]

    def summary(self) -> str:
        lines = [
            f"SccTopoResult: {len(self.items)} items, {len(self.sccs)} SCC(s)",
            f"  Has cycle   : {self.has_cycle}",
        ]
        if self.cycle_groups:
            for cg in self.cycle_groups:
                lines.append(f"  Cycle group : {' ↔ '.join(str(x) for x in cg)}")
        lines.append("  Order:")
        for nid in self.order:
            lvl  = self.levels.get(nid, "?")
            deps = self.edges.get(nid, [])
            tag  = " [CYCLE]" if lvl == -1 else ""
            dep_str = f" ← {deps}" if deps else " (độc lập)"
            lines.append(f"    [{lvl}]{tag} {nid}{dep_str}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items"             : self.items,
            "order"             : self.order,
            "sccs"              : self.sccs,
            "has_cycle"         : self.has_cycle,
            "cycle_groups"      : self.cycle_groups,
            "levels"            : self.levels,
            "condensation_order": self.condensation_order,
        }


@dataclass
class SccLinearAuditEntry:
    """Audit trace chi tiết cho 1 node sau khi giải."""
    node_id      : str
    scc_index    : int
    is_cycle_node: bool
    b_pure       : float              # b_fn(node_id, item) — hằng số thuần, trước outside deps
    b_effective  : float              # B_vec[i] = b_pure + Σ(coeff_j × resolved_j) outside SCC
    x_value      : float              # nghiệm x_i cuối cùng
    solve_method : str                # "direct" | "gaussian" | "iterative_fallback" | ...
    deps_detail  : List[Dict]         # chi tiết từng dep (node, coeff, x_dep, contribution, source)
    matrix_A     : Optional[List[List[float]]] = None   # A_intra (chỉ khi Gaussian)
    vector_B     : Optional[List[float]]       = None   # B_ext   (chỉ khi Gaussian)
    solution_X   : Optional[List[float]]       = None   # nghiệm X từ Gaussian/Seidel
    iterations   : Optional[int]               = None   # số vòng Gauss-Seidel (nếu dùng)

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items()}

    def explain(self) -> str:
        """Human-readable trace — dùng để debug khi có cycle."""
        tag   = " [CYCLE]" if self.is_cycle_node else ""
        lines = [
            f"━━ {self.node_id}{tag}  [SCC #{self.scc_index}, method={self.solve_method}]",
            f"   b_pure (from b_fn)  : {self.b_pure:>20,.6f}",
            f"   b_effective (B_ext) : {self.b_effective:>20,.6f}",
        ]
        if self.deps_detail:
            lines.append("   deps:")
            for d in self.deps_detail:
                src_tag = f"  [{d.get('source','')}]" if d.get('source') else ""
                x_str   = f"{d['x_dep']:>14,.4f}"  if d.get('x_dep')       is not None else "    (unknown)   "
                c_str   = f"{d['contribution']:>14,.4f}" if d.get('contribution') is not None else "    (in A_mat)  "
                lines.append(
                    f"     ← {str(d.get('node','?')):<22}"
                    f"  coeff={d.get('coeff',0):>10.6f}"
                    f"  x={x_str}"
                    f"  contrib={c_str}"
                    f"{src_tag}"
                )
        lines.append(f"   x (solution)       : {self.x_value:>20,.6f}")
        if self.solve_method == "gaussian" and self.matrix_A is not None:
            lines.append(f"   [Gaussian] A_intra = {self.matrix_A}")
            lines.append(f"   [Gaussian] B_ext   = {self.vector_B}")
            lines.append(f"   [Gaussian] X       = {[round(v, 6) for v in (self.solution_X or [])]}")
        if self.iterations is not None:
            lines.append(f"   [Iterative] iters  = {self.iterations}")
        return "\n".join(lines)


@dataclass
class SccLinearSolveResult:
    """Kết quả đầy đủ của solve_linear_on_graph / SccLinearSolver.solve()."""
    items        : List[Any]                        # nodes đã sort theo condensation order
    values       : Dict[str, float]                 # {node_id: x_value}
    audit        : Dict[str, SccLinearAuditEntry]   # trace từng node
    warnings     : List[str]                        # Gaussian fallback, divergence, etc.
    has_cycle    : bool
    cycle_groups : List[List[str]]                  # list các SCC size > 1
    solve_order  : List[str]                        # thứ tự giải theo condensation

    def summary(self) -> str:
        """Báo cáo đầy đủ — dùng khi cần debug toàn bộ."""
        W = 64
        sep = "═" * W
        lines = [
            f"╔{sep}╗",
            f"║{'  SCC LINEAR SOLVER v29 — KẾT QUẢ':^{W}}║",
            f"╠{sep}╣",
            f"║  Tổng nodes  : {len(self.items):<6} Cycle: {'CÓ' if self.has_cycle else 'KHÔNG':<6}{'':30}║",
        ]
        if self.cycle_groups:
            lines.append(f"╠{sep}╣")
            for i, cg in enumerate(self.cycle_groups):
                s = f"  Cycle {i+1}: {' ↔ '.join(str(n) for n in cg)}"
                lines.append(f"║{s:<{W}}║")
        if self.warnings:
            lines.append(f"╠{sep}╣")
            for w in self.warnings:
                # Wrap long warnings
                for chunk in [w[k:k+W-4] for k in range(0, len(w), W-4)]:
                    lines.append(f"║  ⚠  {chunk:<{W-5}}║")
        lines.append(f"╠{sep}╣")
        lines.append(f"║{'  CHI TIẾT TỪNG NODE':^{W}}║")
        lines.append(f"╚{sep}╝")
        for node_id in self.solve_order:
            e = self.audit.get(node_id)
            if e:
                lines.append(e.explain())
        return "\n".join(lines)

    def summary_cycles(self) -> str:
        """Chỉ hiển thị cycle groups + nghiệm — dùng cho log ngắn gọn."""
        if not self.has_cycle:
            return "Không có cycle."
        lines = [f"SccLinearSolver v29 — {len(self.cycle_groups)} cycle group(s):"]
        for cg in self.cycle_groups:
            lines.append(f"  Nhóm ({len(cg)} nodes): {' ↔ '.join(str(n) for n in cg)}")
            for node_id in cg:
                e = self.audit.get(node_id)
                if e:
                    lines.append(
                        f"    {node_id}: x={e.x_value:,.4f}"
                        f"  b_pure={e.b_pure:,.4f}"
                        f"  method={e.solve_method}"
                    )
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    ⚠ {w}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "has_cycle"   : self.has_cycle,
            "cycle_groups": self.cycle_groups,
            "solve_order" : self.solve_order,
            "warnings"    : self.warnings,
            "values"      : self.values,
            "audit"       : {k: v.to_dict() for k, v in self.audit.items()},
        }


# ============================================================================
# Engine Core Types
# ============================================================================

@dataclass
class IncrementalStats:
    """Statistics for one lazy calculate_incremental() call"""
    total_nodes: int = 0
    skipped_nodes: int = 0
    recalculated_nodes: int = 0
    changed_inputs: int = 0
    affected_nodes: int = 0
    elapsed_ms: float = 0.0

    @property
    def skip_ratio(self) -> float:
        if self.total_nodes == 0:
            return 0.0
        return self.skipped_nodes / self.total_nodes

    def __str__(self) -> str:
        return (
            f"IncrementalStats(total={self.total_nodes}, "
            f"recalc={self.recalculated_nodes}, skip={self.skipped_nodes}, "
            f"skip_ratio={self.skip_ratio:.1%}, "
            f"changed_inputs={self.changed_inputs}, "
            f"affected={self.affected_nodes}, "
            f"elapsed={self.elapsed_ms:.3f}ms)"
        )


@dataclass
class ValidationResult:
    ok:         bool
    errors:     List[str]
    warnings:   List[str]
    normalized: str
    formula:    str

    def raise_if_invalid(self, field_name: Optional[str] = None):
        """Raise FormulaError nếu có lỗi cứng."""
        if not self.ok:
            from .errors import FormulaError, ErrorCode
            msg = "; ".join(self.errors)
            raise FormulaError(
                message=msg,
                code=ErrorCode.VALIDATION_ERROR,
                field_name=field_name,
                formula=self.formula,
            )

    def summary(self) -> str:
        lines = [f"ValidationResult({'OK' if self.ok else 'FAIL'}) — {self.formula!r}"]
        for e in self.errors:
            lines.append(f"  ❌ {e}")
        for w in self.warnings:
            lines.append(f"  ⚠️  {w}")
        return "\n".join(lines)

    def __bool__(self) -> bool:
        return self.ok