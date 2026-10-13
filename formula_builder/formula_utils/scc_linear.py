# formula_utils/scc_linear.py
# Gaussian elimination and SCC-based linear solver for (I-A)x = b on graphs

from typing import List, Dict, Any, Callable, Tuple, Optional
from collections import defaultdict, deque

from .types import SccLinearAuditEntry, SccLinearSolveResult
from .topo import scc_topo_sort_with_info


# ============================================================================
# Gaussian elimination (internal)
# ============================================================================

def _gaussian_eliminate(
    A_mat: List[List[float]],
    B_vec: List[float],
    epsilon: float = 1e-9,
) -> List[float]:
    """
    Giải hệ (I − A_mat) · x = B_vec bằng Gauss-Jordan với partial pivoting.

    Caller truyền vào A (ma trận hệ số của các deps trong SCC).
    Hàm tự xây dựng ma trận bổ trợ M = [(I − A) | b] bên trong.

    Parameters
    ----------
    A_mat   : ma trận n×n chứa hệ số A[i][j]
    B_vec   : vector n phần tử (hằng số b, đã bao gồm cả outside-SCC deps)
    epsilon : ngưỡng pivot — nếu |pivot| < epsilon → RuntimeError (singular)

    Returns : List[float] — nghiệm x
    Raises  : RuntimeError nếu ma trận (I−A) singular/near-singular
              (xảy ra khi Σ_j A[i][j] ≥ 1 — tổng hệ số phân bổ vượt 100%)
    """
    n = len(B_vec)
    # Augmented matrix: M = [(I − A) | b], kích thước n × (n+1)
    M = [
        [(1.0 if i == j else 0.0) - A_mat[i][j] for j in range(n)] + [B_vec[i]]
        for i in range(n)
    ]

    for col in range(n):
        # Chọn hàng có |pivot| lớn nhất → giảm sai số số học
        pivot_row = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[pivot_row][col]) < epsilon:
            raise RuntimeError(
                f"Ma trận (I−A) singular tại cột {col}: "
                f"|pivot| = {abs(M[pivot_row][col]):.2e} < ε = {epsilon}. "
                f"Nguyên nhân thường gặp: tổng hệ số cạnh của node {col} ≥ 1 "
                f"(phân bổ 100% hoặc vòng lặp không giảm)."
            )
        M[col], M[pivot_row] = M[pivot_row], M[col]

        # Chuẩn hoá hàng pivot
        piv = M[col][col]
        for j in range(col, n + 1):
            M[col][j] /= piv

        # Khử toàn bộ cột — Gauss-Jordan eliminates both above and below
        for row in range(n):
            if row == col:
                continue
            factor = M[row][col]
            if abs(factor) < epsilon:
                continue
            for j in range(col, n + 1):
                M[row][j] -= factor * M[col][j]

    return [M[i][n] for i in range(n)]


# ============================================================================
# SccLinearSolver - Giải hệ (I−A)x = b trên đồ thị có SCC
# ============================================================================

