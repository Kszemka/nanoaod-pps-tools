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
MAX_CHAIN_LEN="${MAX_CHAIN_LEN:-5}"
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-0.1}"

# Only ImplicitMT is allowed to introduce parallelism. Without this the "single-threaded by
# construction" Python paths were measured at 107-236% CPU, because numpy's BLAS and ROOT's own
# thread pools do not ask permission.
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export MACHINE SAMPLE_INTERVAL

# Per-implementation datasets. The Python paths are orders of magnitude slower, so forcing them
# onto the same input as the compiled path would blow the per-run timeout; comparisons are made
# through throughput (events/s, tracks/s), never through raw wall time.
# DS_S carries the single-threaded paths. It is ds_x1 -- the 1x member of the size series --
# rather than the source file, because decompression happens inside the measured event loop and
# the source is LZMA:9 while every generated dataset is ZSTD:5 (252 MB against 345 MB for the
# same content, per TESTING.md). Running the Python paths on the source and RDataFrame on a
# copy would put the codec inside what is supposed to be an implementation comparison.
DS_S="${DS_S:-$DATA_DIR/ds_x1.root}"
[[ -f "$DS_S" ]] || DS_S="$REPO_ROOT/examples/test.root"
# The thread and chain sweeps run the same work once per thread count and once per chain
# length, so their dataset has to be one that finishes: 8 copies rather than the 40 of ds_l.
# On Ares ds_l cost 1.77 h for 36 runs, of which 11 hit the timeout and produced nothing, and
# in the runs that did finish setup outweighed the event loop (efficiency/jit: 202 s setup
# against 84 s of loop) -- the fixed cost, not the measurement, is what the hours bought.
# On ds_x8 the same three sweeps take 6-14 s per run with setup at ~40%, all of them finish,
# and there is room for REPEATS=3.
#
# Called DS_MAIN and not DS_L because it is not ds_l: the old name survived the switch and
# read as though the campaign still ran on the 40-copy file.
DS_MAIN="${DS_MAIN:-${DS_L:-$DATA_DIR/ds_x8.root}}"
# Matched pair for the cluster-count control: same contents, same size, different clustering.
# The pair has to match in size or the experiment cannot tell clustering apart from volume.
DS_COARSE="${DS_COARSE:-$DATA_DIR/ds_x8_coarse.root}"
SCALE_SERIES="${SCALE_SERIES:-1 2 4 8 16 32}"

# One-dataset mode: every test on the same file, size series skipped. Gives a complete result
# set quickly, and is meant to be repeated per dataset size into separate RESULTS directories,
# which is also how the size comparison gets built up without one long job.
if [[ -n "${BENCH_INPUT:-}" ]]; then
    DS_S="$BENCH_INPUT"
    DS_MAIN="$BENCH_INPUT"
    SCALE_SERIES=""
    echo "single-dataset mode: $BENCH_INPUT"
fi

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

