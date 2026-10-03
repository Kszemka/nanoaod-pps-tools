#!/usr/bin/env bash
#
# Runs the benchmark campaign and collects timing, memory, CPU and I/O metrics into
# $RESULTS/raw.jsonl, then draws the plots. Two datasets, same experiments:
#
#   DATASET=synthetic (default)  the ds_x1..ds_x32 series: N copies of examples/test.root
#   DATASET=real                 Tier0 NanoAOD as .txt file lists from make_filelists.py
#   DATASET=big                  ~1 TB: ds_1..ds_96.root, plain copies of ds_x32.root from
#                                make_bigset.sh, one repeat each, read cold (COLD=1); T1/T2 on
#                                up to 1 TB, T4 on ~100 GB and the size series (TESTS)
#
# TESTS selects the experiments; ONLY_USED=1 additionally drops the implementations no figure
# uses. Both default per dataset, see below.
#
#   T1  strong scaling   core input (ds_x32 / core.txt), thread count varying  -> Amdahl, USL
#   T2  weak scaling     N threads on N units of work (ds_xN / weak_N.txt)
#   T4  query structure  lazy / eager / Report() x chain length  (single thread, impl input)
#   T5  implementations  RDataFrame / correctionlib / Python / uproot on the impl input,
#                        pinned to one core (PIN_CORE)
#   T6  file width       T1 again on the slim copy of the core input: 6 columns, same events
#   T2S weak on slim     T2 again on slim copies of the weak inputs
#   size / sizepy        T5 against input size (DATASET=big only): RDataFrame and uproot, and
#                        separately Python, pinned to one core on 1..9 copies (~11-98 GB)
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
#   MACHINE=ares DATASET=big  DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh
#   DRY_RUN=1 ./test/run_benchmark.sh    # list the runs without executing them
#
# RESUME=1 appends to an existing $RESULTS/raw.jsonl and skips every label already recorded
# there as ok: a job that ran out of wall clock, or a second job adding TESTS=sizepy to the
# first one's results, runs only what is missing. Failed runs are retried; warm-ups always run.

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

# DATASET=big is one pass over ~1 TB rather than a campaign that can afford repeats: a single
# strong-scaling sweep there is already ~2 h. It also defaults to cold reads (see COLD below)
# and to the variants the thesis actually plots (ONLY_USED).
DATASET="${DATASET:-synthetic}"
if [[ "$DATASET" == big ]]; then
    REPEATS_STRONG="${REPEATS_STRONG:-1}"
    REPEATS_WEAK="${REPEATS_WEAK:-1}"
    REPEATS_QSTRUCT="${REPEATS_QSTRUCT:-1}"
    REPEATS_IMPL="${REPEATS_IMPL:-1}"
    REPEATS_SLIM="${REPEATS_SLIM:-1}"
    COLD="${COLD:-1}"
    ONLY_USED="${ONLY_USED:-1}"
    # Only what ds_x32 could not answer:
    #   strong, weak  on up to the whole 1 TB;
    #   qstruct  on impl.txt, ~100 GB: rdf-eager reads its input up to six times, which on the
    #            whole set would be 6 TB;
    #   size     T5 as a series of sizes instead of one input: the Python and uproot paths
    #            materialise whole columns, so on 1 TB they would die on memory;
    #   sizepy   the Python half of that series, ~9 h and the only runs that can run out of
    #            memory, so it is a second job (TESTS=sizepy RESUME=1) rather than part of this.
    # slim and weakslim, the file-width experiment, do not depend on the input size.
    TESTS="${TESTS:-strong weak qstruct size}"
