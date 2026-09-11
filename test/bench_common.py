#!/usr/bin/env python3
"""
Shared plumbing for the benchmarks: argument parsing, phase timing, memory and I/O counters,
and the JSON record written to stdout for run_benchmark.sh to collect.

Timing is split into four phases, not two, because the costs behave completely differently with
dataset size:

  setup  - opening the file, reading TTree metadata, building the correction JSON
  warmup - a throwaway pass over one entry, which is where cling compiles the kernel
  jit    - building the computation graph
  loop   - triggering it; the only phase that scales with the number of events

The split is not cosmetic. Under the old two-phase version, `rdf-report` minus `rdf-lazy` was
+1.073, +1.089, +1.085, +1.088, +1.088 s across chain lengths 1..5 -- a constant, independent
of both event count and bytes read, that the record attributed to the event loop. With the
phases separated, that cost appears in `wall_jit` (0.343 s locally) and the two implementations'
event loops come out equal (0.299 s against 0.280 s), which is a different conclusion about
`Report()` than the one the numbers previously supported.
"""

import argparse
import json
import os
import resource
import sys
import threading
import time
from contextlib import contextmanager

# Bumped whenever a field changes meaning rather than just being added. Records from different
# versions must not be averaged together, and results get merged across two machines.
#
# 2: n_events in TEST 3 became the whole-tree entry count (count_events) rather than the count
#    after the rp_id filter, which moves events_per_s by the filter's selectivity; the phase
#    split above also redistributes time between wall_setup and wall_loop.
SCHEMA_VERSION = 2

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

# RDataFrame evaluates filters in the order they were declared and never reorders them, so the
# order is the user's decision and it costs something. `selective-first` puts the step that cuts
# hardest (diamond: 276737 -> 75275 events) in front, so the three remaining predicates run on
# roughly a quarter of the events. The predicates are an AND, so every order gives the same
# final count -- which is what makes this a fair comparison, and what validate.py checks.
#
# Only meaningful at full length: a truncated chain in a different order is a different query.
CHAIN_ORDERS = {
    "notebook": CHAIN_STEPS,
    "selective-first": ["diamond", "rp_id", "xi", "double_arm", "pps"],
}


def chain_steps(chain_len, order="notebook"):
    """The first `chain_len` steps of the requested ordering."""
    return CHAIN_ORDERS[order][:chain_len]


def chain_columns(chain_len, order="notebook"):
    """Distinct branches the first `chain_len` steps need, in first-use order."""
    columns = []
    for name in chain_steps(chain_len, order):
        column = CHAIN_COLUMNS[name]
        if column not in columns:
            columns.append(column)
    return columns


def branch_zip_bytes(path, columns, tree="Events"):
    """
    Compressed size on disk of exactly the branches a query names.

    This is the denominator of `read_amplification`: what the query would read if ROOT read
    only what it was asked for. Anything above 1.0 is basket granularity, TTreeCache read-ahead
    or re-reads. Measured on the source NanoAOD it is 1.04 -- essentially nothing -- while on a
    Snapshot-built copy it reached ~560, which is what makes "the chain reads 2.2% of the file"
    a statement about the generated file rather than about RDataFrame.
    """
    if not columns:
        return None
    f = ROOT.TFile.Open(path)
    if not f or f.IsZombie():
        return None
    try:
        obj = f.Get(tree)
        # An RNTuple file returns an RNTuple here, which has no branches and no per-field size
        # in an API stable across 6.32 and later. Returning None omits read_amplification for
        # that format rather than inventing a denominator; the RNTuple and TTree datasets hold
        # the same events, so their bytes_loop can still be compared directly.
        if not obj or not hasattr(obj, "GetBranch"):
            return None
        total = 0
        for name in columns:
            branch = obj.GetBranch(name)
            if branch:
                total += int(branch.GetZipBytes())
        return total or None
    finally:
        f.Close()


