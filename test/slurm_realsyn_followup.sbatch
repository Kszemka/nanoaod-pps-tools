#!/bin/bash -l
#SBATCH --job-name=pps-followup
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --mem=384000
#SBATCH --hint=nomultithread
#SBATCH --time=04:00:00
#SBATCH --exclusive
#SBATCH --output=bench-followup-%j.out
#SBATCH --error=bench-followup-%j.err

# After slurm_real_vs_synthetic.sbatch, on the same data, no downloads. Three phases, one after
# the other (PHASES selects them):
#
#   repeats  r2 and r3 of the Open Data sweep, appended to results-helios-opendata-1tb with
#            RESUME=1, so the real curve gets the same min-max whiskers as the artificial one
#   sizes    the same sweep, 3 repeats, on weak_4.txt (~87 M events) and weak_16.txt (~350 M):
#            the real counterparts of full-100m and full-355m on the optimum-vs-size figure
#                                                     -> results-helios-opendata-weak4, -weak16
#   memory   the chain on a list naming ds_x32_head.root (make_head.py: the first 1/32 of
#            ds_x32, same branches and codec, 36 clusters and ~520 k baskets against 1110 and
#            5.04 M, since the copy writes its own baskets) MEM_COPIES times, warm. If
#            the memory per thread follows branches x baskets rather than branches alone, it
#            drops well below ds_x32's ~200 MB here         -> results-helios-memtest
#            It also writes the layouts (branches, baskets per file) of ds_x32.root and of the
#            slim11 set, if still on scratch, into layout-ds_x32/ and layout-slim11/ there.
#
#   sbatch test/slurm_realsyn_followup.sbatch
#   sbatch --export=ALL,PHASES="memory" test/slurm_realsyn_followup.sbatch
#   sbatch --export=ALL,REAL_RESULTS=$PWD/results-helios-opendata-1tb test/slurm_realsyn_followup.sbatch

set -euo pipefail

export MACHINE="${MACHINE:-helios}"
export SCRATCH_BENCH="${SCRATCH}/bench"
export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"
OPENDATA_DIR="${OPENDATA_DIR:-${SCRATCH_BENCH}/data2}"
SYNTH_DIR="${SYNTH_DIR:-${SCRATCH_BENCH}/data}"
MEM_DIR="${MEM_DIR:-${SCRATCH_BENCH}/memtest}"
SLIM_DIR="${SLIM_DIR:-${SCRATCH_BENCH}/slim11}"
PHASES="${PHASES:-repeats sizes memory}"
REAL_THREADS="${REAL_THREADS:-1 2 4 8 16 32 48 64 96 128 144 160 192}"
MEM_THREADS="${MEM_THREADS:-1 8 32 96 192}"
MEM_COPIES="${MEM_COPIES:-384}"
SIZE_LISTS="${SIZE_LISTS:-4 16}"
# Where slurm_real_vs_synthetic.sbatch wrote it; REAL_RESULTS=... if it has been moved since.
REAL_RESULTS="${REAL_RESULTS:-${SCRATCH_BENCH}/results-helios-opendata-1tb}"

has_phase() { [[ " $PHASES " == *" $1 "* ]]; }

# Every input is checked before the node does anything else.
if has_phase repeats || has_phase sizes; then
    if [[ ! -f "$OPENDATA_DIR/READY" ]]; then
        echo "ERROR: $OPENDATA_DIR/READY missing: the Open Data download is not complete." >&2
        exit 1
    fi
fi
if has_phase repeats && [[ ! -f "$REAL_RESULTS/raw.jsonl" ]]; then
    echo "ERROR: $REAL_RESULTS/raw.jsonl missing. Run slurm_real_vs_synthetic.sbatch first, or" >&2
    echo "  point to the moved directory: sbatch --export=ALL,REAL_RESULTS=<dir> $0" >&2
    exit 1
fi
if has_phase sizes; then
    for n in $SIZE_LISTS; do
        if [[ ! -f "$OPENDATA_DIR/weak_${n}.txt" ]]; then
            echo "ERROR: $OPENDATA_DIR/weak_${n}.txt missing." >&2
            exit 1
        fi
    done
fi
if has_phase memory && [[ ! -f "$MEM_DIR/ds_x32_head.root" && ! -f "$SYNTH_DIR/ds_x32.root" ]]; then
    echo "ERROR: neither $MEM_DIR/ds_x32_head.root nor $SYNTH_DIR/ds_x32.root exists." >&2
    exit 1
fi

# See slurm_benchmark.sbatch: the env's deactivate script trips over set -u.
set +u
eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
micromamba activate pps-bench
set -u
cd "${SCRATCH_BENCH}/nanoaod-pps-tools"

echo "=== allocation ==="
echo "node               : $(hostname) (${MACHINE})"
lscpu | grep -E 'Model name|^CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket|NUMA node\(s\)'
echo "SLURM_CPUS_PER_TASK: ${SLURM_CPUS_PER_TASK:-unset}"
echo "nproc              : $(nproc)"
expected_cpus="${SLURM_CPUS_PER_TASK:-192}"
if [[ "$(nproc)" -lt "$expected_cpus" ]]; then
    echo "ERROR: nproc=$(nproc) but the job asked for $expected_cpus CPUs." >&2
    exit 1
