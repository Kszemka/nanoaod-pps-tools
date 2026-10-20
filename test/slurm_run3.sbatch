#!/bin/bash -l
#SBATCH --job-name=pps-run3
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --mem=384000
#SBATCH --hint=nomultithread
#SBATCH --time=12:00:00
#SBATCH --exclusive
#SBATCH --output=bench-run3-%j.out
#SBATCH --error=bench-run3-%j.err

# One job of the Run 3 campaign: the 11-filter chain (10 branches) on the full original NanoAOD
# files in $SCRATCH/bench/data3, read cold. JOB picks which one. The final campaign runs
# J1, J3 and J4 as steps of slurm_final.sbatch (test/FINAL.md); J2 is not part of it.
#
#   J1  strong11 on core.txt (the whole set), 1-192 threads, and r2/r3 at 80-192 threads
#       (STRONG11_R2_THREADS, STRONG11_R3_THREADS; "" for none), where a run is under a minute
#       and one slow stretch of Lustre would decide a single-run point; first a 1-thread probe
#       on impl.txt (~11 M events) that sets RUN_TIMEOUT
#                                              -> results-helios-run3-chain11
#   J2  weak11, weak_N (N/96 of the set) on N threads, N up to 96; REPEATS_WEAK (default 1)
#       series r1..rN
#                                              -> results-helios-run3-chain11-weak
#   J3  node11: RDataFrame (control) and uproot-pool on the whole set, NODE_THREADS,
#       REPEATS_NODE (default 3) runs each      -> results-helios-run3-node
#   J4  node11: python-pool, the same, into the same directory
#
# The pools take POOL_CHUNK_EVENTS entries of a file per task (default 250000): whole Run 3
# files on 192 Python workers would not fit in the node's memory.
#
# Every job appends with RESUME=1: a resubmitted job runs only what is not yet recorded as ok.
# FRESH=1 moves an existing results directory aside first.
#
# INPUT_GLOB (J1, J3, J4): a wildcard pattern instead of the lists of slurm_fetch_eos.sbatch.
# RDataFrame gets the pattern as it is and opens every match; the job first checks that ROOT
# expands it to the same files as Python's glob, that no match is an incomplete download (sizes
# in $DATA_DIR/run3_sizes.txt, if there), and describes the matches itself (inventory.csv in
# RESULTS: entries for the records, and the compressed size of the chain's ten branches).
#
#   sbatch --export=ALL,JOB=J1 test/slurm_run3.sbatch
#   INPUT_GLOB="$SCRATCH/bench/data3/data/*/*/NANOAOD/*/*/*.root" \
#       RESULTS=$SCRATCH/bench/results-helios-run3-4tb-chain11 \
#       sbatch --partition=plgrid-now --time=12:00:00 --export=ALL,JOB=J1 test/slurm_run3.sbatch
#
# CMS data is not public: it stays on scratch; results hold timings and counts only.

set -euo pipefail

JOB="${JOB:?JOB must be J1, J2, J3 or J4}"
export MACHINE="${MACHINE:-helios}"
SCRATCH_BENCH="${SCRATCH}/bench"
export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"
# The Run 3 files and their lists (test/archive/slurm_fetch_eos.sbatch).
DATA_DIR="${DATA_DIR:-${SCRATCH_BENCH}/data3}"
STRONG_THREADS="${STRONG_THREADS:-1 4 8 12 16 24 32 48 64 80 96 112 128 144 160 176 192}"
WEAK_SERIES="${WEAK_SERIES:-1 2 4 8 16 32 48 64 96}"
NODE_THREADS="${NODE_THREADS:-192}"
REPEAT_THREADS="80 96 112 128 144 160 176 192"
export STRONG11_R2_THREADS="${STRONG11_R2_THREADS-$REPEAT_THREADS}"
export STRONG11_R3_THREADS="${STRONG11_R3_THREADS-$REPEAT_THREADS}"
export REPEATS_NODE="${REPEATS_NODE:-3}"
export POOL_CHUNK_EVENTS="${POOL_CHUNK_EVENTS:-250000}"
export SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-0.05}"

case "$JOB" in
    J1) name=chain11 ;;
    J2) name=chain11-weak ;;
    J3|J4) name=node ;;
    *) echo "ERROR: JOB must be J1, J2, J3 or J4, not '$JOB'." >&2; exit 1 ;;
esac
RESULTS="${RESULTS:-${SCRATCH_BENCH}/results-helios-run3-${name}}"
INPUT_GLOB="${INPUT_GLOB:-}"

