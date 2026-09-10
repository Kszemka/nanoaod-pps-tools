#!/usr/bin/env python3
"""
Shared plumbing for the three benchmarks: argument parsing, phase timing, memory and I/O
counters, and the JSON record written to stdout for run_benchmark.sh to collect.

Timing is split into `setup` and `loop` phases because the setup cost (opening the file, cling
JIT-compiling the kernel) is a fixed ~seconds that does not grow with the dataset. Folding it
into one number makes the compiled path look artificially bad on small inputs.
"""

import argparse
import json
import os
import resource
import sys
import time
from contextlib import contextmanager

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (REPO_ROOT, os.path.join(REPO_ROOT, "corrections-examples")):
    if path not in sys.path:
        sys.path.insert(0, path)

import ROOT  # noqa: E402

ROOT.gROOT.SetBatch(True)
ROOT.gErrorIgnoreLevel = ROOT.kWarning

DEFAULT_RP_ID = 22
DEFAULT_ARM = "45"
DEFAULT_POT = "box"

# Filter chain for TEST 2, in order -- the notebook's rdata_analysis() chain, with its
# nPPSLocalTrack > 0 baseline as an explicit first step so --chain-len sweeps the whole thing.
#
# Steps 1-3 and 5 each introduce a new branch; step 4 deliberately does not (it reuses
# decRPId), which is what makes the bytes-read curve flatten there instead of growing with
# every filter.
CHAIN_STEPS = ["pps", "double_arm", "diamond", "rp_id", "xi"]
CHAIN_COLUMNS = {
    "pps": "nPPSLocalTrack",
    "double_arm": "PPSLocalTrack_decRPId",
    "diamond": "PPSLocalTrack_rpType",
    "rp_id": "PPSLocalTrack_decRPId",
    "xi": "Proton_singleRP_xi",
}
MAX_CHAIN_LEN = len(CHAIN_STEPS)
ARM_LEFT_RPS = (23, 123)
ARM_RIGHT_RPS = (3, 103)
DIAMOND_RP_TYPE = 5
XI_RANGE = (0.05, 0.1)


def chain_columns(chain_len):
    """Distinct branches the first `chain_len` steps need, in first-use order."""
    columns = []
    for name in CHAIN_STEPS[:chain_len]:
        column = CHAIN_COLUMNS[name]
        if column not in columns:
            columns.append(column)
    return columns



def build_parser(description, impls):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input", required=True, help="benchmark .root file")
    parser.add_argument("--impl", required=True, choices=impls)
    parser.add_argument("--mode", default="vector", choices=["vector", "loop"])
    parser.add_argument("--threads", type=int, default=0, help="0 disables ImplicitMT")
    parser.add_argument("--rp-id", type=int, default=DEFAULT_RP_ID)
    parser.add_argument("--arm", default=DEFAULT_ARM)
    parser.add_argument("--pot-type", default=DEFAULT_POT, choices=["box", "cyl"])
    parser.add_argument("--max-events", type=int, default=0, help="0 uses the whole file")
    parser.add_argument("--tag", default="", help="free-form label copied into the output record")
    return parser


def setup_root(threads):
    if threads and threads > 0:
        ROOT.EnableImplicitMT(threads)
    return threads or 1


def warmup(args, build_and_trigger, tree="Events"):
    """
    Runs the same graph over a single entry so cling compiles the filter expressions and the
    efficiency kernel before the timed phase starts.

    Without this, the compiled path pays a fixed few seconds of JIT inside the measured loop and
    looks slower than it is -- a cost that a real analysis pays once, not once per event.
    Must run before EnableImplicitMT: Range() is not supported under implicit multi-threading.
    """
    build_and_trigger(ROOT.RDataFrame(tree, args.input).Range(1))


def make_dataframe(args, tree="Events"):
    df = ROOT.RDataFrame(tree, args.input)
    if args.max_events:
        df = df.Range(args.max_events)
    return df


def resolve_threads(args):
    """Range() and ImplicitMT are mutually exclusive, so capping events forces one thread."""
    if args.max_events and args.threads:
        args.threads = 0
    return args.threads


def build_efficiency_json(arm_key, pot_type, out_dir="/tmp"):
    """Writes the region_idx -> efficiency correctionlib JSON. Setup only, never timed."""
    from build_correction import build_diamond_efficiency_json

    efficiency_file = os.path.join(REPO_ROOT, "app", "efficiency.json")
    with open(efficiency_file) as f:
        run_number = int(next(iter(json.load(f))))
    out_path = os.path.join(out_dir, f"bench_eff_{pot_type}_{arm_key}.json")
    return build_diamond_efficiency_json(
        efficiency_file, arm_key, run_number, out_path, pot_type=pot_type
    )


def peak_rss_kb():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports kB, macOS reports bytes.
    return rss // 1024 if sys.platform == "darwin" else rss


class Bench:
    """Collects one measurement record. Use `with bench.phase("loop"):` around timed work."""

    def __init__(self, args, test_name):
        self.record = {
            "test": test_name,
            "impl": args.impl,
            "mode": args.mode,
            "threads": args.threads,
            "rp_id": args.rp_id,
            "arm": args.arm,
            "pot_type": args.pot_type,
            "max_events": args.max_events,
            "tag": args.tag,
            "input": os.path.basename(args.input),
            "machine": os.environ.get("MACHINE", "local"),
            "root_version": ROOT.gROOT.GetVersion(),
        }

    @contextmanager
    def phase(self, name):
        bytes_before = ROOT.TFile.GetFileBytesRead()
        start = time.perf_counter()
        yield
        self.record[f"wall_{name}"] = time.perf_counter() - start
        self.record[f"bytes_{name}"] = int(ROOT.TFile.GetFileBytesRead() - bytes_before)

    def finish(self, checksums, n_events=None, n_tracks=None):
        self.record["checksums"] = checksums
        self.record["n_events"] = n_events
        self.record["n_tracks"] = n_tracks
        self.record["peak_rss_kb"] = peak_rss_kb()
        self.record["bytes_total"] = int(ROOT.TFile.GetFileBytesRead())
        loop = self.record.get("wall_loop", 0.0)
        if n_events and loop > 0:
            self.record["events_per_s"] = n_events / loop
        if n_tracks and loop > 0:
            self.record["tracks_per_s"] = n_tracks / loop
        print("BENCH " + json.dumps(self.record))
        return self.record
