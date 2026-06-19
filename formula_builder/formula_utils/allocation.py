# formula_utils/allocation.py
# Allocation Engine v20 - phân bổ chi phí nhiều nguồn → nhiều đích

from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple, Optional, Union
from collections import defaultdict


# ============================================================================
# Module-level helpers
# ============================================================================

def _to_float(v: Any, default: float = 0.0) -> float:
    """Chuyển bất kỳ giá trị nào sang float an toàn."""
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _apply_rounding(
    amounts: List[float],
    total: float,
    policy: str,
    digits: int,
) -> List[float]:
    """
    Làm tròn amounts và điều chỉnh lệch để sum(result) == total.

    policy:
        'last'    — cộng chênh lệch vào phần tử cuối
        'largest' — cộng chênh lệch vào phần tử lớn nhất
        'none'    — làm tròn nhưng không điều chỉnh
    """
    if policy == "none" or not amounts:
        return [round(a, digits) for a in amounts]
    rounded = [round(a, digits) for a in amounts]
    diff = round(total - sum(rounded), digits)
    if diff == 0:
        return rounded
    if policy == "last":
        rounded[-1] = round(rounded[-1] + diff, digits)
    elif policy == "largest":
        idx = max(range(len(rounded)), key=lambda i: rounded[i])
        rounded[idx] = round(rounded[idx] + diff, digits)
    return rounded


# ============================================================================
# Type alias
# ============================================================================

# (source_id, source_amount, target_id, allocated, ratio, method, weight)
AllocTuple = Tuple[Any, float, Any, float, float, str, float]

_ALLOC_METHODS = frozenset({
    "equal",         # chia đều tất cả đích
    "qty",           # theo trọng số qty của đích
    "amount",        # theo trọng số amount của đích
    "weight",        # theo trọng số bất kỳ (target["alloc_weight"])
    "pct",           # % cố định (tổng phải = 100, target["alloc_pct"])
    "manual_amount", # số tiền cố định trên target (target["alloc_amount"])
    "manual_pct",    # % nhập tay (target["manual_pct"])
    "mixed",         # pass1=manual_amount → pass2=manual_pct → pass3=residual
})


# ============================================================================
# AllocationLine
# ============================================================================

@dataclass
class AllocationLine:
    """Một dòng kết quả phân bổ."""
    source_id: Any
    source_amount: float
    target_id: Any
    allocated: float
    ratio: float
    method: str
    weight: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_amount": self.source_amount,
            "target_id": self.target_id,
            "allocated": self.allocated,
            "ratio": self.ratio,
            "method": self.method,
            "weight": self.weight,
            "meta": self.meta,
        }


# ============================================================================
# AllocationResult
# ============================================================================

