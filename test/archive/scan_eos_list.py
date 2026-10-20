#!/usr/bin/env python3
"""
Run 3 NanoAOD on EOS -> a larger run3_sizes.txt for fetch_eos.sh. One file, no repository:
copy it to lxplus and run it with the ROOT of an LCG view.

Input: run3_all_sizes.txt, "<path under /eos/cms/store/data/<era>/<PD>/NANOAOD/<version>/> <bytes>"
per line (find -printf '%p %s\n' over the NANOAOD directories).

  sample  K files of every (era, PD, version) of the --pd primary datasets -> sample.txt
  scan    every file of a list, over xrootd: entries, missing chain columns, events with PPS
          and events left after each of the 11 filters (run3 cuts) -> CSV, one row per file,
          appended as it goes, so a rerun resumes; --no-chain reads the headers only;
          --budget-tb stops once that many TB of usable files are scanned
  rank    sizes list + the sample's scan: one processing per (era, PD), physics PDs, without
          --have, datasets ordered by events left after the chain per byte -> ranked.txt
  write   ranked.txt + its scan: the usable files in ranked order up to --budget-tb, after the
          --have list -> run3_sizes_new.txt

    source /cvmfs/sft.cern.ch/lcg/views/LCG_106/x86_64-el9-gcc13-opt/setup.sh
    python scan_eos_list.py sample run3_all_sizes.txt -o sample.txt
    python scan_eos_list.py scan sample.txt -o sample_scan.csv --jobs 8
    python scan_eos_list.py rank run3_all_sizes.txt --scan sample_scan.csv \\
        --have ~/run3_sizes.txt -o ranked.txt
    python scan_eos_list.py scan ranked.txt -o ranked_scan.csv --jobs 8 --no-chain --budget-tb 8.2
    python scan_eos_list.py write ranked.txt --scan ranked_scan.csv --have ~/run3_sizes.txt \\
        --budget-tb 8.2 -o run3_sizes_new.txt

Files are opened as root://eoscms.cern.ch//eos/...: the Kerberos ticket of the lxplus session
is the credential, nothing is stored.
"""

import argparse
import csv
import multiprocessing
import os
import re
import sys
from collections import defaultdict

PHYSICS_PDS = r"^(BTagMu|DisplacedJet|EGamma\d|JetMET\d|Muon\d|MuonEG|MuonShower|Tau)$"
VERSION = re.compile(r"^(?P<campaign>.+?)(?:_(?P<part>v\d+))?-v(?P<n>\d+)$")

# Must stay equal to bench_spec.PERIODS["run3"] and impl_rdf.chain_filters: the benchmark's
# chain_cuts() signature below is what ties the counts to the campaign.
CHAIN_CUTS = ("theta_y,multi_proton,multi_rp_idx==-1,single_rp_idx>=0,track_x>4,track_y>0,pps,"
              "double_arm(23|123)&(3|103),diamond==4,rp_id==23,xi[0.05,0.1]")
CHAIN = [
    ("theta_y", "ROOT::VecOps::Any(Proton_singleRP_thetaY != 0)"),
    ("multi_proton", "nProton_singleRP > 1"),
    ("multi_rp_idx", "ROOT::VecOps::Any(PPSLocalTrack_multiRPProtonIdx == -1)"),
    ("single_rp_idx", "ROOT::VecOps::Any(PPSLocalTrack_singleRPProtonIdx >= 0)"),
    ("track_x", "ROOT::VecOps::Any(PPSLocalTrack_x > 4)"),
    ("track_y", "ROOT::VecOps::Any(PPSLocalTrack_y > 0)"),
    ("pps", "nPPSLocalTrack > 0"),
    ("double_arm", "ROOT::VecOps::Any(PPSLocalTrack_decRPId == 23 || PPSLocalTrack_decRPId == 123)"
                   " && ROOT::VecOps::Any(PPSLocalTrack_decRPId == 3 || PPSLocalTrack_decRPId == 103)"),
    ("diamond", "ROOT::VecOps::Any(PPSLocalTrack_rpType == 4)"),
    ("rp_id", "ROOT::VecOps::Any(PPSLocalTrack_decRPId == 23)"),
    ("xi", "ROOT::VecOps::Any(Proton_singleRP_xi >= 0.05 && Proton_singleRP_xi <= 0.1)"),
]
STEPS = [name for name, _ in CHAIN]
COLUMNS = ["Proton_singleRP_thetaY", "nProton_singleRP", "PPSLocalTrack_multiRPProtonIdx",
           "PPSLocalTrack_singleRPProtonIdx", "PPSLocalTrack_x", "PPSLocalTrack_y",
           "nPPSLocalTrack", "PPSLocalTrack_decRPId", "PPSLocalTrack_rpType", "Proton_singleRP_xi"]