# run_one <label> <script> [args...]
#
# The RSS trace is written by the benchmark process itself, into $RSS_TRACE. It used to be
# sampled from here with `ps -p $!`, but the command is wrapped in `timeout` and
# `/usr/bin/time`, so $! was the wrapper's pid: every trace collected that way is a flat line
# at the ~1.1 MB resident size of `timeout`.
run_one() {
    local label="$1" script="$2"
    shift 2

    # Planning a cluster job means knowing how many runs it is before spending the grant hours.
    # Counting them by reading the script is unreliable, because the thread sweep is capped at
    # run time by the dataset's cluster count and whole blocks are skipped when a file is absent.
    if [[ -n "${DRY_RUN:-}" ]]; then
        DRY_RUN_COUNT=$((${DRY_RUN_COUNT:-0} + 1))
        printf '  [%3d] %-44s %s %s\n' "$DRY_RUN_COUNT" "$label" "$script" "$*"
        return
    fi

    local time_file stdout_file
    time_file="$(mktemp)"
    stdout_file="$(mktemp)"
    export RSS_TRACE="$RESULTS/rss_${label}.csv"

    local -a cmd=("$PY" "$TEST_DIR/$script" "$@")
    [[ -n "$TIME_BIN" ]] && cmd=("$TIME_BIN" -v -o "$time_file" "${cmd[@]}")
    [[ -n "$TIMEOUT_BIN" ]] && cmd=("$TIMEOUT_BIN" "${RUN_TIMEOUT_OVERRIDE:-$RUN_TIMEOUT}" "${cmd[@]}")

    echo "  -> $label"
    "${cmd[@]}" >"$stdout_file" 2>/dev/null
    local exit_code=$?

    if [[ $exit_code -ne 0 ]]; then
        echo "     FAILED (exit $exit_code) -- recorded as a limit, not dropped" >&2
        # Enough fields for plot_results.py to draw it as a censored point rather than to drop
        # it: a run that hit the timeout is a statement about the implementation's limit.
        printf '{"label":"%s","status":"failed","exit_code":%d,"machine":"%s","timeout_s":%s}\n' \
            "$label" "$exit_code" "$MACHINE" "${RUN_TIMEOUT_OVERRIDE:-$RUN_TIMEOUT}" >>"$RAW"
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
    # In a dry run the datasets are usually not built yet -- that is the point of asking how
    # long the job will take before building them.
    if [[ -n "${DRY_RUN:-}" ]]; then
        if [[ ! -f "$1" ]]; then
            echo "  MISSING: $1"
            [[ "$DRY_RUN" == "have" ]] && return 1
        fi
        return 0
    fi
    if [[ ! -f "$1" ]]; then
        echo "Missing dataset $1 -- run make_dataset.py first (see README.md)." >&2
        return 1
    fi
    # plot_results.py reads the cluster count and file size of the dataset actually used, so a
    # dataset missing from dataset_info.json silently turns the thread-scaling cap and the
    # bytes-read annotation into numbers taken from some other file.
    #
    # Only enforced when a description file exists at all: with none, the plots fall back to
    # printing no cap, which is honest. A file that exists but omits this dataset is the
    # dangerous case, because then the fallback is another dataset's numbers.
    [[ -f "$RESULTS/dataset_info.json" ]] || return 0
    if ! "$PY" "$TEST_DIR/plot_results.py" --describes "$1" --results "$RESULTS" >/dev/null; then
        echo "Dataset $1 is not described in $RESULTS/dataset_info.json." >&2
        echo "Re-run make_all_datasets.sh (it appends a description per file)." >&2
        return 1
    fi
}

# For blocks that are skipped rather than fatal when their dataset is absent.
#
# Two planning questions need opposite answers here, so DRY_RUN has two modes:
#
#   DRY_RUN=1     assume every dataset exists -- "how long is the full campaign", asked before
#                 spending hours generating the inputs
#   DRY_RUN=have  count only what the files on disk allow -- "what would tonight's run
#                 actually produce", which is the question when the set is incomplete and
#                 whole experiments would silently skip
have_dataset() {
    if [[ "${DRY_RUN:-}" == "have" ]]; then
        if [[ ! -f "$1" ]]; then
            echo "  SKIP: $(basename "$1") is missing -- this whole block would not run"
            return 1
        fi
        return 0
    fi
    [[ -n "${DRY_RUN:-}" || -f "$1" ]]
}

cmd_quick() {
    local input="${QUICK_INPUT:-$REPO_ROOT/examples/test.root}"
    echo "Smoke test on $input"
    run_one "quick_filter_rdf" bench_filter.py --input "$input" --impl rdf
    run_one "quick_filter_python" bench_filter.py --input "$input" --impl python
    run_one "quick_filter_uproot" bench_filter.py --input "$input" --impl uproot
    run_one "quick_chain_lazy" bench_chain.py --input "$input" --impl rdf-lazy --chain-len 3
    run_one "quick_chain_python" bench_chain.py --input "$input" --impl python --chain-len 3
    run_one "quick_chain_uproot" bench_chain.py --input "$input" --impl uproot --chain-len 3
    run_one "quick_eff_jit" bench_efficiency.py --input "$input" --impl jit
    run_one "quick_eff_python" bench_efficiency.py --input "$input" --impl python
    run_one "quick_eff_uproot" bench_efficiency.py --input "$input" --impl uproot
    run_one "quick_select" bench_selectivity.py --input "$input" --impl contiguous
}

cmd_validate() {
    "$PY" "$TEST_DIR/validate.py" --input "${QUICK_INPUT:-$REPO_ROOT/examples/test.root}"
}