fi
echo "phases             : $PHASES"
echo

export PY="$(command -v python)"
export STORAGE=lustre TESTS=strongchain

fresh_results() {
    if [[ -f "$1/raw.jsonl" ]]; then
        mv "$1" "$1-archived-$(date +%Y%m%d_%H%M%S)"
    fi
    mkdir -p "$1"
}

echo "=== correctness [$(date +%H:%M:%S)] ==="
"$PY" test/validate.py --threads 8

if has_phase repeats; then
    echo "=== repeats: Open Data 1 TB, r2 and r3 [$(date +%H:%M:%S)] ==="
    "$PY" test/dataset_json.py --out "$REAL_RESULTS" --input "$OPENDATA_DIR/core.txt" \
        --inventory "$OPENDATA_DIR/local.csv"
    DATASET=real DATA_DIR="$OPENDATA_DIR" CHAIN_ARGS="--period 2016" COLD=1 REPEATS_STRONG=3 \
        RESUME=1 THREADS_LIST="$REAL_THREADS" RESULTS="$REAL_RESULTS" RUN_TIMEOUT=14400 \
        bash test/run_benchmark.sh
fi

if has_phase sizes; then
    for n in $SIZE_LISTS; do
        echo "=== sizes: Open Data weak_${n}.txt [$(date +%H:%M:%S)] ==="
        results="${SCRATCH_BENCH}/results-helios-opendata-weak${n}"
        fresh_results "$results"
        "$PY" test/dataset_json.py --out "$results" --input "$OPENDATA_DIR/weak_${n}.txt" \
            --inventory "$OPENDATA_DIR/local.csv"
        DATASET=real DATA_DIR="$OPENDATA_DIR" DS_CORE="$OPENDATA_DIR/weak_${n}.txt" \
            CHAIN_ARGS="--period 2016" COLD=1 REPEATS_STRONG=3 THREADS_LIST="$REAL_THREADS" \
            RESULTS="$results" RUN_TIMEOUT=7200 bash test/run_benchmark.sh
    done
fi

if has_phase memory; then
    echo "=== memory: ds_x32 head x ${MEM_COPIES} [$(date +%H:%M:%S)] ==="
    mkdir -p "$MEM_DIR"
    if [[ ! -f "$MEM_DIR/ds_x32_head.root" ]]; then
        "$PY" test/make_head.py --input "$SYNTH_DIR/ds_x32.root" --output "$MEM_DIR/ds_x32_head.root"
    fi
    # The lists run_benchmark.sh expects for DATASET=real; only core.txt is measured.
    for ((i = 0; i < MEM_COPIES; i++)); do echo ds_x32_head.root; done >"$MEM_DIR/core.txt"
    echo ds_x32_head.root >"$MEM_DIR/impl.txt"
    echo ds_x32_head.root >"$MEM_DIR/weak_1.txt"
    results="${SCRATCH_BENCH}/results-helios-memtest"
    fresh_results "$results"
    "$PY" test/dataset_json.py --out "$results" --input "$MEM_DIR/core.txt"
    # Layouts of the inputs the earlier campaigns measured, for plot_memory_layout.py's fit.
    if [[ -f "$SYNTH_DIR/ds_x32.root" ]]; then
        "$PY" test/dataset_json.py --out "$results/layout-ds_x32" --input "$SYNTH_DIR/ds_x32.root"
    fi
    slim_ref="$(ls "$SLIM_DIR/ds_1.root" "$SLIM_DIR/unit.root" 2>/dev/null | head -1 || true)"
    if [[ -n "$slim_ref" ]]; then
        "$PY" test/dataset_json.py --out "$results/layout-slim11" --input "$slim_ref"
    else
        echo "  no slim11 file in $SLIM_DIR: give its layout to plot_memory_layout.py by hand"
    fi
    # Warm: memory does not depend on where the bytes come from, and a cold read of one file
    # named 384 times would be a warm read after the first anyway.
    DATASET=real DATA_DIR="$MEM_DIR" WEAK_SERIES=1 CHAIN_ARGS="" COLD="" REPEATS_STRONG=1 \
        THREADS_LIST="$MEM_THREADS" RESULTS="$results" RUN_TIMEOUT=2400 bash test/run_benchmark.sh
fi

echo "done [$(date +%H:%M:%S)]. Copy results-helios-{opendata-1tb,opendata-weak4,opendata-weak16,memtest}"
echo "to results/real-1/, then plot_real_vs_synthetic.py, plot_optimum.py and"
echo "plot_memory_layout.py (test/README.md, Open Data)."
sacct -j "${SLURM_JOB_ID}" --format=JobID,JobName,State,Elapsed,MaxRSS,NCPUS,ReqMem || true