FIELDS = ["path", "size_bytes", "entries", "missing_columns", "with_pps"] + STEPS + ["error"]


# --- lists -----------------------------------------------------------------------------------

def read_sizes(path):
    """[(eos path, bytes or None)] of a "<path> [<bytes>]" list; blank lines and # skipped."""
    out = []
    with open(path) as f:
        for line in f:
            fields = line.split()
            if fields and not fields[0].startswith("#"):
                out.append((fields[0], int(fields[1]) if len(fields) > 1 else None))
    return out


def describe(path):
    """era, PD, version, campaign, part, -vN and run (PromptReco: /000/RRR/RRR/) of a path."""
    p = path.split("/")
    version = p[8]
    match = VERSION.match(version)
    return {
        "era": p[5], "pd": p[6], "version": version,
        "campaign": match["campaign"] if match else version,
        "part": (match["part"] or "") if match else "",
        "n": int(match["n"]) if match else 0,
        "run": int(p[10] + p[11]) if len(p) > 12 and p[9] == "000" else None,
    }


def dataset(path):
    d = describe(path)
    return f"{d['era']}/{d['pd']}/{d['version']}"


def deduplicate(files):
    """
    One processing of every event: 2024 MINIv6NANOv15 over PromptReco, in 2023 a re-NANO
    (22Sep2023, 24Jan2024) over the prompt NanoAOD of the same part _vK, the highest -vN of
    every (campaign, part), and of PromptReco, whose -vN are run ranges, each run once.
    """
    info = [(path, size, describe(path)) for path, size in files]
    rereco = lambda d: not d["campaign"].startswith("Prompt")
    parts, best, run_best = defaultdict(set), defaultdict(int), {}
    for _, _, d in info:
        key = (d["era"], d["pd"])
        if rereco(d):
            parts[key].add(d["part"])
        best[key + (d["campaign"], d["part"])] = max(best[key + (d["campaign"], d["part"])], d["n"])
        if d["campaign"] == "PromptReco":
            run = key + (d["run"],)
            run_best[run] = max(run_best.get(run, 0), d["n"])
    kept = []
    for path, size, d in info:
        key = (d["era"], d["pd"])
        if not rereco(d):
            if d["era"].startswith("Run2023"):
                if d["part"] in parts[key] or (d["campaign"] == "PromptReco" and parts[key]):
                    continue
            elif key in parts:
                continue
        if d["campaign"] == "PromptReco":
            if d["n"] != run_best[key + (d["run"],)]:
                continue
        elif d["n"] != best[key + (d["campaign"], d["part"])]:
            continue
        kept.append((path, size))
    return kept


def write_sizes(path, files):
    with open(path + ".partial", "w") as f:
        f.writelines(f"{p} {s}\n" for p, s in files)
    os.replace(path + ".partial", path)


def load_scan(path):
    with open(path) as f:
        return {r["path"]: r for r in csv.DictReader(f)}


def problem(row):
    """Why a scanned file cannot go into the benchmark, or "" if it can."""
    if row["error"]:
        return "unreadable"
    if row["missing_columns"]:
        return "no chain columns"
    if not int(row["entries"] or 0):
        return "empty"
    return ""


def usable(row):
    return not problem(row)


# --- scan ------------------------------------------------------------------------------------

ROOT = None


def init_worker():
    global ROOT
    os.environ.setdefault("XRD_REQUESTTIMEOUT", "300")
    os.environ.setdefault("XRD_STREAMTIMEOUT", "300")
    import ROOT as root
    root.gROOT.SetBatch(True)
    root.gErrorIgnoreLevel = root.kError
    ROOT = root


def scan_file(task):
    path, size, prefix, with_chain = task
    url = prefix + path if path.startswith("/") else path
    row = dict.fromkeys(FIELDS, "")
    row.update(path=path, size_bytes=size if size is not None else "")
    try:
        f = ROOT.TFile.Open(url)
        if not f or f.IsZombie():
            raise OSError(f"cannot open {url}")
        tree = f.Get("Events")
        if not tree:
            raise OSError("no Events tree")
        row["entries"] = int(tree.GetEntries())
        if size is None:
            row["size_bytes"] = int(f.GetSize())
        branches = {b.GetName() for b in tree.GetListOfBranches()}
        f.Close()
        missing = [c for c in COLUMNS if c not in branches]
        row["missing_columns"] = " ".join(missing)
        if with_chain and row["entries"] and not missing:
            df = ROOT.RDataFrame("Events", url)
            with_pps = df.Filter("nPPSLocalTrack > 0").Count()
            node = df
            for name, expr in CHAIN:
                node = node.Filter(expr, name)
            report = node.Report()
            counts = [int(cut.GetPass()) for cut in report]
            row["with_pps"] = int(with_pps.GetValue())
            row.update(zip(STEPS, counts))
    except Exception as exc:  # noqa: BLE001 -- one bad file must not stop the others
        row["error"] = (str(exc).splitlines() or [type(exc).__name__])[0][:300]
    return row