@dataclass
class AllocationResult:
    """
    Kết quả phân bổ đầy đủ.
    Tương thích ngược hoàn toàn với AllocationResult v19.
    """
    lines: List[AllocationLine]
    source_totals: Dict[Any, float]
    target_totals: Dict[Any, float]
    unallocated: Dict[Any, float]
    warnings: List[str]
    ok: bool = True
    _sources: List[Dict[str, Any]] = field(default=None, repr=False, compare=False)
    _targets: List[Dict[str, Any]] = field(default=None, repr=False, compare=False)
    _source_id_key: str = field(default="id", repr=False, compare=False)
    _target_id_key: str = field(default="id", repr=False, compare=False)

    # ----------------------------------------------------------------------
    # Lookup & write-back
    # ----------------------------------------------------------------------

    def to_line_map(self) -> Dict[Any, "AllocationLine"]:
        """Dict {target_id → AllocationLine} — lookup O(1)."""
        return {ln.target_id: ln for ln in self.lines}

    def apply_to(
        self,
        rows,
        id_key: str = "id",
        out_key: str = "allocated",
    ) -> "AllocationResult":
        """
        Ghi allocated vào rows[i][out_key] (hoặc setattr) dựa trên rows[i][id_key].
        Trả self để chain: result.apply_to(rows).warnings
        """
        ln_map = self.to_line_map()
        for row in rows:
            try:
                rid = row[id_key]
            except (KeyError, TypeError):
                rid = getattr(row, id_key, None)
            ln = ln_map.get(rid)
            if ln is None:
                continue
            try:
                row[out_key] = ln.allocated
            except (KeyError, TypeError):
                setattr(row, out_key, ln.allocated)
        return self

    # ----------------------------------------------------------------------
    # Serialization
    # ----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lines": [line.to_dict() for line in self.lines],
            "source_totals": self.source_totals,
            "target_totals": self.target_totals,
            "unallocated": self.unallocated,
            "warnings": self.warnings,
            "ok": self.ok,
        }

    def to_sources_detail(
        self,
        sources: List[Dict[str, Any]] = None,
        source_id_key: str = None,
    ) -> List[Dict[str, Any]]:
        """Mỗi source dict gốc + allocated_total + unallocated + allocated_to."""
        sources = sources if sources is not None else (self._sources or [])
        source_id_key = source_id_key if source_id_key is not None else self._source_id_key
        by_src: Dict[Any, list] = defaultdict(list)
        for ln in self.lines:
            by_src[ln.source_id].append({
                "target_id": ln.target_id, "allocated": ln.allocated,
                "ratio": ln.ratio, "method": ln.method,
                "weight": ln.weight, "meta": ln.meta,
            })
        result = []
        for src in sources:
            sid = src.get(source_id_key)
            row = dict(src)
            row["allocated_total"] = self.source_totals.get(sid, 0.0)
            row["unallocated"] = self.unallocated.get(sid, 0.0)
            row["allocated_to"] = by_src.get(sid, [])
            result.append(row)
        return result

    def to_targets_detail(
        self,
        targets: List[Dict[str, Any]] = None,
        target_id_key: str = None,
    ) -> List[Dict[str, Any]]:
        """Mỗi target dict gốc + received_total + received_from."""
        targets = targets if targets is not None else (self._targets or [])
        target_id_key = target_id_key if target_id_key is not None else self._target_id_key
        by_tgt: Dict[Any, list] = defaultdict(list)
        for ln in self.lines:
            by_tgt[ln.target_id].append({
                "source_id": ln.source_id,
                "source_amount": ln.source_amount,
                "allocated": ln.allocated,
                "ratio": ln.ratio,
                "method": ln.method,
                "weight": ln.weight,
                "meta": ln.meta,
            })
        result = []
        for tgt in targets:
            tid = tgt.get(target_id_key)
            row = dict(tgt)
            row["received_total"] = self.target_totals.get(tid, 0.0)
            row["received_from"] = by_tgt.get(tid, [])
            result.append(row)
        return result

    def to_full_dict(
        self,
        sources: List[Dict[str, Any]] = None,
        targets: List[Dict[str, Any]] = None,
        source_id_key: str = None,
        target_id_key: str = None,
    ) -> Dict[str, Any]:
        return {
            "sources": self.to_sources_detail(sources, source_id_key),
            "targets": self.to_targets_detail(targets, target_id_key),
            "source_totals": self.source_totals,
            "target_totals": self.target_totals,
            "lines": [line.to_dict() for line in self.lines],
            "unallocated": self.unallocated,
            "warnings": self.warnings,
            "ok": self.ok,
        }

    def summary(self) -> str:
        out = [f"AllocationResult: {len(self.lines)} dòng, ok={self.ok}"]
        for sid, total in self.source_totals.items():
            una = self.unallocated.get(sid, 0)
            out.append(f"  Nguồn {sid}: phân bổ {total:,.2f}, còn dư {una:,.2f}")
        for tid, total in self.target_totals.items():
            out.append(f"  Đích   {tid}: nhận {total:,.2f}")
        if self.warnings:
            out.append("  Cảnh báo:")
            for w in self.warnings:
                out.append(f"    ⚠ {w}")
        return "\n".join(out)

    # ----------------------------------------------------------------------
    # Group helpers
    # ----------------------------------------------------------------------

    def group_by_source(
        self,
        sources: List[Dict[str, Any]] = None,
        source_id_key: str = None,
        include_totals_only: bool = False,
    ) -> Dict[Any, Dict[str, Any]]:
        sources = sources if sources is not None else (self._sources or [])
        source_id_key = source_id_key if source_id_key is not None else self._source_id_key
        by_src: Dict[Any, list] = defaultdict(list)
        for ln in self.lines:
            by_src[ln.source_id].append({
                "target_id": ln.target_id,
                "allocated": ln.allocated,
                "ratio": ln.ratio,
                "method": ln.method,
                "weight": ln.weight,
                "meta": ln.meta,
            })
        src_map: Dict[Any, Dict] = {s.get(source_id_key): dict(s) for s in sources} if sources else {}
        result: Dict[Any, Dict] = {}
        for sid in self.source_totals:
            row = dict(src_map.get(sid, {}))
            row["allocated_total"] = self.source_totals.get(sid, 0.0)
            row["unallocated"] = self.unallocated.get(sid, 0.0)
            if not include_totals_only:
                row["allocated_to"] = by_src.get(sid, [])
            result[sid] = row
        return result

    def group_by_target(
        self,
        targets: List[Dict[str, Any]] = None,
        target_id_key: str = None,
        include_totals_only: bool = False,
    ) -> Dict[Any, Dict[str, Any]]:
        targets = targets if targets is not None else (self._targets or [])
        target_id_key = target_id_key if target_id_key is not None else self._target_id_key
        by_tgt: Dict[Any, list] = defaultdict(list)
        for ln in self.lines:
            by_tgt[ln.target_id].append({
                "source_id": ln.source_id,
                "source_amount": ln.source_amount,
                "allocated": ln.allocated,
                "ratio": ln.ratio,
                "method": ln.method,
                "weight": ln.weight,
                "meta": ln.meta,
            })
        tgt_map: Dict[Any, Dict] = {t.get(target_id_key): dict(t) for t in targets} if targets else {}
        result: Dict[Any, Dict] = {}
        for tid in self.target_totals:
            row = dict(tgt_map.get(tid, {}))
            row["received_total"] = self.target_totals.get(tid, 0.0)
            if not include_totals_only:
                row["received_from"] = by_tgt.get(tid, [])
            result[tid] = row
        return result

    def to_flat_rows(self, *, ratio_as_pct: bool = False) -> List[Dict[str, Any]]:
        return [
            {
                "source_id": ln.source_id,
                "source_amount": ln.source_amount,
                "target_id": ln.target_id,
                "allocated": ln.allocated,
                "ratio": round(ln.ratio * 100, 4) if ratio_as_pct else ln.ratio,
                "method": ln.method,
                "weight": ln.weight,
            }
            for ln in self.lines
        ]

    def print_by_source(
        self,
        sources: List[Dict[str, Any]] = None,
        source_id_key: str = None,
        label_key: str = None,
    ) -> None:
        sources = sources if sources is not None else (self._sources or [])
        source_id_key = source_id_key if source_id_key is not None else self._source_id_key
        src_map = {s.get(source_id_key): s for s in sources}
        for sid, row in self.group_by_source(sources, source_id_key).items():
            label = f"  {src_map[sid].get(label_key, '')}" if label_key and sid in src_map else ""
            amt = row.get("amount") or row.get("source_amount") or 0
            print(f"\n[{sid}]{label}")
            if amt:
                print(f"  gốc            : {amt:>18,.2f}")
            print(f"  allocated_total: {row['allocated_total']:>18,.2f}"
                  f"  unallocated: {row['unallocated']:>12,.2f}")
            for item in row.get("allocated_to", []):
                meta_str = f"  meta={item['meta']}" if item["meta"] else ""
                print(f"    → {item['target_id']:12}  {item['allocated']:>16,.2f}"
                      f"  ({item['ratio']:6.2%})  [{item['method']}]"
                      f"  weight={item['weight']:>10,.2f}{meta_str}")

    def print_by_target(
        self,
        targets: List[Dict[str, Any]] = None,
        target_id_key: str = None,
        label_key: str = None,
    ) -> None:
        targets = targets if targets is not None else (self._targets or [])
        target_id_key = target_id_key if target_id_key is not None else self._target_id_key
        tgt_map = {t.get(target_id_key): t for t in targets}
        for tid, row in self.group_by_target(targets, target_id_key).items():
            label = f"  {tgt_map[tid].get(label_key, '')}" if label_key and tid in tgt_map else ""
            print(f"\n[{tid}]{label}")
            print(f"  received_total : {row['received_total']:>18,.2f}")
            for item in row.get("received_from", []):
                meta_str = f"  meta={item['meta']}" if item["meta"] else ""
                print(f"    ← {item['source_id']:12}  {item['allocated']:>16,.2f}"
                      f"  ({item['ratio']:6.2%})  [{item['method']}]"
                      f"  weight={item['weight']:>10,.2f}{meta_str}")