fi
# Copies per point of the size and sizepy series (DATASET=big).
SIZE_SERIES="${SIZE_SERIES:-1 2 4 6 8 9}"
RESUME="${RESUME:-}"
# The discarded warm-up runs absorb the first process's cold ROOT libraries. Without them that
# cost lands on the first measured run (r1_strong_filter_rdf_t0).
WARMUP_RUNS="${WARMUP_RUNS:-1}"
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
# COLD=1 drops the inputs' pages from the page cache before every run, so each run reads them
# from the file system instead of from RAM. Only meaningful on a set of distinct files: see
# make_bigset.sh for why the 1 TB input is copies rather than one file named many times.
COLD="${COLD:-}"
# ONLY_USED=1 runs just the implementations that end up in a figure or a number in the thesis.
ONLY_USED="${ONLY_USED:-}"
# Which experiments to run, in the order below. Names are the ones that appear in the labels:
#   strong    T1  thread sweep on the core input        -> Amdahl, USL, efficiency, RSS, cores
#   weak      T2  N threads on N units of work
#   qstruct   T4  lazy vs eager vs Report(), 1 thread
#   impl      T5  RDataFrame vs Python vs uproot, pinned to one core
#   slim      T6  T1 again on the 6-column copy         -> where the ceiling comes from
#   weakslim  T2S T2 again on the 6-column copies
#   size      T5's RDataFrame and uproot runs on each point of SIZE_SERIES (DATASET=big)
#   sizepy    T5's Python runs on the same points, smallest first (DATASET=big)
#   strong11  T1 for the 11-filter chain alone (bench_chain --chain long), on the slim set
#             whose files hold just its 10 branches (DATASET=big, DATA_DIR=<slim set>)
#   weak11    T2 for the same chain on the same set
TESTS="${TESTS:-strong weak qstruct impl slim weakslim}"

# has_test <name>
has_test() {
    [[ " $TESTS " == *" $1 "* ]]
}
for requested in $TESTS; do
    case "$requested" in
        strong|weak|qstruct|impl|slim|weakslim) ;;
        size|sizepy|strong11|weak11)
            if [[ "$DATASET" != big ]]; then
                echo "ERROR: TESTS=$requested needs DATASET=big (the ds_N.root copies)." >&2
                exit 1
            fi
            ;;
        *) echo "ERROR: unknown test '$requested' in TESTS." >&2; exit 1 ;;
    esac
done

# The slim set holds only the 11-filter chain's branches, so nothing else can run on it: the
# 5-filter chain and the filter would, but they are measured on the full files, and the
# efficiency column's x/y are not there at all.
ONLY_CHAIN11=1
for requested in $TESTS; do
    [[ "$requested" == strong11 || "$requested" == weak11 ]] || ONLY_CHAIN11=""
done
# T1 for the long chain: no t0 (its ImplicitMT(1) penalty is measured on the full files) and no
# t2, which on 1 TB costs half a t1. STRONG11_R2_THREADS are measured a second time, after the
# whole first sweep, so the repeat sees the node at a different moment. STRONG11_R3_THREADS
# give a third run where the first two disagree, so the median no longer averages an outlier.
STRONG11_THREADS="${STRONG11_THREADS:-$(for t in $THREADS_LIST; do
    [[ "$t" == 0 || "$t" == 2 ]] || printf '%s ' "$t"; done)}"
STRONG11_R2_THREADS="${STRONG11_R2_THREADS:-}"
STRONG11_R3_THREADS="${STRONG11_R3_THREADS:-}"
# The same for weak11: points of WEAK_SERIES measured once more, labelled r3.
WEAK11_R3_SERIES="${WEAK11_R3_SERIES:-}"

