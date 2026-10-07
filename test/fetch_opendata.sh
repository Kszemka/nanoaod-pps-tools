#!/usr/bin/env bash
#
# Downloads CERN Open Data files named in a URL list (make_filelists.py --transfer-list) into
# <out-dir>/<era>/<PD>/<file>, verifying each file's adler32 checksum against the portal's
# index (opendata_index.py). Open Data is public: no account, certificate or proxy is needed.
#
# The same for CMS data from DAS (das_index.py: index.csv and urls.txt with root:// URIs at an
# AAA redirector), with --transport xrdcp: xrdcp then authenticates with $X509_USER_PROXY and
# verifies against $X509_CERT_DIR (grid_env.sh, slurm_fetch_das.sbatch).
#
#   ./test/fetch_opendata.sh --urls urls.txt --index index.csv \
#       [--out-dir $SCRATCH/bench/data2] [--jobs 10] [--streams 1] \
#       [--transport xrdcp|https] [--dry-run]
#
# --jobs is the number of files in flight, --streams the number of TCP streams xrdcp opens per
# file (xrootd allows up to 15; worth 2-4 only when one stream is held back by latency). Every
# 10 files the total so far and its rate are logged, which is what to look at before changing
# either: past the link's or the eospublic server's limit, more streams only add retries.
#
# Transport: xrdcp when it is on PATH (checksum verified by xrdcp itself), otherwise curl over
# https://opendata.cern.ch/eos/... with the checksum computed afterwards by python3. Not
# https://eospublic.cern.ch: its certificate chains to the CERN Grid CA, which the system
# trust store does not hold, and TLS verification is not to be switched off.
#
# Files go through a .partial name and are skipped if they already exist at the right size, so
# an interrupted download is resumed by running the same command again; only files that are
# missing or failed are fetched. Failures of the last run are listed in <out-dir>/failed.txt.
# At the end <out-dir>/local.txt lists every file of the URL list that is present, ready for
# inventory_files.py --compare.
#
# Long, so start it in tmux on the login node (or as a batch job, if compute nodes can reach
# eospublic.cern.ch).

set -euo pipefail

URLS=""
INDEX=""
OUT_DIR="${SCRATCH:+$SCRATCH/bench/data2}"
JOBS=10
STREAMS=1
DRY_RUN=0
TRANSPORT=""
ATTEMPTS=3

while [[ $# -gt 0 ]]; do
    case "$1" in
        --urls) URLS="$2"; shift 2 ;;
        --index) INDEX="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        --jobs) JOBS="$2"; shift 2 ;;
        --streams) STREAMS="$2"; shift 2 ;;
        --transport) TRANSPORT="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) sed -n '2,/^$/p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "ERROR: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

for value in URLS INDEX OUT_DIR; do
    if [[ -z "${!value}" ]]; then
        echo "ERROR: --$(tr '[:upper:]_' '[:lower:]-' <<<"$value") is required." >&2
        exit 1
    fi
done
for file in "$URLS" "$INDEX"; do
    if [[ ! -f "$file" ]]; then
        echo "ERROR: missing $file" >&2
        exit 1
    fi
done
mkdir -p "$OUT_DIR"

if [[ -z "$TRANSPORT" ]]; then
    if command -v xrdcp >/dev/null; then
        TRANSPORT=xrdcp
    else
        TRANSPORT=https
    fi
fi
case "$TRANSPORT" in
    xrdcp) command -v xrdcp >/dev/null || { echo "ERROR: xrdcp not on PATH." >&2; exit 1; } ;;
    https)
        if ! command -v curl >/dev/null || ! command -v python3 >/dev/null; then
            echo "ERROR: neither xrdcp nor curl + python3 is available." >&2
            exit 1
        fi ;;
    *) echo "ERROR: --transport must be xrdcp or https" >&2; exit 1 ;;
esac

