#!/usr/bin/env python3
# benchmark_v31_comprehensive.py — Performance benchmark for Formula Builder v31
# =============================================================================
# Mô phỏng scenario thực tế:
#   1. Single-engine: 1 BOM, 1000 công thức, evaluate đơn lẻ
#   2. Multi-BOM: 1000 sản phẩm, mỗi BOM 1000 công thức, sequential
#   3. Batch: 1000 dòng, engine dùng chung → calculate_batch
#   4. Trace: performance cost khi bật trace_fields
#   5. Audit: performance cost của audit session
#   6. Snapshot: cost tạo EnterpriseSnapshot 5-layer
#   7. Incremental: chỉ tính node bị ảnh hưởng
#   8. Cost template: phân tích nhóm chi phí đa tầng
# =============================================================================

import sys, os, time, random, json, gc, itertools, statistics, hashlib

# Add the frappe-bench to path to import formula_builder
FRAPPE_BENCH = os.path.expanduser("~/frappe-bench")
sys.path.insert(0, FRAPPE_BENCH)
sys.path.insert(0, os.path.join(FRAPPE_BENCH, "apps"))

# Redirect stdout for proper encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# =============================================================================
# IMPORT ENGINE
# =============================================================================

try:
    from formula_builder.formula_utils.engine_public import FormulaEngine
    from formula_builder.formula_utils.engine_core import FormulaEngineCore, IncrementalContext
    from formula_builder.formula_utils.engine_trace import FormulaEngineTrace
    from formula_builder.formula_utils.engine_audit import FormulaEngineAudit
    from formula_builder.formula_utils.types import (
        SnapshotTag, SnapshotStatus, AuditSession, AuditReport
    )
    from formula_builder.formula_utils.funcs.registry import BASE_FUNCS

    print("✅ Loaded FormulaEngine v31 (public)")
