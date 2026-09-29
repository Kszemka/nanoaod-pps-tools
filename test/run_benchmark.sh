#!/usr/bin/env bash
#
# Runs the benchmark campaign and collects timing, memory, CPU and I/O metrics into
# $RESULTS/raw.jsonl, then draws the plots. Two datasets, same experiments:
#
#   DATASET=synthetic (default)  the ds_x1..ds_x32 series: N copies of examples/test.root
#   DATASET=real                 Tier0 NanoAOD as .txt file lists from make_filelists.py
#
#   T1  strong scaling   core input (ds_x32 / core.txt), thread count varying  -> Amdahl, USL
#   T2  weak scaling     N threads on N units of work (ds_xN / weak_N.txt)
#   T4  query structure  lazy / eager / Report() x chain length  (single thread, impl input)
#   T5  implementations  RDataFrame / correctionlib / Python / uproot on the impl input,
#                        pinned to one core (PIN_CORE)
#   T6  file width       T1 again on the slim copy of the core input: 6 columns, same events
#   T2S weak on slim     T2 again on slim copies of the weak inputs
#
# T3 is memory and has no runs of its own: every run writes an RSS trace and a peak.
# T1 and T6 include t0, ImplicitMT off, so speedup can be quoted against the fastest serial
# run as well as against ImplicitMT(1).
#
# Each measurement runs in its own process, so the cling JIT cost cannot be amortised across
# repeats; the benchmarks move it into their own "setup"/"jit" phases instead, and only "loop"
# is comparable between implementations.
#
# Usage:
#   MACHINE=ares DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh
#   MACHINE=ares DATASET=real DATA_DIR=$SCRATCH/bench/real ./test/run_benchmark.sh
#   DRY_RUN=1 ./test/run_benchmark.sh    # list the runs without executing them

set -uo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$TEST_DIR")"

# Prefer the repo venv over whatever python3 is on PATH: PyROOT usually lives in exactly one
# interpreter, and picking the wrong one fails late and confusingly.
if [[ -z "${PY:-}" && -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PY="$REPO_ROOT/.venv/bin/python"
fi
PY="${PY:-python3}"

RESULTS="${RESULTS:-$TEST_DIR/results}"
DATA_DIR="${DATA_DIR:-$TEST_DIR/data}"
MACHINE="${MACHINE:-local}"
# 12 and 24 are not decoration: fit_usl needs points either side of the maximum, and with only
# powers of two the region where the curve turns over is three points.
THREADS_LIST="${THREADS_LIST:-1 2 4 8 12 16 24 32 48}"
CHAIN_LENS="${CHAIN_LENS:-1 3 5}"
REPEATS_STRONG="${REPEATS_STRONG:-5}"
REPEATS_WEAK="${REPEATS_WEAK:-3}"
REPEATS_QSTRUCT="${REPEATS_QSTRUCT:-2}"
REPEATS_IMPL="${REPEATS_IMPL:-3}"
REPEATS_SLIM="${REPEATS_SLIM:-3}"
# T5 compares implementations on one core. uproot starts its own threads however its executors
# are set (442-444% CPU on Ares with TrivialExecutor), so the core is enforced from outside.
PIN_CORE="${PIN_CORE:-2}"
# The Python chain on ds_x32 needs ~1100 s. A timeout does not slow anything down -- it only
# decides whether a slow run is recorded or thrown away.
RUN_TIMEOUT="${RUN_TIMEOUT:-2400}"
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-0.1}"

# Inputs are a .root file or a .txt list of them; every benchmark accepts both. Each variable
# can still be overridden on its own.
DATASET="${DATASET:-synthetic}"
case "$DATASET" in
    synthetic)
        DS_CORE="${DS_CORE:-$DATA_DIR/ds_x32.root}"
        DS_IMPL="${DS_IMPL:-$DS_CORE}"
        DS_SLIM="${DS_SLIM:-$DATA_DIR/ds_x32_slim.root}"
        # Clusters per thread are flat to 1% across ds_x1..ds_x32.
        WEAK_PATTERN="${WEAK_PATTERN:-ds_x%s.root}"
        WEAK_SLIM_PATTERN="${WEAK_SLIM_PATTERN:-ds_x%s_slim.root}"
        WEAK_SERIES="${WEAK_SERIES:-1 2 4 8 16 32}"
        ;;
    real)
        DS_CORE="${DS_CORE:-$DATA_DIR/core.txt}"
        # ~11 M events, the size of ds_x32: the Python chain alone is ~20 min there.
        DS_IMPL="${DS_IMPL:-$DATA_DIR/impl.txt}"
        DS_SLIM="${DS_SLIM:-$DATA_DIR/core_slim.txt}"
        # make_filelists.py sizes weak_N to N x (core events / 48); sets.json has the deviations.
        WEAK_PATTERN="${WEAK_PATTERN:-weak_%s.txt}"
        # weak_N lists are subsets of core, so their slim files already exist in slim/.
        WEAK_SLIM_PATTERN="${WEAK_SLIM_PATTERN:-weak_%s_slim.txt}"
        WEAK_SERIES="${WEAK_SERIES:-1 2 4 8 16 32 48}"
        ;;
    *)
        echo "ERROR: DATASET must be 'synthetic' or 'real', not '$DATASET'" >&2
        exit 1
        ;;