cmd_full() {
    require_dataset "$DS_S" || return 1
    require_dataset "$DS_MAIN" || return 1

    local max_threads
    max_threads="$("$PY" "$TEST_DIR/plot_results.py" --max-threads --for-input "$DS_MAIN" \
        --results "$RESULTS" 2>/dev/null || echo 999)"

    for repeat in $(seq 1 "$REPEATS"); do
        echo "=== repeat $repeat/$REPEATS ==="

        # Thread sweep: one representative run per test. The chain-length sweep is deliberately
        # not repeated per thread count -- it measures bytes read and event-loop counts, which
        # are deterministic and thread-independent, so running it seven times only costs time.
        for threads in $THREADS_LIST; do
            if [[ "$threads" -gt "$max_threads" ]]; then
                echo "  skipping ${threads} threads: only ~${max_threads} clusters-worth of parallelism"
                continue
            fi
            run_one "r${repeat}_filter_rdf_t${threads}" bench_filter.py \
                --input "$DS_MAIN" --impl rdf --threads "$threads"
            run_one "r${repeat}_chain_rdf-lazy_l${MAX_CHAIN_LEN}_t${threads}" bench_chain.py \
                --input "$DS_MAIN" --impl rdf-lazy --chain-len "$MAX_CHAIN_LEN" --threads "$threads"
            run_one "r${repeat}_eff_jit_t${threads}" bench_efficiency.py \
                --input "$DS_MAIN" --impl jit --threads "$threads"
        done

        # Chain-length sweep: single-threaded, where lazy/eager/report differ.
        for len in $(seq 1 "$MAX_CHAIN_LEN"); do
            for impl in rdf-lazy rdf-eager rdf-report; do
                run_one "r${repeat}_chain_${impl}_l${len}" bench_chain.py \
                    --input "$DS_MAIN" --impl "$impl" --chain-len "$len"
            done
        done

        # Predicate compilation style: the same query with the RVec expressions moved out of
        # the Filter() string into pre-declared functions. Isolates how much of the fixed cost
        # is cling compiling the predicate body.
        for style in jit callable; do
            run_one "r${repeat}_chain_style-${style}" bench_chain.py \
                --input "$DS_MAIN" --impl rdf-lazy --chain-len "$MAX_CHAIN_LEN" \
                --filter-style "$style" --tag "$style"
        done

        # Filter order. RDataFrame never reorders predicates, so this is the user's decision
        # and it costs something; every order returns the same counts, which validate.py checks.
        #
        # Only at the full chain length: a truncated chain in a different order applies a
        # different set of filters, so bench_chain.py rejects the combination outright rather
        # than quietly comparing two different queries.
        if [[ "$MAX_CHAIN_LEN" -eq 5 ]]; then
            for order in notebook selective-first; do
                run_one "r${repeat}_chain_order-${order}" bench_chain.py \
                    --input "$DS_MAIN" --impl rdf-lazy --chain-len "$MAX_CHAIN_LEN" \
                    --chain-order "$order" --tag "$order"
            done
        fi

        # Does row selectivity ever reduce I/O? See bench_selectivity.py.
        for selection in scattered contiguous; do
            run_one "r${repeat}_select_${selection}" bench_selectivity.py \
                --input "$DS_MAIN" --impl "$selection" --tag "$selection"
        done

        # Python paths: single-threaded by construction (GIL), and on the small dataset.
        # DS_S is ds_x1 rather than the source file so that it shares the series' compression:
        # decompression happens inside the measured loop, so comparing a ZSTD file against the
        # LZMA source would put the codec inside the implementation comparison.
        run_one "r${repeat}_filter_python_vector" bench_filter.py \
            --input "$DS_S" --impl python --mode vector
        run_one "r${repeat}_filter_python_loop" bench_filter.py \
            --input "$DS_S" --impl python --mode loop
        run_one "r${repeat}_filter_uproot" bench_filter.py \
            --input "$DS_S" --impl uproot
        for len in $(seq 1 "$MAX_CHAIN_LEN"); do
            run_one "r${repeat}_chain_python_l${len}" bench_chain.py \
                --input "$DS_S" --impl python --chain-len "$len" --mode vector
            run_one "r${repeat}_chain_uproot_l${len}" bench_chain.py \
                --input "$DS_S" --impl uproot --chain-len "$len" --mode vector
        done
        # Short-circuiting is what RDataFrame does between chain steps; the plain vector mode
        # evaluates every step on every event, so without this the time-vs-length curves of the
        # two sides are not comparable.
        run_one "r${repeat}_chain_python_shortcircuit" bench_chain.py \
            --input "$DS_S" --impl python --chain-len "$MAX_CHAIN_LEN" --mode vector-shortcircuit
        run_one "r${repeat}_chain_uproot_shortcircuit" bench_chain.py \
            --input "$DS_S" --impl uproot --chain-len "$MAX_CHAIN_LEN" --mode vector-shortcircuit

        for mode in vector loop; do
            run_one "r${repeat}_eff_python_${mode}" bench_efficiency.py \
                --input "$DS_S" --impl python --mode "$mode"
        done
        run_one "r${repeat}_eff_uproot" bench_efficiency.py --input "$DS_S" --impl uproot
        run_one "r${repeat}_eff_correctionlib" bench_efficiency.py \
            --input "$DS_S" --impl correctionlib
    done

    cmd_scaling
    cmd_clusters
    cmd_layout
    cmd_rntuple
    cmd_first_read
    [[ -n "${DRY_RUN:-}" ]] || "$PY" "$TEST_DIR/plot_results.py" --results "$RESULTS"
}

