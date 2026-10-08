#!/usr/bin/env python3
"""
Describes a set of NanoAOD files before they are used as benchmark input: one CSV row per file.

Run it twice. On lxplus, over the candidate files on EOS, to decide what is worth transferring
(one schema, every column the benchmarks read, PPS actually present). And on Ares, over what
arrived, with --compare pointing at the lxplus CSV: entry counts and byte sizes must match file
for file, which is the check that the transfer is complete.

Per file:
  era, primary_dataset, version, run   parsed from the /store path (Open Data paths: no run)
  size_bytes, entries, clusters        clusters are what ImplicitMT divides the work by
  n_branches, schema                   schema = short SHA-256 of the sorted branch names;
                                       files with different values cannot share a TChain safely
  compression                          file-level codec, e.g. "2:9" = LZMA level 9
  missing_columns                      benchmark columns absent from the file
  pps_fraction, rp_fraction            events with nPPSLocalTrack > 0, and with a track in the
                                       benchmark's default RP; one event loop over two small
                                       branches, skipped with --no-loop

  lxplus:  source /cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc12-opt/setup.sh
           python test/inventory_files.py --list files.txt --prefix /eos/cms/store \\
               --output inventory_lxplus.csv
  Ares:    find $SCRATCH/bench/real -name '*.root' -not -path '*/slim/*' > ares_files.txt
           python test/inventory_files.py --list ares_files.txt --output inventory_ares.csv \\
               --compare inventory_lxplus.csv

The list may also hold remote URLs (root://, https://), e.g. the CERN Open Data files from
archive/opendata_index.py: each file is then opened over the network and only its metadata and the two
PPS branches are read, a few percent of its size. --jobs N describes N files at a time.

  Open Data: python test/inventory_files.py --list scan.txt --output remote.csv --jobs 8
"""

import argparse
import csv
import hashlib
import multiprocessing
import os
import re
import sys
from collections import defaultdict

import bench_common as bc

ROOT = bc.ROOT

FIELDS = [
    "name", "path", "era", "primary_dataset", "version", "run", "size_bytes", "entries",
    "clusters", "events_per_cluster", "n_branches", "schema", "compression",
    "missing_columns", "pps_fraction", "rp_fraction", "error",
]

STORE_PATH = re.compile(
    r"/(?P<era>[^/]+)/(?P<pd>[^/]+)/NANOAOD/(?P<version>[^/]+)/000/(?P<r1>\d{3})/(?P<r2>\d{3})/"
)
# /eos/opendata/cms/Run2016H/SingleMuon/NANOAOD/UL2016_MiniAODv2_NanoAODv9-v1/120000/<uuid>.root,
# and the same below any download directory that keeps <era>/<PD>/ (archive/fetch_opendata.sh).
OPENDATA_PATH = re.compile(r"/(?P<era>Run\d{4}[A-Z])/(?P<pd>[^/]+)/(?:NANOAOD/(?P<version>[^/]+)/)?")
REMOTE = ("root://", "http://", "https://")


def benchmark_columns():
    return sorted(set(bc.chain_columns(len(bc.LONG_CHAIN_STEPS), "long"))
                  | set(bc.EFFICIENCY_COLUMNS))


def read_list(list_path, prefix):
    """
    Paths from a list, with --prefix joined in front. A `find .` listing mixes "./backfill/..."
    and "/backfill/...", and os.path.join would silently drop the prefix for the second form,
    so both are reduced to "backfill/..." first.
    """
    with open(list_path) as f:
        entries = [line.strip() for line in f]
    entries = [e for e in entries if e and not e.startswith("#")]
    if not prefix:
        return entries
    return [os.path.normpath(os.path.join(prefix, re.sub(r"^\.?/+", "", e))) for e in entries]


def describe(path, rp_id, with_loop):
    row = {"name": os.path.basename(path), "path": path}
    match = STORE_PATH.search(path)
    if match:
        row.update(era=match["era"], primary_dataset=match["pd"], version=match["version"],
                   run=int(match["r1"] + match["r2"]))
    elif match := OPENDATA_PATH.search(path):
        row.update(era=match["era"], primary_dataset=match["pd"], version=match["version"])
    try:
        layout = bc.tree_layout(path)
        row["size_bytes"] = layout["size_bytes"] if path.startswith(REMOTE) \
            else os.path.getsize(path)
    except OSError as exc:
        row["error"] = str(exc)
        return row

    branches = layout["branches"]
    row.update(
        entries=layout["entries"],
        clusters=layout["clusters"],
        events_per_cluster=round(layout["entries"] / max(layout["clusters"], 1)),
        n_branches=len(branches),
        schema=hashlib.sha256("\n".join(sorted(branches)).encode()).hexdigest()[:12],
        compression=f"{layout['compression_algorithm']}:{layout['compression_level']}",
    )
    missing = [c for c in benchmark_columns() if c not in set(branches)]
    row["missing_columns"] = " ".join(missing)

    if with_loop and not missing and layout["entries"]:
        df = ROOT.RDataFrame("Events", path)
        with_pps = df.Filter("nPPSLocalTrack > 0").Count()
        in_rp = df.Filter(f"ROOT::VecOps::Any(PPSLocalTrack_decRPId == {rp_id})").Count()
        row["pps_fraction"] = round(with_pps.GetValue() / layout["entries"], 5)
        row["rp_fraction"] = round(in_rp.GetValue() / layout["entries"], 5)
    return row


