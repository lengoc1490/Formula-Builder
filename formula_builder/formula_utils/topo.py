# formula_utils/topo.py
# Topological sorting and dependency graph utilities

import ast
import json
import re
from collections import defaultdict, deque
from typing import Dict, List, Set, Any, Tuple, Callable, Optional
from dataclasses import dataclass

from .errors import FormulaError, ErrorCode
from .types import TopoSortResult

# Pre-compiled regex for fast identifier extraction (v31 optimization)
_RE_STRING = re.compile(r"""(?:"[^"]*"|'[^']*')""")
_RE_ATTR = re.compile(r'\.[a-zA-Z_]\w*')        # attribute access: .field
_RE_IDENTIFIER = re.compile(r'[a-zA-Z_]\w*')


# ============================================================================
# DependencyGraph - used internally by FormulaEngineCore
# ============================================================================

class DependencyGraph:
    def __init__(self):
        self.graph = defaultdict(set)         # parent → children
        self.reverse_graph = defaultdict(set) # child → parents
        self.nodes = set()

    def add_node(self, name: str):
        self.nodes.add(name)

    def add_edge(self, parent: str, child: str):
        """Add dependency: child depends on parent"""
        self.graph[parent].add(child)
        self.reverse_graph[child].add(parent)

    def build(self, ast_map: Dict[str, ast.Expression]):
        """Build graph from AST map"""
        # Add all nodes first
        for name in ast_map:
            self.add_node(name)

        # Build edges
        for name, tree in ast_map.items():
            used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            for dep in used & self.nodes:
                self.add_edge(dep, name)

        # Detect cycles immediately
        self._detect_cycles()

    def build_from_exprs(self, exprs: Dict[str, str]):
        """Build graph from raw formula expressions (regex-based, no AST needed).

        Fast path: dùng regex để extract identifiers từ formula text,
        tránh phải parse AST. Xử lý cẩn thận:
        1. Strip string literals ('...', "...") → tránh nhầm 'NC' với biến NC
        2. Strip attribute access (.field) → tránh nhầm snap.total thành
           dependency vào "total" (chỉ "snap" mới là variable reference)
        3. Extract identifiers còn lại và match với known formula names
        """
        # Add all nodes
        for name in exprs:
            self.add_node(name)

        # Build edges — purify text first, then extract identifiers
        for name, expr in exprs.items():
            clean = _RE_STRING.sub('""', expr)   # Bước 1: xóa string literals (tránh 'NC' → biến NC)
            clean = _RE_ATTR.sub('', clean)       # Bước 2: xóa .field (tránh snap.total → dep vào total)
            identifiers = set(_RE_IDENTIFIER.findall(clean))
            for dep in identifiers & self.nodes:
                self.add_edge(dep, name)  # Bao gồm self-reference (a = a + 1 là cycle thật)

        # Detect cycles
        self._detect_cycles()

    def _detect_cycles(self):
        visited = set()
        rec_stack = set()
        cycle_path = []

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            cycle_path.append(node)
            
            for child in self.graph[node]:
                if child not in visited:
                    if dfs(child):
                        return True
                elif child in rec_stack:
                    # Found cycle - show exact path
                    idx = cycle_path.index(child)
                    cycle = " → ".join(cycle_path[idx:] + [child])
                    raise FormulaError(
                        f"Circular dependency: {cycle}", 
                        code=ErrorCode.CIRCULAR_DEPENDENCY, 
                        level="FATAL"
                    )
            
            cycle_path.pop()
            rec_stack.remove(node)
            return False

        for node in list(self.nodes):
            if node not in visited:
                dfs(node)

    def topological_sort(self) -> List[str]:
        """Kahn's algorithm for topological sorting"""
        indegree = {node: 0 for node in self.nodes}
        for node in self.graph:
            for child in self.graph[node]:
                indegree[child] += 1
        
        q = deque([node for node in indegree if indegree[node] == 0])
        order = []
        
        while q:
            node = q.popleft()
            order.append(node)
            for child in self.graph[node]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    q.append(child)
        
        if len(order) != len(self.nodes):
            raise FormulaError(
                "Circular dependency prevents topological sort", 
                code=ErrorCode.CIRCULAR_DEPENDENCY
            )
        
        return order

    def get_affected(self, changed: Set[str]) -> Set[str]:
        affected = set(changed)
        queue = deque(changed)
        
        while queue:
            node = queue.popleft()
            for child in self.graph[node]:
                if child not in affected:
                    affected.add(child)
                    queue.append(child)
        
        return affected

    def max_depth(self) -> int:
        if not self.nodes:
            return 0

        memo: Dict[str, int] = {}

        def _dfs(node: str) -> int:
            if node in memo:
                return memo[node]
            parents = self.reverse_graph.get(node, set())
            if not parents:
                memo[node] = 0
                return 0
            depth = 1 + max(_dfs(p) for p in parents)
            memo[node] = depth
            return depth

        return max(_dfs(n) for n in self.nodes)