# The same queries against the same events stored as an RNTuple. Everything this benchmark
# reports about how much RDataFrame reads is mediated by TTree's baskets, clusters and
# TTreeCache; RNTuple has none of those, so it says which findings are about RDataFrame and
# which are about the format underneath it.
cmd_rntuple() {
    local dataset="${RNTUPLE_INPUT:-$DATA_DIR/ds_x8_rntuple.root}"
    have_dataset "$dataset" || return 0
    echo "=== RNTuple against TTree ==="
    for threads in 1 8; do
        run_one "rntuple_filter_t${threads}" bench_filter.py \
            --input "$dataset" --format rntuple --impl rdf --threads "$threads" --tag rntuple
        run_one "rntuple_chain_t${threads}" bench_chain.py \
            --input "$dataset" --format rntuple --impl rdf-lazy \
            --chain-len "$MAX_CHAIN_LEN" --threads "$threads" --tag rntuple
        # TTree arm of the same comparison, so the pair is measured in the same job on the
        # same node rather than against numbers from a different run.
        run_one "ttree_filter_t${threads}" bench_filter.py \
            --input "$DS_MAIN" --impl rdf --threads "$threads" --tag ttree
        run_one "ttree_chain_t${threads}" bench_chain.py \
            --input "$DS_MAIN" --impl rdf-lazy --chain-len "$MAX_CHAIN_LEN" \
            --threads "$threads" --tag ttree
    done
}

# Memory and time as a function of dataset size -- the main result, and the one that does not
# depend on cache state or machine load.
cmd_scaling() {
    echo "=== size scaling ==="
    for copies in $SCALE_SERIES; do
        local dataset="$DATA_DIR/ds_x${copies}.root"
        have_dataset "$dataset" || continue
        run_one "scale_eff_jit_x${copies}" bench_efficiency.py --input "$dataset" --impl jit
        run_one "scale_eff_python_x${copies}" bench_efficiency.py --input "$dataset" --impl python
        run_one "scale_eff_uproot_x${copies}" bench_efficiency.py --input "$dataset" --impl uproot
        run_one "scale_chain_rdf_x${copies}" bench_chain.py \
            --input "$dataset" --impl rdf-lazy --chain-len 3
        # The Python chain is both the slowest thing in the campaign and the whole point of
        # the memory plot, so it gets a timeout that grows with the dataset.
        #
        # A timeout is not a censored point here. For a time measurement "did not finish in
        # 300 s" is still a lower bound and plot_results.py draws it, but the process dies
        # before printing its BENCH line, so peak_rss_kb is never recorded at all -- the
        # largest points, the ones the RSS-vs-size plot exists to show, would simply be
        # missing. Measured 10130 events/s at 8 copies, i.e. 276 s, which is also why the flat
        # 300 s is not merely too small for x16 and x32: x8 sits 8% under it.
        #
        # Never below RUN_TIMEOUT, so a caller who raised it globally -- as
        # slurm_benchmark.sbatch does -- keeps the more generous limit. This scaling exists to
        # stop the default from deleting the large points, not to impose a tighter ceiling on
        # someone who already thought about it.
        scaled_timeout=$(( copies * 45 + 120 ))
        RUN_TIMEOUT_OVERRIDE=$(( scaled_timeout > RUN_TIMEOUT ? scaled_timeout : RUN_TIMEOUT ))
        run_one "scale_chain_python_x${copies}" bench_chain.py \
            --input "$dataset" --impl python --chain-len 3
        unset RUN_TIMEOUT_OVERRIDE
        # uproot is the implementation the memory plot is really about: it materialises the
        # columns too, but as flat buffers rather than one Python object per event, so it
        # separates "materialising is expensive" from "PyROOT's per-event objects are".
        run_one "scale_chain_uproot_x${copies}" bench_chain.py \
            --input "$dataset" --impl uproot --chain-len 3
    done
}

