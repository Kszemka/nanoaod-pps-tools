#!/bin/bash -l
#SBATCH --job-name=pps-fetch
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=fetch-opendata-%j.out
#SBATCH --error=fetch-opendata-%j.err

# Job 1 of the real-vs-artificial comparison: puts ~1 TB of CMS Run 2 NanoAOD from CERN Open
# Data (UL2016 NanoAODv9, Run2016H first, then Run2016G) into $OUT_DIR, checks it and writes the
# benchmark's lists. Job 2 (slurm_real_vs_synthetic.sbatch) starts only after this one exits 0;
# test/opendata_helios.sh submits both.
#
#   0. network     can this node reach eospublic.cern.ch at all
#   1. index       opendata_index.py: every file with URI, size, adler32  -> index.csv, scan.txt
#      scan        inventory_files.py over the URIs: schema, entries, PPS -> remote.csv
#   2. select      benchmark columns present, PPS in >= MIN_PPS of events, any schema, eras in
#                  ERAS order, up to MAX_GB (default 1040, the artificial set's size) -> urls.txt
#   3. fetch       fetch_opendata.sh: FETCH_JOBS files at a time, XRD_STREAMS per file, adler32
#                  checked per file; repeated up to FETCH_ATTEMPTS times while files are missing
#   4. verify      inventory_files.py --compare remote.csv: entries and size, file by file
#      lists       make_filelists.py -> core.txt, weak_N.txt, impl.txt, sets.json
#   5. READY       written last, with a summary; its existence means the set is complete
#
# Each step is skipped when its output already exists, so a job that ran out of time is simply
# submitted again. Open Data is public: no account, certificate or proxy is involved.
#
#   sbatch test/slurm_fetch_opendata.sbatch
#   sbatch --export=ALL,FETCH_JOBS=16,XRD_STREAMS=2 test/slurm_fetch_opendata.sbatch
#
# Without network on the compute nodes step 0 stops the job; the same file then runs on the
# login node, in tmux, without Slurm:
#   tmux new -s fetch 'bash test/slurm_fetch_opendata.sbatch 2>&1 | tee fetch-opendata.log'
#
# 16 CPUs: each xrdcp computes adler32 as the data arrive, about a core per stream, and the scan
# opens SCAN_JOBS files at once.

set -euo pipefail

SCRATCH_BENCH="${SCRATCH:-}/bench"
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    # sbatch runs a copy of this file from the spool directory, so its own path says nothing.
    REPO="${REPO:-${SCRATCH_BENCH}/nanoaod-pps-tools}"
else
    REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
fi
if [[ -z "${PY:-}" ]]; then
    export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"
    # See slurm_benchmark.sbatch: the env's deactivate script trips over set -u.
    set +u
    eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
    micromamba activate pps-bench
    set -u
    PY="$(command -v python)"
fi
cd "$REPO"

OUT_DIR="${OUT_DIR:-${SCRATCH_BENCH}/data2}"
MAX_GB="${MAX_GB:-1040}"
ERAS="${ERAS:-Run2016H Run2016G}"
MIN_PPS="${MIN_PPS:-0.01}"
FETCH_JOBS="${FETCH_JOBS:-10}"
XRD_STREAMS="${XRD_STREAMS:-1}"
SCAN_JOBS="${SCAN_JOBS:-16}"
FETCH_ATTEMPTS="${FETCH_ATTEMPTS:-3}"
mkdir -p "$OUT_DIR"
cd "$OUT_DIR"
T="$REPO/test"
read -r -a eras <<<"$ERAS"

stamp() { date +%H:%M:%S; }
echo "=== Open Data -> $OUT_DIR: up to $MAX_GB GB of ${ERAS}, $FETCH_JOBS files x" \
    "$XRD_STREAMS stream(s) [$(stamp)]"
if [[ -f READY ]]; then
    echo "already complete:"
    cat READY
    exit 0
fi

echo "=== 0. network [$(stamp)]"
if command -v xrdfs >/dev/null; then
    reach=(timeout 60 xrdfs eospublic.cern.ch ls /eos/opendata/cms)
else
    reach=(curl -fsS --max-time 60 -o /dev/null "https://opendata.cern.ch/api/records/?size=1")
