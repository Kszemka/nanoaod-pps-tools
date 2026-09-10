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
import json
import os
import sys

import ROOT

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCE = os.path.join(REPO_ROOT, "examples", "test.root")


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
        "root_version": ROOT.gROOT.GetVersion(),
        "branches": per_branch,
    }
    info["compression_factor"] = info["tot_bytes"] / max(info["zip_bytes"], 1)
    info["n_tracks"] = int(ROOT.RDataFrame(tree_name, path).Sum("nPPSLocalTrack").GetValue())
    f.Close()
    return info


def build(source, out_path, copies, autoflush, tree_name="Events", compression=None):
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

    # All ~2000 branches are kept on purpose: TEST 2 measures how few of them RDataFrame
    # actually reads, which only means something if the unread ones are present.
    ROOT.RDataFrame(chain).Snapshot(tree_name, out_path, "", opts)
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
    parser.add_argument("--describe-only", action="store_true", help="only describe --out")
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
        build(args.source, args.out, args.copies, args.autoflush, args.tree, compression)

    info = describe(args.out, args.tree)
    info["copies"] = args.copies

    print(json.dumps(info, indent=2))

    threads_supported = info["n_clusters"] // 4
    print(f"\n-> {info['n_clusters']} clusters: thread sweep is meaningful up to ~{threads_supported}")
    if threads_supported < 48:
        print("   WARNING: fewer than 4 clusters per thread at 48 threads. Lower --autoflush.")

    if os.path.exists(args.source):
        overhead = info["file_size_bytes"] / (os.path.getsize(args.source) * max(args.copies, 1))
        print(f"-> size vs {args.copies}x source: {overhead:.2f}x (smaller clusters compress worse)")

    info_path = args.info_out or os.path.join(os.path.dirname(os.path.abspath(args.out)), "dataset_info.json")
    existing = {}
    if os.path.exists(info_path):
        with open(info_path) as f:
            existing = json.load(f)
    existing[os.path.basename(args.out)] = info
    with open(info_path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"-> dataset info written to {info_path}")


if __name__ == "__main__":
    main()
