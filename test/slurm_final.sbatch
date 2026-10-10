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
# the same node, so that no measurement shares Lustre with another (test/FINAL.md):
#
#   gate   check_chain11.py --period 2016 over every Run 2 file (~5 min): does the chain mean
#          the same thing in all of them      -> $SCRATCH/bench/run2_chain11_gate.{txt,status}
#   gate3  the same with --period run3 over every Run 3 file (~5-10 min)
#                                             -> $SCRATCH/bench/run3_chain11_gate.{txt,status}
#   J1     strong11 on Run 3, data3/core.txt (RUN3_DATA), --period run3 (slurm_run3.sbatch);
#          only if gate3 exited 0             -> results-helios-run3-chain11
#   J3     RDataFrame on 192 threads and uproot in a pool of 192 processes on Run 3, three runs
#          each (slurm_run3.sbatch)           -> results-helios-run3-node
#   R      strong11 on Run 2 Open Data, data2/core.txt, --period 2016; only if gate exited 0
#                                             -> results-helios-run2-chain11-1tb
#   J4     Python (AsNumpy) in a pool of 192 processes on Run 3, chunks of POOL_CHUNK_EVENTS,
#          three runs, 1.5 h each at most; a run that times out is not repeated
#                                             -> results-helios-run3-node
#
# J1 and R: threads 1-192 once, 80-192 three times. Estimated ~6-9 h in all; J4 is last, so
# running out of time or memory there costs nothing else.
#
# One job because the QoS of plgrid-now allows one job per user, pending ones included
# (MaxSubmitPU=1): a chain with dependencies cannot even be queued. Its limits are also the
# allocation above: one node, 384000 MB, MaxTime=12:00:00.
#
# Before the first step the job checks that the inputs of every step in STEPS are there, and
# stops at once otherwise: a node held for 12 h should not find out in hour 4 that a set is gone.
#
# Nothing is lost when the job dies: every run is appended to its raw.jsonl on Lustre as soon as
# it ends, and the same job submitted again runs only what is missing (RESUME=1). After each
# step a line goes to $SCRATCH/bench/final_progress.log; a step that ended with 0 and left no
# failed run behind writes final_state/<step>.done with its cuts and is skipped next time
# (delete the file to run it again). A results directory with records of other cuts than the
# current ones (bench_spec.chain_cuts) is moved aside to <dir>-oldcuts-<date> before its step.
# A failed step does not stop the next one; the summary at the end of the log lists them all.
#
#   sbatch test/slurm_final.sbatch
#   sbatch --export=ALL,STEPS="J1 J3" test/slurm_final.sbatch    # only some steps
#   DRY_RUN=1 bash test/slurm_final.sbatch                        # print the steps, run nothing
#
# CMS data is not public: it stays on scratch; results hold timings and counts only.

set -uo pipefail

ALL_STEPS="gate gate3 J1 J3 R J4"
STEPS="${STEPS:-$ALL_STEPS}"
DRY_RUN="${DRY_RUN:-}"
for step in $STEPS; do
    case "$step" in
        gate|gate3|J1|J3|R|J4) ;;
        *) echo "ERROR: STEPS: unknown step '$step' ($ALL_STEPS)." >&2; exit 1 ;;
    esac
done

if [[ -n "$DRY_RUN" ]]; then
    SCRATCH_BENCH="${SCRATCH:-\$SCRATCH}/bench"
else
    SCRATCH_BENCH="${SCRATCH:?SCRATCH is not set}/bench"
fi
THREADS="1 4 8 12 16 24 32 48 64 80 96 112 128 144 160 176 192"
REPEAT_THREADS="80 96 112 128 144 160 176 192"
RUN2_DATA="${SCRATCH_BENCH}/data2"
R_RESULTS="${SCRATCH_BENCH}/results-helios-run2-chain11-1tb"
# The Run 3 files and their lists (test/archive/slurm_fetch_eos.sbatch).
RUN3_DATA="${RUN3_DATA:-${SCRATCH_BENCH}/data3}"
RUN3_RESULTS="${SCRATCH_BENCH}/results-helios-run3-chain11"
NODE_RESULTS="${SCRATCH_BENCH}/results-helios-run3-node"
PROGRESS="${SCRATCH_BENCH}/final_progress.log"
STATE_DIR="${SCRATCH_BENCH}/final_state"

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

period_of() {
    case "$1" in
        gate|R) echo 2016 ;;
        *) echo run3 ;;
    esac
}

results_of() {
    case "$1" in
        R) echo "$R_RESULTS" ;;
        J1) echo "$RUN3_RESULTS" ;;
        J3|J4) echo "$NODE_RESULTS" ;;
    esac
}