class SccLinearSolver:
    """
    Solver tổng quát cho hệ phương trình tuyến tính dạng (I−A)x=b trên đồ thị.

    Phương trình mỗi node i:
        x_i = b_i + Σ_j  A[i][j] × x_j

    Xử lý 4 tình huống tự động qua Tarjan SCC + condensation order:
        1. Độc lập    → x = b_fn()
        2. Tuần tự   → x = b_fn() + Σ(coeff × resolved[dep])
        3. Quay vòng → Gaussian (I−A)x=b, fallback Gauss-Seidel
        4. Hỗn hợp  → dep ∉ SCC → cộng vào B_ext; dep ∈ SCC → vào A_intra

    Parameters
    ----------
    items          : list of objects (nodes)
    id_fn          : item → node_id (str, unique)
    deps_fn        : item → List[(dep_id, edge_data)]
                     CHỈ trả deps có hệ số A[i][j] ≠ 0 (linear deps thực sự).
    b_fn           : (node_id, item) → float
                     Hằng số thuần của node.
    coeff_fn       : (node_id, dep_id, edge_data) → float
                     Hệ số A[i][j].  Nhận node_id để tính A bất đối xứng.
    output_fn      : (node_id, x_value, item, resolved_dict) → None
                     Callback ghi nghiệm vào item.
    feasibility_fn : optional (scc_nodes, data_map) → List[str]
                     Kiểm tra tính khả thi trước khi giải SCC.
    epsilon        : ngưỡng pivot Gaussian (default 1e-9)
    max_iter_fallback : số vòng Gauss-Seidel fallback khi Gaussian thất bại
                       (0 = không fallback, trả b_vec làm xấp xỉ)
    tol_fallback   : ngưỡng hội tụ Gauss-Seidel (default 1e-6)
    clamp_nonneg   : True → clamp x ≥ 0 sau khi giải (phù hợp cost/qty)
    warn_large_scc : cảnh báo nếu SCC có nhiều hơn n nodes (default 15)
    """

    def __init__(
        self,
        items: List[Any],
        id_fn: Callable[[Any], str],
        deps_fn: Callable[[Any], List[Tuple[str, Any]]],
        b_fn: Callable[[str, Any], float],
        coeff_fn: Callable[[str, str, Any], float],
        output_fn: Callable[[str, float, Any, Dict[str, float]], None],
        feasibility_fn: Optional[Callable[[List[str], Dict[str, Any]], List[str]]] = None,
        epsilon: float = 1e-9,
        max_iter_fallback: int = 50,
        tol_fallback: float = 1e-6,
        clamp_nonneg: bool = True,
        warn_large_scc: int = 15,
    ):
        self.items = items
        self.id_fn = id_fn
        self.deps_fn = deps_fn
        self.b_fn = b_fn
        self.coeff_fn = coeff_fn
        self.output_fn = output_fn
        self.feasibility_fn = feasibility_fn
        self.epsilon = epsilon
        self.max_iter_fallback = max_iter_fallback
        self.tol_fallback = tol_fallback
        self.clamp_nonneg = clamp_nonneg
        self.warn_large_scc = warn_large_scc

    def solve(self) -> SccLinearSolveResult:
        if not self.items:
            return SccLinearSolveResult(
                items=[], values={}, audit={}, warnings=[],
                has_cycle=False, cycle_groups=[], solve_order=[],
            )

        # 1. Build data_map + dep_map
        data_map: Dict[str, Any] = {}
        dep_map: Dict[str, List[Tuple[str, Any]]] = {}

        for item in self.items:
            node_id = self.id_fn(item)
            if not node_id or node_id in data_map:
                continue
            data_map[node_id] = item
            dep_map[node_id] = list(self.deps_fn(item) or [])

        # Filter: only keep deps that exist in data_map, remove self-loops
        for node_id in dep_map:
            dep_map[node_id] = [
                (dep_id, edge_data)
                for dep_id, edge_data in dep_map[node_id]
                if dep_id in data_map and dep_id != node_id
            ]

        # 2. Tarjan SCC + condensation order (using scc_topo_sort_with_info from topo)
        scc_info = scc_topo_sort_with_info(
            items=list(data_map.values()),
            id_fn=self.id_fn,
            deps_fn=lambda item: [d for d, _ in dep_map.get(self.id_fn(item), [])],
        )

        # 3. Giải theo condensation order
        resolved: Dict[str, float] = {}
        audit: Dict[str, SccLinearAuditEntry] = {}
        warnings: List[str] = []
        solve_order: List[str] = []

        for scc_idx in scc_info.condensation_order:
            scc_nodes = scc_info.sccs[scc_idx]

            if len(scc_nodes) == 1:
                self._solve_single(
                    scc_nodes[0], scc_idx, data_map, dep_map, resolved, audit
                )
            else:
                # Large SCC warning
                if self.warn_large_scc > 0 and len(scc_nodes) > self.warn_large_scc:
                    warnings.append(
                        f"SCC lớn ({len(scc_nodes)} nodes): {scc_nodes[:5]}... "
                        f"— Gaussian O(n³) có thể chậm. Kiểm tra lại đồ thị phụ thuộc."
                    )
                if self.feasibility_fn:
                    warnings.extend(self.feasibility_fn(scc_nodes, data_map) or [])
                self._solve_scc_gaussian(
                    scc_nodes, scc_idx, data_map, dep_map, resolved, audit, warnings
                )

            solve_order.extend(scc_nodes)

        # 4. Ghi kết quả qua output_fn
        for node_id, item in data_map.items():
            self.output_fn(node_id, resolved.get(node_id, 0.0), item, resolved)

        ordered_items = [data_map[nid] for nid in solve_order if nid in data_map]

        return SccLinearSolveResult(
            items=ordered_items,
            values=dict(resolved),
            audit=audit,
            warnings=warnings,
            has_cycle=scc_info.has_cycle,
            cycle_groups=scc_info.cycle_groups,
            solve_order=solve_order,
        )

    # --------------------------------------------------------------------------
    # Single node: independent or sequential
    # --------------------------------------------------------------------------

    def _solve_single(
        self,
        node_id: str,
        scc_idx: int,
        data_map: Dict[str, Any],
        dep_map: Dict[str, List[Tuple[str, Any]]],
        resolved: Dict[str, float],
        audit: Dict[str, SccLinearAuditEntry],
    ) -> None:
        """
        x[i] = b_fn(i) + Σ_j coeff(i,j) × resolved[j]
        """
        item = data_map[node_id]
        b_val = self.b_fn(node_id, item)
        ax_sum = 0.0
        deps_detail = []

        for dep_id, edge_data in dep_map.get(node_id, []):
            coeff = self.coeff_fn(node_id, dep_id, edge_data)
            x_dep = resolved.get(dep_id, 0.0)
            contrib = coeff * x_dep
            ax_sum += contrib
            deps_detail.append({
                "node": dep_id, "coeff": coeff,
                "x_dep": x_dep, "contribution": contrib,
                "source": "sequential",
            })

        x_val = b_val + ax_sum
        if self.clamp_nonneg:
            x_val = max(0.0, x_val)
        resolved[node_id] = x_val

        audit[node_id] = SccLinearAuditEntry(
            node_id=node_id, scc_index=scc_idx, is_cycle_node=False,
            b_pure=b_val, b_effective=b_val + ax_sum,
            x_value=x_val, solve_method="direct",
            deps_detail=deps_detail,
        )

    # --------------------------------------------------------------------------
    # SCC with cycles: Gaussian (I−A)x = B_ext
    # --------------------------------------------------------------------------

    def _solve_scc_gaussian(
        self,
        scc_nodes: List[str],
        scc_idx: int,
        data_map: Dict[str, Any],
        dep_map: Dict[str, List[Tuple[str, Any]]],
        resolved: Dict[str, float],
        audit: Dict[str, SccLinearAuditEntry],
        warnings: List[str],
    ) -> None:
        """
        Build and solve (I − A_intra) x = B_ext, where:
            A_intra[i][j] = coeff(i, j)   if j ∈ SCC
            B_ext[i]      = b_fn(i) + Σ_{j ∉ SCC} coeff(i,j) × resolved[j]
        """
        scc_set = set(scc_nodes)
        n = len(scc_nodes)
        idx_map = {nid: i for i, nid in enumerate(scc_nodes)}

        A_mat = [[0.0] * n for _ in range(n)]
        B_vec = [0.0] * n
        b_pure_vec = [0.0] * n
        deps_detail = [[] for _ in range(n)]

        for i, node_id in enumerate(scc_nodes):
            item = data_map[node_id]
            b_pure = self.b_fn(node_id, item)
            B_vec[i] = b_pure
            b_pure_vec[i] = b_pure

            for dep_id, edge_data in dep_map.get(node_id, []):
                coeff = self.coeff_fn(node_id, dep_id, edge_data)

                if dep_id in scc_set:
                    # Inside SCC → unknown → into A_intra
                    A_mat[i][idx_map[dep_id]] += coeff
                    deps_detail[i].append({
                        "node": dep_id, "coeff": coeff,
                        "x_dep": None, "contribution": None,
                        "source": "inside_scc",
                    })
                else:
                    # Outside SCC → already resolved → add to B_ext
                    x_dep = resolved.get(dep_id, 0.0)
                    contrib = coeff * x_dep
                    B_vec[i] += contrib
                    deps_detail[i].append({
                        "node": dep_id, "coeff": coeff,
                        "x_dep": x_dep, "contribution": contrib,
                        "source": "outside_scc",
                    })

        # Solve (I − A_intra)x = B_ext
        try:
            X = _gaussian_eliminate(A_mat, B_vec, self.epsilon)
            solve_method = "gaussian"
            iters = None
        except RuntimeError as exc:
            warn_msg = (
                f"Gaussian thất bại cho SCC {scc_nodes}: {exc}."
                + (f" Fallback Gauss-Seidel ({self.max_iter_fallback} vòng)."
                   if self.max_iter_fallback > 0
                   else " Dùng B_ext làm nghiệm xấp xỉ (max_iter_fallback=0).")
            )
            warnings.append(warn_msg)
            if self.max_iter_fallback > 0:
                X, solve_method, iters = self._iterative_fallback(
                    scc_nodes, A_mat, B_vec, warnings
                )
            else:
                X, solve_method, iters = list(B_vec), "fallback_constant", 0

        # Update resolved + audit
        for i, node_id in enumerate(scc_nodes):
            x_val = max(0.0, X[i]) if self.clamp_nonneg else X[i]
            resolved[node_id] = x_val

            # Fill inside_scc deps with resolved values
            detail = [dict(d) for d in deps_detail[i]]
            for d in detail:
                if d["source"] == "inside_scc":
                    j = idx_map[d["node"]]
                    d["x_dep"] = max(0.0, X[j]) if self.clamp_nonneg else X[j]
                    d["contribution"] = d["coeff"] * d["x_dep"]

            audit[node_id] = SccLinearAuditEntry(
                node_id=node_id, scc_index=scc_idx, is_cycle_node=True,
                b_pure=b_pure_vec[i], b_effective=B_vec[i],
                x_value=x_val, solve_method=solve_method,
                deps_detail=detail,
                matrix_A=A_mat, vector_B=list(B_vec), solution_X=list(X),
                iterations=iters,
            )

    # --------------------------------------------------------------------------
    # Gauss-Seidel fallback
    # --------------------------------------------------------------------------

    def _iterative_fallback(
        self,
        scc_nodes: List[str],
        A_mat: List[List[float]],
        B_vec: List[float],
        warnings: List[str],
    ) -> Tuple[List[float], str, int]:
        """
        Gauss-Seidel: X^{k+1}_i = B[i] + Σ_{j≠i} A[i][j] × X^k_j
        """
        n = len(scc_nodes)
        X = list(B_vec)  # initial x₀ = b
        prev_delta = float("inf")

        for it in range(1, self.max_iter_fallback + 1):
            old = list(X)
            for i in range(n):
                X[i] = B_vec[i] + sum(
                    A_mat[i][j] * X[j] for j in range(n) if i != j
                )
            delta = max(abs(X[i] - old[i]) for i in range(n))

            if delta < self.tol_fallback:
                return X, "iterative_fallback", it

            # Divergence guard: delta increases > 100× → stop early
            if delta > prev_delta * 100:
                warnings.append(
                    f"Gauss-Seidel phân kỳ cho SCC {scc_nodes} "
                    f"sau {it} vòng (delta={delta:.3e}). "
                    f"Trả B_ext làm xấp xỉ — kiểm tra spectral radius(A_intra)."
                )
                return list(B_vec), "iterative_fallback_diverged", it

            prev_delta = delta

        warnings.append(
            f"Gauss-Seidel không hội tụ sau {self.max_iter_fallback} vòng "
            f"cho SCC {scc_nodes}. delta cuối = {prev_delta:.3e}. "
            f"Trả nghiệm xấp xỉ — tăng max_iter_fallback nếu cần."
        )
        return X, "iterative_fallback", self.max_iter_fallback


