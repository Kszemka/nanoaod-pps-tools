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
import os
import random
import subprocess
import sys

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


def check_geometry(n_points=100000, seed=1):
    print("== TEST 3 geometry: generated C++ vs Python ==")
    ok = True
    for pot_type in ("box", "cyl"):
        for arm_key in ("45", "56"):
            func_name = f"validateRegion_{pot_type}_{arm_key}"
            ROOT.gInterpreter.Declare(
                diamond_geometry.get_cpp_source(arm_key, pot_type, func_name)
            )
            cpp = getattr(ROOT, func_name)
            random.seed(seed)
            mismatches = 0
            for _ in range(n_points):
                x = random.uniform(-10.0, 30.0)
                y = random.uniform(-15.0, 25.0)
                if cpp(x, y) != diamond_geometry.assign_region(x, y, arm_key, pot_type):
                    mismatches += 1
            status = "OK" if mismatches == 0 else "MISMATCH"
            print(f"  {pot_type} arm{arm_key}: {mismatches}/{n_points} -> {status}")
            ok = ok and mismatches == 0
    return ok


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
    args = parser.parse_args()

    common = ["--input", args.input]
    if args.max_events:
        common += ["--max-events", str(args.max_events)]

    ok = compare(
        "TEST 1 -- single filter",
        [
            ("rdf", run_bench("bench_filter.py", *common, "--impl", "rdf")["checksums"]),
            (
                "python/vector",
                run_bench("bench_filter.py", *common, "--impl", "python", "--mode", "vector")["checksums"],
            ),
            (
                "python/loop",
                run_bench("bench_filter.py", *common, "--impl", "python", "--mode", "loop")["checksums"],
            ),
        ],
    )

    for chain_len in range(1, bc.MAX_CHAIN_LEN + 1):
        records = []
        for impl in ("rdf-eager", "rdf-report", "python", "rdf-lazy"):
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
        ],
    )

    print("\nRESULT:", "all checks passed" if ok else "FAILURES -- do not trust the timings")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
