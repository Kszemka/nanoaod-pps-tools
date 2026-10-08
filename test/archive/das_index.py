#!/usr/bin/env python3
"""
Lists CMS NanoAOD files from DAS for a download over xrootd (AAA): one CSV row per file, in the
columns fetch_opendata.sh reads (those of opendata_index.py, plus the dataset).

  index   dasgoclient: the datasets matching --query, one processing per (primary dataset,
          era), its disk replicas and its files, into --out-dir:
            datasets.csv  every candidate dataset, what was decided about it and why
            index.csv     uri, name, size_bytes, adler32, recid, era, primary_dataset, version,
                          dataset
            remote.csv    name, entries, size_bytes: the reference for inventory_files.py --compare
            sample.txt    the first file of every selected dataset, for a remote column check
  select  index.csv, without the datasets whose sample file lacks benchmark columns
          (inventory_files.py output given as --exclude) -> --output, up to --max-gb: era by era
          in --era-order, then primary dataset, then file name. The order does not depend on the
          budget, so a larger --max-gb selects a superset of a smaller one.

Dataset names are /<PD>/<era>-<campaign>[_<part>]-v<N>/NANOAOD, e.g.
/Muon0/Run2023C-22Sep2023_v1-v1/NANOAOD. The parts (_v1 .. _v4 in era C) are different run
ranges of the same era, so all are kept; of each part only the highest -vN. Per (PD, era) one
campaign: the first of --campaigns that exists, or without --campaigns the newest (DAS creation
time, else the date in its name, prompt processing counting as oldest) whose parts all have a
complete copy on disk. Datasets only on tape are listed and skipped: they need a Rucio rule
first. Muon0 and Muon1 hold different events, so both are kept.

dasgoclient authenticates with $X509_USER_PROXY (grid_env.sh, slurm_fetch_das.sbatch).

    python test/das_index.py index --query '/Muon*/Run2023*/NANOAOD' --out-dir .
    python test/das_index.py select --index index.csv --max-gb 1040 \\
        --era-order Run2023C Run2023D Run2023B --exclude sample.csv --output urls.txt
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime

INDEX_FIELDS = ["uri", "name", "size_bytes", "adler32", "recid", "era", "primary_dataset",
                "version", "dataset"]
REMOTE_FIELDS = ["name", "path", "size_bytes", "entries"]
DATASET_FIELDS = ["dataset", "primary_dataset", "era", "campaign", "part", "version", "created",
                  "files", "events", "size_gb", "disk_sites", "status", "note"]

NAME = re.compile(r"^/(?P<pd>[^/]+)/(?P<era>Run\d{4}[A-Z])-(?P<processing>.+)-v(?P<version>\d+)"
                  r"/NANOAOD$")
PROCESSING = re.compile(r"^(?P<campaign>.+?)(?:_(?P<part>v\d+))?$")
NAME_DATE = re.compile(r"(\d{1,2}[A-Z][a-z]{2}\d{4})")
NOT_DISK = re.compile(r"_(Tape|MSS|Buffer|Export)$")


# --- dasgoclient -----------------------------------------------------------------------------

def das(query, attempts=3):
    """The records of one dasgoclient -json query; cmsweb is retried, not trusted to be up."""
    last = ""
    for attempt in range(1, attempts + 1):
        try:
            proc = subprocess.run([os.environ.get("DASGOCLIENT", "dasgoclient"), "-query", query,
                                   "-json"], capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            last = "timeout after 900 s"
        else:
            if proc.returncode == 0:
                return parse_json(proc.stdout)
            last = (proc.stderr.strip() or proc.stdout.strip())[-500:]
        if attempt < attempts:
            time.sleep(15 * attempt)
    raise RuntimeError(f"dasgoclient -query {query!r} failed {attempts} times: {last}")


def parse_json(text):
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    return data if isinstance(data, list) else [data]


def merged(records, key):
    """
    The items under `key` of every record, merged by name: DAS answers one query from several
    services (DBS, Rucio), each record carrying part of an item's fields.
    """
    items = {}
    for record in records:
        for item in record.get(key) or []:
            name = item.get("name")
            if not name:
                continue
            target = items.setdefault(name, {})
            target.update({k: v for k, v in item.items() if v not in (None, "")})
    return items


def first(item, *keys):
    for key in keys:
        if item.get(key) not in (None, ""):
            return item[key]
    return None


def timestamp(value):
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value)[:19], fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def percent(value):
    """'100.00%', 100, 1.0 -> 100.0; None when DAS gave nothing to go by."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        number = float(text.rstrip("%"))
    except ValueError:
        return None
    return number if text.endswith("%") or number > 1 else number * 100


