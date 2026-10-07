#!/usr/bin/env bash
#
# Grid tools for reading CMS data from DAS over xrootd (AAA): voms-proxy-*, xrdcp/xrdfs,
# dasgoclient, the IGTF CA certificates and the VOMS configuration of the cms VO.
#
#   bash test/grid_env.sh --install     # once, on the login node: whatever CVMFS does not give
#   source test/grid_env.sh             # every time: exports the paths, installs nothing
#
# Sources, first one found:
#   CA certificates   /cvmfs/grid.cern.ch/etc/grid-security/certificates, else ca-policy-lcg in
#                     the micromamba env pps-grid
#   VOMS (vomses,     /cvmfs/grid.cern.ch/etc/grid-security/{vomses,vomsdir}, else ~/.voms,
#   vomsdir)          written by --install
#   voms-proxy-*,     PATH (e.g. pps-bench already has xrootd), else pps-grid
#   xrdcp, xrdfs
#   dasgoclient       /cvmfs/cms.cern.ch/common, else $SCRATCH/bench/bin (GitHub release)
#
# pps-grid is a separate env so that nothing in pps-bench (ROOT, numpy) is changed. Its bin
# directory goes to the end of PATH: its python, if it has one, never shadows pps-bench's.
#
# X509_USER_PROXY defaults to ~/.x509up_cms: home is shared with the compute nodes, /tmp is not.
# The proxy itself is made by hand (voms-proxy-init asks for the key's passphrase); see
# slurm_fetch_das.sbatch. Nothing here reads ~/.globus or the proxy.

_grid_bench="${SCRATCH:+$SCRATCH/bench}"
_grid_bench="${_grid_bench:-$HOME/bench}"
_grid_mamba="${MAMBA_ROOT_PREFIX:-${_grid_bench}/micromamba}"
_grid_env="${_grid_mamba}/envs/pps-grid"
_grid_cvmfs=/cvmfs/grid.cern.ch/etc/grid-security
_grid_bin="${_grid_bench}/bin"
DASGOCLIENT_URL="${DASGOCLIENT_URL:-https://github.com/dmwm/dasgoclient/releases/latest/download/dasgoclient_amd64}"

# The cms VO's VOMS server (CERN IAM), as published by CERN; public configuration, not a secret.
# Only used without CVMFS. Check against /etc/vomses on lxplus if voms-proxy-init rejects it.
_grid_vomses='"cms" "voms-cms-auth.cern.ch" "443" "/DC=ch/DC=cern/OU=computers/CN=cms-auth.cern.ch" "cms"'
_grid_lsc='/DC=ch/DC=cern/OU=computers/CN=cms-auth.cern.ch
/DC=ch/DC=cern/CN=CERN Grid Certification Authority'

grid_install() {
    set -euo pipefail
    if [[ ! -d "$_grid_cvmfs/certificates" ]] || ! command -v voms-proxy-init >/dev/null \
        || ! command -v xrdcp >/dev/null; then
        local mamba="${_grid_mamba}/bin/micromamba"
        if [[ ! -x "$mamba" ]]; then
            echo "ERROR: no micromamba at $mamba (set MAMBA_ROOT_PREFIX)." >&2
            return 1
        fi
        if [[ ! -d "$_grid_env" ]]; then
            echo "=== micromamba env pps-grid: voms, xrootd, ca-policy-lcg (conda-forge)"
            MAMBA_ROOT_PREFIX="$_grid_mamba" "$mamba" create -y -n pps-grid -c conda-forge \
                voms xrootd ca-policy-lcg
        else
            echo "  pps-grid already exists: $_grid_env"
        fi
    fi
    if [[ ! -d "$_grid_cvmfs/vomses" ]]; then
        echo "=== ~/.voms: vomses and .lsc of the cms VO"
        mkdir -p "$HOME/.voms/vomses" "$HOME/.voms/vomsdir/cms"
        printf '%s\n' "$_grid_vomses" >"$HOME/.voms/vomses/cms-auth.cern.ch"
        printf '%s\n' "$_grid_lsc" >"$HOME/.voms/vomsdir/cms/voms-cms-auth.cern.ch.lsc"
    fi
    if [[ ! -x /cvmfs/cms.cern.ch/common/dasgoclient && ! -x "$_grid_bin/dasgoclient" ]]; then
        echo "=== dasgoclient from $DASGOCLIENT_URL"
        mkdir -p "$_grid_bin"
        curl -fsSL --proto '=https' -o "$_grid_bin/dasgoclient.partial" "$DASGOCLIENT_URL"
        chmod 755 "$_grid_bin/dasgoclient.partial"
        mv "$_grid_bin/dasgoclient.partial" "$_grid_bin/dasgoclient"
    fi
    grid_setup
    grid_report
}

grid_setup() {
    if [[ -d "$_grid_cvmfs/certificates" ]]; then
        export X509_CERT_DIR="$_grid_cvmfs/certificates"
    elif [[ -d "$_grid_env/etc/grid-security/certificates" ]]; then
        export X509_CERT_DIR="$_grid_env/etc/grid-security/certificates"
    fi
    if [[ -d "$_grid_cvmfs/vomses" ]]; then
        export VOMS_USERCONF="$_grid_cvmfs/vomses" X509_VOMS_DIR="$_grid_cvmfs/vomsdir"
    elif [[ -d "$HOME/.voms/vomses" ]]; then
        export VOMS_USERCONF="$HOME/.voms/vomses" X509_VOMS_DIR="$HOME/.voms/vomsdir"
    fi
    if [[ -d "$_grid_env/bin" && ":$PATH:" != *":$_grid_env/bin:"* ]]; then
        export PATH="$PATH:$_grid_env/bin"
    fi
    local dir
    for dir in /cvmfs/cms.cern.ch/common "$_grid_bin"; do
        if [[ -x "$dir/dasgoclient" ]]; then
            [[ ":$PATH:" == *":$dir:"* ]] || export PATH="$PATH:$dir"
            break
        fi
    done
    export X509_USER_PROXY="${X509_USER_PROXY:-$HOME/.x509up_cms}"
}

# grid_report: what was found; returns 1 if anything the download needs is missing.
grid_report() {
    local missing=0 tool
    for tool in voms-proxy-init voms-proxy-info xrdcp xrdfs dasgoclient; do
        if command -v "$tool" >/dev/null; then
            echo "  $tool: $(command -v "$tool")"
        else
            echo "  $tool: MISSING (bash test/grid_env.sh --install)"
            missing=1
        fi
    done
    local var
    for var in X509_CERT_DIR VOMS_USERCONF X509_VOMS_DIR; do
        if [[ -n "${!var:-}" && -d "${!var}" ]]; then
            echo "  $var=${!var}"
        else
            echo "  $var: MISSING (bash test/grid_env.sh --install)"
            missing=1
        fi
    done
    echo "  X509_USER_PROXY=$X509_USER_PROXY"
    return "$missing"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        --install) grid_install ;;
        --check) grid_setup; grid_report ;;
        *) sed -n '2,/^$/p' "$0"; echo "  (source it, or run with --install or --check)" ;;
    esac
else
    grid_setup
fi