# cuts_of <period>: the chain with every cut of the period, as the records carry it.
cuts_of() {
    "$PY" -c 'import sys; sys.path.insert(0, "test"); import bench_spec
print(bench_spec.chain_cuts(sys.argv[1]))' "$1"
}

# results_state <dir> <cuts>: "<ok> <unresolved failures> <records of other cuts>" of a results
# directory. A failure is resolved by an ok run of the same label, or is a pool run that hit
# RUN_TIMEOUT (exit 124), which run_benchmark.sh does not repeat.
results_state() {
    "$PY" - "$1/raw.jsonl" "$2" <<'PYEOF'
import json, os, sys

path, cuts = sys.argv[1], sys.argv[2]
ok, failed, other = set(), set(), 0
if os.path.exists(path):
    with open(path) as f:
        for line in f:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("status") == "ok":
                ok.add(record.get("label"))
                other += record.get("chain_cuts") != cuts
            elif not ("_node_chain11_" in str(record.get("label"))
                      and record.get("exit_code") == 124):
                failed.add(record.get("label"))
print(len(ok), len(failed - ok), other)
PYEOF
}

# set_aside <step>: moves the step's results directory aside if it holds records of other cuts.
set_aside() {
    local dir state
    dir="$(results_of "$1")"
    [[ -n "$dir" && -f "$dir/raw.jsonl" ]] || return 0
    read -r -a state <<< "$(results_state "$dir" "$(cuts_of "$(period_of "$1")")")"
    if [[ "${state[2]:-0}" -gt 0 ]]; then
        echo "$dir: ${state[2]} records of other cuts, moved aside"
        run mv "$dir" "$dir-oldcuts-$(date +%Y%m%d_%H%M%S)"
    fi
}

# gate_files <step>: the .txt and .status of a gate step.
gate_files() {
    case "$1" in
        gate) echo "${SCRATCH_BENCH}/run2_chain11_gate.txt ${SCRATCH_BENCH}/run2_chain11_gate.status" ;;
        gate3) echo "${SCRATCH_BENCH}/run3_chain11_gate.txt ${SCRATCH_BENCH}/run3_chain11_gate.status" ;;
    esac
}

# gate_passed <step>: the gate exited 0 for the current cuts.
gate_passed() {
    local files
    read -r -a files <<< "$(gate_files "$1")"
    [[ "$(cat "${files[1]}" 2>/dev/null)" == 0 ]] \
        && [[ "$(head -n 1 "${files[0]}" 2>/dev/null)" == "chain_cuts: $(cuts_of "$(period_of "$1")")" ]]
}

# Exit 3: a file the chain cannot read (e.g. a missing column); 2: a column with two types;
# 4: the chain leaves no event of the whole set.
run_gate() {
    local step="$1" inventory="$2" per_file="$3" files
    read -r -a files <<< "$(gate_files "$step")"
    local gate=(timeout 3600 "$PY" test/check_chain11.py --inventory "$inventory"
        --period "$(period_of "$step")" --jobs 96 --per-file "$per_file")
    # The first line of a gate is the cuts it ran with; one of other cuts is no answer for these.
    if [[ -f "${files[1]}" ]] \
        && [[ "$(head -n 1 "${files[0]}" 2>/dev/null)" != "chain_cuts: $(cuts_of "$(period_of "$step")")" ]]; then
        echo "the saved gate ran with other cuts: running it again"
        run rm -f "${files[1]}"
    fi
    if [[ -n "$DRY_RUN" ]]; then
        run "${gate[@]}"
        echo "    > ${files[0]}, exit code > ${files[1]}"
        return 0
    fi
    if [[ -f "${files[1]}" ]]; then
        echo "gate already ran: exit $(cat "${files[1]}") (delete ${files[1]} to rerun)"
        return "$(cat "${files[1]}")"
    fi
    "${gate[@]}" > "${files[0]}"
    local status=$?
    echo "$status" > "${files[1]}"
    tail -n 40 "${files[0]}"
    return "$status"
}

step_gate() {
    run_gate gate "$RUN2_DATA/local.csv" "${SCRATCH_BENCH}/run2_chain11.csv"
}

step_gate3() {
    run_gate gate3 "$RUN3_DATA/local.csv" "${SCRATCH_BENCH}/run3_chain11.csv"
}

# needs_gate <gate> <step>: the step runs only after its gate passed with the current cuts.
needs_gate() {
    [[ -n "$DRY_RUN" ]] && return 0
    gate_passed "$1" && return 0
    echo "skipped: $1 did not exit 0 with the current cuts (see $(gate_files "$1" | cut -d' ' -f1))"
    return 1
}

