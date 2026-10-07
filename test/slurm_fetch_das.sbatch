#!/bin/bash -l
#SBATCH --job-name=pps-fetch-das
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=fetch-das-%j.out
#SBATCH --error=fetch-das-%j.err

# Run 3 NanoAOD from DAS into $OUT_DIR (default $SCRATCH/bench/data3) over the CMS xrootd
# federation (AAA), checked and turned into the benchmark's lists, like
# slurm_fetch_opendata.sbatch does for Open Data. Default: /Muon*/Run2023*/NANOAOD, ~1 TB.
#
#   0. checks      grid tools (grid_env.sh), proxy (exists, valid >= PROXY_MIN_VALID, /cms
#                  attribute, owner, mode 600, outside the repository and OUT_DIR), cmsweb and
#                  the redirector reachable, MAX_GB within the scratch quota
#   1. index       das_index.py index: one processing per (PD, era), complete disk copies only
#                  -> datasets.csv, index.csv, remote.csv, sample.txt
#      columns     inventory_files.py --no-loop over sample.txt (one file per dataset, remote):
#                  a dataset without the benchmark columns is dropped -> sample.csv
#   2. select      das_index.py select: up to MAX_GB, era by era in ERAS order -> urls.txt
#                  LIST_ONLY=1 stops here, after printing what DAS has and what was chosen
#   3. fetch       fetch_opendata.sh --transport xrdcp: FETCH_JOBS files at a time, adler32
#                  from DBS checked by xrdcp; repeated up to FETCH_ATTEMPTS times
#   4. verify      inventory_files.py --compare remote.csv: entries and size against DBS
#      lists       make_filelists.py -> core.txt, weak_N.txt, impl.txt, sets.json
#   5. READY       written last; with DELETE_PROXY=1 (default) the proxy is then deleted
#
# Each step is skipped when its output exists, so a job that ran out of time is submitted again.
# selection.txt records the query and the budget: a different DAS_QUERY, CAMPAIGNS or REDIRECTOR
# redoes everything from step 1, a different MAX_GB or ERAS from step 2. Files already
# downloaded stay; with a larger MAX_GB only the new ones are fetched.
#
# Once, on the login node (CVMFS provides what it can, the rest goes to the env pps-grid):
#   bash test/grid_env.sh --install
# Before every download, on the login node -- voms-proxy-init asks for the key's passphrase,
# which no script stores:
#   source test/grid_env.sh
#   chmod 400 ~/.globus/userkey.pem; chmod 644 ~/.globus/usercert.pem
#   openssl x509 -in ~/.globus/usercert.pem -noout -text \
#       | grep -E 'Not After|Public-Key|Signature Algorithm|Issuer|Subject:'
#   voms-proxy-init --voms cms --rfc --bits 2048 --valid 48:00 --out ~/.x509up_cms
#   chmod 600 ~/.x509up_cms && voms-proxy-info --all --file ~/.x509up_cms
# --valid 48:00 covers ~1 TB with room for a resubmission; up to 192:00 for several TB.
#
#   sbatch --export=ALL,LIST_ONLY=1 test/slurm_fetch_das.sbatch    # what DAS has, what is chosen
#   sbatch test/slurm_fetch_das.sbatch                             # ~1 TB
#   sbatch --export=ALL,MAX_GB=4000 test/slurm_fetch_das.sbatch    # more, same directory
#   sbatch --export=ALL,CAMPAIGNS=22Sep2023 test/slurm_fetch_das.sbatch
#
# CMS data from DAS is not public: it stays on scratch, outside the repository.

set -euo pipefail

SCRATCH_BENCH="${SCRATCH:-}/bench"
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    # sbatch runs a copy of this file from the spool directory, so its own path says nothing.
    REPO="${REPO:-${SCRATCH_BENCH}/nanoaod-pps-tools}"
else
    REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
