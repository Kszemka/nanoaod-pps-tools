#!/bin/bash -l
#SBATCH --job-name=pps-final
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid-now
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --mem=384000
#SBATCH --hint=nomultithread
#SBATCH --time=12:00:00
#SBATCH --exclusive
#SBATCH --output=bench-final-%j.out
#SBATCH --error=bench-final-%j.err

# The final Helios campaign of the 11-filter chain as one job, its steps one after the other on
# the same node, so that no measurement shares Lustre with another:
#
#   bigset  make_bigset.sh: ds_1..ds_96.root in data/ from data/ds_x32.root, only the copies
#         not already there at full size (~0.5-1 h for all 96, 1.04 TB; seconds when complete)
#   gate  check_chain11.py --period 2016 over every Run 2 file (~5 min): does the chain mean
#         the same thing in all of them        -> $SCRATCH/bench/run2_chain11_gate.{txt,status}
#   F     strong11 on the artificial full files, ds_1..ds_96.root in data/ (1.07 G events)
#                                              -> results-helios-full11-1tb
#   R     strong11 on Run 2 Open Data, data2/core.txt, --period 2016; only if the gate exited 0
#                                              -> results-helios-run2-chain11-1tb
#   J1    strong11 on Run 3, data3-full/core.txt (RUN3_DATA), --period run3 (slurm_run3.sbatch)
#                                              -> results-helios-run3-chain11
#   J3    RDataFrame on 192 threads and uproot in a pool of 192 processes on Run 3, three runs
#         each (slurm_run3.sbatch)             -> results-helios-run3-node
#
# F, R and J1: threads 1-192 once, 80-192 three times. Estimated ~6-7.5 h in all, plus the
# copies when bigset has to make them.
#
# One job because the QoS of plgrid-now allows one job per user, pending ones included
# (MaxSubmitPU=1): a chain with dependencies cannot even be queued. Its limits are also the
# allocation above: one node, 384000 MB, MaxTime=12:00:00.
#
# Before the first step the job checks that the inputs of every step in STEPS are there, and
# stops at once otherwise: a node held for 12 h should not find out in hour 4 that a set is gone.
#
# A failed step does not stop the next one; the summary at the end of the log lists them all.
# Everything appends with RESUME=1 and the gate keeps its exit code, so after running out of
# time the same job submitted again runs only what is missing. J1 moves a results directory
# with the old cuts (records whose period is not run3) aside first.
#
#   sbatch test/slurm_final.sbatch
#   sbatch --export=ALL,STEPS="J1 J3" test/slurm_final.sbatch    # only some steps
#   DRY_RUN=1 bash test/slurm_final.sbatch                        # print the steps, run nothing
#
# CMS data is not public: it stays on scratch; results hold timings and counts only.

set -uo pipefail

STEPS="${STEPS:-bigset gate F R J1 J3}"
DRY_RUN="${DRY_RUN:-}"
for step in $STEPS; do
    case "$step" in
        bigset|gate|F|R|J1|J3) ;;
        *) echo "ERROR: STEPS: unknown step '$step' (bigset gate F R J1 J3)." >&2; exit 1 ;;
    esac
done

if [[ -n "$DRY_RUN" ]]; then
    SCRATCH_BENCH="${SCRATCH:-\$SCRATCH}/bench"
else
    SCRATCH_BENCH="${SCRATCH:?SCRATCH is not set}/bench"
fi
GATE_TXT="${SCRATCH_BENCH}/run2_chain11_gate.txt"
GATE_STATUS="${SCRATCH_BENCH}/run2_chain11_gate.status"
THREADS="1 4 8 12 16 24 32 48 64 80 96 112 128 144 160 176 192"
REPEAT_THREADS="80 96 112 128 144 160 176 192"
RUN3_RESULTS="${SCRATCH_BENCH}/results-helios-run3-chain11"
# The set every Run 3 measurement so far read (2454 files, core.txt 2307).
RUN3_DATA="${RUN3_DATA:-${SCRATCH_BENCH}/data3-full}"

# Each step sets its own; one left in the submitting shell would point a step at another's
# results or data.
unset RESULTS DATA_DIR DATASET TESTS CHAIN_ARGS RUN_TIMEOUT THREADS_LIST EVENT_COUNTS \
    DATASET_JSON_INPUT DATASET_JSON_INVENTORY FRESH JOB

