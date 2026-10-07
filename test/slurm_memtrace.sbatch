#!/bin/bash -l
#SBATCH --job-name=pps-memtrace
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --mem=384000
#SBATCH --hint=nomultithread
#SBATCH --time=01:00:00
#SBATCH --exclusive
#SBATCH --output=bench-memtrace-%j.out
#SBATCH --error=bench-memtrace-%j.err

# RSS over time through the event loop, which the earlier campaigns could not record (their
# sampler was a Python thread, starved of the GIL by the C++ loop). Peak RSS against threads on
# the 96 copies of ds_x32 bends: ~350 MB per thread up to 48 threads, about twice a single
# ds_x32, and 110-150 MB above. The traces show whether that is two trees per thread while a
# worker moves to its next file, and fewer live trees when threads wait on Lustre.
#
# The 5-filter chain, cold reads as in full-1tb, THREAD_POINTS, 2 repeats, every SAMPLE_INTERVAL
# seconds. PHASES selects the inputs, one after the other:
#
#   files96   ds_1..ds_96.root (full-1tb's input)       -> results-helios-memtrace-96files
#   file1     ds_x32.root alone (full-11m's input)      -> results-helios-memtrace-1file
#   opendata  the Open Data core.txt, 653 files          -> results-helios-memtrace-opendata
#
# About 20 min. The traces are rss_r<N>_strong_chain_rdf-lazy_t<n>.csv in each directory.
#
#   sbatch test/slurm_memtrace.sbatch
#   sbatch --export=ALL,PHASES="files96 file1" test/slurm_memtrace.sbatch

set -euo pipefail

export MACHINE="${MACHINE:-helios}"
export SCRATCH_BENCH="${SCRATCH}/bench"
export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"
SYNTH_DIR="${SYNTH_DIR:-${SCRATCH_BENCH}/data}"
OPENDATA_DIR="${OPENDATA_DIR:-${SCRATCH_BENCH}/data2}"
PHASES="${PHASES:-files96 file1 opendata}"
THREAD_POINTS="${THREAD_POINTS:-16 48 128 192}"
REPEATS="${REPEATS:-2}"
export SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-0.05}"

has_phase() { [[ " $PHASES " == *" $1 "* ]]; }

# Every input is checked before the node does anything else.
if has_phase files96; then
    copies="$(cat "$SYNTH_DIR/copies.txt" 2>/dev/null || echo 96)"
    for ((i = 1; i <= copies; i++)); do
        if [[ ! -f "$SYNTH_DIR/ds_$i.root" ]]; then
            echo "ERROR: $SYNTH_DIR/ds_$i.root missing: sbatch test/slurm_make_bigset.sbatch" >&2
            exit 1
        fi
    done
fi
if has_phase file1 && [[ ! -f "$SYNTH_DIR/ds_x32.root" ]]; then
    echo "ERROR: $SYNTH_DIR/ds_x32.root missing." >&2
    exit 1
fi
if has_phase opendata && [[ ! -f "$OPENDATA_DIR/READY" ]]; then
    echo "ERROR: $OPENDATA_DIR/READY missing: the Open Data download is not complete." >&2
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
echo "SLURM_CPUS_PER_TASK: ${SLURM_CPUS_PER_TASK:-unset}"
echo "nproc              : $(nproc)"
expected_cpus="${SLURM_CPUS_PER_TASK:-192}"
if [[ "$(nproc)" -lt "$expected_cpus" ]]; then
    echo "ERROR: nproc=$(nproc) but the job asked for $expected_cpus CPUs." >&2
    exit 1
fi
echo "phases             : $PHASES"
echo "threads, repeats   : $THREAD_POINTS, $REPEATS"
echo "sample interval    : ${SAMPLE_INTERVAL}s"
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

if has_phase files96; then
    echo "=== 96 files: ds_1..ds_${copies}.root [$(date +%H:%M:%S)] ==="
    results="${SCRATCH_BENCH}/results-helios-memtrace-96files"
    fresh_results "$results"
    DATASET=big DATA_DIR="$SYNTH_DIR" COLD=1 REPEATS_STRONG="$REPEATS" \
        THREADS_LIST="$THREAD_POINTS" RESULTS="$results" RUN_TIMEOUT=1800 \
        bash test/run_benchmark.sh
fi

if has_phase file1; then
    echo "=== 1 file: ds_x32.root [$(date +%H:%M:%S)] ==="
    results="${SCRATCH_BENCH}/results-helios-memtrace-1file"
    fresh_results "$results"
    # DATASET=synthetic would want the whole ds_x1..ds_x32 series; a one-line list does not.
    lists="${SCRATCH_BENCH}/memtrace-1file"
    mkdir -p "$lists"
    for name in core impl weak_1; do echo "$SYNTH_DIR/ds_x32.root" >"$lists/$name.txt"; done
    DATASET=real DATA_DIR="$lists" WEAK_SERIES=1 CHAIN_ARGS="" COLD=1 REPEATS_STRONG="$REPEATS" \
        THREADS_LIST="$THREAD_POINTS" RESULTS="$results" RUN_TIMEOUT=600 \
        bash test/run_benchmark.sh
fi

if has_phase opendata; then
    echo "=== Open Data: core.txt [$(date +%H:%M:%S)] ==="
    results="${SCRATCH_BENCH}/results-helios-memtrace-opendata"
    fresh_results "$results"
    DATASET=real DATA_DIR="$OPENDATA_DIR" CHAIN_ARGS="--period 2016" COLD=1 \
        REPEATS_STRONG="$REPEATS" THREADS_LIST="$THREAD_POINTS" RESULTS="$results" \
        RUN_TIMEOUT=1800 bash test/run_benchmark.sh
fi

echo "done [$(date +%H:%M:%S)]. Copy results-helios-memtrace-{96files,1file,opendata} to"
echo "results/real-1/; rss_*.csv there now cover the event loop (rss_trace_source statm-process)."
sacct -j "${SLURM_JOB_ID}" --format=JobID,JobName,State,Elapsed,MaxRSS,NCPUS,ReqMem || true