# ============================================================================
# AllocationEngine
# ============================================================================

class AllocationEngine:
    """
    Engine phân bổ chi phí — logic 7 method viết 1 lần, 3 output mode.

    Khởi tạo:
        engine = AllocationEngine(sources, targets, method="mixed", ...)

    Chọn output mode:
        engine.to_result()             → AllocationResult
        engine.to_inplace(out_key)     → ghi thẳng vào targets, trả (src, tgt, warns)
        engine.to_lines()              → list[AllocTuple]
    """

    __slots__ = (
        "_sources", "_targets", "_method",
        "_rd", "_policy", "_mrm",
        "_sik", "_sak", "_tik",
        "_tqk", "_tak", "_twk", "_tpk", "_tmak", "_tmpk",
        "_gk",
    )

    def __init__(
        self,
        sources: List[Dict[str, Any]],
        targets: List[Dict[str, Any]],
        method: str = "equal",
        *,
        source_id_key: str = "id",
        source_amount_key: str = "amount",
        target_id_key: str = "id",
        target_qty_key: str = "qty",
        target_amount_key: str = "amount",
        target_weight_key: str = "alloc_weight",
        target_pct_key: str = "alloc_pct",
        target_manual_amount_key: str = "alloc_amount",
        target_manual_pct_key: str = "manual_pct",
        group_key: Optional[str] = None,
        rounding_policy: str = "last",
        round_digits: int = 2,
        mixed_residual_method: str = "qty",
    ) -> None:
        if method not in _ALLOC_METHODS:
            raise ValueError(
                f"AllocationEngine: method '{method}' không hợp lệ. "
                f"Hợp lệ: {sorted(_ALLOC_METHODS)}"
            )
        if rounding_policy not in ("last", "largest", "none"):
            raise ValueError("rounding_policy phải là 'last' | 'largest' | 'none'")

        self._sources = sources
        self._targets = targets
        self._method = method
        self._rd = round_digits
        self._policy = rounding_policy
        self._mrm = mixed_residual_method
        self._sik = source_id_key
        self._sak = source_amount_key
        self._tik = target_id_key
        self._tqk = target_qty_key
        self._tak = target_amount_key
        self._twk = target_weight_key
        self._tpk = target_pct_key
        self._tmak = target_manual_amount_key
        self._tmpk = target_manual_pct_key
        self._gk = group_key

    # ----------------------------------------------------------------------
    # Grouping
    # ----------------------------------------------------------------------

    def _build_groups(self) -> List[Tuple[Any, List[Dict], List[Dict]]]:
        """Trả [(group_val, [sources], [targets]), ...]."""
        gk = self._gk
        if not gk:
            return [("__ALL__", self._sources, self._targets)]
        grp_s: Dict[Any, List] = {}
        grp_t: Dict[Any, List] = {}
        for s in self._sources:
            grp_s.setdefault(s.get(gk, "__ALL__"), []).append(s)
        for t in self._targets:
            grp_t.setdefault(t.get(gk, "__ALL__"), []).append(t)
        all_keys = set(grp_s) | set(grp_t)
        return [(k, grp_s.get(k, []), grp_t.get(k, [])) for k in all_keys]

    # ----------------------------------------------------------------------
    # Core compute
    # ----------------------------------------------------------------------

    def _compute_batch(
        self,
        src_amount: float,
        sid: Any,
        grp_targets: List[Dict],
        warns: List[str],
    ) -> Tuple[List[float], List[str], List[float]]:
        """
        Tính (amounts, methods, weights) cho 1 source trên grp_targets.
        """
        n = len(grp_targets)
        rd = self._rd
        pol = self._policy

        def _r(v): return round(v, rd)
        def _n(v): return _to_float(v)
        def _rl(lst, tot): return _apply_rounding(lst, tot, pol, rd)
        def _wts(key):
            ws = [_n(t.get(key)) for t in grp_targets]
            total = sum(ws)
            if total == 0:
                warns.append(f"Nguồn '{sid}': tổng '{key}' = 0, fallback equal.")
                ws, total = [1.0] * n, float(n)
            return ws, total

        m = self._method

        # EQUAL
        if m == "equal":
            raw = src_amount / n if n else 0.0
            return _rl([raw] * n, src_amount), ["equal"] * n, [1.0] * n

        # QTY / AMOUNT / WEIGHT
        if m in ("qty", "amount", "weight"):
            wkey = {"qty": self._tqk, "amount": self._tak, "weight": self._twk}[m]
            ws, total_w = _wts(wkey)
            amts = _rl([src_amount * w / total_w for w in ws], src_amount)
            return amts, [m] * n, ws

        # PCT
        if m == "pct":
            pcts = [_n(t.get(self._tpk)) for t in grp_targets]
            total = sum(pcts)
            if abs(total - 100.0) > 0.01:
                warns.append(f"Nguồn '{sid}': tổng pct = {total:.4f} ≠ 100, normalize.")
                if total == 0:
                    pcts, total = [100.0 / n] * n, 100.0
                else:
                    pcts = [p * 100.0 / total for p in pcts]
            amts = _rl([src_amount * p / 100.0 for p in pcts], src_amount)
            return amts, ["pct"] * n, pcts

        # MANUAL_AMOUNT
        if m == "manual_amount":
            amts = [_r(_n(t.get(self._tmak))) for t in grp_targets]
            return amts, ["manual_amount"] * n, amts[:]

        # MANUAL_PCT
        if m == "manual_pct":
            pcts = [_n(t.get(self._tmpk)) for t in grp_targets]
            total = sum(pcts)
            if abs(total - 100.0) > 0.01:
                warns.append(f"Nguồn '{sid}': tổng manual_pct = {total:.4f} ≠ 100, normalize.")
                if total > 0:
                    pcts = [p * 100.0 / total for p in pcts]
            amts = _rl([src_amount * p / 100.0 for p in pcts], src_amount)
            return amts, ["manual_pct"] * n, pcts

        # MIXED
        if m == "mixed":
            return self._compute_mixed(src_amount, sid, grp_targets, warns)

        return [0.0] * n, ["unknown"] * n, [0.0] * n

    def _compute_mixed(
        self,
        src_amount: float,
        sid: Any,
        grp_targets: List[Dict],
        warns: List[str],
    ) -> Tuple[List[float], List[str], List[float]]:
        """
        Mixed — 3 pass tuần tự:
        Pass 1 — alloc_amount
        Pass 2 — manual_pct
        Pass 3 — residual (qty/amount/weight/equal)
        """
        n = len(grp_targets)
        rd = self._rd
        mak = self._tmak
        mpk = self._tmpk

        def _r(v): return round(v, rd)
        def _n(v): return _to_float(v)
        def _rl(lst, tot): return _apply_rounding(lst, tot, self._policy, rd)

        amounts = [0.0] * n
        methods = ["mixed"] * n
        weights = [0.0] * n
        idx_p2: List[int] = []
        idx_p3: List[int] = []
        total_p1 = 0.0

        # Pass 1 — alloc_amount cố định
        for i, tgt in enumerate(grp_targets):
            v = tgt.get(mak)
            if v is not None:
                amt = _r(_n(v))
                amounts[i] = amt
                weights[i] = amt
                methods[i] = "mixed:manual_amount"
                total_p1 += amt
            else:
                idx_p2.append(i)

        # Pass 2 — manual_pct tính trên phần còn lại
        rem1 = src_amount - total_p1
        total_p2 = 0.0
        for i in idx_p2:
            v = grp_targets[i].get(mpk)
            if v is not None:
                pct = _n(v)
                amt = _r(rem1 * pct / 100.0)
                amounts[i] = amt
                weights[i] = pct
                methods[i] = f"mixed:manual_pct({pct:.2f}%)"
                total_p2 += amt
            else:
                idx_p3.append(i)

        # Pass 3 — residual
        rem2 = _r(src_amount - total_p1 - total_p2)
        if idx_p3 and rem2 != 0:
            rm = self._mrm
            wkey = {"qty": self._tqk, "amount": self._tak, "weight": self._twk}.get(rm)
            if wkey:
                ws = [_n(grp_targets[i].get(wkey)) for i in idx_p3]
                total = sum(ws)
                if total == 0:
                    ws, total = [1.0] * len(idx_p3), float(len(idx_p3))
            else:
                ws, total = [1.0] * len(idx_p3), float(len(idx_p3))
            sub = _rl([rem2 * w / total for w in ws], rem2)
            for ii, i in enumerate(idx_p3):
                amounts[i] = sub[ii]
                weights[i] = ws[ii]
                methods[i] = f"mixed:{rm}"
        elif not idx_p3 and rem2 != 0:
            warns.append(
                f"Nguồn '{sid}': sau pass1+pass2 còn dư {rem2:,.{rd}f}"
                f" nhưng không có đích residual."
            )

        return amounts, methods, weights

    @staticmethod
    def _acc(d: Dict[Any, float], k: Any, v: float, rd: int) -> None:
        d[k] = round((d.get(k) or 0.0) + v, rd)

    # ----------------------------------------------------------------------
    # Output mode 1: to_result
    # ----------------------------------------------------------------------

    def to_result(self) -> AllocationResult:
        warns: List[str] = []
        all_lines: List[AllocationLine] = []
        src_totals: Dict[Any, float] = {}
        tgt_totals: Dict[Any, float] = {}
        unalloc: Dict[Any, float] = {}
        rd = self._rd
        acc = self._acc

        for _gv, grp_src, grp_tgt in self._build_groups():
            if not grp_src:
                continue
            if not grp_tgt:
                for s in grp_src:
                    sid = s.get(self._sik)
                    acc(unalloc, sid, _to_float(s.get(self._sak)), rd)
                    warns.append(f"Nguồn '{sid}': không có đích để phân bổ.")
                continue

            for src in grp_src:
                sid = src.get(self._sik)
                src_amount = _to_float(src.get(self._sak))
                amts, meths, wts = self._compute_batch(src_amount, sid, grp_tgt, warns)

                alloc_sum = 0.0
                for tgt, amt, meth, w in zip(grp_tgt, amts, meths, wts):
                    tid = tgt.get(self._tik)
                    ratio = round(amt / src_amount, rd) if src_amount else 0.0
                    if "mixed:" in meth:
                        if "manual_amount" in meth:
                            stage = "pass1_manual_amount"
                        elif "manual_pct" in meth:
                            stage = "pass2_manual_pct"
                        else:
                            stage = "pass3_residual"
                        meta: Dict[str, Any] = {"mixed_stage": stage}
                    else:
                        meta = {}
                    all_lines.append(AllocationLine(
                        source_id=sid, source_amount=src_amount,
                        target_id=tid, allocated=amt,
                        ratio=ratio, method=meth, weight=w, meta=meta,
                    ))
                    acc(tgt_totals, tid, amt, rd)
                    alloc_sum += amt

                acc(src_totals, sid, alloc_sum, rd)
                una = round(src_amount - alloc_sum, rd)
                if abs(una) > 10 ** (-rd):
                    acc(unalloc, sid, una, rd)

        return AllocationResult(
            lines=all_lines,
            source_totals=src_totals,
            target_totals=tgt_totals,
            unallocated=unalloc,
            warnings=warns,
            ok=not any("không có đích" in w for w in warns),
            _sources=self._sources,
            _targets=self._targets,
            _source_id_key=self._sik,
            _target_id_key=self._tik,
        )

    # ----------------------------------------------------------------------
    # Output mode 2: to_inplace
    # ----------------------------------------------------------------------

    def to_inplace(
        self,
        out_key: str = "allocated",
        reset_before: bool = True,
    ) -> Tuple[Dict[Any, float], Dict[Any, float], List[str]]:
        warns: List[str] = []
        src_totals: Dict[Any, float] = {}
        tgt_totals: Dict[Any, float] = {}
        rd = self._rd
        acc = self._acc

        if reset_before:
            for t in self._targets:
                try:
                    t[out_key] = 0.0
                except TypeError:
                    setattr(t, out_key, 0.0)

        for _gv, grp_src, grp_tgt in self._build_groups():
            if not grp_src:
                continue
            if not grp_tgt:
                for s in grp_src:
                    warns.append(f"Nguồn '{s.get(self._sik)}': không có đích để phân bổ.")
                continue

            for src in grp_src:
                sid = src.get(self._sik)
                src_amount = _to_float(src.get(self._sak))
                amts, _, _ = self._compute_batch(src_amount, sid, grp_tgt, warns)

                alloc_sum = 0.0
                for tgt, amt in zip(grp_tgt, amts):
                    try:
                        tgt[out_key] = round((tgt.get(out_key) or 0.0) + amt, rd)
                        tid = tgt.get(self._tik)
                    except TypeError:
                        setattr(tgt, out_key, round((getattr(tgt, out_key, 0.0) or 0.0) + amt, rd))
                        tid = getattr(tgt, self._tik, None)
                    acc(tgt_totals, tid, amt, rd)
                    alloc_sum += amt
                acc(src_totals, sid, alloc_sum, rd)

        return src_totals, tgt_totals, warns

    # ----------------------------------------------------------------------
    # Output mode 3: to_lines
    # ----------------------------------------------------------------------

    def to_lines(
        self,
    ) -> Tuple[List[AllocTuple], Dict[Any, float], Dict[Any, float], List[str]]:
        warns: List[str] = []
        lines: List[AllocTuple] = []
        src_totals: Dict[Any, float] = {}
        tgt_totals: Dict[Any, float] = {}
        rd = self._rd
        acc = self._acc

        for _gv, grp_src, grp_tgt in self._build_groups():
            if not grp_src:
                continue
            if not grp_tgt:
                for s in grp_src:
                    warns.append(f"Nguồn '{s.get(self._sik)}': không có đích để phân bổ.")
                continue

            for src in grp_src:
                sid = src.get(self._sik)
                src_amount = _to_float(src.get(self._sak))
                amts, meths, wts = self._compute_batch(src_amount, sid, grp_tgt, warns)

                alloc_sum = 0.0
                for tgt, amt, meth, w in zip(grp_tgt, amts, meths, wts):
                    tid = tgt.get(self._tik)
                    ratio = round(amt / src_amount, rd) if src_amount else 0.0
                    lines.append((sid, src_amount, tid, amt, ratio, meth, w))
                    acc(tgt_totals, tid, amt, rd)
                    alloc_sum += amt
                acc(src_totals, sid, alloc_sum, rd)

        return lines, src_totals, tgt_totals, warns