# run <command...>: the command, or its printout under DRY_RUN.
run() {
    if [[ -n "$DRY_RUN" ]]; then
        printf '   '
        printf ' %q' "$@"
        echo
        return 0
    fi
    "$@"
}

FULL11_VARS=(MACHINE=helios TESTS=strong11 COLD=1 STORAGE=lustre RESUME=1
    THREADS_LIST="$THREADS" STRONG11_R2_THREADS="$REPEAT_THREADS"
    STRONG11_R3_THREADS="$REPEAT_THREADS" RUN_TIMEOUT=7200)

# A copy cut short by the quota stays behind as ds_N.root.partial and keeps its share of it,
# and the steps after this one still have to write their results to the same scratch.
step_bigset() {
    local dir="${SCRATCH_BENCH}/data"
    run bash test/make_bigset.sh --source "$dir/ds_x32.root" --copies 96 && return 0
    run rm -f "$dir"/ds_*.root.partial
    return 1
}

# all_copies: ds_1..ds_96.root there, each at the size of ds_x32.root.
all_copies() {
    local dir="${SCRATCH_BENCH}/data" size i
    size="$(wc -c < "$dir/ds_x32.root")" || return 1
    for ((i = 1; i <= 96; i++)); do
        [[ -f "$dir/ds_${i}.root" && "$(wc -c < "$dir/ds_${i}.root")" -eq "$size" ]] || return 1
    done
}

# Exit 3: a file the chain cannot read (e.g. a missing column); 2: a column with two types;
# 4: the chain leaves no event of the whole set.
step_gate() {
    local gate=(timeout 3600 python test/check_chain11.py
        --inventory "${SCRATCH_BENCH}/data2/local.csv" --period 2016 --jobs 96
        --per-file "${SCRATCH_BENCH}/run2_chain11.csv")
    # A gate older than exit code 4 passed a chain that leaves nothing with 0; kept, that 0
    # would send R onto the same empty chain again.
    if [[ -f "$GATE_STATUS" ]] && grep -q ', 0 left after the chain' "$GATE_TXT" 2>/dev/null; then
        echo "the saved gate left no event: running it again"
        run rm -f "$GATE_STATUS"
    fi
    if [[ -n "$DRY_RUN" ]]; then
        run "${gate[@]}"
        echo "    > $GATE_TXT, exit code > $GATE_STATUS"
        return 0
    fi
    if [[ -f "$GATE_STATUS" ]]; then
        echo "gate already ran: exit $(cat "$GATE_STATUS") (delete $GATE_STATUS to rerun)"
        return "$(cat "$GATE_STATUS")"
    fi
    set +u
    eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
    micromamba activate pps-bench
    set -u
    "${gate[@]}" > "$GATE_TXT"
    local status=$?
    echo "$status" > "$GATE_STATUS"
    tail -n 40 "$GATE_TXT"
    return "$status"
}

step_F() {
    local dir="${SCRATCH_BENCH}/data"
    if [[ -z "$DRY_RUN" ]] && ! all_copies; then
        echo "skipped: ds_1..ds_96.root are not all there at full size (see the bigset step)"
        return 1
    fi
    run env "${FULL11_VARS[@]}" DATASET=big BIG_COPIES=96 WEAK_UNIT=1 DATA_DIR="$dir" \
        RESULTS="${SCRATCH_BENCH}/results-helios-full11-1tb" \
        DATASET_JSON_INPUT="$dir/ds_1.root" CHAIN_ARGS= \
        bash test/slurm_benchmark.sbatch
}

step_R() {
    local dir="${SCRATCH_BENCH}/data2" results="${SCRATCH_BENCH}/results-helios-run2-chain11-1tb"
    if [[ -z "$DRY_RUN" && "$(cat "$GATE_STATUS" 2>/dev/null)" != 0 ]]; then
        echo "skipped: the gate did not exit 0 (see $GATE_TXT)"
        return 1
    fi
    # Records of a chain that passed nothing (the 2016 cuts before the strip track cuts) would
    # be skipped by RESUME as if they were done.
    if [[ -f "$results/raw.jsonl" ]] && grep -qE '"events_passed": 0[,}]' "$results/raw.jsonl"; then
        run mv "$results" "$results-nopass-$(date +%Y%m%d_%H%M%S)"
    fi
    run env "${FULL11_VARS[@]}" DATASET=real DATA_DIR="$dir" \
        RESULTS="$results" \
        DATASET_JSON_INPUT="$dir/core.txt" DATASET_JSON_INVENTORY="$dir/local.csv" \
        EVENT_COUNTS="$dir/local.csv" CHAIN_ARGS="--period 2016" \
        bash test/slurm_benchmark.sbatch
}