# Inputs are a .root file or a .txt list of them; every benchmark accepts both. Each variable
# can still be overridden on its own.
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
    big)
        # ds_1.root .. ds_$BIG_COPIES.root in DATA_DIR, from make_bigset.sh. The lists over
        # them are written below into lists/, so the layout is the same as `real` and nothing
        # further down has to know which of the two it is running on.
        # The slim set's build job writes copies.txt: its count comes from a measurement.
        BIG_COPIES="${BIG_COPIES:-$(cat "$DATA_DIR/copies.txt" 2>/dev/null || echo 96)}"
        # T4's input: rdf-eager reads it up to six times, which on the whole set would be 6 TB.
        IMPL_COPIES="${IMPL_COPIES:-9}"
        DS_CORE="${DS_CORE:-$DATA_DIR/lists/core.txt}"
        DS_IMPL="${DS_IMPL:-$DATA_DIR/lists/impl.txt}"
        DS_SLIM="${DS_SLIM:-$DATA_DIR/lists/core_slim.txt}"
        WEAK_PATTERN="${WEAK_PATTERN:-lists/weak_%s.txt}"
        WEAK_SLIM_PATTERN="${WEAK_SLIM_PATTERN:-lists/weak_%s_slim.txt}"
        SIZE_PATTERN="${SIZE_PATTERN:-lists/size_%s.txt}"
        WEAK_SERIES="${WEAK_SERIES:-1 2 4 8 16 32 48}"
        # Copies per thread at each weak point. 2 on Ares, where 48 threads x 2 is the whole
        # set; 1 on Helios, where 96 threads x 1 is, and 192 threads at 2 would need 4 TB.
        WEAK_UNIT="${WEAK_UNIT:-2}"
        if has_test slim || has_test weakslim; then
            echo "ERROR: DATASET=big has no slim copies; TESTS=slim/weakslim run on ds_x32." >&2
            exit 1
        fi
        # WEAK_UNIT x N distinct copies at N threads: without them the largest weak points
        # would reuse files and stop being a weak-scaling series.
        for n in $WEAK_SERIES; do
            if [[ $((WEAK_UNIT * n)) -gt "$BIG_COPIES" ]]; then
                echo "ERROR: weak point $n needs $((WEAK_UNIT * n)) copies, BIG_COPIES is $BIG_COPIES." >&2
                exit 1
            fi
        done
        for n in $IMPL_COPIES $SIZE_SERIES; do
            if [[ "$n" -gt "$BIG_COPIES" ]]; then
                echo "ERROR: $n copies asked for, BIG_COPIES is $BIG_COPIES." >&2
                exit 1
            fi
        done
        ;;
    *)
        echo "ERROR: DATASET must be 'synthetic', 'real' or 'big', not '$DATASET'" >&2
        exit 1
        ;;
esac

weak_input() {
    printf "%s/${WEAK_PATTERN}" "$DATA_DIR" "$1"
}

weak_slim_input() {
    printf "%s/${WEAK_SLIM_PATTERN}" "$DATA_DIR" "$1"
}

size_input() {
    printf "%s/${SIZE_PATTERN:-}" "$DATA_DIR" "$1"
}

# write_big_list <name> <copies>: lists/<name> over the first <copies> of ds_N.root. Entries are
# relative to the list (../ds_N.root), the rule bench_common.input_files applies, so the set
# stays valid wherever DATA_DIR is mounted.
write_big_list() {
    local path="$DATA_DIR/lists/$1" count="$2" i
    for ((i = 1; i <= count; i++)); do
        printf '../ds_%d.root\n' "$i"
    done >"${path}.partial"
    mv "${path}.partial" "$path"
}

if [[ "$DATASET" == big && -z "${DRY_RUN:-}" ]]; then
    mkdir -p "$DATA_DIR/lists"
    write_big_list core.txt "$BIG_COPIES"
    write_big_list impl.txt "$IMPL_COPIES"
    for n in $WEAK_SERIES; do
        write_big_list "weak_${n}.txt" $((WEAK_UNIT * n))
    done
    for n in $SIZE_SERIES; do
        write_big_list "size_${n}.txt" "$n"
    done
    echo "lists: $DATA_DIR/lists (core $BIG_COPIES, impl $IMPL_COPIES, weak ${WEAK_UNIT}N, size N copies)"
fi

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