# ============================================================================
# Alias functions (drop-in replacement for v19)
# ============================================================================

def allocate(
    sources: List[Dict[str, Any]],
    targets: List[Dict[str, Any]],
    method: str = "equal",
    *,
    source_id_key: str = "id",
    source_amount_key: str = "amount",
    target_id_key: str = "id",
    target_qty_key: str = "qty",
    target_amount_key: str = "amount",
    target_weight_key: str = "alloc_weight",
    target_pct_key: str = "alloc_pct",
    target_manual_amount_key: str = "alloc_amount",
    target_manual_pct_key: str = "manual_pct",
    group_key: Optional[str] = None,
    rounding_policy: str = "last",
    round_digits: int = 2,
    mixed_residual_method: str = "qty",
) -> AllocationResult:
    """Hàm phân bổ chính — drop-in replacement cho allocate() v19."""
    return AllocationEngine(
        sources, targets, method,
        source_id_key=source_id_key, source_amount_key=source_amount_key,
        target_id_key=target_id_key, target_qty_key=target_qty_key,
        target_amount_key=target_amount_key, target_weight_key=target_weight_key,
        target_pct_key=target_pct_key,
        target_manual_amount_key=target_manual_amount_key,
        target_manual_pct_key=target_manual_pct_key,
        group_key=group_key, rounding_policy=rounding_policy,
        round_digits=round_digits, mixed_residual_method=mixed_residual_method,
    ).to_result()