def init_worker(threads, no_loop):
    if not no_loop:
        bc.setup_root(threads)


def describe_task(task):
    return describe(*task)


def load_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def compare(rows, reference_path):
    """Rows whose entries or size differ from the reference, matched on file name."""
    reference = {r["name"]: r for r in load_csv(reference_path)}
    problems = []
    for row in rows:
        ref = reference.get(row["name"])
        if ref is None:
            problems.append(f"{row['name']}: not in {reference_path}")
            continue
        for field in ("entries", "size_bytes"):
            if str(row.get(field, "")) != str(ref.get(field, "")):
                problems.append(f"{row['name']}: {field} {row.get(field)} != {ref.get(field)}")
    return problems


def summarise(rows):
    groups = defaultdict(lambda: {"files": 0, "entries": 0, "bytes": 0, "pps": []})
    for row in rows:
        if row.get("error"):
            continue
        key = (row.get("run"), row.get("version"), row.get("schema"),
               "ok" if not row.get("missing_columns") else "missing columns")
        g = groups[key]
        g["files"] += 1
        g["entries"] += row["entries"]
        g["bytes"] += row["size_bytes"]
        if row.get("pps_fraction") is not None:
            g["pps"].append(row["pps_fraction"])
    print(f"{'run':>7} {'version':24} {'schema':12} {'columns':16} {'files':>5} "
          f"{'events':>12} {'GB':>7} {'PPS':>6}")
    for key, g in sorted(groups.items(), key=lambda kv: -kv[1]["entries"]):
        pps = f"{sum(g['pps']) / len(g['pps']):.3f}" if g["pps"] else "-"
        print(f"{str(key[0]):>7} {str(key[1]):24} {str(key[2]):12} {key[3]:16} {g['files']:>5} "
              f"{g['entries']:>12} {g['bytes'] / 1e9:>7.2f} {pps:>6}")
    errors = [r for r in rows if r.get("error")]
    if errors:
        print(f"{len(errors)} files could not be read:")
        for row in errors:
            print(f"  {row['path']}: {row['error']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", required=True, help="text file, one path per line")
    parser.add_argument("--prefix", default="", help="joined in front of relative paths")
    parser.add_argument("--output", required=True, help="CSV to write")
    parser.add_argument("--compare", help="CSV from the other side of a transfer")
    parser.add_argument("--no-loop", action="store_true",
                        help="metadata only: skip the PPS fractions")
    parser.add_argument("--threads", type=int, default=4, help="ImplicitMT for the PPS loop")
    parser.add_argument("--rp-id", type=int, default=bc.DEFAULT_RP_ID)
    parser.add_argument("--jobs", type=int, default=1,
                        help="files described at a time, each in its own process")
    args = parser.parse_args()

    paths = read_list(args.list, args.prefix)
    tasks = [(path, args.rp_id, not args.no_loop) for path in paths]
    if args.jobs > 1:
        # spawn, not fork: a forked child would inherit the parent's ROOT and TBB state.
        context = multiprocessing.get_context("spawn")
        with context.Pool(args.jobs, initializer=init_worker,
                          initargs=(args.threads, args.no_loop)) as pool:
            rows = []
            for index, row in enumerate(pool.imap(describe_task, tasks), 1):
                print(f"[{index}/{len(paths)}] {row['path']}", file=sys.stderr)
                rows.append(row)
    else:
        init_worker(args.threads, args.no_loop)
        rows = []
        for index, task in enumerate(tasks, 1):
            print(f"[{index}/{len(paths)}] {task[0]}", file=sys.stderr)
            rows.append(describe_task(task))

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} files -> {args.output}")
    summarise(rows)

    if args.compare:
        problems = compare(rows, args.compare)
        if problems:
            print(f"TRANSFER CHECK FAILED ({len(problems)}):")
            for line in problems:
                print(f"  {line}")
            return 1
        print(f"transfer check: all {len(rows)} files match {args.compare}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