def disk_sites(dataset):
    """Sites holding a complete disk copy of the dataset."""
    sites = []
    for name, site in merged(das(f"site dataset={dataset}"), "site").items():
        if NOT_DISK.search(name) or str(site.get("kind", "")).lower() == "tape":
            continue
        share = percent(first(site, "dataset_fraction", "replica_fraction", "block_fraction",
                              "block_completion"))
        if share is None or share >= 99.99:
            sites.append(name)
    return sorted(sites)


def summary(dataset):
    items = [item for record in das(f"summary dataset={dataset}")
             for item in record.get("summary") or []]
    item = items[0] if items else {}
    return {"files": first(item, "nfiles", "num_file"),
            "events": first(item, "nevents", "num_event"),
            "size": first(item, "file_size", "size")}


def files(dataset):
    """(lfn, size, nevents, adler32) of every file; a file without adler32 is an error."""
    out = []
    for name, item in sorted(merged(das(f"file dataset={dataset}"), "file").items()):
        if not name.endswith(".root"):
            continue
        size = first(item, "size", "file_size")
        events = first(item, "nevents", "event_count")
        adler = first(item, "adler32")
        if size is None or events is None or adler is None:
            raise RuntimeError(f"{dataset}: DAS gives no size, nevents or adler32 for {name}")
        out.append((name, int(float(size)), int(float(events)), str(adler).lower()))
    return out


# --- index -----------------------------------------------------------------------------------

def campaign_age(campaign, datasets):
    """Sort key, larger = newer: DAS creation time, else the date in the campaign's name."""
    created = max(d["created"] for d in datasets)
    match = NAME_DATE.search(campaign)
    try:
        named = datetime.strptime(match[1], "%d%b%Y").timestamp() if match else 0.0
    except ValueError:
        named = 0.0
    return (created, 0 if campaign.startswith("Prompt") else 1, named, campaign)