fi
if [[ -z "${PY:-}" ]]; then
    export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"
    # See slurm_benchmark.sbatch: the env's deactivate script trips over set -u.
    set +u
    eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
    micromamba activate pps-bench
    set -u
    PY="$(command -v python)"
fi
T="$REPO/test"
# shellcheck source=grid_env.sh
source "$T/grid_env.sh"

OUT_DIR="${OUT_DIR:-${SCRATCH_BENCH}/data3}"
MAX_GB="${MAX_GB:-1040}"
DAS_QUERY="${DAS_QUERY:-/Muon*/Run2023*/NANOAOD}"
ERAS="${ERAS:-Run2023C Run2023D Run2023B}"
CAMPAIGNS="${CAMPAIGNS:-}"
REDIRECTOR="${REDIRECTOR:-root://cms-xrd-global.cern.ch/}"
FETCH_JOBS="${FETCH_JOBS:-8}"
XRD_STREAMS="${XRD_STREAMS:-1}"
SCAN_JOBS="${SCAN_JOBS:-16}"
FETCH_ATTEMPTS="${FETCH_ATTEMPTS:-3}"
MIN_PPS="${MIN_PPS:-0.01}"
PROXY_MIN_VALID="${PROXY_MIN_VALID:-6:00}"
LIST_ONLY="${LIST_ONLY:-}"
DELETE_PROXY="${DELETE_PROXY:-1}"
mkdir -p "$OUT_DIR"
cd "$OUT_DIR"
read -r -a eras <<<"$ERAS"
campaigns=()
[[ -n "$CAMPAIGNS" ]] && read -r -a campaigns <<<"$CAMPAIGNS"

stamp() { date +%H:%M:%S; }
fail() { echo "ERROR: $*" >&2; exit 1; }

echo "=== DAS $DAS_QUERY -> $OUT_DIR: up to $MAX_GB GB of ${ERAS}, $FETCH_JOBS files x" \
    "$XRD_STREAMS stream(s) via $REDIRECTOR [$(stamp)]"

index_key="query=$DAS_QUERY campaigns=$CAMPAIGNS redirector=$REDIRECTOR"
select_key="max_gb=$MAX_GB eras=$ERAS min_pps=$MIN_PPS"
if [[ -f selection.txt ]]; then
    old_select="$(sed -n 2p selection.txt)"
    if [[ "$(sed -n 1p selection.txt)" != "$index_key" ]]; then
        echo "  query changed: index and selection are redone"
        rm -f datasets.csv index.csv remote.csv sample.txt sample.csv
        old_select=""
    fi
    if [[ "$old_select" != "$select_key" ]]; then
        echo "  budget changed: selection, verification and lists are redone"
        rm -f urls.txt manifest.txt local.txt local.csv sets.json core.txt impl.txt weak_*.txt READY
    fi
fi
printf '%s\n%s\n' "$index_key" "$select_key" >selection.txt
if [[ -f READY ]]; then
    echo "already complete:"
    cat READY
    exit 0
fi

echo "=== 0. checks [$(stamp)]"
grid_report || fail "grid tools missing; run 'bash test/grid_env.sh --install' on the login node."

proxy="$X509_USER_PROXY"
[[ -f "$proxy" ]] || fail "no proxy at $proxy; make it on the login node (see the header)."
[[ "$(stat -c %U "$proxy")" == "$USER" ]] || fail "$proxy is not owned by $USER."
case "$(stat -c %a "$proxy")" in
    600|400) ;;
    *) fail "$proxy is readable by others; chmod 600 it (or make a new one)." ;;