if [[ -n "$INPUT_GLOB" && "$JOB" == J2 ]]; then
    echo "ERROR: J2 needs the weak_N lists; INPUT_GLOB is for J1, J3 and J4." >&2
    exit 1
fi
if [[ -z "$INPUT_GLOB" && ! -f "$DATA_DIR/READY" ]]; then
    echo "ERROR: $DATA_DIR/READY missing: the lists and READY are built by test/archive/slurm_fetch_eos.sbatch." >&2
    exit 1
fi

# See slurm_benchmark.sbatch: the env's deactivate script trips over set -u.
set +u
eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
micromamba activate pps-bench
set -u
cd "${SCRATCH_BENCH}/nanoaod-pps-tools"
export PY="$(command -v python)"

echo "=== allocation ==="
echo "job                : $JOB -> $RESULTS"
echo "node               : $(hostname) (${MACHINE})"
echo "SLURM_CPUS_PER_TASK: ${SLURM_CPUS_PER_TASK:-unset}"
echo "nproc              : $(nproc)"
expected_cpus="${SLURM_CPUS_PER_TASK:-192}"
if [[ "$(nproc)" -lt "$expected_cpus" ]]; then
    echo "ERROR: nproc=$(nproc) but the job asked for $expected_cpus CPUs." >&2
    exit 1
fi
echo
[[ -z "$INPUT_GLOB" ]] && cat "$DATA_DIR/READY"
echo

if [[ -n "${FRESH:-}" && -f "$RESULTS/raw.jsonl" ]]; then
    mv "$RESULTS" "$RESULTS-archived-$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$RESULTS"
if [[ -n "$INPUT_GLOB" ]]; then
    echo "=== input: $INPUT_GLOB [$(date +%H:%M:%S)] ==="
    "$PY" - "$INPUT_GLOB" "$DATA_DIR/run3_sizes.txt" "$DATA_DIR" <<'PYEOF' || exit 1
import glob, os, sys

import ROOT

pattern, sizes_path, data_dir = sys.argv[1:]
files = sorted(glob.glob(pattern))
added = ROOT.TChain("Events").Add(pattern)
print(f"  {len(files)} files match (Python glob), ROOT adds {added}")
if not files or added != len(files):
    sys.exit("ERROR: ROOT does not expand the pattern to the files Python's glob finds.")
if os.path.exists(sizes_path):
    prefix = "/eos/cms/store/"
    expected = {}
    with open(sizes_path) as f:
        for line in f:
            path, size = line.split()
            expected[os.path.normpath(os.path.join(data_dir, path[len(prefix):]))] = int(size)
    bad = [p for p in files
           if os.path.normpath(p) in expected and os.path.getsize(p) != expected[os.path.normpath(p)]]
    for p in bad[:5]:
        print(f"  incomplete: {p}")
    if bad:
        sys.exit(f"ERROR: {len(bad)} matches are incomplete downloads; move them out of the pattern.")
    print(f"  every match listed in {os.path.basename(sizes_path)} has its size")
PYEOF
    if [[ ! -s "$RESULTS/inventory.csv" ]]; then
        PYTHONPATH=test "$PY" test/archive/inventory_files.py --input "$INPUT_GLOB" \
            --output "$RESULTS/inventory.csv.partial" --jobs 96 --threads 1 --no-loop \
            2>/dev/null | tail -n 30
        mv "$RESULTS/inventory.csv.partial" "$RESULTS/inventory.csv"
    fi
    "$PY" - "$RESULTS/inventory.csv" <<'PYEOF' || exit 1
import csv, sys

with open(sys.argv[1]) as f:
    rows = list(csv.DictReader(f))
bad = [r for r in rows if r.get("error") or r.get("missing_columns")]
gb = sum(int(r["size_bytes"] or 0) for r in rows) / 1e9
chain_gb = sum(int(r["chain_zip_bytes"] or 0) for r in rows) / 1e9
events = sum(int(r["entries"] or 0) for r in rows)
print(f"  files {len(rows)}  GB {gb:.1f}  events {events}")
print(f"  chain11 branches: {chain_gb:.1f} GB compressed ({100 * chain_gb / max(gb, 1e-9):.2f}% of the set)")
for r in bad[:5]:
    print(f"  unusable: {r['path']}: {r.get('error') or 'missing ' + r['missing_columns']}")