def scan(args):
    files = read_sizes(args.list)
    done = load_scan(args.output) if os.path.exists(args.output) else {}
    good = sum(int(r["size_bytes"] or 0) for r in done.values() if usable(r))
    budget = args.budget_tb * 1e12 if args.budget_tb else None
    tasks = [(p, s, args.prefix, not args.no_chain) for p, s in files if p not in done]
    print(f"chain_cuts: {CHAIN_CUTS}")
    print(f"{len(files)} files in {args.list}, {len(done)} already in {args.output}, "
          f"{len(tasks)} to scan" + (f", until {args.budget_tb} TB usable" if budget else ""))
    if budget and good >= budget:
        tasks = []

    new = not os.path.exists(args.output)
    with open(args.output, "a", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        if tasks:
            context = multiprocessing.get_context("spawn")
            # Every file JITs its own filters and Cling never frees them: replace workers.
            pool = context.Pool(args.jobs, initializer=init_worker, maxtasksperchild=25)
            try:
                for i, row in enumerate(pool.imap(scan_file, tasks), 1):
                    writer.writerow(row)
                    out.flush()
                    if usable(row):
                        good += int(row["size_bytes"])
                    print(f"[{i}/{len(tasks)}] usable {good / 1e12:.2f} TB  "
                          f"{row['error'] or row['missing_columns'] or row['entries']}  "
                          f"{row['path']}", file=sys.stderr, flush=True)
                    if budget and good >= budget:
                        print(f"budget of {args.budget_tb} TB reached", file=sys.stderr)
                        break
            finally:
                pool.terminate()
                pool.join()

    rows = list(load_scan(args.output).values())
    ok = [r for r in rows if usable(r)]
    problems = defaultdict(int)
    for r in rows:
        if not usable(r):
            problems[problem(r)] += 1
    print(f"{len(rows)} files scanned: {len(ok)} usable "
          f"({sum(int(r['size_bytes']) for r in ok) / 1e12:.2f} TB, "
          f"{sum(int(r['entries']) for r in ok)} events)"
          + "".join(f", {n} {why}" for why, n in sorted(problems.items())))
    for r in [r for r in rows if r["error"]][:10]:
        print(f"  {r['path']}: {r['error']}")
    return 0


# --- sample / rank / write -------------------------------------------------------------------

def sample(args):
    pd = re.compile(args.pd)
    by_dataset = defaultdict(list)
    for path, size in read_sizes(args.sizes):
        if pd.match(describe(path)["pd"]):
            by_dataset[dataset(path)].append((path, size))
    chosen = []
    for _, files in sorted(by_dataset.items()):
        files.sort()
        picks = sorted({int(i * len(files) / args.per_dataset) for i in range(args.per_dataset)})
        chosen += [files[i] for i in picks]
    write_sizes(args.output, chosen)
    print(f"{len(by_dataset)} datasets, {len(chosen)} files, "
          f"{sum(s for _, s in chosen) / 1e9:.0f} GB -> {args.output}")
    return 0


def rank(args):
    pd = re.compile(args.pd)
    have = {p for p, _ in read_sizes(args.have)} if args.have else set()
    files = deduplicate([(p, s) for p, s in read_sizes(args.sizes) if pd.match(describe(p)["pd"])])
    candidates = defaultdict(list)
    for path, size in files:
        if path not in have:
            candidates[dataset(path)].append((path, size))

    stats = defaultdict(lambda: {"bytes": 0, "entries": 0, "pps": 0, "passed": 0, "files": 0,
                                 "bad": []})
    for row in load_scan(args.scan).values():
        s = stats[dataset(row["path"])]
        if not usable(row) or row["xi"] == "":
            s["bad"].append(row["error"] or row["missing_columns"] or problem(row)
                            or "scanned with --no-chain")
            continue
        s["files"] += 1
        s["bytes"] += int(row["size_bytes"])
        s["entries"] += int(row["entries"])
        s["pps"] += int(row["with_pps"])
        s["passed"] += int(row["xi"])

    ranked, dropped = [], []
    for key, members in candidates.items():
        s = stats.get(key)
        size = sum(sz for _, sz in members)
        if not s or not s["files"]:
            dropped.append((key, len(members), size,
                            "not sampled" if not s else "sample: " + "; ".join(sorted(set(s["bad"])))))
        elif not s["passed"]:
            dropped.append((key, len(members), size, "sample: nothing passes the chain"))
        else:
            ranked.append((s["passed"] / s["bytes"], key, sorted(members), s))
    ranked.sort(key=lambda r: -r[0])

    out = [f for _, _, members, _ in ranked for f in members]
    write_sizes(args.output, out)

    print(f"chain_cuts: {CHAIN_CUTS}")
    print(f"have: {len(have)} files, {sum(s for _, s in read_sizes(args.have)) / 1e12:.2f} TB"
          if args.have else "have: none")
    print(f"{'#':>3} {'dataset':52} {'files':>6} {'GB':>8} {'cum TB':>7} {'ev/GB':>9} "
          f"{'PPS':>6} {'chain':>6} {'est. passed':>12}")
    cum = 0
    for i, (density, key, members, s) in enumerate(ranked, 1):
        size = sum(sz for _, sz in members)
        cum += size
        print(f"{i:>3} {key:52} {len(members):>6} {size / 1e9:>8.1f} {cum / 1e12:>7.2f} "
              f"{s['entries'] / s['bytes'] * 1e9:>9.0f} {s['pps'] / s['entries']:>6.3f} "
              f"{s['passed'] / s['entries']:>6.3f} {density * size:>12.3g}")
    print(f"dropped ({len(dropped)} datasets, "
          f"{sum(d[2] for d in dropped) / 1e12:.2f} TB):")
    for key, n, size, why in sorted(dropped):
        print(f"    {key:52} {n:>6} {size / 1e9:>8.1f}  {why}")
    print(f"{len(out)} files, {cum / 1e12:.2f} TB in ranked order -> {args.output}")
    return 0


def write(args):
    ranked = read_sizes(args.ranked)
    scanned = load_scan(args.scan)
    have = read_sizes(args.have) if args.have else []
    budget = args.budget_tb * 1e12
    chosen, size, skipped, unscanned = [], 0, defaultdict(int), 0
    for path, sz in ranked:
        if size >= budget:
            break
        row = scanned.get(path)
        if row is None:
            unscanned += 1
            continue
        if not usable(row):
            skipped[problem(row)] += 1
            continue
        if args.min_passed and row["xi"] != "" and int(row["xi"]) < args.min_passed:
            skipped["below --min-passed"] += 1
            continue
        chosen.append((path, int(row["size_bytes"])))
        size += int(row["size_bytes"])

    write_sizes(args.output, have + chosen)
    totals = defaultdict(lambda: [0, 0, 0])
    for path, sz in chosen:
        t = totals[describe(path)["era"]]
        t[0] += 1
        t[1] += sz
        t[2] += int(scanned[path]["entries"])
    print(f"  {'era':10} {'files':>6} {'TB':>7} {'events':>12}")
    for era, (n, sz, ev) in sorted(totals.items()):
        print(f"  {era:10} {n:>6} {sz / 1e12:>7.2f} {ev:>12}")
    print(f"new: {len(chosen)} files, {size / 1e12:.2f} TB; skipped: "
          + (", ".join(f"{n} {why}" for why, n in skipped.items()) or "none"))
    if size < budget:
        print(f"WARNING: {budget / 1e12:.2f} TB not reached ({unscanned} ranked files not "
              f"scanned yet): run scan with a larger --budget-tb, then write again")
    print(f"{len(have)} have + {len(chosen)} new = {len(have) + len(chosen)} files, "
          f"{(sum(s for _, s in have) + size) / 1e12:.2f} TB -> {args.output}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sample", help="K files of every dataset")
    p.add_argument("sizes")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--per-dataset", type=int, default=2)
    p.add_argument("--pd", default=PHYSICS_PDS, help="regex of the primary datasets to keep")

    p = sub.add_parser("scan", help="entries, columns, PPS, chain of every file of a list")
    p.add_argument("list")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--prefix", default="root://eoscms.cern.ch/",
                   help="put in front of /eos paths; '' opens them through the FUSE mount")
    p.add_argument("--no-chain", action="store_true", help="headers only: entries and columns")
    p.add_argument("--budget-tb", type=float, help="stop once this many TB are usable")

    p = sub.add_parser("rank", help="datasets by events left after the chain per byte")
    p.add_argument("sizes")
    p.add_argument("--scan", required=True, help="scan CSV of the sample")
    p.add_argument("--have", help="the current run3_sizes.txt")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--pd", default=PHYSICS_PDS)

    p = sub.add_parser("write", help="usable ranked files up to the budget, after --have")
    p.add_argument("ranked")
    p.add_argument("--scan", required=True, help="scan CSV of ranked.txt")
    p.add_argument("--have", help="the current run3_sizes.txt, kept first")
    p.add_argument("--budget-tb", type=float, required=True, help="TB of new files")
    p.add_argument("--min-passed", type=int, default=0,
                   help="drop files with fewer events after the chain (needs a scan with chain)")
    p.add_argument("-o", "--output", required=True)

    args = parser.parse_args()
    return {"sample": sample, "scan": scan, "rank": rank, "write": write}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