# ============================================================================
# Core topological sort utilities (Kahn's algorithm)
# ============================================================================

def _build_topo_graph(
    items: List[Any],
    id_fn: Callable[[Any], Any],
    deps_fn: Callable[[Any], List[Any]],
    track_edges: bool = False,
) -> Tuple[Dict, List, "defaultdict[Any, List]", Dict, Dict]:
    """Build graph for topological sorting."""
    # Index: take first occurrence if duplicate id
    id_to_item: Dict[Any, Any] = {}
    order_seen: List[Any] = []
    for item in items:
        iid = id_fn(item)
        if iid not in id_to_item:
            id_to_item[iid] = item
            order_seen.append(iid)

    id_set = set(id_to_item)   # O(1) membership

    # Build graph
    graph = defaultdict(list)
    in_degree = {nid: 0 for nid in order_seen}
    edges: Dict[Any, List[Any]] = ({nid: [] for nid in order_seen} if track_edges else {})

    for item_id, item in id_to_item.items():
        seen_deps: set = set()
        for dep_id in deps_fn(item):
            if (
                dep_id
                and dep_id in id_set
                and dep_id != item_id
                and dep_id not in seen_deps
            ):
                seen_deps.add(dep_id)
                graph[dep_id].append(item_id)
                in_degree[item_id] += 1
                if track_edges:
                    edges[item_id].append(dep_id)

    return id_to_item, order_seen, graph, in_degree, edges


def topo_sort(
    items: List[Any],
    id_fn: Callable[[Any], Any],
    deps_fn: Callable[[Any], List[Any]],
) -> List[Any]:
    """Simple topological sort (Kahn) - returns sorted items."""
    id_to_item, order_seen, graph, in_degree, _ = _build_topo_graph(
        items, id_fn, deps_fn, track_edges=False
    )

    queue = deque(nid for nid in order_seen if in_degree[nid] == 0)
    topo_order = []

    while queue:
        cur = queue.popleft()
        topo_order.append(cur)
        for neighbor in graph[cur]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Cycle fallback — không crash, append theo thứ tự gốc
    if len(topo_order) < len(id_to_item):
        visited = set(topo_order)
        topo_order.extend(nid for nid in order_seen if nid not in visited)

    return [id_to_item[nid] for nid in topo_order]


def topo_sort_with_info(
    items: List[Any],
    id_fn: Callable[[Any], Any],
    deps_fn: Callable[[Any], List[Any]],
) -> TopoSortResult:
    """Topological sort with metadata (levels, cycle info)."""
    id_to_item, order_seen, graph, in_degree, edges = _build_topo_graph(
        items, id_fn, deps_fn, track_edges=True
    )

    # Kahn's + level tracking
    levels: Dict[Any, int] = {}
    queue = deque()

    for nid in order_seen:
        if in_degree[nid] == 0:
            queue.append(nid)
            levels[nid] = 0

    topo_order = []
    while queue:
        cur = queue.popleft()
        topo_order.append(cur)
        for neighbor in graph[cur]:
            in_degree[neighbor] -= 1
            levels[neighbor] = max(levels.get(neighbor, 0), levels[cur] + 1)
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Cycle detection
    visited = set(topo_order)
    cycle_nodes = [nid for nid in order_seen if nid not in visited]
    has_cycle = len(cycle_nodes) > 0

    if has_cycle:
        topo_order.extend(cycle_nodes)
        for nid in cycle_nodes:
            levels[nid] = -1   # mark cycle node

    return TopoSortResult(
        items=[id_to_item[nid] for nid in topo_order],
        order=topo_order,
        has_cycle=has_cycle,
        cycle_nodes=cycle_nodes,
        levels=levels,
        edges=edges,
    )


class TopoSorter:
    """Reusable sorter with pre-bound id_fn and deps_fn."""
    def __init__(
        self,
        id_fn: Callable[[Any], Any],
        deps_fn: Callable[[Any], List[Any]],
    ):
        self.id_fn = id_fn
        self.deps_fn = deps_fn

    def sort(self, items: List[Any]) -> List[Any]:
        """Quick sort - returns sorted list."""
        return topo_sort(items, self.id_fn, self.deps_fn)

    def sort_with_info(self, items: List[Any]) -> TopoSortResult:
        """Full metadata result."""
        return topo_sort_with_info(items, self.id_fn, self.deps_fn)