if bad:
    sys.exit(f"ERROR: {len(bad)} files cannot be read by the chain; move them out of the pattern.")
PYEOF
    if [[ ! -f "$RESULTS/dataset.json" ]]; then
        "$PY" test/dataset_json.py --out "$RESULTS" --input "$INPUT_GLOB" \
            --inventory "$RESULTS/inventory.csv"
    fi
    export DS_CORE="$INPUT_GLOB" DS_IMPL="$INPUT_GLOB"
else
    cp "$DATA_DIR/READY" "$DATA_DIR/sets.json" "$RESULTS/"
    if [[ ! -f "$RESULTS/dataset.json" ]]; then
        "$PY" test/dataset_json.py --out "$RESULTS" --input "$DATA_DIR/core.txt" \
            --inventory "$DATA_DIR/local.csv"
    fi
fi

echo "=== correctness [$(date +%H:%M:%S)] ==="
"$PY" test/validate.py --threads 8

export DATASET=real DATA_DIR COLD=1 STORAGE=lustre RESUME=1 RESULTS
export REPEATS_WEAK="${REPEATS_WEAK:-1}"
# The Run 3 cuts (bench_spec.PERIODS["run3"]): the default period's diamond cuts drop almost
# every event of 2024F-2026D.
export CHAIN_ARGS="${CHAIN_ARGS:---period run3}"
# Event counts for the records (n_events, events_per_s), read after the timed phases, from the
# inventory instead of opening every file after every run. The pools count entries themselves.
export EVENT_COUNTS="$DATA_DIR/local.csv"
[[ -n "$INPUT_GLOB" ]] && export EVENT_COUNTS="$RESULTS/inventory.csv"

case "$JOB" in
J1)
    if [[ -n "$INPUT_GLOB" ]]; then
        # No impl.txt to probe on: one thread on ~4.5 TB is ~4 h, so 6 h per run.
        export RUN_TIMEOUT="${RUN_TIMEOUT:-21600}"
    else
        # How long one thread takes on the whole set decides RUN_TIMEOUT for every point: the
        # probe reads impl.txt cold through the same chain and scales by events.
        echo "=== probe: 1 thread on impl.txt [$(date +%H:%M:%S)] ==="
        read -r -a chain_args <<< "${CHAIN_ARGS:-}"
        probe="$("$PY" test/bench_chain.py --input "$DATA_DIR/impl.txt" --impl rdf-lazy \
            --chain long --threads 1 ${chain_args[@]+"${chain_args[@]}"} | sed -n 's/^BENCH //p')"
        timeout_s="$("$PY" - "$probe" "$DATA_DIR/sets.json" <<'PYEOF'
import json, sys

probe, sets = json.loads(sys.argv[1]), json.load(open(sys.argv[2]))
seconds = probe["wall_loop"] * sets["core"]["events"] / probe["n_events"]
print(f"  impl.txt: {probe['n_events']} events, loop {probe['wall_loop']:.1f} s; "
      f"core.txt ({sets['core']['events']} events) at 1 thread: ~{seconds / 60:.0f} min",
      file=sys.stderr)
print(max(2400, int(3 * seconds)))
PYEOF
)"
        export RUN_TIMEOUT="${RUN_TIMEOUT:-$timeout_s}"
    fi
    echo "  RUN_TIMEOUT=${RUN_TIMEOUT}s"
    TESTS=strong11 THREADS_LIST="$STRONG_THREADS" bash test/run_benchmark.sh
    ;;
J2)
    TESTS=weak11 WEAK_SERIES="$WEAK_SERIES" RUN_TIMEOUT="${RUN_TIMEOUT:-7200}" \
        bash test/run_benchmark.sh
    ;;
J3)
    TESTS=node11 NODE_IMPLS="rdf-lazy uproot-pool" NODE_THREADS="$NODE_THREADS" \
        RUN_TIMEOUT="${RUN_TIMEOUT:-10800}" bash test/run_benchmark.sh
    ;;
J4)
    TESTS=node11 NODE_IMPLS=python-pool NODE_THREADS="$NODE_THREADS" \
        RUN_TIMEOUT="${RUN_TIMEOUT:-21600}" bash test/run_benchmark.sh
    ;;
esac

echo "done [$(date +%H:%M:%S)]. Copy $RESULTS to results/run3/${name}/ on the laptop."
sacct -j "${SLURM_JOB_ID}" --format=JobID,JobName,State,Elapsed,MaxRSS,NCPUS,ReqMem || true