fi
if ! "${reach[@]}" >/dev/null; then
    echo "ERROR: $(hostname) cannot reach CERN Open Data ('${reach[*]}' failed)." >&2
    echo "       Run this file on the login node instead (see the header), then submit" >&2
    echo "       the benchmark with: bash test/opendata_helios.sh --bench-only" >&2
    exit 1
fi
echo "  $(hostname) reaches CERN Open Data"

echo "=== 1. index and remote scan [$(stamp)]"
if [[ ! -s index.csv || ! -s scan.txt ]]; then
    "$PY" "$T/opendata_index.py" --era "${eras[@]}" --output index.csv.partial \
        --urls scan.txt.partial
    mv scan.txt.partial scan.txt
    mv index.csv.partial index.csv
fi
if [[ ! -s remote.csv ]]; then
    # One ROOT thread per file: the scan waits on the network, not on the CPU.
    "$PY" "$T/inventory_files.py" --list scan.txt --output remote.csv.partial \
        --jobs "$SCAN_JOBS" --threads 1
    mv remote.csv.partial remote.csv
fi

echo "=== 2. selection: up to $MAX_GB GB [$(stamp)]"
if [[ ! -s urls.txt ]]; then
    "$PY" "$T/make_filelists.py" --inventory remote.csv --any-schema --min-pps "$MIN_PPS" \
        --max-gb "$MAX_GB" --era-order "${eras[@]}" --transfer-list urls.txt.partial
    mv urls.txt.partial urls.txt
fi

echo "=== 3. download [$(stamp)]"
fetched=""
for ((attempt = 1; attempt <= FETCH_ATTEMPTS; attempt++)); do
    if bash "$T/fetch_opendata.sh" --urls urls.txt --index index.csv --out-dir "$OUT_DIR" \
        --jobs "$FETCH_JOBS" --streams "$XRD_STREAMS"; then
        fetched=1
        break
    fi
    echo "  attempt $attempt of $FETCH_ATTEMPTS left files missing; retrying [$(stamp)]"
done
if [[ -z "$fetched" ]]; then
    echo "ERROR: files still missing after $FETCH_ATTEMPTS attempts; see $OUT_DIR/failed.txt." >&2
    echo "       Submitting this job again resumes where it stopped." >&2
    exit 1
fi

echo "=== 4. verification and lists [$(stamp)]"
if [[ ! -s local.csv ]]; then
    "$PY" "$T/inventory_files.py" --list local.txt --output local.csv.partial \
        --compare remote.csv --jobs "$SCAN_JOBS" --threads 1
    mv local.csv.partial local.csv
fi
if [[ ! -s sets.json ]]; then
    # core.txt is the whole set: the budget is the download's own, with a margin.
    core_gb="$(awk -v g="$MAX_GB" 'BEGIN { print g * 1.1 + 1 }')"
    "$PY" "$T/make_filelists.py" --inventory local.csv --any-schema --min-pps "$MIN_PPS" \
        --core-gb "$core_gb" --core-events 1e12 --out-dir "$OUT_DIR"
fi

echo "=== 5. READY [$(stamp)]"
"$PY" - local.csv sets.json >READY.partial <<'PYEOF'
import csv, json, sys

rows = [r for r in csv.DictReader(open(sys.argv[1])) if not r.get("error")]
core = json.load(open(sys.argv[2]))["core"]
gb = sum(int(r["size_bytes"]) for r in rows) / 1e9
events = sum(int(r["entries"]) for r in rows)
schemas = sorted({r["schema"] for r in rows})
eras = sorted({r["era"] for r in rows})
pps = sum(float(r["pps_fraction"]) * int(r["entries"]) for r in rows) / max(events, 1)
print(f"files {len(rows)}  GB {gb:.1f}  events {events}  eras {' '.join(eras)}")
print(f"schemas {len(schemas)}: {' '.join(schemas)}")
print(f"events with PPS {pps:.3f}  codec {' '.join(sorted({r['compression'] for r in rows}))}")
print(f"core.txt: {core['files']} files, {core['events']} events, {core['gb']} GB")
PYEOF
mv READY.partial READY
cat READY
echo "done [$(stamp)]. Benchmark: bash test/opendata_helios.sh --bench-only (if not queued yet)"