def index(args):
    found = merged(das(f"dataset dataset={args.query}"), "dataset")
    if not found:
        print(f"ERROR: DAS has no dataset matching {args.query}", file=sys.stderr)
        return 1
    rows = []
    for name, item in sorted(found.items()):
        row = {"dataset": name, "status": "", "note": ""}
        match = NAME.match(name)
        if not match:
            row.update(status="skipped", note="name not /<PD>/<era>-<processing>-v<N>/NANOAOD")
            rows.append(row)
            continue
        processing = PROCESSING.match(match["processing"])
        row.update(primary_dataset=match["pd"], era=match["era"],
                   campaign=processing["campaign"], part=processing["part"] or "",
                   version=int(match["version"]),
                   created=timestamp(first(item, "creation_time", "creation_date")))
        rows.append(row)

    parsed = [r for r in rows if not r["status"]]
    latest = {}
    for row in parsed:
        key = (row["primary_dataset"], row["era"], row["campaign"], row["part"])
        if key not in latest or row["version"] > latest[key]["version"]:
            latest[key] = row
    for row in parsed:
        key = (row["primary_dataset"], row["era"], row["campaign"], row["part"])
        if latest[key] is not row:
            row.update(status="superseded", note=f"-v{latest[key]['version']} exists")

    by_pd_era = defaultdict(lambda: defaultdict(list))
    for row in latest.values():
        by_pd_era[(row["primary_dataset"], row["era"])][row["campaign"]].append(row)
    for (pd, era), campaigns in sorted(by_pd_era.items()):
        if args.campaigns:
            ranked = [c for c in args.campaigns if c in campaigns]
        else:
            ranked = sorted(campaigns, key=lambda c: campaign_age(c, campaigns[c]), reverse=True)
        chosen = None
        for campaign in ranked:
            parts = campaigns[campaign]
            for row in parts:
                row["disk_sites"] = " ".join(disk_sites(row["dataset"]))
            if all(row["disk_sites"] for row in parts):
                chosen = campaign
                break
            for row in parts:
                if not row["disk_sites"]:
                    row.update(status="tape-only", note="no complete disk copy; needs a Rucio rule")
        for campaign, parts in campaigns.items():
            for row in parts:
                if campaign == chosen:
                    row["status"] = "selected"
                elif not row["status"]:
                    row.update(status="not-chosen",
                               note=f"{pd} {era}: {chosen or 'nothing'} chosen"
                                    + ("" if campaign in ranked else ", not in --campaigns"))

    for row in parsed:
        if row["status"] != "superseded":
            info = summary(row["dataset"])
            row.update(files=info["files"], events=info["events"],
                       size_gb=round(float(info["size"]) / 1e9, 1) if info["size"] else "")
        row["created"] = (datetime.fromtimestamp(row["created"]).strftime("%Y-%m-%d")
                          if row.get("created") else "")

    selected = sorted((r for r in rows if r["status"] == "selected"),
                      key=lambda r: (r["era"], r["primary_dataset"], r["dataset"]))
    index_rows, remote_rows, samples = [], [], []
    redirector = args.redirector.rstrip("/") + "/"
    for row in selected:
        listed = files(row["dataset"])
        if not listed:
            row.update(status="empty", note="DAS lists no .root files")
            continue
        processing = row["dataset"].split("/")[2].split("-", 1)[1]
        for lfn, size, events, adler in listed:
            uri = redirector + lfn
            name = os.path.basename(lfn)
            index_rows.append({"uri": uri, "name": name, "size_bytes": size, "adler32": adler,
                               "recid": "", "era": row["era"],
                               "primary_dataset": row["primary_dataset"],
                               "version": processing, "dataset": row["dataset"]})
            remote_rows.append({"name": name, "path": uri, "size_bytes": size, "entries": events})
        samples.append(redirector + listed[0][0])

    os.makedirs(args.out_dir, exist_ok=True)
    write_csv(os.path.join(args.out_dir, "datasets.csv"), DATASET_FIELDS, rows)
    # Downloads go to <era>/<PD>/<name> and the transfer check matches on the name: both need
    # the names (UUIDs in production) to be unique.
    names = defaultdict(list)
    for row in index_rows:
        names[row["name"]].append(row["dataset"])
    clashes = {n: d for n, d in names.items() if len(d) > 1}
    if clashes:
        for name, datasets in sorted(clashes.items())[:10]:
            print(f"ERROR: {name} in {' '.join(datasets)}", file=sys.stderr)
        print(f"ERROR: {len(clashes)} file names occur more than once", file=sys.stderr)
        return 1
    if not index_rows:
        print("ERROR: no dataset selected; see datasets.csv", file=sys.stderr)
        print_datasets(rows)
        return 1
    write_csv(os.path.join(args.out_dir, "index.csv"), INDEX_FIELDS, index_rows)
    write_csv(os.path.join(args.out_dir, "remote.csv"), REMOTE_FIELDS, remote_rows)
    with open(os.path.join(args.out_dir, "sample.txt"), "w") as f:
        f.writelines(uri + "\n" for uri in samples)

    print_datasets(rows)
    size = sum(r["size_bytes"] for r in index_rows)
    print(f"{len(selected)} datasets selected, {len(index_rows)} files, {size / 1e12:.2f} TB"
          f" -> {args.out_dir}/index.csv")
    return 0


