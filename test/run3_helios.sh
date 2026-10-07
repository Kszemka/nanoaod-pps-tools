#!/usr/bin/env bash
#
# Submits the Run 3 campaign on Helios, every job of slurm_run3.sbatch on its own, each starting
# when the previous one has ended however it ended (afterany): a job that ran out of time does
# not hold up the rest, and its results stay on disk for RESUME.
#
#   J1  strong scaling, 1-192 threads        (TIME_J1, default 12:00:00)
#   J2  weak scaling, up to 96 threads       (TIME_J2, default 06:00:00)
#   J3  whole node: RDataFrame and uproot    (TIME_J3, default 04:00:00)
#   J4  whole node: Python                   (TIME_J4, default 08:00:00)
#
# Takes seconds; run it on the login node from the repository on scratch.
#
#   bash test/run3_helios.sh                    # J1-J4
#   bash test/run3_helios.sh --from J3          # J3 and J4
#   bash test/run3_helios.sh --only J4          # one job
#   bash test/run3_helios.sh --after 1234567    # the first one waits for job 1234567 too
#   TIME_J1=24:00:00 bash test/run3_helios.sh   # a longer limit for one job
#   bash test/run3_helios.sh --dry-run          # print the sbatch commands only

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ALL=(J1 J2 J3 J4)
DATA_DIR="${DATA_DIR:-${SCRATCH:-}/bench/data3}"
FROM=""
ONLY=""
AFTER=""
DRY_RUN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --from) FROM="$2"; shift 2 ;;
        --only) ONLY="$2"; shift 2 ;;
        --after) AFTER="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) sed -n '2,/^$/p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "ERROR: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

jobs=()
started=""
[[ -z "$FROM" ]] && started=1
for job in "${ALL[@]}"; do
    [[ "$job" == "$FROM" ]] && started=1
    if [[ -n "$ONLY" ]]; then
        [[ "$job" == "$ONLY" ]] && jobs+=("$job")
    elif [[ -n "$started" ]]; then
        jobs+=("$job")
    fi
done
if [[ ${#jobs[@]} -eq 0 ]]; then
    echo "ERROR: no job selected (--from/--only take one of ${ALL[*]})." >&2
    exit 1
fi

if [[ -z "$DRY_RUN" ]]; then
    command -v sbatch >/dev/null || { echo "ERROR: no sbatch here; run this on the Helios login node (or use --dry-run)." >&2; exit 1; }
    [[ -f "$DATA_DIR/READY" ]] || { echo "ERROR: $DATA_DIR/READY missing: sbatch test/slurm_fetch_eos.sbatch first." >&2; exit 1; }
    for list in core.txt impl.txt local.csv sets.json; do
        [[ -s "$DATA_DIR/$list" ]] || { echo "ERROR: $DATA_DIR/$list missing." >&2; exit 1; }
    done
    for n in ${WEAK_SERIES:-1 2 4 8 16 32 48 64 96}; do
        [[ -s "$DATA_DIR/weak_${n}.txt" ]] || { echo "ERROR: $DATA_DIR/weak_${n}.txt missing." >&2; exit 1; }
    done
    if grep -q "DIFFERS" "$DATA_DIR/READY"; then
        echo "WARNING: READY reports a chain column with two types; see check_chain11.py." >&2
    fi
fi

default_time() {
    case "$1" in
        J1) echo 12:00:00 ;;
        J2) echo 06:00:00 ;;
        J3) echo 04:00:00 ;;
        J4) echo 08:00:00 ;;
    esac
}

previous="$AFTER"
for job in "${jobs[@]}"; do
    time_var="TIME_${job}"
    time_limit="${!time_var:-$(default_time "$job")}"
    args=(--parsable --time="$time_limit" --job-name="pps-run3-${job}"
          --export=ALL,JOB="$job",DATA_DIR="$DATA_DIR")
    [[ -n "$previous" ]] && args+=(--dependency="afterany:${previous}")
    if [[ -n "$DRY_RUN" ]]; then
        echo "sbatch ${args[*]} test/slurm_run3.sbatch"
        id="<${job}>"
    else
        id="$(sbatch "${args[@]}" test/slurm_run3.sbatch)"
    fi
    echo "$job: $id  (--time $time_limit${previous:+, after $previous})  -> bench-run3-${id}.out"
    previous="$id"
done

echo
echo "follow:  squeue -u \$USER"
echo "results: \$SCRATCH/bench/results-helios-run3-{chain11,chain11-weak,node}"