esac
proxy_real="$(realpath "$proxy")"
for dir in "$REPO" "$OUT_DIR"; do
    if [[ "$proxy_real" == "$(realpath "$dir")"/* ]]; then
        fail "the proxy is inside $dir; it belongs outside the repository and the data."
    fi
done
voms-proxy-info --file "$proxy" --exists --valid "$PROXY_MIN_VALID" >/dev/null \
    || fail "proxy expired or valid for less than $PROXY_MIN_VALID; run voms-proxy-init again."
fqan="$(voms-proxy-info --file "$proxy" --fqan 2>/dev/null | head -n 1)"
[[ "$fqan" == /cms* ]] || fail "the proxy has no /cms VOMS attribute (voms-proxy-init --voms cms)."
echo "  proxy: $fqan, $(($(voms-proxy-info --file "$proxy" --timeleft) / 3600)) h left"

# reach <host> <port>: a TCP connection, nothing sent.
reach() { timeout 30 bash -c "exec 3<>/dev/tcp/$1/$2" 2>/dev/null; }
xrd_host="${REDIRECTOR#root://}"
xrd_host="${xrd_host%%/*}"
xrd_port=1094
if [[ "$xrd_host" == *:* ]]; then
    xrd_port="${xrd_host##*:}"
    xrd_host="${xrd_host%:*}"
fi
reach cmsweb.cern.ch 443 || fail "$(hostname) cannot reach cmsweb.cern.ch:443 (DAS)."
reach "$xrd_host" "$xrd_port" || fail "$(hostname) cannot reach $xrd_host:$xrd_port (xrootd)."
echo "  $(hostname) reaches cmsweb.cern.ch and $xrd_host:$xrd_port"

if command -v lfs >/dev/null && [[ -n "${SCRATCH:-}" ]]; then
    # kB. The file system's name may share the line with the numbers or sit above them.
    read -r used_kb limit_kb < <(lfs quota -u "$USER" "$SCRATCH" | awk '
        function n(x) { gsub(/\*/, "", x); return x }
        $1 ~ /^[0-9]+\*?$/ { print n($1), (n($3) > 0 ? n($3) : n($2)); exit }
        $2 ~ /^[0-9]+\*?$/ { print n($2), (n($4) > 0 ? n($4) : n($3)); exit }') || true
    if [[ -n "${limit_kb:-}" && "$limit_kb" -gt 0 ]]; then
        have_kb="$(du -sk "$OUT_DIR" | awk '{print $1}')"
        # 5% margin, as fetch_opendata.sh: a full quota mid-download breaks every stream.
        need_kb="$(awk -v g="$MAX_GB" -v h="$have_kb" 'BEGIN { n = g * 1.05e9 / 1024 - h; print (n > 0 ? int(n) : 0) }')"
        echo "  quota: $((used_kb / 1048576)) of $((limit_kb / 1048576)) GiB used," \
            "$((need_kb / 1048576)) GiB more needed"
        if ((used_kb + need_kb >= limit_kb)); then
            [[ -n "$LIST_ONLY" ]] || fail "MAX_GB=$MAX_GB does not fit in the quota."
            echo "  WARNING: MAX_GB=$MAX_GB does not fit in the quota (LIST_ONLY: going on)"
        fi
    else
        echo "  quota: no limit reported by lfs; fetch_opendata.sh still checks df"
    fi
else
    echo "  quota: lfs not available; fetch_opendata.sh still checks df"
fi

echo "=== 1. DAS index and column check [$(stamp)]"
if [[ ! -s index.csv ]]; then
    "$PY" "$T/das_index.py" index --query "$DAS_QUERY" --redirector "$REDIRECTOR" --out-dir . \
        ${campaigns[@]+--campaigns "${campaigns[@]}"}
fi
if [[ ! -s sample.csv ]]; then
    # One ROOT thread per file: the scan waits on the network, not on the CPU.
    "$PY" "$T/inventory_files.py" --list sample.txt --output sample.csv.partial --no-loop \
        --jobs "$SCAN_JOBS" --threads 1
    if ! "$PY" - sample.csv.partial <<'PYEOF'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
sys.exit(0 if any(not r.get("error") for r in rows) else 1)
PYEOF
    then
        rm -f sample.csv.partial
        fail "no sample file could be opened over xrootd: proxy, CA ($X509_CERT_DIR) or redirector."
    fi
    mv sample.csv.partial sample.csv
fi