def print_datasets(rows):
    print(f"  {'status':11} {'files':>6} {'events':>12} {'GB':>8}  dataset")
    for row in sorted(rows, key=lambda r: (r["status"] != "selected", r["dataset"])):
        print(f"  {row['status']:11} {row.get('files') or '':>6} {row.get('events') or '':>12} "
              f"{row.get('size_gb', ''):>8}  {row['dataset']}  {row.get('note', '')}")


def write_csv(path, fields, rows):
    with open(path + ".partial", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(path + ".partial", path)


# --- select ----------------------------------------------------------------------------------

def select(args):
    with open(args.index) as f:
        rows = list(csv.DictReader(f))
    dataset_of = {r["name"]: r["dataset"] for r in rows}
    excluded = {}
    if args.exclude:
        with open(args.exclude) as f:
            for sample in csv.DictReader(f):
                problem = sample.get("error") or sample.get("missing_columns")
                if problem:
                    excluded[dataset_of.get(sample["name"], sample["name"])] = problem
    for dataset, problem in sorted(excluded.items()):
        print(f"  excluded {dataset}: {problem}")
    rows = [r for r in rows if r["dataset"] not in excluded]

    rank = {era: i for i, era in enumerate(args.era_order or [])}
    rows.sort(key=lambda r: (rank.get(r["era"], len(rank)), r["era"], r["primary_dataset"],
                             r["uri"]))
    available = sum(int(r["size_bytes"]) for r in rows)
    chosen, size = [], 0
    for row in rows:
        if args.max_gb and size + int(row["size_bytes"]) > args.max_gb * 1e9:
            break
        chosen.append(row)
        size += int(row["size_bytes"])
    if not chosen:
        print("ERROR: nothing selected (every dataset excluded, or --max-gb below one file)",
              file=sys.stderr)
        return 1
    with open(args.output + ".partial", "w") as f:
        f.writelines(r["uri"] + "\n" for r in chosen)
    os.replace(args.output + ".partial", args.output)

    totals = defaultdict(lambda: [0, 0])
    for row in chosen:
        t = totals[(row["era"], row["primary_dataset"])]
        t[0] += 1
        t[1] += int(row["size_bytes"])
    print(f"  {'era':10} {'primary dataset':16} {'files':>6} {'GB':>9}")
    for (era, pd), (n, gb) in totals.items():
        print(f"  {era:10} {pd:16} {n:>6} {gb / 1e9:>9.1f}")
    print(f"{len(chosen)} files, {size / 1e9:.1f} GB of {available / 1e9:.1f} GB on disk "
          f"-> {args.output}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("index", help="query DAS: datasets.csv, index.csv, remote.csv, sample.txt")
    p.add_argument("--query", default="/Muon*/Run2023*/NANOAOD", help="DAS dataset pattern")
    p.add_argument("--campaigns", nargs="+",
                   help="processing campaigns to use, in order of preference (e.g. 22Sep2023)")
    p.add_argument("--redirector", default="root://cms-xrd-global.cern.ch/")
    p.add_argument("--out-dir", default=".")
    p = sub.add_parser("select", help="index.csv -> URL list within a budget")
    p.add_argument("--index", required=True)
    p.add_argument("--max-gb", type=float, help="stop adding files at this total size")
    p.add_argument("--era-order", nargs="+", help="eras to fill the budget from, in this order")
    p.add_argument("--exclude", help="inventory_files.py CSV of sample.txt: datasets to drop")
    p.add_argument("--output", required=True)
    args = parser.parse_args()
    return index(args) if args.command == "index" else select(args)


if __name__ == "__main__":
    sys.exit(main())
