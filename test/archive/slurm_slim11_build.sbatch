#!/bin/bash -l
#SBATCH --job-name=pps-slim11
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64000
#SBATCH --time=04:00:00
#SBATCH --output=slim11-build-%j.out
#SBATCH --error=slim11-build-%j.err

# Builds the input of the 11-filter campaign: a set whose files hold only the chain's 10
# branches, sized so that the chain reads 1 TB from disk.
#
#   1. ds_x32_slim11.root  ds_x32 (11.1 M events) with the 10 branches, same codec and clusters
#   2. unit.root           hadd -fk of UNIT_COPIES of it (default 28: 310.8 M events, ~10.5 GB).
#                          -fk copies the compressed baskets as they are, so codec and cluster
#                          size stay those of the source; checked below on entries and zip bytes
#   3. probe               the chain on unit.root, cold, one thread: bytes it reads per file and
#                          its loop time, so the number of copies comes from a measurement
#   4. ds_1..ds_N.root     make_bigset.sh, N = ceil(TARGET_BYTES / bytes read per file)
#
# Every step is skipped when its output already exists, so a job that ran out of time can be
# resubmitted as it is.
#
#   sbatch test/slurm_slim11_build.sbatch
#   sbatch --export=ALL,SRC=$SCRATCH/bench/data/ds_x32.root,OUT=$SCRATCH/bench/slim11 test/slurm_slim11_build.sbatch

set -euo pipefail

export SCRATCH_BENCH="${SCRATCH}/bench"
export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"
# See slurm_benchmark.sbatch: the env's deactivate script trips over set -u.
set +u
eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
micromamba activate pps-bench
set -u
cd "${SCRATCH_BENCH}/nanoaod-pps-tools"

PY="$(command -v python)"
SRC="${SRC:-${SCRATCH_BENCH}/data/ds_x32.root}"
OUT="${OUT:-${SCRATCH_BENCH}/slim11}"
UNIT_COPIES="${UNIT_COPIES:-28}"
TARGET_BYTES="${TARGET_BYTES:-1000000000000}"
mkdir -p "$OUT"
SLIM="$OUT/ds_x32_slim11.root"
UNIT="$OUT/unit.root"

echo "=== 1. $(basename "$SRC") -> $(basename "$SLIM") [$(date +%H:%M:%S)]"
if [[ ! -f "$SLIM" ]]; then
    PYTHONPATH=test "$PY" test/archive/make_slim.py --columns chain11 --input "$SRC" --output "$SLIM"
fi
ls -l "$SLIM"

echo "=== 2. unit: hadd -fk of ${UNIT_COPIES} x $(basename "$SLIM") [$(date +%H:%M:%S)]"
if [[ ! -f "$UNIT" ]]; then
    inputs=()
    for ((i = 0; i < UNIT_COPIES; i++)); do inputs+=("$SLIM"); done
    rm -f "${UNIT}.partial.root"
    hadd -fk "${UNIT}.partial.root" "${inputs[@]}" >/dev/null
    "$PY" - "$SLIM" "${UNIT}.partial.root" "$UNIT_COPIES" <<'PYEOF'
import sys
import ROOT

slim_path, unit_path, copies = sys.argv[1], sys.argv[2], int(sys.argv[3])

def describe(path):
    f = ROOT.TFile.Open(path)
    t = f.Get("Events")
    zips = {b.GetName(): b.GetZipBytes("*") for b in t.GetListOfBranches()}
    info = (t.GetEntries(), zips, f.GetCompressionSettings())
    f.Close()
    return info

slim_entries, slim_zip, slim_codec = describe(slim_path)
unit_entries, unit_zip, unit_codec = describe(unit_path)
problems = []
if unit_entries != copies * slim_entries:
    problems.append(f"entries {unit_entries} != {copies} x {slim_entries}")
if set(unit_zip) != set(slim_zip):
    problems.append(f"branches differ: {sorted(set(unit_zip) ^ set(slim_zip))}")
for name, size in slim_zip.items():
    if abs(unit_zip.get(name, 0) - copies * size) > 1e-3 * copies * size:
        problems.append(f"{name}: {unit_zip.get(name)} zip bytes, expected {copies * size}")
if unit_codec != slim_codec:
    problems.append(f"codec {unit_codec} != {slim_codec}")
print(f"unit: {unit_entries} entries, {len(unit_zip)} branches, "
      f"{sum(unit_zip.values()) / 1e9:.3f} GB of baskets, codec {unit_codec}")
if problems:
    print("ERROR: hadd did not copy the baskets unchanged:\n  " + "\n  ".join(problems))
    sys.exit(1)
PYEOF
    mv "${UNIT}.partial.root" "$UNIT"
fi
ls -l "$UNIT"

echo "=== 3. probe: cold, 1 thread, the 11-filter chain on $(basename "$UNIT") [$(date +%H:%M:%S)]"
PROBE="$OUT/probe.json"
if [[ ! -f "$PROBE" ]]; then
    "$PY" - "$UNIT" <<'PYEOF'
import os, sys

fd = os.open(sys.argv[1], os.O_RDONLY)
if hasattr(os, "posix_fadvise"):
    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
else:
    print("WARNING: no posix_fadvise; the probe reads warm", file=sys.stderr)
os.close(fd)
PYEOF
    "$PY" test/bench_chain.py --input "$UNIT" --impl rdf-lazy --chain long --threads 1 \
        | grep '^BENCH ' | cut -c7- >"${PROBE}.partial"
    mv "${PROBE}.partial" "$PROBE"
fi
# At least 96: the weak series on Helios takes one copy per thread up to 96 threads.
MIN_COPIES="${MIN_COPIES:-96}"
COPIES="$("$PY" - "$PROBE" "$TARGET_BYTES" "$MIN_COPIES" <<'PYEOF'
import json, math, sys

record = json.load(open(sys.argv[1]))
target, min_copies = int(sys.argv[2]), int(sys.argv[3])
per_file = record["bytes_loop"]
copies = max(math.ceil(target / per_file), min_copies)
loop = record["wall_loop"]
print(f"probe: {record['n_events']} events, {per_file / 1e9:.3f} GB read "
      f"({per_file / record['input_bytes'] * 100:.2f}% of the file), loop {loop:.0f} s, "
      f"{loop / record['n_events'] * 1e6:.3f} us per event, passed "
      f"{record['checksums']['events_passed']}", file=sys.stderr)
print(f"set: {copies} copies -> {copies * per_file / 1e12:.3f} TB read, "
      f"{copies * record['n_events'] / 1e9:.2f} billion events; "
      f"expected 1-thread loop on the whole set {copies * loop / 3600:.1f} h", file=sys.stderr)
print(copies)
PYEOF
)"

echo "=== 4. ${COPIES} copies of $(basename "$UNIT") [$(date +%H:%M:%S)]"
bash test/archive/make_bigset.sh --source "$UNIT" --copies "$COPIES" --out-dir "$OUT"
# Written last, so its existence means the set is complete. run_benchmark.sh takes BIG_COPIES
# from it, which is what lets the campaign job be queued before this one has measured anything.
echo "$COPIES" >"$OUT/copies.txt"

echo
echo "done [$(date +%H:%M:%S)]. For the campaign: DATA_DIR=$OUT (BIG_COPIES=$COPIES, from copies.txt)"