except Exception as e:
    print(f"❌ Cannot load FormulaEngine: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

ENGINE_VERSION = FormulaEngineCore.ENGINE_VERSION
print(f"   Version: {ENGINE_VERSION}")

# =============================================================================
# HELPERS
# =============================================================================

def fmt(n):
    """Format number for display."""
    if n is None:
        return "N/A"
    if isinstance(n, float):
        if abs(n) >= 1_000_000:
            return f"{n:,.0f}"
        elif abs(n) >= 1000:
            return f"{n:,.1f}"
        elif abs(n) >= 1:
            return f"{n:.2f}"
        elif abs(n) >= 0.001:
            return f"{n:.4f}"
        else:
            return f"{n:.6f}"
    return f"{n:,}"

def ms(t):
    """Seconds → milliseconds string."""
    return f"{t * 1000:.2f}ms"

def timer():
    """High-res timer."""
    return time.perf_counter()

def run_and_measure(label, fn, iterations=1, warmup=1):
    """Run fn `iterations` times and return stats dict."""
    # Warmup
    for _ in range(warmup):
        fn()
    gc.collect()

    times = []
    for _ in range(iterations):
        t0 = timer()
        result = fn()
        elapsed = timer() - t0
        times.append(elapsed)

    avg = statistics.mean(times)
    if len(times) > 1:
        stdev = statistics.stdev(times)
    else:
        stdev = 0

    return {
        "label": label,
        "avg_s": avg,
        "min_s": min(times),
        "max_s": max(times),
        "stdev_s": stdev,
        "iterations": iterations,
        "result": result,
    }

# =============================================================================
# GENERATORS — formula & data
# =============================================================================

def generate_linear_chain(n: int, prefix: str = "v") -> list:
    """Generate a linear chain: v0=INPUT, v1=v0+1, v2=v1*2, ...

    Simple DAG — no branching, just sequential dependencies.
    """
    formulas = []
    formulas.append({"name": f"{prefix}0", "formula": "INPUT + 0"})
    for i in range(1, n):
        formulas.append({"name": f"{prefix}{i}", "formula": f"{prefix}{i-1} * 1.05 + {i % 7}"})
    return formulas

def generate_deep_tree(n: int, prefix: str = "t") -> list:
    """Generate a binary tree DAG: leaves → internal nodes → root.

    Depth ~ log2(n), high fan-out. Tests DAG resolution overhead.
    """
    formulas = []
    # Leaf formulas — depend on INPUT
    leaf_count = (n + 1) // 2
    for i in range(leaf_count):
        formulas.append({"name": f"{prefix}_leaf_{i}", "formula": f"INPUT * (1 + {i % 10} / 100)"})

    # Internal nodes — combine children
    internal_start = leaf_count
    remaining = n - leaf_count
    idx = 0
    while remaining > 0 and internal_start < n:
        formulas.append({
            "name": f"{prefix}_node_{idx}",
            "formula": f"{prefix}_leaf_{(idx*2) % leaf_count} + {prefix}_leaf_{(idx*2+1) % leaf_count}"
        })
        idx += 1
        remaining -= 1
    return formulas

def generate_cost_template(n: int, n_groups: int = 10, n_buckets: int = 50) -> list:
    """Generate realistic cost template formulas.

    Mimics real-world cost calculation:
    - n_buckets: leaf cost buckets (VL_NHOM, VL_KINH, NC_SX, ...)
    - n_groups: group aggregates (TONG_VL, TONG_NC, TONG_OH...)
    - Final: GIA_THANH, PROFIT, GIA_BAN, VAT, GIA_VAT
    """
    formulas = []

    # Leaf cost buckets — each depends on INPUT + random factor
    for i in range(n_buckets):
        formulas.append({
            "name": f"bucket_{i}",
            "formula": f"INPUT * (1 + {i % 20} / 100) + {i * 7}"
        })

    # Group aggregates — sum buckets
    buckets_per_group = max(1, n_buckets // max(1, n_groups))
    for g in range(n_groups):
        start = g * buckets_per_group
        end = min(start + buckets_per_group, n_buckets)
        bucket_refs = " + ".join(f"bucket_{i}" for i in range(start, end))
        formulas.append({
            "name": f"group_{g}",
            "formula": bucket_refs
        })

    # Multi-tier cost template — intermediate nodes
    for i in range(min(n - n_buckets - n_groups - 10, 0) + n - n_buckets - n_groups - 10):
        pass  # We already have enough formulas

    # Top-level aggregates
    group_refs = " + ".join(f"group_{g}" for g in range(n_groups))
    formulas.append({"name": "TONG_VL",    "formula": group_refs})
    formulas.append({"name": "TONG_NC",    "formula": f"TONG_VL * 0.15"})
    formulas.append({"name": "TONG_OH",    "formula": f"TONG_VL * 0.05 + TONG_NC * 0.10"})
    formulas.append({"name": "GIA_THANH",  "formula": "TONG_VL + TONG_NC + TONG_OH"})
    formulas.append({"name": "PROFIT",     "formula": "GIA_THANH * 0.18"})
    formulas.append({"name": "GIA_BAN",    "formula": "GIA_THANH + PROFIT"})
    formulas.append({"name": "VAT",        "formula": "GIA_BAN * 0.10"})
    formulas.append({"name": "GIA_VAT",    "formula": "GIA_BAN + VAT"})
    formulas.append({"name": "TONG_M2",    "formula": "INPUT * 0.001"})
    formulas.append({"name": "DON_GIA_M2", "formula": "GIA_VAT / IF(TONG_M2 > 0, TONG_M2, 1)"})

    # Fill remaining slots with computed intermediates
    extra_needed = n - len(formulas)
    for i in range(extra_needed):
        a = i % n_buckets
        b = (i * 3 + 7) % n_buckets
        formulas.append({
            "name": f"computed_{i}",
            "formula": f"bucket_{a} * 0.3 + bucket_{b} * 0.7"
        })

    return formulas[:n]

def generate_realistic_bom(n: int) -> list:
    """Generate BOM-like formulas: vật tư + nhân công + overhead + giá thành.

    Mix of:
    - Row-level formulas (width, height, qty, unit_qty, total_qty, line_total)
    - Cross-row references
    - Global aggregates
    """
    formulas = []
    n_items = max(1, n // 6)  # ~6 formulas per item row

    # Row-level formulas for each "item"
    for i in range(min(n_items, n)):
        p = f"item_{i}"
        formulas.append({"name": f"{p}__width",  "formula": f"W_mm / {max(1, i % 5 + 1)} - {i % 3 * 10}"})
        formulas.append({"name": f"{p}__height", "formula": f"H_mm - {i % 4 * 15}"})
        formulas.append({"name": f"{p}__qty",    "formula": f"{2 + i % 3}"})
        formulas.append({"name": f"{p}__unit_qty", "formula": f"({p}__width / 1000) * ({p}__height / 1000) * {1 + i % 5 * 0.15}"})
        formulas.append({"name": f"{p}__total_qty", "formula": f"{p}__unit_qty * ({p}__qty or 1)"})
        formulas.append({"name": f"{p}__line_total", "formula": f"{p}__total_qty * ({p}__unit_price or 0)"})

    # Truncate to exact n
    formulas = formulas[:max(0, n - 8)]

    # Global aggregates
    item_refs = [f"item_{i}__line_total" for i in range(min(n_items, n))]
    TOTAL = " + ".join(item_refs[:50]) if item_refs else "0"  # limit expression size
    formulas.append({"name": "TONG_VAT_TU",  "formula": TOTAL if len(item_refs) <= 50 else f"sum([{','.join(item_refs[:50])}])"})
    formulas.append({"name": "TONG_NC",      "formula": "TONG_VAT_TU * 0.15"})
    formulas.append({"name": "TONG_OH",      "formula": "TONG_VAT_TU * 0.05"})
    formulas.append({"name": "GIA_THANH",    "formula": "TONG_VAT_TU + TONG_NC + TONG_OH"})
    formulas.append({"name": "PROFIT",       "formula": "GIA_THANH * 0.18"})
    formulas.append({"name": "GIA_BAN",      "formula": "GIA_THANH + PROFIT"})
    formulas.append({"name": "VAT",          "formula": "GIA_BAN * 0.10"})
    formulas.append({"name": "GIA_VAT",      "formula": "GIA_BAN + VAT"})

    return formulas[:n]

# =============================================================================
# BENCHMARK FUNCTIONS
# =============================================================================

def bench_single_engine(formula_count: int, iterations: int = 5):
    """Benchmark single engine with large formula set."""
    print(f"\n{'─'*70}")
    print(f"📊 BENCH 1: Single Engine — {formula_count} formulas")
    print(f"{'─'*70}")

    formulas = generate_cost_template(formula_count)

    # Init
    def do_init():
        return FormulaEngine(
            formulas=formulas,
            on_error="default", default_value=0, deterministic=False,
        )

    t0 = timer()
    engine = do_init()
    init_time = timer() - t0
    print(f"   ⚙️  Init ({formula_count} formulas): {ms(init_time)}")
    print(f"   DAG depth: {engine._graph.max_depth() if hasattr(engine, '_graph') else 'N/A'}")
    print(f"   Topo order: {len(engine._topo_order)} nodes")

    # Benchmark evaluate
    def do_eval():
        return engine.calculate({"INPUT": 1000000})

    # Warmup
    do_eval()

    times = []
    for i in range(iterations):
        gc.collect()
        t0 = timer()
        result = do_eval()
        times.append(timer() - t0)
    avg = statistics.mean(times)

    print(f"   🚀 Evaluate ({iterations} runs): avg={ms(avg)}, min={ms(min(times))}, max={ms(max(times))}")

    # Verify
    if "GIA_VAT" in result:
        print(f"   ✅ GIA_VAT = {fmt(result['GIA_VAT'])}")
    print(f"   Throughput: {fmt(formula_count / avg)} formula-nodes/sec")

    return {
        "init_ms": init_time * 1000,
        "eval_avg_ms": avg * 1000,
        "eval_min_ms": min(times) * 1000,
        "eval_max_ms": max(times) * 1000,
        "nodes_per_sec": formula_count / avg,
        "formula_count": formula_count,
        "dag_depth": engine._dag.max_depth() if hasattr(engine, '_dag') else 0,
    }

def bench_multi_bom(n_products: int, formulas_per_bom: int, iterations: int = 1):
    """Benchmark: N products × M formulas each — sequential evaluation.

    Simulates batch pricing for 1000 products, each with its own BOM.
    """
    print(f"\n{'─'*70}")
    print(f"📊 BENCH 2: Multi-BOM — {n_products} products × ~{formulas_per_bom} formulas each")
    print(f"{'─'*70}")

    total_formulas = 0
    engines = []
    init_times = []

    # Pre-generate engines — different formulas per product (simulate real BOMs)
    print(f"   Building {n_products} engines...")
    t0_total = timer()
    for p in range(n_products):
        # Vary input seed per product → different formula structures
        n = max(10, formulas_per_bom + (p % 5 - 2) * 10)  # slight variation
        formulas = generate_cost_template(n)
        total_formulas += len(formulas)

        t0 = timer()
        engine = FormulaEngine(
            formulas=formulas,
            on_error="default", default_value=0, deterministic=False,
        )
        init_times.append(timer() - t0)
        engines.append(engine)

    init_total = timer() - t0_total

    print(f"   ⚙️  Total init: {ms(init_total)} ({ms(statistics.mean(init_times))} avg per engine)")
    print(f"   Total formulas: {fmt(total_formulas)}")

    # Evaluate all
    eval_times = []
    results = []
    t0_eval = timer()
    for p, engine in enumerate(engines):
        t0 = timer()
        result = engine.calculate({"INPUT": 1000000 + p * 5000})
        eval_times.append(timer() - t0)
        if p == 0:
            results.append(result)  # Keep first result for verification
    eval_total = timer() - t0_eval

    avg_eval = statistics.mean(eval_times)
    print(f"   🚀 Evaluate all {n_products}: {ms(eval_total)}")
    print(f"   Avg per product: {ms(avg_eval)}")
    print(f"   Throughput: {fmt(n_products / eval_total)} products/sec")
    print(f"   Formula throughput: {fmt(total_formulas / eval_total)} formula-nodes/sec")

    # Verify first
    if results and "GIA_VAT" in results[0]:
        print(f"   ✅ Product 0 GIA_VAT = {fmt(results[0]['GIA_VAT'])}")

    return {
        "n_products": n_products,
        "total_formulas": total_formulas,
        "init_total_ms": init_total * 1000,
        "eval_total_ms": eval_total * 1000,
        "avg_per_product_ms": avg_eval * 1000,
        "products_per_sec": n_products / eval_total,
        "formula_nodes_per_sec": total_formulas / eval_total,
    }

def bench_batch_evaluate(n_rows: int, formula_count: int, iterations: int = 3):
    """Benchmark: batch evaluate vs loop — same engine, multiple input rows."""
    print(f"\n{'─'*70}")
    print(f"📊 BENCH 3: Batch vs Loop — {n_rows} rows, {formula_count} formulas each")
    print(f"{'─'*70}")

    formulas = generate_cost_template(formula_count)
    engine = FormulaEngine(
        formulas=formulas,
        on_error="default", default_value=0, deterministic=False,
    )

    # Generate row inputs
    rows = [{"INPUT": 1000000 + i * 5000} for i in range(n_rows)]

    # Method A: Loop (sequential)
    def eval_loop():
        return [engine.calculate(row) for row in rows]

    r_loop = run_and_measure("Loop (sequential)", eval_loop, iterations=iterations)

    # Method B: calculate_batch
    def eval_batch():
        return engine.calculate_batch(rows)

    # warmup for batch
    engine.calculate_batch(rows[:10])
    r_batch = run_and_measure("Batch (calculate_batch)", eval_batch, iterations=iterations)

    speedup = r_loop["avg_s"] / r_batch["avg_s"] if r_batch["avg_s"] > 0 else 0

    print(f"   🔄 Loop  : {ms(r_loop['avg_s'])} avg ({iterations} runs)")
    print(f"   ⚡ Batch : {ms(r_batch['avg_s'])} avg ({iterations} runs)")
    print(f"   📈 Speedup: {speedup:.1f}x")

    return {
        "n_rows": n_rows,
        "formula_count": formula_count,
        "loop_avg_ms": r_loop["avg_s"] * 1000,
        "batch_avg_ms": r_batch["avg_s"] * 1000,
        "speedup": speedup,
    }

def bench_trace_overhead(formula_count: int, iterations: int = 5):
    """Benchmark: cost of enabling trace."""
    print(f"\n{'─'*70}")
    print(f"📊 BENCH 4: Trace Overhead — {formula_count} formulas")
    print(f"{'─'*70}")

    formulas = generate_cost_template(formula_count)
    engine = FormulaEngine(
        formulas=formulas,
        on_error="default", default_value=0, deterministic=False,
    )

    inputs = {"INPUT": 1000000}

    # No trace (fast path)
    def eval_no_trace():
        return engine.calculate(dict(inputs))

    # With trace on 10 fields
    trace_fields = {f"bucket_{i}" for i in range(5)} | {"GIA_VAT", "GIA_THANH", "PROFIT", "TONG_VL", "VAT"}

    def eval_with_trace():
        return engine.calculate(dict(inputs), trace_fields=trace_fields)

    r_no = run_and_measure("No trace", eval_no_trace, iterations=iterations)
    r_trace = run_and_measure("With trace (10 fields)", eval_with_trace, iterations=iterations)

    overhead = (r_trace["avg_s"] - r_no["avg_s"]) / r_no["avg_s"] * 100 if r_no["avg_s"] > 0 else 0

    print(f"   ⚡ No trace  : {ms(r_no['avg_s'])} avg")
    print(f"   🔍 With trace: {ms(r_trace['avg_s'])} avg")
    print(f"   📊 Overhead : {overhead:.1f}%")

    return {
        "no_trace_avg_ms": r_no["avg_s"] * 1000,
        "trace_avg_ms": r_trace["avg_s"] * 1000,
        "overhead_pct": overhead,
    }

def bench_audit(formula_count: int, iterations: int = 5):
    """Benchmark: cost of audit session."""
    print(f"\n{'─'*70}")
    print(f"📊 BENCH 5: Audit Session — {formula_count} formulas")
    print(f"{'─'*70}")

    formulas = generate_cost_template(formula_count)
    engine = FormulaEngine(
        formulas=formulas,
        on_error="default", default_value=0, deterministic=False,
    )

    inputs = {"INPUT": 1000000}

    # Without audit
    def eval_no_audit():
        return engine.calculate(dict(inputs))

    r_no = run_and_measure("No audit", eval_no_audit, iterations=iterations)

    # With audit
    def eval_with_audit():
        session = engine.begin_audit_session(force_materialize=False, sample_rate=0.01)
        result = engine.calculate(dict(inputs))
        report = engine.end_audit_session()
        return result

    r_audit = run_and_measure("With audit", eval_with_audit, iterations=iterations)

    overhead = (r_audit["avg_s"] - r_no["avg_s"]) / r_no["avg_s"] * 100 if r_no["avg_s"] > 0 else 0

    print(f"   ⚡ No audit  : {ms(r_no['avg_s'])} avg")
    print(f"   📋 With audit: {ms(r_audit['avg_s'])} avg")
    print(f"   📊 Overhead : {overhead:.1f}%")

    return {
        "no_audit_avg_ms": r_no["avg_s"] * 1000,
        "audit_avg_ms": r_audit["avg_s"] * 1000,
        "overhead_pct": overhead,
    }

def bench_snapshot(formula_count: int, iterations: int = 5):
    """Benchmark: cost of creating an EnterpriseSnapshot (5-layer)."""
    print(f"\n{'─'*70}")
    print(f"📊 BENCH 6: Snapshot — {formula_count} formulas")
    print(f"{'─'*70}")

    formulas = generate_cost_template(formula_count)
    engine = FormulaEngine(
        formulas=formulas,
        on_error="default", default_value=0, deterministic=False,
    )

    inputs = {"INPUT": 1000000}

    # Evaluate only (no snapshot)
    def eval_only():
        return engine.calculate(dict(inputs))

    r_eval = run_and_measure("Evaluate only", eval_only, iterations=iterations)

    # Evaluate + snapshot
    def eval_and_snapshot():
        result = engine.calculate(dict(inputs))
        snap = engine.snapshot(
            inputs=inputs, outputs=result,
            tag=SnapshotTag.ESTIMATE, status=SnapshotStatus.DRAFT,
            created_by="benchmark", calc_mode="full",
            source_doc="BENCH-001", notes="Benchmark run",
        )
        return snap

    r_snap = run_and_measure("Eval + Snapshot", eval_and_snapshot, iterations=iterations)

    snap_cost = r_snap["avg_s"] - r_eval["avg_s"]
    snap = r_snap.get("result") if hasattr(r_snap, 'get') else None
    if hasattr(r_snap, '__getitem__'):
        snap = r_snap["result"]

    print(f"   ⚡ Eval only    : {ms(r_eval['avg_s'])} avg")
    print(f"   📸 Eval+Snapshot: {ms(r_snap['avg_s'])} avg")
    print(f"   📊 Snapshot cost: {ms(snap_cost)} (+{(snap_cost / r_eval['avg_s'] * 100):.1f}%)" if r_eval["avg_s"] > 0 else "   N/A")

    return {
        "eval_avg_ms": r_eval["avg_s"] * 1000,
        "snapshot_avg_ms": r_snap["avg_s"] * 1000,
        "snapshot_cost_ms": snap_cost * 1000,
        "overhead_pct": (snap_cost / r_eval["avg_s"] * 100) if r_eval["avg_s"] > 0 else 0,
    }

def bench_incremental(formula_count: int, iterations: int = 5):
    """Benchmark: incremental vs full recalc when one input changes."""
    print(f"\n{'─'*70}")
    print(f"📊 BENCH 7: Incremental — {formula_count} formulas, 1 input changed")
    print(f"{'─'*70}")

    formulas = generate_cost_template(formula_count)
    engine = FormulaEngine(
        formulas=formulas,
        on_error="default", default_value=0, deterministic=False,
    )

    inputs_initial = {"INPUT": 1000000}

    # Full recalc
    def full_recalc():
        return engine.calculate({"INPUT": 1000000 + random.randint(1, 10000)})

    r_full = run_and_measure("Full recalc", full_recalc, iterations=iterations)

    # Incremental
    ictx = engine.create_context(initial_inputs=inputs_initial, doc_id="BENCH-001")

    def incremental():
        return engine.calculate_incremental(ictx, {"INPUT": 1000000 + random.randint(1, 10000)})

    r_incr = run_and_measure("Incremental", incremental, iterations=iterations)

    speedup = r_full["avg_s"] / r_incr["avg_s"] if r_incr["avg_s"] > 0 else 0

    print(f"   🔄 Full recalc : {ms(r_full['avg_s'])} avg")
    print(f"   ⚡ Incremental : {ms(r_incr['avg_s'])} avg")
    print(f"   📈 Speedup     : {speedup:.1f}x")

    return {
        "full_avg_ms": r_full["avg_s"] * 1000,
        "incremental_avg_ms": r_incr["avg_s"] * 1000,
        "speedup": speedup,
    }

def bench_cost_analysis(n_buckets: int = 50, n_groups: int = 10, iterations: int = 5):
    """Benchmark: cost template analysis — multi-tier cost aggregation."""
    print(f"\n{'─'*70}")
    print(f"📊 BENCH 8: Cost Template — {n_buckets} buckets → {n_groups} groups → price")
    print(f"{'─'*70}")

    formulas = generate_cost_template(n_buckets + n_groups + 10, n_groups, n_buckets)
    engine = FormulaEngine(
        formulas=formulas,
        on_error="default", default_value=0, deterministic=False,
    )

    print(f"   DAG: {len(formulas)} formulas, depth={engine._dag.max_depth() if hasattr(engine, '_dag') else 'N/A'}")

    inputs = {"INPUT": 1000000}

    def eval_cost():
        return engine.calculate(dict(inputs))

    r = run_and_measure("Cost analysis", eval_cost, iterations=iterations)

    result = r["result"]
    print(f"   ⚡ Avg eval time : {ms(r['avg_s'])}")
    print(f"   💰 Price breakdown:")

    for k in ["TONG_VL", "TONG_NC", "TONG_OH", "GIA_THANH", "PROFIT", "GIA_BAN", "VAT", "GIA_VAT"]:
        if k in result:
            print(f"      {k:<14}: {fmt(result[k])}")

    return {
        "n_buckets": n_buckets,
        "n_groups": n_groups,
        "total_formulas": len(formulas),
        "eval_avg_ms": r["avg_s"] * 1000,
    }


# =============================================================================
# MAIN — run all benchmarks and produce report
# =============================================================================

def main():
    print("=" * 70)
    print("🏁 FORMULA BUILDER v31 — COMPREHENSIVE PERFORMANCE BENCHMARK")
    print("=" * 70)
    print(f"   Python: {sys.version}")
    print(f"   Engine: {ENGINE_VERSION}")
    print(f"   Time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # ── Benchmark 1: Single engine stress ──
    results["single_100"]  = bench_single_engine(100, iterations=10)
    results["single_500"]  = bench_single_engine(500, iterations=5)
    results["single_1000"] = bench_single_engine(1000, iterations=3)

    # ── Benchmark 2: Multi-BOM ──
    results["multi_10x100"]  = bench_multi_bom(10, 100, iterations=1)
    results["multi_100x50"]  = bench_multi_bom(100, 50, iterations=1)
    results["multi_100x100"] = bench_multi_bom(100, 100, iterations=1)
    results["multi_1000x100"] = bench_multi_bom(1000, 100, iterations=1)

    # ── Benchmark 3: Batch vs Loop ──
    results["batch_100x50"]  = bench_batch_evaluate(100, 50)
    results["batch_1000x50"] = bench_batch_evaluate(1000, 50)

    # ── Benchmark 4: Trace ──
    results["trace_100"]  = bench_trace_overhead(100)
    results["trace_500"]  = bench_trace_overhead(500)

    # ── Benchmark 5: Audit ──
    results["audit_100"] = bench_audit(100)
    results["audit_500"] = bench_audit(500)

    # ── Benchmark 6: Snapshot ──
    results["snapshot_100"] = bench_snapshot(100)
    results["snapshot_500"] = bench_snapshot(500)

    # ── Benchmark 7: Incremental ──
    results["incremental_100"]  = bench_incremental(100)
    results["incremental_500"]  = bench_incremental(500)
    results["incremental_1000"] = bench_incremental(1000)

    # ── Benchmark 8: Cost template ──
    results["cost_50b_10g"] = bench_cost_analysis(50, 10)
    results["cost_100b_20g"] = bench_cost_analysis(100, 20)

    # ── Summary ──
    print("\n")
    print("=" * 70)
    print("📊 PERFORMANCE SUMMARY")
    print("=" * 70)

    print("\n┌─────────────────────────────────────────────────────────────────────────────┐")
    print("│  1. SINGLE ENGINE STRESS                                                    │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    for k in ["single_100", "single_500", "single_1000"]:
        r = results.get(k)
        if r:
            print(f"│  {r['formula_count']:>5} formulas → eval {r['eval_avg_ms']:>8.2f}ms avg, "
                  f"{fmt(r['nodes_per_sec']):>10} nodes/sec, depth={r['dag_depth']}")

    print("│                                                                             │")
    print("│  2. MULTI-BOM (Sequential)                                                  │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    for k in ["multi_10x100", "multi_100x50", "multi_100x100", "multi_1000x100"]:
        r = results.get(k)
        if r:
            print(f"│  {r['n_products']:>4} products × {r['total_formulas']//max(1,r['n_products']):>4} f/ea → "
                  f"eval {r['eval_total_ms']:>8.2f}ms, {fmt(r['products_per_sec']):>8} prod/sec")

    print("│                                                                             │")
    print("│  3. BATCH vs LOOP                                                           │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    for k in ["batch_100x50", "batch_1000x50"]:
        r = results.get(k)
        if r:
            print(f"│  {r['n_rows']:>4} rows × {r['formula_count']:>3} formulas → "
                  f"loop {r['loop_avg_ms']:>8.2f}ms, batch {r['batch_avg_ms']:>8.2f}ms, "
                  f"speedup {r['speedup']:>5.1f}x")

    print("│                                                                             │")
    print("│  4. TRACE OVERHEAD                                                          │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    for k in ["trace_100", "trace_500"]:
        r = results.get(k)
        if r:
            print(f"│  {r.get('formula_count', '?'):>5} formulas → no-trace {r['no_trace_avg_ms']:>8.2f}ms, "
                  f"trace {r['trace_avg_ms']:>8.2f}ms, overhead {r['overhead_pct']:>5.1f}%")

    print("│                                                                             │")
    print("│  5. AUDIT OVERHEAD                                                          │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    for k in ["audit_100", "audit_500"]:
        r = results.get(k)
        if r:
            print(f"│  {r.get('formula_count', '?'):>5} formulas → no-audit {r['no_audit_avg_ms']:>8.2f}ms, "
                  f"audit {r['audit_avg_ms']:>8.2f}ms, overhead {r['overhead_pct']:>5.1f}%")

    print("│                                                                             │")
    print("│  6. SNAPSHOT COST                                                           │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    for k in ["snapshot_100", "snapshot_500"]:
        r = results.get(k)
        if r:
            print(f"│  {r.get('formula_count', '?'):>5} formulas → eval {r['eval_avg_ms']:>8.2f}ms, "
                  f"+snapshot {r['snapshot_avg_ms']:>8.2f}ms, cost {r['snapshot_cost_ms']:>8.2f}ms (+{r['overhead_pct']:.0f}%)")

    print("│                                                                             │")
    print("│  7. INCREMENTAL SPEEDUP                                                     │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    for k in ["incremental_100", "incremental_500", "incremental_1000"]:
        r = results.get(k)
        if r:
            print(f"│  {r.get('formula_count', '?'):>5} formulas → full {r['full_avg_ms']:>8.2f}ms, "
                  f"incr {r['incremental_avg_ms']:>8.2f}ms, speedup {r['speedup']:>5.1f}x")

    print("│                                                                             │")
    print("│  8. COST TEMPLATE ANALYSIS                                                  │")
    print("├─────────────────────────────────────────────────────────────────────────────┤")
    for k in ["cost_50b_10g", "cost_100b_20g"]:
        r = results.get(k)
        if r:
            print(f"│  {r['n_buckets']:>3} buckets + {r['n_groups']:>3} groups = {r['total_formulas']:>4} formulas → "
                  f"eval {r['eval_avg_ms']:>8.2f}ms")

    print("└─────────────────────────────────────────────────────────────────────────────┘")

    # ── Export results for report ──
    output_path = os.path.join(os.path.dirname(__file__), "..", "benchmark_results_v31.json")
    # Clean results for JSON (remove objects)
    clean_results = {}
    for k, v in results.items():
        if isinstance(v, dict):
            clean_results[k] = {
                kk: vv for kk, vv in v.items()
                if isinstance(vv, (int, float, str, bool, type(None)))
            }
    with open(output_path, "w") as f:
        json.dump(clean_results, f, indent=2, default=str)
    print(f"\n📁 Results saved to: {output_path}")

    return results

if __name__ == "__main__":
    main()