# One line per file of the URL list: uri size adler32 target. The index is plain CSV without
# quoted fields (URIs, UUID names, dataset names), so awk can split it on commas.
MANIFEST="$OUT_DIR/manifest.txt"
awk -F, -v out="$OUT_DIR" '
    NR == FNR { if (FNR > 1) { size[$1] = $3; cksum[$1] = $4; era[$1] = $6; pd[$1] = $7; name[$1] = $2 }; next }
    /^[[:space:]]*(#|$)/ { next }
    !($1 in size) { print "ERROR: not in the index: " $1 > "/dev/stderr"; bad = 1; next }
    {
        c = cksum[$1]
        while (length(c) < 8) c = "0" c
        printf "%s %s %s %s/%s/%s/%s\n", $1, size[$1], c, out, era[$1], pd[$1], name[$1]
    }
    END { exit bad }
' "$INDEX" "$URLS" >"$MANIFEST"
# The https path rewrites eospublic URIs to opendata.cern.ch; any other server needs xrdcp.
if [[ "$TRANSPORT" == https ]] && grep -qv '^root://eospublic\.cern\.ch/' "$MANIFEST"; then
    echo "ERROR: --transport https only works for CERN Open Data (root://eospublic.cern.ch/);" \
        "use --transport xrdcp." >&2
    exit 1
fi

file_size() { wc -c <"$1" | tr -d ' '; }

total=0
missing=0
need=0
while read -r uri size cksum target; do
    total=$((total + 1))
    if [[ ! -f "$target" || "$(file_size "$target")" -ne "$size" ]]; then
        missing=$((missing + 1))
        need=$((need + size))
    fi
done <"$MANIFEST"
free_kb="$(df -Pk "$OUT_DIR" | awk 'NR == 2 {print $4}')"
need_kb=$((need / 1024))
echo "=== $total files in $(basename "$URLS"), $missing still to fetch:" \
    "$((need_kb / 1048576)) GB needed, $((free_kb / 1048576)) GB free in $OUT_DIR ($TRANSPORT)"
# df knows the file system, not the grant; on Cyfronet the binding limit is the quota (hpc-fs).
echo "    (df only; check the grant's quota with hpc-fs before a 1 TB download)"
# 5% margin: a full file system mid-download leaves every stream with a broken .partial.
if [[ "$need_kb" -gt 0 && $((need_kb + need_kb / 20)) -ge "$free_kb" ]]; then
    echo "ERROR: not enough free space." >&2
    exit 1
fi
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "dry run: manifest in $MANIFEST"
    exit 0
fi

FAILED="$OUT_DIR/failed.txt"
: >"$FAILED"
# One line (bytes) per file fetched by this run; the rate is computed from it.
PROGRESS="$OUT_DIR/progress.txt"
: >"$PROGRESS"
START="$(date +%s)"

# report_rate <label>: files and GB fetched by this run so far, and the mean rate.
report_rate() {
    local elapsed=$(($(date +%s) - START))
    awk -v t="$((elapsed > 0 ? elapsed : 1))" -v label="$1" \
        '{ n++; b += $1 } END { printf "  -- %s: %d files, %.1f GB in %d s, %.0f MB/s\n", label, n, b / 1e9, t, b / 1e6 / t }' \
        "$PROGRESS"
}

# fetch_one <uri> <size> <adler32> <target>
fetch_one() {
    local uri="$1" size="$2" cksum="$3" target="$4" attempt
    if [[ -f "$target" && "$(file_size "$target")" -eq "$size" ]]; then
        return 0
    fi
    mkdir -p "$(dirname "$target")"
    for ((attempt = 1; attempt <= ATTEMPTS; attempt++)); do
        rm -f "${target}.partial"
        if [[ "$TRANSPORT" == xrdcp ]]; then
            local streams=()
            [[ "$STREAMS" -gt 1 ]] && streams=(--streams "$STREAMS")
            xrdcp --nopbar --force ${streams[@]+"${streams[@]}"} --cksum "adler32:$cksum" \
                "$uri" "${target}.partial" 2>>"${target}.log" || continue
        else
            curl -fsSL --retry 3 -o "${target}.partial" \
                "https://opendata.cern.ch/${uri#root://*//}" 2>>"${target}.log" || continue
            [[ "$(adler32 "${target}.partial")" == "$cksum" ]] || {
                echo "adler32 mismatch" >>"${target}.log"; continue; }
        fi
        if [[ "$(file_size "${target}.partial")" -eq "$size" ]]; then
            mv "${target}.partial" "$target"
            rm -f "${target}.log"
            echo "  $(basename "$target")"
            # Lines this short are appended atomically, so parallel fetches can share the file.
            echo "$size" >>"$PROGRESS"
            if (($(wc -l <"$PROGRESS") % 10 == 0)); then
                report_rate "so far"
            fi
            return 0
        fi
        echo "size mismatch" >>"${target}.log"
    done
    rm -f "${target}.partial"
    echo "$uri" >>"$FAILED"
    echo "  FAILED $(basename "$target") (see ${target}.log)" >&2
}

adler32() {
    python3 - "$1" <<'EOF'
import sys, zlib
value = 1
with open(sys.argv[1], "rb") as f:
    for block in iter(lambda: f.read(1 << 24), b""):
        value = zlib.adler32(block, value)
print(f"{value:08x}")
EOF
}

export -f fetch_one adler32 file_size report_rate
export TRANSPORT ATTEMPTS FAILED STREAMS PROGRESS START
echo "=== fetching with $JOBS files in flight${STREAMS:+, $STREAMS stream(s) per file}"
xargs -P "$JOBS" -L 1 bash -c 'fetch_one "$@"' _ <"$MANIFEST" || true
report_rate "this run"

# xargs reports a failure but not which file; count what is there instead.
LOCAL="$OUT_DIR/local.txt"
: >"$LOCAL"
present=0
while read -r uri size cksum target; do
    if [[ -f "$target" && "$(file_size "$target")" -eq "$size" ]]; then
        echo "$target" >>"$LOCAL"
        present=$((present + 1))
    fi
done <"$MANIFEST"
echo "done: $present of $total files in $OUT_DIR, list in $LOCAL"
if [[ "$present" -ne "$total" ]]; then
    echo "ERROR: $((total - present)) files missing (failed.txt); run the same command again." >&2
    exit 1
fi