esac

weak_input() {
    printf "%s/${WEAK_PATTERN}" "$DATA_DIR" "$1"
}

weak_slim_input() {
    printf "%s/${WEAK_SLIM_PATTERN}" "$DATA_DIR" "$1"
}

# The .root files behind an input: the file itself, or a list's entries with relative paths
# resolved against the list's directory (the rule bench_common.input_files applies).
list_files() {
    local path="$1" base line
    if [[ "$path" != *.txt ]]; then
        echo "$path"
        return
    fi
    base="$(cd "$(dirname "$path")" && pwd)"
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" == \#* ]] && continue
        if [[ "$line" == /* ]]; then echo "$line"; else echo "$base/$line"; fi
    done <"$path"
}

# Only ImplicitMT is allowed to introduce parallelism. Without this the single-threaded Python
# paths were measured at 107-236% CPU, because numpy's BLAS does not ask permission.
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export MACHINE SAMPLE_INTERVAL

if [[ -z "${DRY_RUN:-}" ]] && ! "$PY" -c "import ROOT" 2>/dev/null; then
    echo "ERROR: '$PY' cannot import ROOT. Set PY=/path/to/python with PyROOT." >&2
    exit 1
fi

# Every experiment needs its files, and a missing weak-scaling point would otherwise just
# vanish from the curve.
INPUTS=("$DS_CORE" "$DS_IMPL")
for n in $WEAK_SERIES; do
    INPUTS+=("$(weak_input "$n")")
done
missing=0
for input in "${INPUTS[@]}"; do
    if [[ ! -f "$input" ]]; then
        echo "ERROR: missing $input" >&2
        missing=1
        continue
    fi
    while IFS= read -r file; do
        if [[ ! -f "$file" ]]; then
            echo "ERROR: missing $file (listed in $input)" >&2
            missing=1
        fi
    done < <(list_files "$input")
done
[[ "$missing" -eq 0 || -n "${DRY_RUN:-}" ]] || exit 1

mkdir -p "$RESULTS"
RAW="$RESULTS/raw.jsonl"

TIME_BIN=""
for candidate in /usr/bin/time /usr/local/bin/gtime "$(command -v gtime 2>/dev/null)"; do
    if [[ -x "$candidate" ]] && "$candidate" -v true >/dev/null 2>&1; then
        TIME_BIN="$candidate"
        break
    fi
done
if [[ -z "$TIME_BIN" ]]; then
    echo "WARNING: GNU time -v not found; peak RSS and CPU% come from getrusage only." >&2
fi

TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"

TASKSET_BIN="$(command -v taskset || true)"
if [[ -n "$TASKSET_BIN" ]] && ! "$TASKSET_BIN" -c "$PIN_CORE" true 2>/dev/null; then
    echo "WARNING: cannot pin to core $PIN_CORE; T5 runs unpinned." >&2
    TASKSET_BIN=""
elif [[ -z "$TASKSET_BIN" && -z "${DRY_RUN:-}" ]]; then
    echo "WARNING: taskset not found; T5 runs unpinned and uproot may use several cores." >&2
fi

# run_one <label> <script> [args...]
#
# The RSS trace is written by the benchmark process itself, into $RSS_TRACE: the command is
# wrapped in `timeout` and `/usr/bin/time`, so a pid seen from here would be the wrapper's.
# With PINNED=1 the benchmark process (and every thread it starts) is confined to PIN_CORE.
run_one() {
    local label="$1" script="$2"
    shift 2
    local pinned=""
    [[ -n "${PINNED:-}" && -n "$TASKSET_BIN" ]] && pinned="$PIN_CORE"

    if [[ -n "${DRY_RUN:-}" ]]; then
        DRY_RUN_COUNT=$((${DRY_RUN_COUNT:-0} + 1))
        printf '  [%3d] %-44s %s %s%s\n' "$DRY_RUN_COUNT" "$label" "$script" "$*" \
            "${pinned:+  [core $pinned]}"
        return
    fi

    local time_file stdout_file
    time_file="$(mktemp)"
    stdout_file="$(mktemp)"
    export RSS_TRACE="$RESULTS/rss_${label}.csv"

    local -a cmd=("$PY" "$TEST_DIR/$script" "$@")
    [[ -n "$pinned" ]] && cmd=("$TASKSET_BIN" -c "$pinned" "${cmd[@]}")
    [[ -n "$TIME_BIN" ]] && cmd=("$TIME_BIN" -v -o "$time_file" "${cmd[@]}")
    [[ -n "$TIMEOUT_BIN" ]] && cmd=("$TIMEOUT_BIN" "$RUN_TIMEOUT" "${cmd[@]}")

    echo "  -> $label"
    "${cmd[@]}" >"$stdout_file" 2>/dev/null
    local exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        echo "     FAILED (exit $exit_code) -- recorded as a limit, not dropped" >&2
        printf '{"label":"%s","status":"failed","exit_code":%d,"machine":"%s","timeout_s":%s}\n' \
            "$label" "$exit_code" "$MACHINE" "$RUN_TIMEOUT" >>"$RAW"
        rm -f "$time_file" "$stdout_file"
        return
    fi

    "$PY" - "$stdout_file" "$time_file" "$label" "$pinned" >>"$RAW" <<'PYEOF'
import json, re, sys

stdout_path, time_path, label, pinned = sys.argv[1:5]
record = {}
with open(stdout_path) as f:
    for line in f:
        if line.startswith("BENCH "):
            record = json.loads(line[6:])
record["label"] = label
record["status"] = "ok"
record["pinned_core"] = int(pinned) if pinned else None

patterns = {
    "time_maxrss_kb": (r"Maximum resident set size \(kbytes\):\s*(\d+)", int),
    "cpu_percent": (r"Percent of CPU this job got:\s*(\d+)%", int),
    "elapsed_s": (r"Elapsed \(wall clock\) time.*:\s*(?:(\d+):)?(\d+):([\d.]+)", None),
    "ctx_voluntary": (r"Voluntary context switches:\s*(\d+)", int),
    "ctx_involuntary": (r"Involuntary context switches:\s*(\d+)", int),
}
try:
    text = open(time_path).read()
except OSError:
    text = ""
for key, (pattern, cast) in patterns.items():
    match = re.search(pattern, text)
    if not match:
        continue
    if key == "elapsed_s":
        hours, minutes, seconds = match.groups()
        record[key] = int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)
    else:
        record[key] = cast(match.group(1))
print(json.dumps(record))
PYEOF
    rm -f "$time_file" "$stdout_file"
}

# --exclusive reserves the node, not the filesystem: the inputs are tens of GB on shared Lustre,
# so without this the first run on each file carries a cold read. Reading the whole files
# (rather than running one benchmark) warms every branch the tests touch. make_slim.py writes
# through .partial names, so an existing slim input is always a complete one.
SLIM_INPUTS=("$DS_SLIM")
for n in $WEAK_SERIES; do
    SLIM_INPUTS+=("$(weak_slim_input "$n")")
done
if [[ -z "${DRY_RUN:-}" ]]; then
    if [[ ! -f "$DS_SLIM" ]]; then
        echo "=== writing $(basename "$DS_SLIM") ==="
        "$PY" "$TEST_DIR/make_slim.py" --input "$DS_CORE" --output "$DS_SLIM" || exit 1
    fi
    for n in $WEAK_SERIES; do
        slim_input="$(weak_slim_input "$n")"
        if [[ ! -f "$slim_input" ]]; then
            echo "=== writing $(basename "$slim_input") ==="
            "$PY" "$TEST_DIR/make_slim.py" --input "$(weak_input "$n")" --output "$slim_input" \
                || exit 1
        fi
    done
    echo "=== warming the page cache ==="
    for input in "${INPUTS[@]}" "${SLIM_INPUTS[@]}"; do
        list_files "$input"
    done | sort -u | while IFS= read -r file; do
        cat "$file" >/dev/null
    done
fi

# The page cache is not the only cold thing: the first process of the job also loads ROOT's
# libraries and PCH off Lustre, and in the previous campaign r1_strong_filter_rdf_t1 ran at
# 69% CPU and 13.9 s against 99% and 9.6 s for the same label later. These runs absorb that
# and are never plotted (the plots select on the r<N>_ prefix).
echo "=== discarded warm-up runs ==="
run_one "warmup_filter_rdf" bench_filter.py --input "$DS_CORE" --impl rdf
run_one "warmup_chain_rdf-lazy" bench_chain.py --input "$DS_CORE" --impl rdf-lazy
run_one "warmup_eff_jit" bench_efficiency.py --input "$DS_CORE" --impl jit

# T1: the same events every time, thread count varying. Repeats are the outer loop so that
# slow drift on the node spreads across thread counts instead of landing on one of them.
echo "=== T1 strong scaling on $(basename "$DS_CORE") ==="
for repeat in $(seq 1 "$REPEATS_STRONG"); do
    for threads in 0 $THREADS_LIST; do
        run_one "r${repeat}_strong_filter_rdf_t${threads}" bench_filter.py \
            --input "$DS_CORE" --impl rdf --threads "$threads"
        run_one "r${repeat}_strong_chain_rdf-lazy_t${threads}" bench_chain.py \
            --input "$DS_CORE" --impl rdf-lazy --threads "$threads"
        run_one "r${repeat}_strong_eff_jit_t${threads}" bench_efficiency.py \
            --input "$DS_CORE" --impl jit --threads "$threads"
    done
done

# T2: N threads against N units of work, so each thread keeps the same slice of it. Ideal
# weak scaling is a flat wall-time line.
echo "=== T2 weak scaling: $WEAK_PATTERN on N threads ==="
for repeat in $(seq 1 "$REPEATS_WEAK"); do
    for n in $WEAK_SERIES; do
        weak_ds="$(weak_input "$n")"
        run_one "r${repeat}_weak_filter_rdf_t${n}" bench_filter.py \
            --input "$weak_ds" --impl rdf --threads "$n"
        run_one "r${repeat}_weak_chain_rdf-lazy_t${n}" bench_chain.py \
            --input "$weak_ds" --impl rdf-lazy --threads "$n"
        run_one "r${repeat}_weak_eff_jit_t${n}" bench_efficiency.py \
            --input "$weak_ds" --impl jit --threads "$n"
    done
done

# T4: single-threaded, because the number of event loops is a property of how the query was
# written rather than of the machine.
echo "=== T4 query structure: chain lengths $CHAIN_LENS ==="
for repeat in $(seq 1 "$REPEATS_QSTRUCT"); do
    for len in $CHAIN_LENS; do
        for impl in rdf-lazy rdf-eager rdf-report; do
            run_one "r${repeat}_qstruct_chain_${impl}_l${len}" bench_chain.py \
                --input "$DS_IMPL" --impl "$impl" --chain-len "$len"
        done
    done
done

# T5: every implementation on one input, so the comparison a reader is most likely to
# challenge is "same files, same codec, same events". The Python chain alone costs ~16 min
# on ~11 M events, which is why the impl input is not the (larger) core input on real data,
# and why it runs in the first repeat only. With a single run the RDF chain and efficiency
# came out 12-24% slower than the identical T1 t0 runs, hence the repeats for the rest.
echo "=== T5 implementations on $(basename "$DS_IMPL")${TASKSET_BIN:+, pinned to core $PIN_CORE} ==="
export PINNED=1
for repeat in $(seq 1 "$REPEATS_IMPL"); do
    run_one "r${repeat}_impl_filter_rdf" bench_filter.py --input "$DS_IMPL" --impl rdf
    run_one "r${repeat}_impl_filter_python_vector" bench_filter.py \
        --input "$DS_IMPL" --impl python --mode vector
    run_one "r${repeat}_impl_filter_python_loop" bench_filter.py \
        --input "$DS_IMPL" --impl python --mode loop
    run_one "r${repeat}_impl_filter_uproot" bench_filter.py --input "$DS_IMPL" --impl uproot

    run_one "r${repeat}_impl_chain_rdf-lazy" bench_chain.py --input "$DS_IMPL" --impl rdf-lazy
    if [[ "$repeat" -eq 1 ]]; then
        run_one "r${repeat}_impl_chain_python" bench_chain.py --input "$DS_IMPL" --impl python
    fi
    run_one "r${repeat}_impl_chain_uproot" bench_chain.py --input "$DS_IMPL" --impl uproot

    run_one "r${repeat}_impl_eff_jit" bench_efficiency.py --input "$DS_IMPL" --impl jit
    run_one "r${repeat}_impl_eff_correctionlib" bench_efficiency.py \
        --input "$DS_IMPL" --impl correctionlib
    run_one "r${repeat}_impl_eff_python_vector" bench_efficiency.py \
        --input "$DS_IMPL" --impl python --mode vector
    run_one "r${repeat}_impl_eff_python_loop" bench_efficiency.py \
        --input "$DS_IMPL" --impl python --mode loop
    run_one "r${repeat}_impl_eff_uproot" bench_efficiency.py --input "$DS_IMPL" --impl uproot
done
unset PINNED
# uproot as a user gets it, with whatever threads it starts; a separate, labelled point.
run_one "r1_impl_filter_uproot-default" bench_filter.py --input "$DS_IMPL" --impl uproot \
    --tag own-threads
run_one "r1_impl_chain_uproot-default" bench_chain.py --input "$DS_IMPL" --impl uproot \
    --tag own-threads
run_one "r1_impl_eff_uproot-default" bench_efficiency.py --input "$DS_IMPL" --impl uproot \
    --tag own-threads

# T6: T1's sweep on an input that differs from the core one only in width. If the per-thread
# cost (on ds_x32: ~245 MB RSS and ~55 ms of loop time per extra thread) comes from the ~2000
# branches every worker has to set up, it shrinks here and the speedup peak moves right.
echo "=== T6 file width: $(basename "$DS_SLIM") ==="
for repeat in $(seq 1 "$REPEATS_SLIM"); do
    for threads in 0 $THREADS_LIST; do
        run_one "r${repeat}_slim_filter_rdf_t${threads}" bench_filter.py \
            --input "$DS_SLIM" --impl rdf --threads "$threads"
        run_one "r${repeat}_slim_chain_rdf-lazy_t${threads}" bench_chain.py \
            --input "$DS_SLIM" --impl rdf-lazy --threads "$threads"
        run_one "r${repeat}_slim_eff_jit_t${threads}" bench_efficiency.py \
            --input "$DS_SLIM" --impl jit --threads "$threads"
    done
done

# T2S: T2 on the slim copies. On the full files one unit of work (0.24-0.52 s of loop per
# thread) is smaller than the ~1 s of CPU each worker spends building its ~2000-branch tree,
# so T2 mostly measures that setup. Here the setup is gone and what remains is the scaling of
# the work itself.
echo "=== T2S weak scaling on slim: $WEAK_SLIM_PATTERN on N threads ==="
for repeat in $(seq 1 "$REPEATS_WEAK"); do
    for n in $WEAK_SERIES; do
        weak_ds="$(weak_slim_input "$n")"
        run_one "r${repeat}_weakslim_filter_rdf_t${n}" bench_filter.py \
            --input "$weak_ds" --impl rdf --threads "$n"
        run_one "r${repeat}_weakslim_chain_rdf-lazy_t${n}" bench_chain.py \
            --input "$weak_ds" --impl rdf-lazy --threads "$n"
        run_one "r${repeat}_weakslim_eff_jit_t${n}" bench_efficiency.py \
            --input "$weak_ds" --impl jit --threads "$n"
    done
done

if [[ -n "${DRY_RUN:-}" ]]; then
    echo
    echo "dry run: ${DRY_RUN_COUNT:-0} runs, each capped at ${RUN_TIMEOUT}s"
else
    echo "Records in $RAW"
    "$PY" "$TEST_DIR/plot_results.py" --results "$RESULTS"
fi