# Control for the thread-scaling plateau. Same size and contents, an order of magnitude fewer
# TTree clusters: RDataFrame hands out work per cluster, so if the curve flattens earlier here,
# the plateau belongs to the file layout and not to the code.
#
# The pair must match in event count. Comparing a fine-clustered 8-copy file against a
# coarse-clustered 40-copy one would let volume masquerade as clustering -- exactly the
# confounding this experiment exists to rule out -- so the mismatch is a hard error.
cmd_clusters() {
    local fine="${CLUSTER_FINE:-$DS_MAIN}"
    local coarse="${CLUSTER_COARSE:-$DS_COARSE}"
    have_dataset "$coarse" && have_dataset "$fine" || return 0
    if [[ -z "${DRY_RUN:-}" ]] \
       && ! "$PY" "$TEST_DIR/plot_results.py" --same-size "$fine" "$coarse" --results "$RESULTS"; then
        echo "ERROR: cluster-control pair differs in event count -- skipping." >&2
        return 1
    fi
    echo "=== cluster-count control ==="
    for threads in $THREADS_LIST; do
        run_one "clusters_fine_t${threads}" bench_efficiency.py \
            --input "$fine" --impl jit --threads "$threads" --tag fine
        run_one "clusters_coarse_t${threads}" bench_efficiency.py \
            --input "$coarse" --impl jit --threads "$threads" --tag coarse
    done
}

# Where the read amplification comes from. Measured on the source NanoAOD, the full chain reads
# 1.04x the compressed size of the branches it names -- no amplification at all -- while on
# ds_l it reached ~560x. Same events, different file, so the cause is layout. These runs vary
# one candidate at a time:
#
#   default - the 8-copy file the rest of the campaign uses
#   slim    - same content, only the 9 branches any test reads
#   coarse  - same content, all branches, 25x larger autoflush and therefore larger baskets
#
# each with TTreeCache on and off, which separates basket granularity from the cache's
# read-ahead as the explanation.
cmd_layout() {
    echo "=== read amplification vs file layout ==="
    for variant in "" _slim _coarse; do
        local dataset="$DATA_DIR/ds_x8${variant}.root"
        have_dataset "$dataset" || continue
        local tag="${variant:-_default}"
        tag="${tag#_}"
        run_one "layout_${tag}_cache-on" bench_chain.py \
            --input "$dataset" --impl rdf-lazy --chain-len "$MAX_CHAIN_LEN" --tag "$tag"
        run_one "layout_${tag}_cache-off" bench_chain.py \
            --input "$dataset" --impl rdf-lazy --chain-len "$MAX_CHAIN_LEN" \
            --tree-cache off --tag "${tag}-nocache"
    done
}

# Cold storage read against a warm page cache. The old version ran the same warm file three
# times and measured 0.901/0.894/0.936 s -- i.e. nothing at all. --no-cache evicts the file
# first (posix_fadvise, Linux only), which is a real cold read without needing a dataset
# several times the size of the node's RAM.
cmd_first_read() {
    have_dataset "$DS_MAIN" || return 0
    echo "=== cold read vs warm cache ==="
    run_one "cache_cold" bench_efficiency.py --input "$DS_MAIN" --impl jit --no-cache --tag cold
    for attempt in 1 2; do
        run_one "cache_warm_a${attempt}" bench_efficiency.py \
            --input "$DS_MAIN" --impl jit --tag warm
    done
}

case "${1:-full}" in
    quick) cmd_quick ;;
    validate) cmd_validate ;;
    scaling) cmd_scaling ;;
    clusters) cmd_clusters ;;
    layout) cmd_layout ;;
    rntuple) cmd_rntuple ;;
    cache) cmd_first_read ;;
    full) cmd_full ;;
    *)
        echo "Usage: $0 {quick|validate|scaling|clusters|layout|rntuple|cache|full}" >&2
        exit 1
        ;;
esac

if [[ -n "${DRY_RUN:-}" ]]; then
    echo
    echo "dry run: ${DRY_RUN_COUNT:-0} runs, each capped at ${RUN_TIMEOUT}s"
    echo "worst case ${DRY_RUN_COUNT:-0} x ${RUN_TIMEOUT}s = $(( ${DRY_RUN_COUNT:-0} * RUN_TIMEOUT / 3600 ))h"
else
    echo "Records in $RAW"
fi