step_J1() {
    # Records with the old (2026) cuts would be skipped by RESUME as if they were done.
    if [[ -f "$RUN3_RESULTS/raw.jsonl" ]] \
        && grep -o '"period": "[^"]*"' "$RUN3_RESULTS/raw.jsonl" | grep -qv '"period": "run3"'; then
        run mv "$RUN3_RESULTS" "$RUN3_RESULTS-oldcuts-$(date +%Y%m%d_%H%M%S)"
    fi
    run env JOB=J1 DATA_DIR="$RUN3_DATA" bash test/slurm_run3.sbatch
}

step_J3() {
    run env JOB=J3 DATA_DIR="$RUN3_DATA" bash test/slurm_run3.sbatch
}

# list_paths <list>...: the list files themselves and every path in them (relative paths are
# relative to the list's directory). data3-full/data is a link into data3/data, so the lists
# can be there while the files they name are not.
list_paths() {
    local list path
    for list in "$@"; do
        echo "$list"
        [[ -f "$list" ]] || continue
        while IFS= read -r path || [[ -n "$path" ]]; do
            [[ -z "$path" || "$path" == \#* ]] && continue
            [[ "$path" == /* ]] || path="$(dirname "$list")/$path"
            echo "$path"
        done < "$list"
    done
}

# inputs_of <step>: the files the step cannot run without.
inputs_of() {
    case "$1" in
        bigset) echo "${SCRATCH_BENCH}/data/ds_x32.root" ;;
        gate) echo "${SCRATCH_BENCH}/data2/local.csv" ;;
        F)
            # bigset, earlier in the same job, makes the copies; its own input stands for them.
            [[ " $STEPS " == *" bigset "* ]] && return 0
            local i; for ((i = 1; i <= 96; i++)); do echo "${SCRATCH_BENCH}/data/ds_${i}.root"; done ;;
        R)
            echo "${SCRATCH_BENCH}/data2/local.csv"
            list_paths "${SCRATCH_BENCH}"/data2/{core.txt,impl.txt} ;;
        J1|J3)
            printf '%s\n' "$RUN3_DATA"/{READY,sets.json,local.csv}
            list_paths "$RUN3_DATA"/{core.txt,impl.txt} ;;
    esac
}

missing=()
for step in $STEPS; do
    while IFS= read -r input; do
        [[ -s "$input" ]] || missing+=("$step: $input")
    done < <(inputs_of "$step")
done
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "ERROR: ${#missing[@]} input(s) missing; nothing was run:" >&2
    printf '  %s\n' "${missing[@]:0:20}" >&2
    [[ ${#missing[@]} -gt 20 ]] && echo "  ..." >&2
    echo "Remake them (test/README.md, \"Ostateczna kampania\") or leave the step out of STEPS." >&2
    [[ -z "$DRY_RUN" ]] && exit 1
fi

if [[ -z "$DRY_RUN" ]]; then
    cd "${SCRATCH_BENCH}/nanoaod-pps-tools" || exit 1
    echo "job $SLURM_JOB_ID on $(hostname), steps: $STEPS"
else
    cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
    echo "DRY_RUN: steps $STEPS"
fi

summary=()
for step in $STEPS; do
    start="$(date +%s)"
    echo
    echo "##### $step [$(date '+%F %H:%M:%S')] #####"
    ( "step_$step" )
    status=$?
    minutes=$(( ($(date +%s) - start) / 60 ))
    echo "##### $step: exit $status after ${minutes} min [$(date '+%F %H:%M:%S')] #####"
    summary+=("$(printf '%-5s exit %-3s %5s min' "$step" "$status" "$minutes")")
done

echo
echo "===== summary ====="
printf '%s\n' "${summary[@]}"
echo
echo "copy to the laptop: results-helios-{full11-1tb,run2-chain11-1tb,run3-chain11,run3-node}"
echo "and run2_chain11_gate.txt (test/README.md, \"Ostateczna kampania\")"
[[ -z "$DRY_RUN" ]] && { sacct -j "${SLURM_JOB_ID}" --format=JobID,JobName,State,Elapsed,MaxRSS,NCPUS,ReqMem || true; }
exit 0