step_R() {
    needs_gate gate R || return 1
    set_aside R
    run env "${FULL11_VARS[@]}" DATASET=real DATA_DIR="$RUN2_DATA" RESULTS="$R_RESULTS" \
        DATASET_JSON_INPUT="$RUN2_DATA/core.txt" DATASET_JSON_INVENTORY="$RUN2_DATA/local.csv" \
        EVENT_COUNTS="$RUN2_DATA/local.csv" CHAIN_ARGS="--period 2016" \
        bash test/slurm_benchmark.sbatch
}

step_J1() {
    needs_gate gate3 J1 || return 1
    set_aside J1
    run env JOB=J1 DATA_DIR="$RUN3_DATA" bash test/slurm_run3.sbatch
}

step_J3() {
    needs_gate gate3 J3 || return 1
    set_aside J3
    run env JOB=J3 DATA_DIR="$RUN3_DATA" bash test/slurm_run3.sbatch
}

step_J4() {
    needs_gate gate3 J4 || return 1
    set_aside J4
    run env JOB=J4 DATA_DIR="$RUN3_DATA" REPEATS_NODE=3 RUN_TIMEOUT=5400 \
        bash test/slurm_run3.sbatch
}

# list_paths <list>...: the list files themselves and every path in them (relative paths are
# relative to the list's directory): the lists can be there while the files they name are not.
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
        gate) echo "$RUN2_DATA/local.csv" ;;
        gate3) echo "$RUN3_DATA/local.csv" ;;
        R)
            echo "$RUN2_DATA/local.csv"
            list_paths "$RUN2_DATA"/{core.txt,impl.txt} ;;
        J1|J3|J4)
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
    echo "Remake them (test/FINAL.md) or leave the step out of STEPS." >&2
    [[ -z "$DRY_RUN" ]] && exit 1
fi

if [[ -z "$DRY_RUN" ]]; then
    cd "${SCRATCH_BENCH}/nanoaod-pps-tools" || exit 1
    export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"
    # See slurm_benchmark.sbatch: the env's deactivate script trips over set -u.
    set +u
    eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
    micromamba activate pps-bench
    set -u
    PY="$(command -v python)"
    mkdir -p "$STATE_DIR"
    echo "job $SLURM_JOB_ID on $(hostname), steps: $STEPS"
    echo "$(date '+%F %H:%M:%S') job $SLURM_JOB_ID on $(hostname), steps: $STEPS" >> "$PROGRESS"
else
    cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
    PY="${PY:-$( [[ -x .venv/bin/python ]] && echo .venv/bin/python || command -v python3)}"
    echo "DRY_RUN: steps $STEPS"
fi

# progress <step> <status> <minutes>: one line of final_progress.log, and the .done marker of a
# step that ended with 0 and left no unresolved failure.
progress() {
    local step="$1" status="$2" minutes="$3" cuts dir state line
    cuts="$(cuts_of "$(period_of "$step")")"
    dir="$(results_of "$step")"
    line="$(date '+%F %H:%M:%S') $step exit $status after $minutes min"
    if [[ -n "$dir" ]]; then
        read -r -a state <<< "$(results_state "$dir" "$cuts")"
        line+=", $dir: ${state[0]:-?} ok, ${state[1]:-?} failed"
    else
        state=(0 0 0)
    fi
    [[ -n "$DRY_RUN" ]] && { echo "    progress: $line"; return 0; }
    echo "$line" >> "$PROGRESS"
    if [[ "$status" == 0 && "${state[1]:-}" == 0 ]]; then
        echo "$cuts" > "$STATE_DIR/$step.done"
    fi
}

summary=()
for step in $STEPS; do
    start="$(date +%s)"
    echo
    echo "##### $step [$(date '+%F %H:%M:%S')] #####"
    if [[ -z "$DRY_RUN" && "$(cat "$STATE_DIR/$step.done" 2>/dev/null)" == "$(cuts_of "$(period_of "$step")")" ]]; then
        echo "already done with the current cuts (delete $STATE_DIR/$step.done to run it again)"
        summary+=("$(printf '%-5s done earlier' "$step")")
        continue
    fi
    ( "step_$step" )
    status=$?
    minutes=$(( ($(date +%s) - start) / 60 ))
    echo "##### $step: exit $status after ${minutes} min [$(date '+%F %H:%M:%S')] #####"
    progress "$step" "$status" "$minutes"
    summary+=("$(printf '%-5s exit %-3s %5s min' "$step" "$status" "$minutes")")
done

echo
echo "===== summary ====="
printf '%s\n' "${summary[@]}"
echo
echo "copy to the laptop: results-helios-{run3-chain11,run3-node,run2-chain11-1tb}"
echo "and run{2,3}_chain11_gate.txt (test/FINAL.md)"
[[ -z "$DRY_RUN" ]] && { sacct -j "${SLURM_JOB_ID}" --format=JobID,JobName,State,Elapsed,MaxRSS,NCPUS,ReqMem || true; }
exit 0
