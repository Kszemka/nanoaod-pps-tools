#!/usr/bin/env python3
"""
Builds benchmark datasets by replicating a source NanoAOD file N times.

Uses RDataFrame.Snapshot with an explicit fAutoFlush rather than TFileMerger/hadd: hadd would
carry over the source file's clustering, leaving the TTree cluster count an accidental function
of file size. RDataFrame parallelises over clusters, not entries, so an uncontrolled cluster
count silently caps the thread-scaling sweep and produces a plateau that looks like a property
of the code but is really a property of the file.
"""

import argparse
import fcntl
import json
import os
import sys

import ROOT

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = os.path.join(REPO_ROOT, "examples", "test.root")


def merge_info(info_path, name, info):
    """Add one entry to dataset_info.json without losing a concurrent writer's.

    Generating the datasets is the long pole of the campaign, and since the files are
    independent the obvious way to shorten it is to build several at once. A plain
    read-modify-write drops entries when two of them finish close together: both read the same
    version and the later write wins. The dataset that lost its description then aborts
    run_benchmark.sh hours later, because require_dataset treats an undescribed input as fatal.

    The write itself goes through a temporary file so a reader never sees it half-finished.
    """
    with open(info_path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = {}
        if os.path.exists(info_path):
            try:
                with open(info_path) as f:
                    existing = json.load(f)
            except ValueError:
                # A file truncated by an interrupted run is worth rebuilding rather than
                # inheriting: every entry is reproducible with --describe-only.
                print(f"WARNING: {info_path} was unreadable and is being rebuilt", file=sys.stderr)
        existing[name] = info
        tmp_path = info_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(existing, f, indent=2)
        os.replace(tmp_path, info_path)


def cluster_count(tree):
    n_entries = tree.GetEntries()
    it = tree.GetClusterIterator(0)
    count, start = 0, 0
    while start < n_entries:
        count += 1
        start = it.Next()
    return count


def describe(path, tree_name="Events"):
    """Collects the dataset facts the benchmark and its verification steps depend on."""
    f = ROOT.TFile.Open(path)
    tree = f.Get(tree_name)
    branches = [
        "PPSLocalTrack_decRPId",
        "PPSLocalTrack_rpType",
        "Proton_singleRP_xi",
        "PPSLocalTrack_x",
        "PPSLocalTrack_y",
    ]
    per_branch = {}
    for name in branches:
        branch = tree.GetBranch(name)
        if branch:
            per_branch[name] = {
                "zip_bytes": int(branch.GetZipBytes()),
                "tot_bytes": int(branch.GetTotBytes()),
                # ROOT reads a whole basket at a time, so this is the granularity of every
                # read: the quantity the read-amplification result has to be explained by.
                "basket_size": int(branch.GetBasketSize()),
                "n_baskets": int(branch.GetWriteBasket()),
            }

    info = {
        "path": os.path.abspath(path),
        "tree": tree_name,
        "n_events": int(tree.GetEntries()),
        "file_size_bytes": os.path.getsize(path),
        "n_clusters": cluster_count(tree),
        "auto_flush": int(tree.GetAutoFlush()),
        "n_branches": tree.GetListOfBranches().GetEntries(),
        "tot_bytes": int(tree.GetTotBytes()),
        "zip_bytes": int(tree.GetZipBytes()),
        "compression_algorithm": int(f.GetCompressionAlgorithm()),
        "compression_level": int(f.GetCompressionLevel()),
        "root_version": ROOT.gROOT.GetVersion(),
        "branches": per_branch,
    }
    info["compression_factor"] = info["tot_bytes"] / max(info["zip_bytes"], 1)
    info["n_tracks"] = int(ROOT.RDataFrame(tree_name, path).Sum("nPPSLocalTrack").GetValue())
    f.Close()
    return info


# The branches the benchmarked queries touch. Used by --slim, which is the layout control:
# everything else in the file is dead weight that no test ever reads.
USED_BRANCHES = [
    "run",
    "luminosityBlock",
    "event",
    "nPPSLocalTrack",
    "PPSLocalTrack_decRPId",
    "PPSLocalTrack_rpType",
    "PPSLocalTrack_x",
    "PPSLocalTrack_y",
    "Proton_singleRP_xi",
]


def build(source, out_path, copies, autoflush, tree_name="Events", compression=None, slim=False):
    chain = ROOT.TChain(tree_name)
    for _ in range(copies):
        chain.Add(source)

    if compression is None:
        src = ROOT.TFile.Open(source)
        compression = (src.GetCompressionAlgorithm(), src.GetCompressionLevel())
        src.Close()

    opts = ROOT.RDF.RSnapshotOptions()
    opts.fAutoFlush = autoflush
    opts.fMode = "RECREATE"
    opts.fCompressionAlgorithm = compression[0]
    opts.fCompressionLevel = compression[1]

    # Basket size is deliberately left to ROOT. RSnapshotOptions::fBasketSize only exists from
    # ROOT 6.34 (Ares has 6.32), and measured on one copy it does the opposite of what the name
    # suggests: asking for 1 MiB baskets produced 105 kB ones against a 247 kB default, because
    # it sets the initial allocation and OptimizeBaskets then rebalances everything to fit a
    # cluster. --autoflush is the knob that actually moves basket size, which is what ds_x8 and
    # ds_x8_coarse differ in.
    columns = ""
    if slim:
        available = {str(name) for name in ROOT.RDataFrame(chain).GetColumnNames()}
        kept = [name for name in USED_BRANCHES if name in available]
        columns = "^(" + "|".join(kept) + ")$"

    # Outside --slim, all ~2000 branches are kept on purpose: TEST 2 measures how few of them
    # RDataFrame actually reads, which only means something if the unread ones are present.
    ROOT.RDataFrame(chain).Snapshot(tree_name, out_path, columns, opts)
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--out", required=True, help="output .root path")
    parser.add_argument("--copies", type=int, required=True)
    parser.add_argument(
        "--autoflush",
        type=int,
        default=25000,
        help="entries per TTree cluster; keep clusters >= 4x the max thread count",
    )
    parser.add_argument("--tree", default="Events")
    parser.add_argument(
        "--compression",
        default=None,
        help="'algorithm:level' (e.g. '5:5'); default matches the source file",
    )
    parser.add_argument(
        "--info-out",
        default=None,
        help="where to append the dataset description (default: <out dir>/dataset_info.json)",
    )
    parser.add_argument(
        "--slim",
        action="store_true",
        help="keep only the branches the benchmarked queries read, instead of all ~2000",
    )
    parser.add_argument("--describe-only", action="store_true", help="only describe --out")
    parser.add_argument(
        "--expect-settings",
        action="store_true",
        help="with --describe-only: fail if the existing file's compression or autoflush "
        "differs from --compression and --autoflush",
    )
    args = parser.parse_args()

    if not args.describe_only:
        if not os.path.exists(args.source):
            sys.exit(f"Source not found: {args.source}")
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        compression = None
        if args.compression:
            algorithm, level = args.compression.split(":")
            compression = (int(algorithm), int(level))
        print(f"Building {args.out}: {args.copies} x {args.source}, autoflush={args.autoflush}")
        # Snapshot writes straight to the destination, so a build cut short -- SLURM time
        # limit, the OOM killer, a sibling build failing under JOBS>1 -- leaves a truncated
        # file at the final path. That file passes every later existence test, so the next run
        # reuses it and the series silently gains a point with the wrong number of events.
        # Building beside the target and moving it into place makes the file appear only once
        # it is complete.
        partial_path = args.out + ".part"
        build(
            args.source,
            partial_path,
            args.copies,
            args.autoflush,
            args.tree,
            compression,
            slim=args.slim,
        )
        os.replace(partial_path, args.out)

    info = describe(args.out, args.tree)
    info["copies"] = args.copies

    print(json.dumps(info, indent=2))

    # A file that already exists is reused rather than rebuilt, which is what makes rerunning
    # this script cheap -- but it also means a path that resolves to a differently built file
    # joins the size series carrying someone else's settings. A symlink to an earlier dataset
    # is the easy way to do that by accident, and it passes every `-f` test.
    #
    # Checked up front because the alternative is finding out from the consistency report
    # hours later, after the whole generation job has run.
    if args.expect_settings:
        # Otherwise the buffered description lands after the unbuffered error in a redirected
        # log, which is the only place anyone will read this from.
        sys.stdout.flush()
        problems = []
        if args.compression:
            algorithm, level = (int(part) for part in args.compression.split(":"))
            actual = (info.get("compression_algorithm"), info.get("compression_level"))
            if actual != (algorithm, level):
                problems.append(f"compression {actual[0]}:{actual[1]}, expected {algorithm}:{level}")
        if info.get("auto_flush") != args.autoflush:
            problems.append(f"autoflush {info.get('auto_flush')}, expected {args.autoflush}")
        if problems:
            target = os.path.realpath(args.out)
            print(f"\nERROR: {args.out} does not match the series settings:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            if target != os.path.abspath(args.out):
                print(f"  (it is a symlink to {target})", file=sys.stderr)
            print(
                "Decompression happens inside the measured event loop and clustering sets the\n"
                "parallelism, so a series mixing these is not a comparable plot. Delete this\n"
                "file and let the script rebuild it.",
                file=sys.stderr,
            )
            sys.exit(1)

    threads_supported = info["n_clusters"] // 4
    print(f"\n-> {info['n_clusters']} clusters: thread sweep is meaningful up to ~{threads_supported}")
    if threads_supported < 48:
        print("   WARNING: fewer than 4 clusters per thread at 48 threads. Lower --autoflush.")

    if os.path.exists(args.source):
        overhead = info["file_size_bytes"] / (os.path.getsize(args.source) * max(args.copies, 1))
        print(f"-> size vs {args.copies}x source: {overhead:.2f}x (smaller clusters compress worse)")

    info_path = args.info_out or os.path.join(os.path.dirname(os.path.abspath(args.out)), "dataset_info.json")
    merge_info(info_path, os.path.basename(args.out), info)
    print(f"-> dataset info written to {info_path}")


if __name__ == "__main__":
    main()