echo "=== 2. selection: up to $MAX_GB GB [$(stamp)]"
if [[ ! -s urls.txt || -n "$LIST_ONLY" ]]; then
    "$PY" "$T/das_index.py" select --index index.csv --max-gb "$MAX_GB" --era-order "${eras[@]}" \
        --exclude sample.csv --output urls.txt
fi
if [[ -n "$LIST_ONLY" ]]; then
    "$PY" - datasets.csv <<'PYEOF'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
print(f"  {'status':11} {'files':>6} {'events':>12} {'GB':>8}  dataset")
for r in sorted(rows, key=lambda r: (r["status"] != "selected", r["dataset"])):
    print(f"  {r['status']:11} {r['files']:>6} {r['events']:>12} {r['size_gb']:>8}  "
          f"{r['dataset']}  {r['note']}")
for status in ("selected", "tape-only"):
    gb = sum(float(r["size_gb"] or 0) for r in rows if r["status"] == status)
    print(f"  {status}: {gb / 1000:.2f} TB")
PYEOF
    echo "LIST_ONLY: stopping before the download [$(stamp)]"
    exit 0
fi

echo "=== 3. download [$(stamp)]"
fetched=""
for ((attempt = 1; attempt <= FETCH_ATTEMPTS; attempt++)); do
    if bash "$T/fetch_opendata.sh" --urls urls.txt --index index.csv --out-dir "$OUT_DIR" \
        --jobs "$FETCH_JOBS" --streams "$XRD_STREAMS" --transport xrdcp; then
        fetched=1
        break
    fi
    echo "  attempt $attempt of $FETCH_ATTEMPTS left files missing; retrying [$(stamp)]"
done
if [[ -z "$fetched" ]]; then
    echo "ERROR: files still missing after $FETCH_ATTEMPTS attempts; see $OUT_DIR/failed.txt." >&2
    echo "       Submitting this job again resumes where it stopped (the proxy is kept)." >&2
    exit 1
fi

echo "=== 4. verification and lists [$(stamp)]"
if [[ ! -s local.csv ]]; then
    "$PY" "$T/inventory_files.py" --list local.txt --output local.csv.partial \
        --compare remote.csv --jobs "$SCAN_JOBS" --threads 1
    mv local.csv.partial local.csv
fi
if [[ ! -s sets.json ]]; then
    # core.txt is the whole set: the budget is the download's own, with a margin.
    core_gb="$(awk -v g="$MAX_GB" 'BEGIN { print g * 1.1 + 1 }')"
    "$PY" "$T/make_filelists.py" --inventory local.csv --any-schema --min-pps "$MIN_PPS" \
        --core-gb "$core_gb" --core-events 1e12 --out-dir "$OUT_DIR"
fi

echo "=== 5. READY [$(stamp)]"
"$PY" - local.csv sets.json >READY.partial <<'PYEOF'
import csv, json, sys

rows = [r for r in csv.DictReader(open(sys.argv[1])) if not r.get("error")]
core = json.load(open(sys.argv[2]))["core"]
gb = sum(int(r["size_bytes"]) for r in rows) / 1e9
events = sum(int(r["entries"]) for r in rows)
schemas = sorted({r["schema"] for r in rows})
groups = sorted({f"{r['era']}/{r['primary_dataset']}" for r in rows})
pps = sum(float(r["pps_fraction"] or 0) * int(r["entries"]) for r in rows) / max(events, 1)
print(f"files {len(rows)}  GB {gb:.1f}  events {events}  {' '.join(groups)}")
print(f"schemas {len(schemas)}: {' '.join(schemas)}")
print(f"events with PPS {pps:.3f}  codec {' '.join(sorted({r['compression'] for r in rows}))}")
print(f"core.txt: {core['files']} files, {core['events']} events, {core['gb']} GB")
PYEOF
mv READY.partial READY
cat READY
if [[ "$DELETE_PROXY" == 1 ]]; then
    rm -f "$proxy"
    echo "  proxy $proxy deleted"
fi
echo "done [$(stamp)]"
