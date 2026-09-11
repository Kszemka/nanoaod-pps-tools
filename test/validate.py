#!/usr/bin/env python3
"""
Correctness checks that must pass before any timing number is worth reading.

1. All implementations of a given test produce the same control values.
2. TEST 2's per-filter counts agree between the eager, Report() and Python paths.
3. The generated C++ assignRegion() agrees with diamond_geometry.assign_region() on a dense
   grid. Checked as part of TEST 3, the only test that uses the geometry at all: this is the
   only thing standing between a silent transcription bug and plausible-looking but wrong
   efficiency numbers.
"""

import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TEST_DIR)
for path in (TEST_DIR, REPO_ROOT, os.path.join(REPO_ROOT, "corrections-examples")):
    if path not in sys.path:
        sys.path.insert(0, path)

import ROOT  # noqa: E402

ROOT.gROOT.SetBatch(True)

import app.diamond_geometry as diamond_geometry  # noqa: E402
import bench_common as bc  # noqa: E402

TOLERANCE = 1e-6


def check_geometry(n_points=100000, seed=1, scalar_sample=2000):
    """
    Compares the generated C++ assignRegion() with diamond_geometry.assign_region().

    The C++ side is called once per (pot, arm) on the whole point array rather than once per
    point: the cppyy call overhead dwarfs the handful of arithmetic operations inside, and
    per-point calls made this check take minutes instead of a fraction of a second.

    The Python reference is vectorised the same way, so a subsample is additionally compared
    against the original scalar assign_region() -- otherwise a bug shared by both vectorised
    versions could pass unnoticed.
    """
    print("== TEST 3 geometry: generated C++ vs Python ==")
    rng = np.random.default_rng(seed)
    xs = rng.uniform(-10.0, 30.0, n_points)
    ys = rng.uniform(-15.0, 25.0, n_points)

    ok = True
    for pot_type in ("box", "cyl"):
        for arm_key in ("45", "56"):
            func_name = f"validateRegion_{pot_type}_{arm_key}"
            bulk_name = f"{func_name}_bulk"
            ROOT.gInterpreter.Declare(
                diamond_geometry.get_cpp_source(arm_key, pot_type, func_name)
                + f"""
ROOT::RVec<int> {bulk_name}(const ROOT::RVec<double>& xs, const ROOT::RVec<double>& ys) {{
    ROOT::RVec<int> out(xs.size());
    for (std::size_t i = 0; i < xs.size(); ++i) out[i] = {func_name}(xs[i], ys[i]);
    return out;
}}
"""
            )
            cpp_regions = np.asarray(
                getattr(ROOT, bulk_name)(ROOT.VecOps.AsRVec(xs), ROOT.VecOps.AsRVec(ys))
            )
            py_regions = _assign_region_vectorised(xs, ys, arm_key, pot_type)

            mismatches = int(np.count_nonzero(cpp_regions != py_regions))
            scalar_bad = sum(
                1
                for i in range(0, n_points, max(n_points // scalar_sample, 1))
                if py_regions[i]
                != diamond_geometry.assign_region(xs[i], ys[i], arm_key, pot_type)
            )
            status = "OK" if mismatches == 0 and scalar_bad == 0 else "MISMATCH"
            print(
                f"  {pot_type} arm{arm_key}: {mismatches}/{n_points} vs C++, "
                f"{scalar_bad} vs scalar Python -> {status}"
            )
            ok = ok and mismatches == 0 and scalar_bad == 0
    return ok


def _assign_region_vectorised(xs, ys, arm_key, pot_type):
    """NumPy transcription of diamond_geometry.assign_region, for the whole array at once."""
    config = diamond_geometry.POT_CONFIG[pot_type]
    center_x, center_y = config["centers"][arm_key]
    theta = math.radians(config["angles_deg"][arm_key])
    cos_theta, sin_theta = math.cos(theta), math.sin(theta)
    n_regions = config["n_regions"]
    size_x = diamond_geometry.DIAMOND_SIZE_X
    half_y = diamond_geometry.DIAMOND_SIZE_Y / 2

    dx, dy = xs - center_x, ys - center_y
    u = dx * cos_theta + dy * sin_theta
    v = -dx * sin_theta + dy * cos_theta

    edges = np.array([-n_regions * size_x / 2 + i * size_x for i in range(n_regions + 1)])
    # side="left" minus one reproduces assign_region's inclusive-on-both-ends bins: a u landing
    # exactly on an internal edge falls into the lower region, as the scalar loop does.
    region = np.searchsorted(edges, u, side="left") - 1
    region = np.where(u == edges[0], 0, region)

    inside = (v >= -half_y) & (v <= half_y) & (region >= 0) & (region < n_regions)
    return np.where(inside, region, -1)


def run_bench(script, *args):
    result = subprocess.run(
        [sys.executable, os.path.join(TEST_DIR, script), *args],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("BENCH "):
            return json.loads(line[6:])
    raise RuntimeError(f"{script} {' '.join(args)} produced no record:\n{result.stderr[-2000:]}")


def close(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= TOLERANCE * max(1.0, abs(a), abs(b))
    return a == b


def compare(name, records):
    reference_impl, reference = records[0]
    ok = True
    print(f"== {name} ==")
    print(f"  {reference_impl:22s} {json.dumps(reference)}")
    for impl, checksums in records[1:]:
        shared = set(reference) & set(checksums)
        matches = all(close(reference[k], checksums[k]) for k in shared)
        ok = ok and matches
        print(f"  {impl:22s} {json.dumps(checksums)} -> {'OK' if matches else 'MISMATCH'}")
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=os.path.join(REPO_ROOT, "examples", "test.root"))
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--grid-points", type=int, default=100000)
    parser.add_argument(
        "--threads",
        type=int,
        default=0,
        help="also check that the compiled kernel gives identical results on N threads",
    )
    args = parser.parse_args()

    common = ["--input", args.input]
    if args.max_events:
        # Range() and ImplicitMT are mutually exclusive, so the threaded check needs the
        # whole file.
        common += ["--max-events", str(args.max_events)]

    ok = compare(
        "TEST 1 -- single filter",
        [
            ("rdf", run_bench("bench_filter.py", *common, "--impl", "rdf")["checksums"]),
            (
                "rdf/callable",
                run_bench("bench_filter.py", *common, "--impl", "rdf",
                          "--filter-style", "callable")["checksums"],
            ),
            (
                "python/vector",
                run_bench("bench_filter.py", *common, "--impl", "python", "--mode", "vector")["checksums"],
            ),
            (
                "python/loop",
                run_bench("bench_filter.py", *common, "--impl", "python", "--mode", "loop")["checksums"],
            ),
            ("uproot", run_bench("bench_filter.py", *common, "--impl", "uproot")["checksums"]),
        ],
    )

    for chain_len in range(1, bc.MAX_CHAIN_LEN + 1):
        records = []
        for impl in ("rdf-eager", "rdf-report", "python", "uproot", "rdf-lazy"):
            record = run_bench(
                "bench_chain.py", *common, "--impl", impl, "--chain-len", str(chain_len)
            )
            checksums = dict(record["checksums"])
            # rdf-lazy deliberately does not collect per-filter counts -- that is precisely what
            # it trades away for a single event loop -- so it is compared on the final count only.
            if checksums.get("intermediate") is None:
                checksums.pop("intermediate", None)
            records.append((f"{impl} [{record['event_loops']} loops]", checksums))
        ok &= compare(f"TEST 2 -- chain-len {chain_len}", records)

    # Short-circuiting changes how much work is done per step, never the outcome, so the
    # intermediate counts are allowed to differ while the final count must not.
    shortcircuit = []
    for impl in ("python", "uproot"):
        for mode in ("vector", "vector-shortcircuit"):
            record = run_bench("bench_chain.py", *common, "--impl", impl, "--mode", mode,
                               "--chain-len", str(bc.MAX_CHAIN_LEN))
            shortcircuit.append(
                (f"{impl}/{mode}", {"events_passed": record["checksums"]["events_passed"]})
            )
    ok &= compare("TEST 2 -- short-circuiting must not change the answer", shortcircuit)

    # Filter order is the user's choice, and the predicates are an AND, so every order has to
    # end on the same count. This is what licenses reading the ordering experiment as a pure
    # cost difference rather than as two different queries.
    ordering = []
    for order in sorted(bc.CHAIN_ORDERS):
        record = run_bench("bench_chain.py", *common, "--impl", "rdf-lazy",
                           "--chain-len", str(bc.MAX_CHAIN_LEN), "--chain-order", order)
        ordering.append((f"rdf-lazy/{order}", {"events_passed": record["checksums"]["events_passed"]}))
    ok &= compare("TEST 2 -- filter order must not change the answer", ordering)

    # Geometry first within TEST 3: if the transcription is wrong, the implementations below can
    # still agree with each other perfectly and all be wrong together.
    ok &= check_geometry(args.grid_points)

    ok &= compare(
        "TEST 3 -- per-track efficiency",
        [
            ("jit", run_bench("bench_efficiency.py", *common, "--impl", "jit")["checksums"]),
            (
                "correctionlib",
                run_bench("bench_efficiency.py", *common, "--impl", "correctionlib")["checksums"],
            ),
            (
                "python/vector",
                run_bench("bench_efficiency.py", *common, "--impl", "python", "--mode", "vector")["checksums"],
            ),
            (
                "python/loop",
                run_bench("bench_efficiency.py", *common, "--impl", "python", "--mode", "loop")["checksums"],
            ),
            (
                "uproot",
                run_bench("bench_efficiency.py", *common, "--impl", "uproot")["checksums"],
            ),
        ],
    )

    if args.threads > 1:
        if args.max_events:
            print("\n== thread safety: skipped (--max-events forces a single thread) ==")
        else:
            # The JIT kernel is stateless by construction; this is what proves it stayed that
            # way. A race here would show up as a small, run-dependent drift in eff_sum.
            ok &= compare(
                f"TEST 3 -- thread safety (1 vs {args.threads} threads)",
                [
                    (
                        "jit / 1 thread",
                        run_bench("bench_efficiency.py", *common, "--impl", "jit")["checksums"],
                    ),
                    (
                        f"jit / {args.threads} threads",
                        run_bench(
                            "bench_efficiency.py", *common, "--impl", "jit",
                            "--threads", str(args.threads),
                        )["checksums"],
                    ),
                ],
            )

    print("\nRESULT:", "all checks passed" if ok else "FAILURES -- do not trust the timings")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
