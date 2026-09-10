#!/usr/bin/env bash
#
# Runs the benchmark matrix and collects timing, memory, CPU and I/O metrics.
#
# Each measurement runs in its own process, so the cling JIT cost cannot be amortised across
# repeats; the benchmarks move it into their own "setup" phase instead, and only "loop" is
# comparable between implementations.
#
# Usage:
#   MACHINE=ares DATA_DIR=$SCRATCH/bench/data ./run_benchmark.sh full
#   ./run_benchmark.sh quick        # smoke test on the source file
#   ./run_benchmark.sh validate     # cross-check implementations, no timings

set -uo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$TEST_DIR")"

# Prefer the repo venv over whatever python3 is on PATH: PyROOT usually lives in exactly one
# interpreter, and picking the wrong one fails late and confusingly.
if [[ -z "${PY:-}" && -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PY="$REPO_ROOT/.venv/bin/python"
fi
PY="${PY:-python3}"

if ! "$PY" -c "import ROOT" 2>/dev/null; then
    echo "ERROR: '$PY' cannot import ROOT. Set PY=/path/to/python with PyROOT." >&2
    exit 1
fi

RESULTS="${RESULTS:-$TEST_DIR/results}"
DATA_DIR="${DATA_DIR:-$TEST_DIR/data}"
MACHINE="${MACHINE:-local}"
RUN_TIMEOUT="${RUN_TIMEOUT:-300}"
REPEATS="${REPEATS:-3}"
THREADS_LIST="${THREADS_LIST:-1 2 4 8 16 32 48}"
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-0.1}"

export MACHINE

# Per-implementation datasets. The Python paths are orders of magnitude slower, so forcing them
# onto the same input as the compiled path would blow the per-run timeout; comparisons are made
# through throughput (events/s, tracks/s), never through raw wall time.
# DS_S is the unmodified source file: the Python paths are single-threaded, so its clustering
# is irrelevant to them and re-encoding a 1x copy would buy nothing.
DS_S="${DS_S:-$REPO_ROOT/examples/test.root}"
DS_L="${DS_L:-$DATA_DIR/ds_l.root}"
DS_L_COARSE="${DS_L_COARSE:-$DATA_DIR/ds_l_coarse.root}"
SCALE_SERIES="${SCALE_SERIES:-1 2 4 8 16 32 64}"

mkdir -p "$RESULTS"
RAW="$RESULTS/raw.jsonl"

# Keep the dataset description next to the results: plot_results.py reads the cluster count from
# there, and a results directory copied off the cluster has to stay self-describing.
if [[ -f "$DATA_DIR/dataset_info.json" ]]; then
    cp "$DATA_DIR/dataset_info.json" "$RESULTS/dataset_info.json"
fi

TIME_BIN=""
for candidate in /usr/bin/time /usr/local/bin/gtime "$(command -v gtime 2>/dev/null)"; do
    if [[ -x "$candidate" ]] && "$candidate" -v true >/dev/null 2>&1; then
        TIME_BIN="$candidate"
        break
    fi
done
if [[ -z "$TIME_BIN" ]]; then
    echo "WARNING: GNU time -v not found; peak RSS and CPU%% come from getrusage only." >&2
fi

TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"

sample_rss() {
    local pid="$1" out="$2"
    echo "t_s,rss_kb,pcpu" >"$out"
    local start
    start=$(date +%s.%N)
    while kill -0 "$pid" 2>/dev/null; do
        local line
        line=$(ps -o rss=,pcpu= -p "$pid" 2>/dev/null | tr -s ' ' | sed 's/^ //')
        if [[ -n "$line" ]]; then
            printf '%s,%s\n' "$(echo "$(date +%s.%N) - $start" | bc)" "${line// /,}" >>"$out"
        fi
        sleep "$SAMPLE_INTERVAL"
    done
}

# run_one <label> <script> [args...]
run_one() {
    local label="$1" script="$2"
    shift 2

    local time_file stdout_file rss_csv
    time_file="$(mktemp)"
    stdout_file="$(mktemp)"
    rss_csv="$RESULTS/rss_${label}.csv"

    local -a cmd=("$PY" "$TEST_DIR/$script" "$@")
    [[ -n "$TIME_BIN" ]] && cmd=("$TIME_BIN" -v -o "$time_file" "${cmd[@]}")
    [[ -n "$TIMEOUT_BIN" ]] && cmd=("$TIMEOUT_BIN" "$RUN_TIMEOUT" "${cmd[@]}")

    echo "  -> $label"
    "${cmd[@]}" >"$stdout_file" 2>/dev/null &
    local pid=$!
    sample_rss "$pid" "$rss_csv" &
    local sampler=$!
    wait "$pid"
    local exit_code=$?
    wait "$sampler" 2>/dev/null

    if [[ $exit_code -ne 0 ]]; then
        echo "     FAILED (exit $exit_code) -- recorded as a limit, not dropped" >&2
        printf '{"label":"%s","status":"failed","exit_code":%d,"machine":"%s"}\n' \
            "$label" "$exit_code" "$MACHINE" >>"$RAW"
        rm -f "$time_file" "$stdout_file"
        return
    fi

    "$PY" - "$stdout_file" "$time_file" "$label" >>"$RAW" <<'PYEOF'
import json, re, sys

stdout_path, time_path, label = sys.argv[1], sys.argv[2], sys.argv[3]
record = {}
with open(stdout_path) as f:
    for line in f:
        if line.startswith("BENCH "):
            record = json.loads(line[6:])
record["label"] = label
record["status"] = "ok"

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

require_dataset() {
    if [[ ! -f "$1" ]]; then
        echo "Missing dataset $1 -- run make_dataset.py first (see README.md)." >&2
        return 1
    fi
}

cmd_quick() {
    local input="${QUICK_INPUT:-$REPO_ROOT/examples/test.root}"
    echo "Smoke test on $input"
    run_one "quick_filter_rdf" bench_filter.py --input "$input" --impl rdf
    run_one "quick_filter_python" bench_filter.py --input "$input" --impl python
    run_one "quick_chain_lazy" bench_chain.py --input "$input" --impl rdf-lazy --chain-len 3
    run_one "quick_chain_python" bench_chain.py --input "$input" --impl python --chain-len 3
    run_one "quick_eff_jit" bench_efficiency.py --input "$input" --impl jit
    run_one "quick_eff_python" bench_efficiency.py --input "$input" --impl python
}

cmd_validate() {
    "$PY" "$TEST_DIR/validate.py" --input "${QUICK_INPUT:-$REPO_ROOT/examples/test.root}"
}

cmd_full() {
    require_dataset "$DS_S" || return 1
    require_dataset "$DS_L" || return 1

    local max_threads
    max_threads="$("$PY" "$TEST_DIR/plot_results.py" --max-threads --results "$RESULTS" 2>/dev/null || echo 999)"

    for repeat in $(seq 1 "$REPEATS"); do
        echo "=== repeat $repeat/$REPEATS ==="

        # TEST 1 + TEST 2 + TEST 3, thread sweep on the compiled path.
        for threads in $THREADS_LIST; do
            if [[ "$threads" -gt "$max_threads" ]]; then
                echo "  skipping ${threads} threads: only ~${max_threads} clusters-worth of parallelism"
                continue
            fi
            run_one "r${repeat}_filter_rdf_t${threads}" bench_filter.py \
                --input "$DS_L" --impl rdf --threads "$threads"
            for len in 1 2 3 4 5; do
                for impl in rdf-lazy rdf-eager rdf-report; do
                    run_one "r${repeat}_chain_${impl}_l${len}_t${threads}" bench_chain.py \
                        --input "$DS_L" --impl "$impl" --chain-len "$len" --threads "$threads"
                done
            done
            run_one "r${repeat}_eff_jit_t${threads}" bench_efficiency.py \
                --input "$DS_L" --impl jit --threads "$threads"
        done

        # Python paths: single-threaded by construction (GIL), and on the small dataset.
        run_one "r${repeat}_filter_python_vector" bench_filter.py \
            --input "$DS_S" --impl python --mode vector
        run_one "r${repeat}_filter_python_loop" bench_filter.py \
            --input "$DS_S" --impl python --mode loop
        for len in 1 2 3 4 5; do
            run_one "r${repeat}_chain_python_l${len}" bench_chain.py \
                --input "$DS_S" --impl python --chain-len "$len" --mode vector
        done
        for mode in vector loop; do
            run_one "r${repeat}_eff_python_${mode}" bench_efficiency.py \
                --input "$DS_S" --impl python --mode "$mode"
        done
        run_one "r${repeat}_eff_correctionlib" bench_efficiency.py \
            --input "$DS_S" --impl correctionlib
    done

    cmd_scaling
    cmd_clusters
    cmd_first_read
    "$PY" "$TEST_DIR/plot_results.py" --results "$RESULTS"
}

# Memory and time as a function of dataset size -- the main result, and the one that does not
# depend on cache state or machine load.
cmd_scaling() {
    echo "=== size scaling ==="
    for copies in $SCALE_SERIES; do
        local dataset="$DATA_DIR/ds_x${copies}.root"
        [[ -f "$dataset" ]] || continue
        run_one "scale_eff_jit_x${copies}" bench_efficiency.py --input "$dataset" --impl jit
        run_one "scale_eff_python_x${copies}" bench_efficiency.py --input "$dataset" --impl python
        run_one "scale_chain_rdf_x${copies}" bench_chain.py \
            --input "$dataset" --impl rdf-lazy --chain-len 3
        run_one "scale_chain_python_x${copies}" bench_chain.py \
            --input "$dataset" --impl python --chain-len 3
    done
}

# Control for the thread-scaling plateau. Same size and contents as DS_L, an order of magnitude
# fewer TTree clusters: RDataFrame hands out work per cluster, so if the curve flattens earlier
# here, the plateau belongs to the file layout and not to the code.
cmd_clusters() {
    [[ -f "$DS_L_COARSE" ]] || return 0
    echo "=== cluster-count control ==="
    for threads in $THREADS_LIST; do
        run_one "clusters_fine_t${threads}" bench_efficiency.py \
            --input "$DS_L" --impl jit --threads "$threads" --tag fine
        run_one "clusters_coarse_t${threads}" bench_efficiency.py \
            --input "$DS_L_COARSE" --impl jit --threads "$threads" --tag coarse
    done
}

# Cheap proxy for I/O cost: the first touch of a file reads from storage, later ones from the
# page cache. Replaces a true cold-cache experiment, which would need a dataset several times
# the node's RAM.
cmd_first_read() {
    [[ -f "$DS_L" ]] || return 0
    echo "=== first read vs warm cache ==="
    for attempt in 1 2 3; do
        run_one "cache_eff_jit_a${attempt}" bench_efficiency.py --input "$DS_L" --impl jit
    done
}

case "${1:-full}" in
    quick) cmd_quick ;;
    validate) cmd_validate ;;
    scaling) cmd_scaling ;;
    clusters) cmd_clusters ;;
    cache) cmd_first_read ;;
    full) cmd_full ;;
    *)
        echo "Usage: $0 {quick|validate|scaling|clusters|cache|full}" >&2
        exit 1
        ;;
esac

echo "Records in $RAW"
