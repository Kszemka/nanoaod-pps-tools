#!/usr/bin/env python3
"""
Why does reading four branches cost gigabytes on some files and megabytes on others?

The benchmark records `bytes_loop` from TFile::GetFileBytesRead, which says how much was read
but nothing about why. The measurements it produced do not have a single explanation:

  examples/test.root   346 k events   chain-len 5 reads    5.4 MB   (1.04x the branches' size)
  ds_x1 / ds_x8        same content   chain-len 5 reads  8-45 MB    (1.03x)
  ds_m  (2.8 M events) 1.94 GB        chain-len 5 reads   44.9 MB   (no amplification)
  ds_l  (10.9 M)       ~10 GB         chain-len *1* reads 10.2 GB   (the whole file)

and on ds_l it got worse with more threads -- 10.2 GB at 1 thread, 13.6 at 2, 20.4 at 4 -- which
rules out the file layout on its own, because the layout does not change between those runs.

This script attaches a TTreePerfStats to a plain TTree read of exactly the branches a query
needs, which reports what GetFileBytesRead cannot: the number of read calls, how many bytes
were read *beyond* what was asked for, and whether TTreeCache was able to hold a cluster. The
cache-size sweep is the discriminator:

  - if bytes read collapse once the cache is large enough to hold one cluster, the cause is a
    cluster that does not fit the default 30 MB cache, so ROOT reads baskets one at a time and
    the OS read-ahead drags in the neighbouring branches
  - if they do not move with cache size, the cause is basket granularity and the cache is
    irrelevant

Usage:
    python test/diag_io.py --input data/ds_l.root --cache-mb 0 30 128 512
"""

import argparse
import json
import os

import bench_common as bc
import ROOT


def cluster_bytes(tree):
    """
    Average compressed bytes per TTree cluster.

    The quantity to compare against the TTreeCache size: a cluster is the unit ROOT wants to
    read in one go, so a cache smaller than this cannot do its job. With ~2000 branches, this
    grows with fAutoFlush much faster than intuition suggests.
    """
    n_clusters = 0
    n_entries = tree.GetEntries()
    it = tree.GetClusterIterator(0)
    start = 0
    while start < n_entries:
        n_clusters += 1
        start = it.Next()
    return int(tree.GetZipBytes()) / max(n_clusters, 1), n_clusters


def measure(path, columns, cache_bytes, entries=0, tree_name="Events"):
    """One pass over `columns` with a given TTreeCache size, instrumented."""
    f = ROOT.TFile.Open(path)
    tree = f.Get(tree_name)
    per_cluster, n_clusters = cluster_bytes(tree)

    # Only the requested branches are enabled, which is what RDataFrame effectively does: it
    # reads the columns its graph names and nothing else.
    tree.SetBranchStatus("*", 0)
    for name in columns:
        tree.SetBranchStatus(name, 1)

    tree.SetCacheSize(cache_bytes)
    if cache_bytes:
        for name in columns:
            tree.AddBranchToCache(name, True)
        tree.StopCacheLearningPhase()

    stats = ROOT.TTreePerfStats("io", tree)
    bytes_before = ROOT.TFile.GetFileBytesRead()

    n = int(entries) if entries else tree.GetEntries()
    for i in range(n):
        tree.GetEntry(i)
    stats.Finish()

    zip_bytes = bc.branch_zip_bytes(path, columns, tree_name) or 1
    result = {
        "cache_bytes": int(cache_bytes),
        "entries_read": n,
        "n_clusters": n_clusters,
        "cluster_zip_bytes": int(per_cluster),
        # A cache that cannot hold one cluster cannot coalesce a cluster's baskets into one
        # read, which is the mechanism the sweep is testing for.
        "cache_holds_cluster": bool(cache_bytes and cache_bytes >= per_cluster),
        "columns_zip_bytes": int(zip_bytes),
        "file_bytes_read": int(ROOT.TFile.GetFileBytesRead() - bytes_before),
        "perfstats_bytes_read": int(stats.GetBytesRead()),
        # Bytes pulled in that the query never asked for: the amplification, directly.
        "perfstats_bytes_extra": int(stats.GetBytesReadExtra()),
        "read_calls": int(stats.GetReadCalls()),
        "disk_time_s": float(stats.GetDiskTime()),
        "unzip_time_s": float(stats.GetUnzipTime()),
    }
    result["read_amplification"] = result["file_bytes_read"] / zip_bytes
    result["bytes_per_read_call"] = result["file_bytes_read"] / max(result["read_calls"], 1)
    f.Close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--tree", default="Events")
    parser.add_argument(
        "--chain-len",
        type=int,
        default=bc.MAX_CHAIN_LEN,
        help="read the branches the chain of this length needs",
    )
    parser.add_argument(
        "--cache-mb",
        type=int,
        nargs="+",
        default=[0, 30, 128, 512],
        help="TTreeCache sizes to sweep; 0 disables the cache. ROOT's default is 30 MB",
    )
    parser.add_argument(
        "--entries",
        type=int,
        default=0,
        help="stop after this many entries; 0 reads the whole tree",
    )
    parser.add_argument("--out", default=None, help="append the JSON result here")
    args = parser.parse_args()

    columns = bc.chain_columns(args.chain_len)
    print(f"{os.path.basename(args.input)}: reading {columns}\n")

    header = (
        f"{'cache':>8s} {'fits?':>6s} {'read':>10s} {'extra':>10s} "
        f"{'ampl':>8s} {'calls':>9s} {'kB/call':>9s} {'disk_s':>8s} {'unzip_s':>8s}"
    )
    print(header)
    print("-" * len(header))

    results = []
    for cache_mb in args.cache_mb:
        r = measure(args.input, columns, cache_mb * 1024 * 1024, args.entries, args.tree)
        r["input"] = os.path.basename(args.input)
        r["chain_len"] = args.chain_len
        results.append(r)
        print(
            f"{cache_mb:6d}MB {str(r['cache_holds_cluster']):>6s} "
            f"{r['file_bytes_read'] / 1e6:9.1f}M {r['perfstats_bytes_extra'] / 1e6:9.1f}M "
            f"{r['read_amplification']:7.2f}x {r['read_calls']:9d} "
            f"{r['bytes_per_read_call'] / 1e3:9.1f} {r['disk_time_s']:8.2f} "
            f"{r['unzip_time_s']:8.2f}"
        )

    first = results[0]
    print(
        f"\ncluster: {first['cluster_zip_bytes'] / 1e6:.1f} MB compressed x "
        f"{first['n_clusters']} clusters; branches asked for: "
        f"{first['columns_zip_bytes'] / 1e6:.1f} MB"
    )
    best, worst = min(r["read_amplification"] for r in results), max(
        r["read_amplification"] for r in results
    )
    if worst / max(best, 1e-9) > 2:
        print(
            "-> cache size changes bytes read by more than 2x: the amplification is TTreeCache "
            "failing to hold a cluster, not basket granularity."
        )
    else:
        print(
            "-> cache size barely matters: the amplification, if any, is basket granularity "
            "rather than the cache."
        )

    if args.out:
        with open(args.out, "a") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