# drop_pages <file>...
#
# POSIX_FADV_DONTNEED evicts a file's clean pages from the page cache. It needs no privileges
# (unlike /proc/sys/vm/drop_caches, which is root-only and would also throw away ROOT's
# libraries), and it is per-file, so it touches nothing but the inputs.
drop_pages() {
    [[ $# -eq 0 ]] && return 0
    "$PY" - "$@" <<'PYEOF'
import os
import sys

for path in sys.argv[1:]:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    finally:
        os.close(fd)
PYEOF
}

# posix_fadvise is Linux-only (it is absent on macOS), so a cold campaign asked for on a laptop
# would otherwise fail on its first run. Downgrade to warm reads instead and say so: the one
# thing that must not happen is a campaign that labels warm reads "cold".
if [[ -n "$COLD" ]] \
    && ! "$PY" -c 'import os, sys; sys.exit(0 if hasattr(os, "posix_fadvise") else 1)'; then
    echo "WARNING: no posix_fadvise on this platform; running with warm reads (COLD ignored)." >&2
    COLD=""
fi
# Every record says which of the two it is, so a cold campaign can never be averaged into a
# warm one by mistake.
CACHE="${COLD:+cold}"
export CACHE="${CACHE:-warm}"

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
if has_test size || has_test sizepy; then
    for n in $SIZE_SERIES; do
        INPUTS+=("$(size_input "$n")")
    done
fi
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
if [[ "$missing" -ne 0 && "$DATASET" == big ]]; then
    echo "       Make the copies first: bash test/make_bigset.sh --source $DATA_DIR/ds_x32.root" \
        "--copies $BIG_COPIES" >&2
fi
[[ "$missing" -eq 0 || -n "${DRY_RUN:-}" ]] || exit 1

mkdir -p "$RESULTS"
RAW="$RESULTS/raw.jsonl"

# Labels already measured, one per line, for RESUME. A file rather than an associative array
# because macOS still ships bash 3.2.
DONE_LABELS="$(mktemp)"
trap 'rm -f "$DONE_LABELS"' EXIT
if [[ -n "$RESUME" && -f "$RAW" ]]; then
    "$PY" - "$RAW" >"$DONE_LABELS" <<'PYEOF'
import json
import sys

with open(sys.argv[1]) as f:
    for line in f:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("status") == "ok" and record.get("label"):
            print(record["label"])
PYEOF
    echo "RESUME: $(wc -l <"$DONE_LABELS" | tr -d ' ') runs already in $RAW are skipped"
fi

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
# Returns 1 when the run failed or timed out, 0 otherwise (including a run RESUME skipped).
run_one() {
    local label="$1" script="$2"
    shift 2
    local pinned=""
    [[ -n "${PINNED:-}" && -n "$TASKSET_BIN" ]] && pinned="$PIN_CORE"

    if [[ "$label" != warmup_* ]] && grep -Fxq "$label" "$DONE_LABELS"; then
        echo "  == $label (already recorded, skipped)"
        return 0
    fi

    if [[ -n "${DRY_RUN:-}" ]]; then
        DRY_RUN_COUNT=$((${DRY_RUN_COUNT:-0} + 1))
        printf '  [%3d] %-44s %s %s%s\n' "$DRY_RUN_COUNT" "$label" "$script" "$*" \
            "${pinned:+  [core $pinned]}"
        return
    fi

    # Whatever this run is about to read, minus the page cache. The input is taken from the
    # run's own --input so that a run on the slim set does not evict the full one.
    if [[ -n "$COLD" ]]; then
        local -a inputs=()
        local i
        for ((i = 1; i <= $#; i++)); do
            if [[ "${!i}" == "--input" ]]; then
                local next=$((i + 1))
                while IFS= read -r file; do inputs+=("$file"); done \
                    < <(list_files "${!next}")
            fi
        done
        [[ "${#inputs[@]}" -gt 0 ]] && drop_pages "${inputs[@]}"
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
        return 1
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
SLIM_INPUTS=()
if has_test slim || has_test weakslim; then
    SLIM_INPUTS+=("$DS_SLIM")
    for n in $WEAK_SERIES; do
        SLIM_INPUTS+=("$(weak_slim_input "$n")")
    done
fi
if [[ -z "${DRY_RUN:-}" ]] && { has_test slim || has_test weakslim; }; then
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
fi

if [[ -z "${DRY_RUN:-}" ]]; then
    # With COLD the next thing run_one does is throw these pages away again, and on the 1 TB
    # set reading everything first would cost ~1 h for nothing. Instead the campaign checks
    # that eviction works at all, because if it silently did not, every "cold" number would be
    # a warm one. fincore is util-linux >= 2.31 and is not everywhere, hence the fallback.
    if [[ -n "$COLD" ]]; then
        echo "=== cold reads: checking that the page cache can be dropped ==="
        probe="$(list_files "$DS_CORE" | head -1)"
        head -c 65536 "$probe" >/dev/null
        drop_pages "$probe"
        if command -v fincore >/dev/null; then
            resident="$(fincore --bytes --output PAGES --noheadings "$probe" | tr -d ' ')"
            echo "  $(basename "$probe"): ${resident} pages resident after eviction"
            if [[ "${resident:-0}" -ne 0 ]]; then
                echo "ERROR: pages stayed in the cache, so the reads would not be cold." >&2
                echo "       Run with COLD= to measure warm reads instead." >&2
                exit 1
            fi
        else
            echo "  WARNING: fincore not found; eviction not verified." >&2
        fi
    else
        echo "=== warming the page cache ==="
        for input in "${INPUTS[@]}" ${SLIM_INPUTS[@]+"${SLIM_INPUTS[@]}"}; do
            list_files "$input"
        done | sort -u | while IFS= read -r file; do
            cat "$file" >/dev/null
        done
    fi
fi

# The page cache is not the only cold thing: the first process of the job also loads ROOT's
# libraries and PCH off Lustre, and in the previous campaign r1_strong_filter_rdf_t1 ran at
# 69% CPU and 13.9 s against 99% and 9.6 s for the same label later. These runs absorb that
# and are never plotted (the plots select on the r<N>_ prefix).
#
# Under COLD they run on a single file: what they are for is the libraries and the PCH, and
# reading 1 TB three times to get them would cost hours.
WARMUP_INPUT_SET="$DS_CORE"
if [[ -n "$COLD" && -z "${DRY_RUN:-}" ]]; then
    WARMUP_INPUT_SET="$(list_files "$DS_CORE" | head -1)"
fi
if [[ "$WARMUP_RUNS" -eq 1 ]]; then
    echo "=== discarded warm-up runs ==="
    if [[ -z "$ONLY_CHAIN11" ]]; then
        run_one "warmup_filter_rdf" bench_filter.py --input "$WARMUP_INPUT_SET" --impl rdf
        run_one "warmup_chain_rdf-lazy" bench_chain.py --input "$WARMUP_INPUT_SET" --impl rdf-lazy
        run_one "warmup_eff_jit" bench_efficiency.py --input "$WARMUP_INPUT_SET" --impl jit
    fi
    if has_test strong11 || has_test weak11; then
        run_one "warmup_chain11_rdf-lazy" bench_chain.py --input "$WARMUP_INPUT_SET" \
            --impl rdf-lazy --chain long
    fi
fi

# T1 and T2 for the 11-filter chain on the slim set. Labelled strong_/weak_ like T1 and T2, so
# the figures pick them up; the test field (chain11) keeps them apart from the 5-filter chain.
if has_test strong11; then
echo "=== T1 strong scaling, 11-filter chain, on $(basename "$DS_CORE"): $STRONG11_THREADS ==="
for threads in $STRONG11_THREADS; do
    run_one "r1_strong_chain11_rdf-lazy_t${threads}" bench_chain.py \
        --input "$DS_CORE" --impl rdf-lazy --chain long --threads "$threads"
done
for threads in $STRONG11_R2_THREADS; do
    run_one "r2_strong_chain11_rdf-lazy_t${threads}" bench_chain.py \
        --input "$DS_CORE" --impl rdf-lazy --chain long --threads "$threads"
done
for threads in $STRONG11_R3_THREADS; do
    run_one "r3_strong_chain11_rdf-lazy_t${threads}" bench_chain.py \
        --input "$DS_CORE" --impl rdf-lazy --chain long --threads "$threads"
done
fi

if has_test weak11; then
echo "=== T2 weak scaling, 11-filter chain: $WEAK_PATTERN on N threads ==="
for repeat in $(seq 1 "$REPEATS_WEAK"); do
    for n in $WEAK_SERIES; do
        run_one "r${repeat}_weak_chain11_rdf-lazy_t${n}" bench_chain.py \
            --input "$(weak_input "$n")" --impl rdf-lazy --chain long --threads "$n"
    done
done
for n in $WEAK11_R3_SERIES; do
    run_one "r3_weak_chain11_rdf-lazy_t${n}" bench_chain.py \
        --input "$(weak_input "$n")" --impl rdf-lazy --chain long --threads "$n"
done
fi

# T1: the same events every time, thread count varying. Repeats are the outer loop so that
# slow drift on the node spreads across thread counts instead of landing on one of them.
if has_test strong; then
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
fi

# T2: N threads against N units of work, so each thread keeps the same slice of it. Ideal
# weak scaling is a flat wall-time line.
if has_test weak; then
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
fi

# T4: single-threaded, because the number of event loops is a property of how the query was
# written rather than of the machine.
if has_test qstruct; then
echo "=== T4 query structure: chain lengths $CHAIN_LENS ==="
for repeat in $(seq 1 "$REPEATS_QSTRUCT"); do
    for len in $CHAIN_LENS; do
        for impl in rdf-lazy rdf-eager rdf-report; do
            run_one "r${repeat}_qstruct_chain_${impl}_l${len}" bench_chain.py \
                --input "$DS_IMPL" --impl "$impl" --chain-len "$len"
        done
    done
done
fi

# T5: every implementation on one input, so the comparison a reader is most likely to
# challenge is "same files, same codec, same events". The Python chain alone costs ~16 min
# on ~11 M events, which is why the impl input is not the (larger) core input on real data,
# and why it runs in the first repeat only. With a single run the RDF chain and efficiency
# came out 12-24% slower than the identical T1 t0 runs, hence the repeats for the rest.
#
# ONLY_USED=1 drops the three variants that no figure and no number in the thesis uses: the
# AsNumpy `vector` mode (always slower than `loop`, and the figure keeps one Python bar),
# correctionlib (part of the RDataFrame solution, not a competing implementation) and the
# unpinned uproot runs. On the 1 TB set each of them would still cost tens of minutes.
if has_test impl; then
echo "=== T5 implementations on $(basename "$DS_IMPL")${TASKSET_BIN:+, pinned to core $PIN_CORE}${ONLY_USED:+, plotted variants only} ==="
export PINNED=1
for repeat in $(seq 1 "$REPEATS_IMPL"); do
    run_one "r${repeat}_impl_filter_rdf" bench_filter.py --input "$DS_IMPL" --impl rdf
    if [[ -z "$ONLY_USED" ]]; then
        run_one "r${repeat}_impl_filter_python_vector" bench_filter.py \
            --input "$DS_IMPL" --impl python --mode vector
    fi
    run_one "r${repeat}_impl_filter_python_loop" bench_filter.py \
        --input "$DS_IMPL" --impl python --mode loop
    run_one "r${repeat}_impl_filter_uproot" bench_filter.py --input "$DS_IMPL" --impl uproot

    run_one "r${repeat}_impl_chain_rdf-lazy" bench_chain.py --input "$DS_IMPL" --impl rdf-lazy
    if [[ "$repeat" -eq 1 ]]; then
        run_one "r${repeat}_impl_chain_python" bench_chain.py --input "$DS_IMPL" --impl python
    fi
    run_one "r${repeat}_impl_chain_uproot" bench_chain.py --input "$DS_IMPL" --impl uproot

    run_one "r${repeat}_impl_eff_jit" bench_efficiency.py --input "$DS_IMPL" --impl jit
    if [[ -z "$ONLY_USED" ]]; then
        run_one "r${repeat}_impl_eff_correctionlib" bench_efficiency.py \
            --input "$DS_IMPL" --impl correctionlib
        run_one "r${repeat}_impl_eff_python_vector" bench_efficiency.py \
            --input "$DS_IMPL" --impl python --mode vector
    fi
    run_one "r${repeat}_impl_eff_python_loop" bench_efficiency.py \
        --input "$DS_IMPL" --impl python --mode loop
    run_one "r${repeat}_impl_eff_uproot" bench_efficiency.py --input "$DS_IMPL" --impl uproot
done
unset PINNED
# uproot as a user gets it, with whatever threads it starts; a separate, labelled point.
if [[ -z "$ONLY_USED" ]]; then
    run_one "r1_impl_filter_uproot-default" bench_filter.py --input "$DS_IMPL" --impl uproot \
        --tag own-threads
    run_one "r1_impl_chain_uproot-default" bench_chain.py --input "$DS_IMPL" --impl uproot \
        --tag own-threads
    run_one "r1_impl_eff_uproot-default" bench_efficiency.py --input "$DS_IMPL" --impl uproot \
        --tag own-threads
fi
fi

# T6: T1's sweep on an input that differs from the core one only in width. If the per-thread
# cost (on ds_x32: ~245 MB RSS and ~55 ms of loop time per extra thread) comes from the ~2000
# branches every worker has to set up, it shrinks here and the speedup peak moves right.
if has_test slim; then
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
fi

# T2S: T2 on the slim copies. On the full files one unit of work (0.24-0.52 s of loop per
# thread) is smaller than the ~1 s of CPU each worker spends building its ~2000-branch tree,
# so T2 mostly measures that setup. Here the setup is gone and what remains is the scaling of
# the work itself.
if has_test weakslim; then
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
fi

# T5 against input size: the same variants as T5's figure, pinned to one core, on 1..9 copies.
# What one input cannot show is how memory grows with the data: RDataFrame streams cluster by
# cluster, while uproot and AsNumpy hold whole columns, and RDataFrame's fixed JIT cost is
# amortised only past some size. The last point is T5 on ~100 GB.
if has_test size; then
echo "=== T5 against input size, RDataFrame and uproot: $SIZE_SERIES copies${TASKSET_BIN:+, pinned to core $PIN_CORE} ==="
export PINNED=1
for n in $SIZE_SERIES; do
    size_ds="$(size_input "$n")"
    run_one "r1_size_filter_rdf_c${n}" bench_filter.py --input "$size_ds" --impl rdf
    run_one "r1_size_filter_uproot_c${n}" bench_filter.py --input "$size_ds" --impl uproot
    run_one "r1_size_chain_rdf-lazy_c${n}" bench_chain.py --input "$size_ds" --impl rdf-lazy
    run_one "r1_size_chain_uproot_c${n}" bench_chain.py --input "$size_ds" --impl uproot
    run_one "r1_size_eff_jit_c${n}" bench_efficiency.py --input "$size_ds" --impl jit
    run_one "r1_size_eff_uproot_c${n}" bench_efficiency.py --input "$size_ds" --impl uproot
done
unset PINNED
fi

# The Python half of the series, last, smallest first, and the chain (~16 min and ~16.6 GB of
# RSS per copy) after everything else: on 8-9 copies it needs ~133-150 GB of a ~184 GB node,
# and if the kernel kills it every other result is already on disk. A variant that failed at N
# copies is not started on more: it would fail the same way after up to ~2 h of reading, so the
# larger points are recorded as failed with skipped_after = N.
py_failed_filter=""
py_failed_eff=""
py_failed_chain=""

# size_py <variant> <copies> <label> <script> [args...]
size_py() {
    local variant="$1" n="$2" label="$3"
    shift 3
    local failed_var="py_failed_${variant}"
    local failed_at="${!failed_var}"
    if [[ -n "$failed_at" ]]; then
        echo "  -> $label: not run, the same variant failed at $failed_at copies" >&2
        printf '{"label":"%s","status":"failed","exit_code":null,"machine":"%s","skipped_after":%d}\n' \
            "$label" "$MACHINE" "$failed_at" >>"$RAW"
        return
    fi
    run_one "$label" "$@" || printf -v "$failed_var" '%s' "$n"
}

if has_test sizepy; then
echo "=== T5 against input size, Python: $SIZE_SERIES copies${TASKSET_BIN:+, pinned to core $PIN_CORE} ==="
export PINNED=1
for n in $SIZE_SERIES; do
    size_ds="$(size_input "$n")"
    size_py filter "$n" "r1_size_filter_python_loop_c${n}" bench_filter.py \
        --input "$size_ds" --impl python --mode loop
    size_py eff "$n" "r1_size_eff_python_loop_c${n}" bench_efficiency.py \
        --input "$size_ds" --impl python --mode loop
done
for n in $SIZE_SERIES; do
    size_py chain "$n" "r1_size_chain_python_c${n}" bench_chain.py \
        --input "$(size_input "$n")" --impl python
done
unset PINNED
fi

if [[ -n "${DRY_RUN:-}" ]]; then
    echo
    echo "dry run: ${DRY_RUN_COUNT:-0} runs, each capped at ${RUN_TIMEOUT}s"
else
    echo "Records in $RAW"
    "$PY" "$TEST_DIR/plot_results.py" --results "$RESULTS"
fi