def drop_page_cache(path):
    """
    Evicts a file from the page cache so the next read comes from storage.

    Replaces the old "read the same warm file three times" probe, which measured 0.901, 0.894
    and 0.936 s -- i.e. nothing. posix_fadvise is Linux-only; elsewhere this is a no-op and
    says so in the record, rather than letting the caller believe the cache was cold.
    """
    if not hasattr(os, "posix_fadvise"):
        return False
    fd = os.open(path, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    finally:
        os.close(fd)
    return True


def build_parser(description, impls):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input", required=True, help="benchmark .root file")
    parser.add_argument("--impl", required=True, choices=impls)
    parser.add_argument(
        "--mode",
        default="vector",
        choices=["vector", "vector-shortcircuit", "loop"],
        help="vector-shortcircuit narrows to surviving events between chain steps, which is "
             "what RDataFrame does; plain vector evaluates every step on every event",
    )
    parser.add_argument("--threads", type=int, default=0, help="0 disables ImplicitMT")
    parser.add_argument("--rp-id", type=int, default=DEFAULT_RP_ID)
    parser.add_argument("--arm", default=DEFAULT_ARM)
    parser.add_argument("--pot-type", default=DEFAULT_POT, choices=["box", "cyl"])
    parser.add_argument("--max-events", type=int, default=0, help="0 uses the whole file")
    parser.add_argument("--tag", default="", help="free-form label copied into the output record")
    parser.add_argument(
        "--warmup-input",
        default=None,
        help="file used for the cling warmup pass (default: examples/test.root). Every dataset "
             "is a copy of that file, so the schema is identical and warming up on the small "
             "one avoids opening a multi-GB file to process a single entry",
    )
    parser.add_argument(
        "--filter-style",
        default="jit",
        choices=["jit", "callable"],
        help="jit: the whole predicate is a Filter() string for cling to compile. callable: "
             "the body lives in a pre-declared function, leaving a one-line call",
    )
    parser.add_argument(
        "--chain-order",
        default="notebook",
        choices=sorted(CHAIN_ORDERS),
        help="filter order; RDataFrame never reorders predicates itself",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="evict the input from the page cache first (Linux only)",
    )
    parser.add_argument(
        "--tree-cache",
        default="default",
        choices=["default", "off"],
        help="off disables TTreeCache, separating basket granularity from the cache's "
             "read-ahead as an explanation for the read amplification",
    )
    parser.add_argument(
        "--format",
        default="ttree",
        choices=["ttree", "rntuple"],
        help="rntuple reads the input through RDF.FromRNTuple. Baskets, clusters and "
             "TTreeCache are TTree concepts, so every bytes-read result here is partly a "
             "result about the format rather than about RDataFrame",
    )
    return parser


def setup_root(threads):
    if threads and threads > 0:
        ROOT.EnableImplicitMT(threads)
    return threads or 1


def apply_tree_cache(args):
    """`--tree-cache off` turns TTreeCache off process-wide, before any file is opened."""
    if args.tree_cache == "off":
        ROOT.gEnv.SetValue("TTreeCache.Size", 0.0)
        return False
    return True


def warmup_input(args):
    """
    The warmup only has to make cling compile; it does not care which file it reads.

    Every dataset is a Snapshot of the same source, so the schema is identical and warming up
    on the 240 MB source instead of the measured file avoids opening a multi-GB file to process
    a single entry.
    """
    default = os.path.join(REPO_ROOT, "examples", "test.root")
    chosen = args.warmup_input or default
    return chosen if os.path.exists(chosen) else args.input


def warmup(args, build_and_trigger, tree="Events"):
    """
    Runs the same graph over a single entry so cling compiles the filter expressions and the
    efficiency kernel before the timed phase starts.

    Without this, the compiled path pays a fixed few seconds of JIT inside the measured loop and
    looks slower than it is -- a cost that a real analysis pays once, not once per event.
    Must run before EnableImplicitMT: Range() is not supported under implicit multi-threading.
    """
    build_and_trigger(ROOT.RDataFrame(tree, warmup_input(args)).Range(1))


def from_rntuple(name, path):
    """RDataFrame over an RNTuple, under whichever namespace this ROOT release keeps it in."""
    for holder in (ROOT.RDF, getattr(ROOT.RDF, "Experimental", None)):
        factory = getattr(holder, "FromRNTuple", None)
        if factory is not None:
            return factory(name, path)
    sys.exit(f"ROOT {ROOT.gROOT.GetVersion()} cannot make an RDataFrame from an RNTuple")


def count_events(args, tree="Events"):
    """
    Entry count straight from the file's metadata.

    A Count() action would be an entire event loop -- on a 14 M event file that was ~150 s per
    run, spent purely on bookkeeping and charged to the setup phase.
    """
    if getattr(args, "format", "ttree") == "rntuple":
        total = int(from_rntuple(tree, args.input).Count().GetValue())
    else:
        f = ROOT.TFile.Open(args.input)
        total = int(f.Get(tree).GetEntries())
        f.Close()
    return min(total, args.max_events) if args.max_events else total


def make_dataframe(args, tree="Events"):
    if getattr(args, "format", "ttree") == "rntuple":
        df = from_rntuple(tree, args.input)
    else:
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


_PAGE_KB = os.sysconf("SC_PAGE_SIZE") // 1024 if hasattr(os, "sysconf") else 4


def current_rss_kb():
    """
    Resident set size right now, not the peak.

    /proc/self/statm is the only portable-enough source for the *current* value; getrusage
    reports the high-water mark, so a trace built from it can only ever go up. That is the
    fallback off Linux, and the record flags which one was used -- the cluster, where the
    memory result actually matters, is Linux.
    """
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * _PAGE_KB
    except OSError:
        return peak_rss_kb()


def start_rss_trace(interval=0.1):
    """
    Samples this process's RSS into $RSS_TRACE, tagged with the phase it was taken in.

    Sampled from inside the measured process rather than by the runner: the runner launches the
    benchmark behind `timeout` and `/usr/bin/time`, so the pid it could see was the wrapper's.
    Every one of the ~140 traces collected that way is a flat line at the 1.1 MB resident size
    of `timeout` itself. Sampling in-process removes the wrapper problem, and there is no pid
    left to get wrong.
    """
    path = os.environ.get("RSS_TRACE")
    if not path:
        return None

    handle = open(path, "w", buffering=1)
    handle.write("t_s,rss_kb,phase\n")
    state = {"phase": "start"}
    start = time.perf_counter()

    def sample():
        while True:
            handle.write(
                f"{time.perf_counter() - start:.3f},{current_rss_kb()},{state['phase']}\n"
            )
            time.sleep(interval)

    threading.Thread(target=sample, daemon=True).start()
    return state


class Bench:
    """Collects one measurement record. Use `with bench.phase("loop"):` around timed work."""

    def __init__(self, args, test_name):
        self.args = args
        self._trace = start_rss_trace(float(os.environ.get("SAMPLE_INTERVAL", 0.1)))
        self.record = {
            "schema_version": SCHEMA_VERSION,
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
            "filter_style": getattr(args, "filter_style", "jit"),
            "chain_order": getattr(args, "chain_order", "notebook"),
            "tree_cache": getattr(args, "tree_cache", "default"),
            "format": getattr(args, "format", "ttree"),
            # Everything resident before any measurement started: the interpreter, PyROOT and
            # numpy. On the 240 MB file this was ~470 MB of a 474-1000 MB peak, which is why
            # peak RSS on its own could not separate a streaming implementation from a
            # materialising one.
            "rss_baseline_kb": current_rss_kb(),
            "rss_trace_source": "statm" if os.path.exists("/proc/self/statm") else "getrusage",
        }
        if getattr(args, "no_cache", False):
            self.record["cache_dropped"] = drop_page_cache(args.input)

    @contextmanager
    def phase(self, name):
        """
        Times a phase. Re-entering the same phase accumulates rather than overwrites, because
        setup legitimately comes in two parts: what must precede the cling warmup (building the
        correction JSON) and what must follow it (EnableImplicitMT, which makes Range() -- and
        therefore the warmup -- unavailable).
        """
        if self._trace is not None:
            self._trace["phase"] = name
        bytes_before = ROOT.TFile.GetFileBytesRead()
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        read = int(ROOT.TFile.GetFileBytesRead() - bytes_before)
        self.record[f"wall_{name}"] = self.record.get(f"wall_{name}", 0.0) + elapsed
        self.record[f"bytes_{name}"] = self.record.get(f"bytes_{name}", 0) + read
        if self._trace is not None:
            self._trace["phase"] = f"after_{name}"

    def note_columns(self, columns):
        """Records which branches the query names, and their compressed size on disk."""
        self.record["columns"] = list(columns)
        self.record["columns_zip_bytes"] = branch_zip_bytes(self.args.input, columns)

    def override_bytes(self, name, value):
        """
        Replaces a phase's byte count with one reported by the implementation itself.

        Needed for the uproot path: the phase counter reads TFile::GetFileBytesRead, which only
        sees I/O that went through ROOT, so without this every uproot run claims to have read
        zero bytes and its read amplification comes out as 0.00.
        """
        self.record[f"bytes_{name}"] = int(value)
        self.record["bytes_source"] = "implementation"

    def finish(self, checksums, n_events=None, n_tracks=None):
        self.record["checksums"] = checksums
        self.record["n_events"] = n_events
        self.record["n_tracks"] = n_tracks
        self.record["peak_rss_kb"] = peak_rss_kb()
        self.record["peak_rss_net_kb"] = peak_rss_kb() - self.record["rss_baseline_kb"]
        self.record["bytes_total"] = int(ROOT.TFile.GetFileBytesRead())

        # RNTuple does not read through TFile's byte counter, so the counter reports a flat
        # zero for it. Blanking the fields keeps that out of the plots: a zero here would read
        # as "RNTuple read nothing", which is a far stronger claim than "we cannot see it".
        if self.record.get("format") == "rntuple" and not self.record.get("bytes_source"):
            for key in [k for k in self.record if k.startswith("bytes_")]:
                self.record[key] = None
            self.record["bytes_source"] = "unavailable"

        # What a real analysis pays once per process, as opposed to once per event.
        self.record["wall_fixed"] = sum(
            self.record.get(f"wall_{name}", 0.0) for name in ("setup", "warmup", "jit")
        )

        # Only meaningful over the whole file: columns_zip_bytes is the size of the entire
        # branch, so with --max-events the denominator covers entries that were never read.
        expected = self.record.get("columns_zip_bytes")
        if expected and not self.args.max_events:
            self.record["read_amplification"] = self.record.get("bytes_loop", 0) / expected

        loop = self.record.get("wall_loop", 0.0)
        if n_events and loop > 0:
            self.record["events_per_s"] = n_events / loop
        if n_tracks and loop > 0:
            self.record["tracks_per_s"] = n_tracks / loop
        print("BENCH " + json.dumps(self.record))
        return self.record