def allocate_inplace(
    sources: List[Dict[str, Any]],
    targets,
    out_key: str = "allocated",
    *,
    method: str = "qty",
    source_id_key: str = "id",
    source_amount_key: str = "amount",
    target_id_key: str = "id",
    target_qty_key: str = "qty",
    target_amount_key: str = "amount",
    target_weight_key: str = "alloc_weight",
    target_pct_key: str = "alloc_pct",
    target_manual_amount_key: str = "alloc_amount",
    target_manual_pct_key: str = "manual_pct",
    group_key: Optional[str] = None,
    rounding_policy: str = "last",
    round_digits: int = 2,
    mixed_residual_method: str = "qty",
    reset_before: bool = True,
) -> Tuple[Dict[Any, float], Dict[Any, float], List[str]]:
    """Ghi thẳng vào targets[i][out_key]."""
    return AllocationEngine(
        sources, targets, method,
        source_id_key=source_id_key, source_amount_key=source_amount_key,
        target_id_key=target_id_key, target_qty_key=target_qty_key,
        target_amount_key=target_amount_key, target_weight_key=target_weight_key,
        target_pct_key=target_pct_key,
        target_manual_amount_key=target_manual_amount_key,
        target_manual_pct_key=target_manual_pct_key,
        group_key=group_key, rounding_policy=rounding_policy,
        round_digits=round_digits, mixed_residual_method=mixed_residual_method,
    ).to_inplace(out_key=out_key, reset_before=reset_before)