# ============================================================================
# Public API function
# ============================================================================

def solve_linear_on_graph(
    items: List[Any],
    id_fn: Callable[[Any], str],
    deps_fn: Callable[[Any], List[Tuple[str, Any]]],
    b_fn: Callable[[str, Any], float],
    coeff_fn: Callable[[str, str, Any], float],
    output_fn: Callable[[str, float, Any, Dict[str, float]], None],
    feasibility_fn: Optional[Callable[[List[str], Dict[str, Any]], List[str]]] = None,
    epsilon: float = 1e-9,
    max_iter_fallback: int = 50,
    tol_fallback: float = 1e-6,
    clamp_nonneg: bool = True,
    warn_large_scc: int = 15,
) -> SccLinearSolveResult:
    """
    Giải hệ x_i = b_i + Σ_j A[i][j]×x_j trên đồ thị — API tổng quát v29.

    Dùng cho bất kỳ bài toán dạng (I−A)x=b có cấu trúc đồ thị:
        - Giá thành LSX có quay vòng bán thành phẩm
        - PageRank / authority scoring
        - BOM explosion cost (multi-level, có cycle)
        - Network flow cost / transfer pricing
        - Leontief Input-Output model
        - Inventory cascade / unit cost propagation

    CONTRACT của deps_fn (quan trọng):
        Chỉ trả deps có hệ số A[i][j] ≠ 0 — tức là các dep TẠO ràng buộc
        tuyến tính. Deps đã xử lý hoàn toàn trong b_fn không cần đưa vào.

    Parameters
    ----------
    items             : list of any object đại diện node
    id_fn             : item → node_id (str, unique)
    deps_fn           : item → [(dep_id, edge_data), ...]
                        CHỈ deps có A[i][j] ≠ 0
    b_fn              : (node_id, item) → float
                        Hằng số thuần — KHÔNG bao gồm dep contributions.
    coeff_fn          : (node_id, dep_id, edge_data) → float
                        Hệ số A[i][j]
    output_fn         : (node_id, x_value, item, resolved) → None
    feasibility_fn    : optional — kiểm tra tính khả thi của SCC cycle nodes
    epsilon           : ngưỡng singular matrix Gaussian (default 1e-9)
    max_iter_fallback : vòng Gauss-Seidel khi Gaussian thất bại (0 = tắt)
    tol_fallback      : ngưỡng hội tụ Gauss-Seidel (default 1e-6)
    clamp_nonneg      : clamp x ≥ 0 (phù hợp cost/qty; False cho các domain khác)
    warn_large_scc    : ngưỡng cảnh báo SCC lớn (default 15 nodes)

    Returns SccLinearSolveResult:
        .values       : Dict[str, float]               — {node_id: x_value}
        .has_cycle    : bool
        .cycle_groups : List[List[str]]                — SCCs có size > 1
        .audit        : Dict[str, SccLinearAuditEntry] — trace từng node
        .warnings     : List[str]
    """
    solver = SccLinearSolver(
        items=items,
        id_fn=id_fn,
        deps_fn=deps_fn,
        b_fn=b_fn,
        coeff_fn=coeff_fn,
        output_fn=output_fn,
        feasibility_fn=feasibility_fn,
        epsilon=epsilon,
        max_iter_fallback=max_iter_fallback,
        tol_fallback=tol_fallback,
        clamp_nonneg=clamp_nonneg,
        warn_large_scc=warn_large_scc,
    )
    return solver.solve()