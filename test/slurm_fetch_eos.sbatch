#!/bin/bash -l
#SBATCH --job-name=pps-fetch-eos
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=16G
#SBATCH --time=06:00:00
#SBATCH --output=fetch-eos-%j.out
#SBATCH --error=fetch-eos-%j.err

# The benchmark's lists over the Run 3 files that fetch_eos.sh copied from CERN EOS into $OUT_DIR
# (default $SCRATCH/bench/data3). Nothing here connects to CERN.
#
#   1. check       every file in SIZES is here with its size -> local.txt
#   2. inventory   inventory_files.py: entries, schema, codec, pps_fraction -> local.csv
#      lists       make_filelists.py -> core.txt, weak_N.txt, impl.txt, sets.json
#   3. READY       written last
#
#   tmux new -s run3; CERN_USER=<login> bash test/fetch_eos.sh   # on the login node, first
#   sbatch test/slurm_fetch_eos.sbatch
#
# Each step is skipped when its output exists. With more files in SIZES (a larger selection on
# lxplus), run fetch_eos.sh again and delete local.csv, sets.json and READY before submitting.
#
# CMS data is not public: it stays on scratch, outside the repository.

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
T="$REPO/test"

OUT_DIR="${OUT_DIR:-${SCRATCH_BENCH}/data3}"
SIZES="${SIZES:-run3_sizes.txt}"
SCAN_JOBS="${SCAN_JOBS:-16}"
MIN_PPS="${MIN_PPS:-0.01}"
cd "$OUT_DIR"

stamp() { date +%H:%M:%S; }
fail() { echo "ERROR: $*" >&2; exit 1; }

if [[ -f READY ]]; then
    echo "already complete:"
    cat READY
    exit 0
fi

echo "=== 1. check [$(stamp)]"
[[ -s "$SIZES" ]] || fail "no $SIZES in $OUT_DIR; run fetch_eos.sh on the login node first."
missing=0
while read -r path size; do
    rel="${path#/eos/cms/store/}"
    if [[ "$(stat -c %s "$rel" 2>/dev/null)" != "$size" ]]; then
        ((missing += 1))
        ((missing <= 5)) && echo "  missing or incomplete: $rel"
    fi
done <"$SIZES"
((missing == 0)) || fail "$missing files missing or incomplete; run fetch_eos.sh again."
awk -v d="$OUT_DIR" '{ sub("^/eos/cms/store/", "", $1); print d "/" $1 }' "$SIZES" >local.txt
total_gb="$(awk '{ s += $2 } END { printf "%.1f", s / 1e9 }' "$SIZES")"
echo "  all $(wc -l <local.txt) files have the size from $SIZES: $total_gb GB"

echo "=== 2. inventory and lists [$(stamp)]"
if [[ ! -s local.csv ]]; then
    "$PY" "$T/inventory_files.py" --list local.txt --output local.csv.partial \
        --jobs "$SCAN_JOBS" --threads 1
    mv local.csv.partial local.csv
fi
if [[ ! -s sets.json ]]; then
    # core.txt is the whole set: the budget is the download's own, with a margin.
    core_gb="$(awk -v g="$total_gb" 'BEGIN { print g * 1.1 + 1 }')"
    "$PY" "$T/make_filelists.py" --inventory local.csv --any-schema --min-pps "$MIN_PPS" \
        --core-gb "$core_gb" --core-events 1e12 --out-dir "$OUT_DIR"
fi

echo "=== 3. READY [$(stamp)]"
"$PY" - local.csv sets.json >READY.partial <<'PYEOF'
import csv, json, sys

rows = [r for r in csv.DictReader(open(sys.argv[1])) if not r.get("error")]
core = json.load(open(sys.argv[2]))["core"]
gb = sum(int(r["size_bytes"]) for r in rows) / 1e9
events = sum(int(r["entries"]) for r in rows)
schemas = sorted({r["schema"] for r in rows})
groups = sorted({f"{r['era']}/{r['primary_dataset']}" for r in rows})
pps = sum(float(r["pps_fraction"] or 0) * int(r["entries"]) for r in rows) / max(events, 1)
print(f"files {len(rows)}  GB {gb:.1f}  events {events}  {' '.join(groups)}")
print(f"schemas {len(schemas)}: {' '.join(schemas)}")
print(f"events with PPS {pps:.3f}  codec {' '.join(sorted({r['compression'] for r in rows}))}")
print(f"core.txt: {core['files']} files, {core['events']} events, {core['gb']} GB")
PYEOF
mv READY.partial READY
cat READY
echo "done [$(stamp)]"