# ============================================================================
# SCC (Strongly Connected Components) topological sort using Tarjan
# ============================================================================

def _tarjan_scc_iterative(
    nodes: List[Any],
    graph: Dict[Any, List[Any]],
) -> List[List[Any]]:
    """Iterative Tarjan's algorithm for SCC detection."""
    index_counter = [0]
    stack: List[Any] = []
    on_stack: Set[Any] = set()
    index: Dict[Any, int] = {}
    lowlink: Dict[Any, int] = {}
    sccs: List[List[Any]] = []

    for start in nodes:
        if start in index:
            continue

        # Iterative DFS — frame = (node, neighbor_iterator)
        call_stack = [(start, iter(graph.get(start, [])))]
        index[start] = lowlink[start] = index_counter[0]
        index_counter[0] += 1
        stack.append(start)
        on_stack.add(start)

        while call_stack:
            v, nbrs = call_stack[-1]
            try:
                w = next(nbrs)
                if w not in index:
                    # Tree edge — push
                    index[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    call_stack.append((w, iter(graph.get(w, []))))
                elif w in on_stack:
                    # Back edge
                    if lowlink[v] > index[w]:
                        lowlink[v] = index[w]
            except StopIteration:
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    if lowlink[parent] > lowlink[v]:
                        lowlink[parent] = lowlink[v]
                # Root of SCC?
                if lowlink[v] == index[v]:
                    scc = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        scc.append(w)
                        if w == v:
                            break
                    sccs.append(scc)

    return sccs  # reverse topo order


def _build_scc_graph(
    items: List[Any],
    id_fn: Callable,
    deps_fn: Callable,
) -> Tuple[Dict[Any, Any], List[Any], Dict[Any, List[Any]], Dict[Any, List[Any]]]:
    """Build graph for SCC detection."""
    id_to_item: Dict[Any, Any] = {}
    order_seen: List[Any] = []
    deps_graph: Dict[Any, List[Any]] = {}
    edges: Dict[Any, List[Any]] = {}

    for item in items:
        iid = id_fn(item)
        if iid not in id_to_item:
            id_to_item[iid] = item
            order_seen.append(iid)

    id_set = set(id_to_item)

    for iid in order_seen:
        item = id_to_item[iid]
        seen: Set[Any] = set()
        dep_list = []
        for dep in deps_fn(item):
            if dep and dep in id_set and dep != iid and dep not in seen:
                seen.add(dep)
                dep_list.append(dep)
        deps_graph[iid] = dep_list
        edges[iid] = dep_list[:]

    return id_to_item, order_seen, deps_graph, edges


def scc_topo_sort_with_info(
    items: List[Any],
    id_fn: Callable[[Any], Any],
    deps_fn: Callable[[Any], List[Any]],
) -> 'SccTopoResult':
    """Topological sort that preserves SCC cycles as groups."""
    # Import here to avoid circular import
    from .types import SccTopoResult

    if not items:
        return SccTopoResult(
            items=[], order=[], sccs=[], node_to_scc={},
            condensation_order=[], has_cycle=False,
            cycle_groups=[], levels={}, edges={},
        )

    id_to_item, order_seen, deps_graph, edges = _build_scc_graph(items, id_fn, deps_fn)

    # Tarjan SCC
    sccs_raw = _tarjan_scc_iterative(list(id_to_item.keys()), deps_graph)
    # Tarjan returns REVERSE topo order → reverse to get natural order
    sccs_raw = list(reversed(sccs_raw))

    node_to_scc: Dict[Any, int] = {}
    for idx, scc in enumerate(sccs_raw):
        for node in scc:
            node_to_scc[node] = idx

    # Condensation graph
    n_scc = len(sccs_raw)
    indeg = {i: 0 for i in range(n_scc)}
    forward_cond: Dict[int, List[int]] = defaultdict(list)

    for u, deps in deps_graph.items():
        su = node_to_scc[u]
        for v in deps:
            sv = node_to_scc[v]
            if su != sv:
                # u depends on v → sv must come before su
                if su not in forward_cond[sv]:
                    forward_cond[sv].append(su)
                    indeg[su] += 1

    # Topo sort condensation (Kahn's)
    queue = deque(i for i in range(n_scc) if indeg[i] == 0)
    condensation_order: List[int] = []
    indeg_copy = dict(indeg)

    while queue:
        cur = queue.popleft()
        condensation_order.append(cur)
        for nxt in forward_cond[cur]:
            indeg_copy[nxt] -= 1
            if indeg_copy[nxt] == 0:
                queue.append(nxt)

    remaining = [i for i in range(n_scc) if i not in set(condensation_order)]
    condensation_order.extend(remaining)

    # Assign levels
    scc_level: Dict[int, int] = {i: 0 for i in range(n_scc)}
    scc_deps: Dict[int, Set[int]] = {i: set() for i in range(n_scc)}
    for u, deps in deps_graph.items():
        su = node_to_scc[u]
        for v in deps:
            sv = node_to_scc[v]
            if su != sv:
                scc_deps[su].add(sv)

    for si in condensation_order:
        if scc_deps[si]:
            scc_level[si] = max(scc_level[sv] for sv in scc_deps[si]) + 1

    levels: Dict[Any, int] = {}
    for idx, scc in enumerate(sccs_raw):
        base = scc_level[idx]
        for node in scc:
            levels[node] = -1 if len(scc) > 1 else base

    cycle_groups = [scc for scc in sccs_raw if len(scc) > 1]
    has_cycle = len(cycle_groups) > 0

    sorted_ids: List[Any] = []
    for si in condensation_order:
        sorted_ids.extend(sccs_raw[si])

    sorted_items = [id_to_item[nid] for nid in sorted_ids if nid in id_to_item]

    return SccTopoResult(
        items=sorted_items,
        order=sorted_ids,
        sccs=sccs_raw,
        node_to_scc=node_to_scc,
        condensation_order=condensation_order,
        has_cycle=has_cycle,
        cycle_groups=cycle_groups,
        levels=levels,
        edges=edges,
    )


def scc_topo_sort(
    items: List[Any],
    id_fn: Callable[[Any], Any],
    deps_fn: Callable[[Any], List[Any]],
) -> List[Any]:
    """Return items sorted by condensation order, with SCCs grouped."""
    return scc_topo_sort_with_info(items, id_fn, deps_fn).items


class SccTopoSorter:
    """Reusable SCC-based topological sorter."""
    def __init__(
        self,
        id_fn: Callable[[Any], Any],
        deps_fn: Callable[[Any], List[Any]],
    ):
        self.id_fn = id_fn
        self.deps_fn = deps_fn

    def sort(self, items: List[Any]) -> List[Any]:
        return scc_topo_sort(items, self.id_fn, self.deps_fn)

    def sort_with_info(self, items: List[Any]) -> 'SccTopoResult':
        return scc_topo_sort_with_info(items, self.id_fn, self.deps_fn)


# ============================================================================
# Convenience functions for dict-based data (for BASE_FUNCS)
# ============================================================================

def topo_sort_data(
    items: List[Dict],
    id_key: str,
    deps_list_key: str,
    dep_id_key: str,
) -> List[Dict]:
    """Topological sort for list of dicts with nested dependencies."""
    def _deps_fn(item):
        raw = item.get(deps_list_key)
        if not raw:
            return []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return []
        if not isinstance(raw, list):
            return []
        return [d.get(dep_id_key) for d in raw if isinstance(d, dict) and d.get(dep_id_key)]

    return topo_sort(
        items=items,
        id_fn=lambda x: x.get(id_key),
        deps_fn=_deps_fn,
    )


def topo_sort_flat(
    items: List[Dict],
    id_key: str,
    dep_ids_key: str,
) -> List[Dict]:
    """Topological sort for list of dicts with simple list of dependency IDs."""
    return topo_sort(
        items=items,
        id_fn=lambda x: x.get(id_key),
        deps_fn=lambda x: x.get(dep_ids_key) or [],
    )


def scc_topo_sort_data(
    items: List[Dict],
    id_key: str,
    deps_list_key: str,
    dep_id_key: str,
) -> List[Dict]:
    """SCC-based topological sort for dict data."""
    def _deps_fn(item):
        raw = item.get(deps_list_key) or []
        if isinstance(raw, str):
            try:
                import json as _json
                raw = _json.loads(raw)
            except Exception:
                raw = []
        return [d.get(dep_id_key) for d in raw if d.get(dep_id_key)]

    return scc_topo_sort(
        items,
        id_fn=lambda x: x.get(id_key),
        deps_fn=_deps_fn,
    )


def scc_topo_sort_flat(
    items: List[Dict],
    id_key: str,
    dep_ids_key: str,
) -> List[Dict]:
    """SCC-based topological sort for dict with simple list of dep IDs."""
    return scc_topo_sort(
        items,
        id_fn=lambda x: x.get(id_key),
        deps_fn=lambda x: x.get(dep_ids_key) or [],
    )