def allocate_fast(
    sources: List[Dict[str, Any]],
    targets: List[Dict[str, Any]],
    method: str = "equal",
    *,
    source_id_key: str = "id",
    source_amount_key: str = "amount",
    target_id_key: str = "id",
    target_qty_key: str = "qty",
    target_amount_key: str = "amount",
    target_weight_key: str = "alloc_weight",
    target_pct_key: str = "alloc_pct",
    target_manual_amount_key: str = "alloc_amount",
    target_manual_pct_key: str = "manual_pct",
    group_key: Optional[str] = None,
    rounding_policy: str = "last",
    round_digits: int = 2,
    mixed_residual_method: str = "qty",
) -> Tuple[List[AllocTuple], Dict[Any, float], Dict[Any, float], List[str]]:
    """Trả list[AllocTuple] thay AllocationResult — pipeline nhanh."""
    return AllocationEngine(
        sources, targets, method,
        source_id_key=source_id_key, source_amount_key=source_amount_key,
        target_id_key=target_id_key, target_qty_key=target_qty_key,
        target_amount_key=target_amount_key, target_weight_key=target_weight_key,
        target_pct_key=target_pct_key,
        target_manual_amount_key=target_manual_amount_key,
        target_manual_pct_key=target_manual_pct_key,
        group_key=group_key, rounding_policy=rounding_policy,
        round_digits=round_digits, mixed_residual_method=mixed_residual_method,
    ).to_lines()