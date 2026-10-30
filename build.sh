#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# e-con NetraVis6L_USB stereo camera — Isaac Sim installer (Linux)
#
# Verifies the package, locates Isaac Sim, and registers the econ.netravis.menu extension
# so the cameras appear under Create -> Sensors -> Camera and Depth Sensors -> e-con on
# every launch. Pure Python — nothing to compile.
#
# Usage:
#   ./build.sh                         # register the extension with Isaac Sim
#   ISAACSIM_PATH=… ./build.sh         # skip Isaac Sim auto-detection
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Configuration (override via env) ──────────────────────────────────────────
# Extensions this package installs.
EXT_NAMES="${EXT_NAMES:-econ.netravis.menu}"

# Folder holding exts/ (this package).
INSTALL_DIR="${INSTALL_DIR:-${SCRIPT_DIR}}"

# ── Helpers ───────────────────────────────────────────────────────────────────
info()  { printf '[INFO] %s\n'  "$*"; }
err()   { printf '[ERROR] %s\n' "$*" >&2; }

# ── 1. Check the extension is present ────────────────────────────────────────
for _n in ${EXT_NAMES}; do
    if [ ! -d "${INSTALL_DIR}/exts/${_n}" ]; then
        err "Extension not found at ${INSTALL_DIR}/exts/${_n}."
        err "This package must contain exts/${_n}/ (config/extension.toml + python)."
        exit 1
    fi
    info "Found extension: ${INSTALL_DIR}/exts/${_n}"
done

# ── 2. Locate the Isaac Sim install (holds isaac-sim.sh) ─────────────────────────
# $ISAACSIM_PATH (or $ISAAC_SIM_PATH) wins. Otherwise every install in the usual places
# is collected (then $HOME is searched): one is used directly, several are listed to pick from.
isaac_version() { { head -c 60 "$1/VERSION" 2>/dev/null || true; } | cut -d+ -f1 | tr -d '\n'; }
ISAACSIM_PATH="${ISAACSIM_PATH:-${ISAAC_SIM_PATH:-}}"
if [ -z "${ISAACSIM_PATH}" ]; then
    CANDIDATES=()
    for cand in \
        "${HOME}"/.local/share/ov/pkg/isaac-sim-* \
        "${HOME}"/.local/share/ov/pkg/isaac_sim-* \
        "${HOME}"/isaacsim* "${HOME}"/isaac-sim* "${HOME}"/isaac_sim* \
        "${HOME}"/[Dd]ownloads/isaacsim* "${HOME}"/[Dd]ownloads/isaac-sim* \
        /opt/isaacsim* /opt/isaac-sim* ; do
        if [ -x "${cand}/isaac-sim.sh" ]; then CANDIDATES+=("$(cd "${cand}" && pwd -P)"); fi
    done
    if [ ${#CANDIDATES[@]} -eq 0 ]; then
        info "Searching for isaac-sim.sh under ${HOME} …"
        # Skip Trash and .cache.
        while IFS= read -r found; do
            CANDIDATES+=("$(cd "$(dirname "${found}")" && pwd -P)")
        done < <(find "${HOME}" -maxdepth 7 -type d \( -name Trash -o -name .cache \) -prune \
                      -o -type f -name isaac-sim.sh -print 2>/dev/null || true)
    fi
    if [ ${#CANDIDATES[@]} -gt 0 ]; then         # de-duplicate (symlinks resolve to one folder)
        mapfile -t CANDIDATES < <(printf '%s\n' "${CANDIDATES[@]}" | awk 'NF && !seen[$0]++')
    fi
    if [ ${#CANDIDATES[@]} -eq 1 ]; then
        ISAACSIM_PATH="${CANDIDATES[0]}"
    elif [ ${#CANDIDATES[@]} -gt 1 ]; then
        info "Found ${#CANDIDATES[@]} Isaac Sim installs:"
        FIRST_EXT="${EXT_NAMES%% *}"
        for i in "${!CANDIDATES[@]}"; do
            mark=""
            [ -d "${CANDIDATES[$i]}/extsUser/${FIRST_EXT}" ] && mark="   [NetraVis6L_USB installed]"
            printf '  %d) %s   Isaac Sim %s%s\n' "$((i + 1))" "${CANDIDATES[$i]}" \
                "$(isaac_version "${CANDIDATES[$i]}")" "${mark}"
        done
        if [ ! -t 0 ]; then
            err "Several Isaac Sim installs found. Re-run with ISAACSIM_PATH set to the one you launch:"
            err "  ISAACSIM_PATH=<one of the folders above> ./$(basename "$0")"
            exit 1
        fi
        while :; do
            printf "Install into which one? [1-%d], or blank to abort: " "${#CANDIDATES[@]}"
            read -r pick
            [ -z "${pick}" ] && { err "Aborted — no Isaac Sim chosen."; exit 1; }
            if [[ "${pick}" =~ ^[0-9]+$ ]] && [ "${pick}" -ge 1 ] && [ "${pick}" -le ${#CANDIDATES[@]} ]; then
                ISAACSIM_PATH="${CANDIDATES[$((pick - 1))]}"
                break
            fi
            err "Enter a number from 1 to ${#CANDIDATES[@]}."
        done
    fi
fi
# Still nothing -> ask for the folder (interactive only).
while [ -z "${ISAACSIM_PATH}" ] || [ ! -x "${ISAACSIM_PATH}/isaac-sim.sh" ]; do
    if [ ! -t 0 ]; then
        err "Isaac Sim not found. Re-run with: ISAACSIM_PATH=/path/to/isaacsim ./$(basename "$0")"
        exit 1
    fi
    printf "Enter the Isaac Sim folder (contains isaac-sim.sh), or blank to abort: "
    read -r ISAACSIM_PATH
    [ -z "${ISAACSIM_PATH}" ] && { err "Aborted — no Isaac Sim path given."; exit 1; }
    ISAACSIM_PATH="${ISAACSIM_PATH/#\~/$HOME}"
    [ -x "${ISAACSIM_PATH}/isaac-sim.sh" ] || err "No isaac-sim.sh in '${ISAACSIM_PATH}' — try again."
done
info "Using Isaac Sim at: ${ISAACSIM_PATH}   (Isaac Sim $(isaac_version "${ISAACSIM_PATH}"))"

# ── 3. Register so it auto-loads on every normal launch ──────────────────────
#   (a) copy the extension into <isaac>/extsUser (a copy, so it keeps working if this
#       folder is moved);
#   (b) add it to the Full app's .kit [dependencies], which is read on every launch.
if ! command -v python3 >/dev/null 2>&1; then
    err "python3 not found — needed to register the extensions. Install python3 and re-run."
    exit 1
fi

EXTSUSER="${ISAACSIM_PATH}/extsUser"
mkdir -p "${EXTSUSER}"
for _n in ${EXT_NAMES}; do
    _dir="${INSTALL_DIR}/exts/${_n}"
    rm -rf "${EXTSUSER:?}/${_n}"
    cp -r "${_dir}" "${EXTSUSER}/${_n}"
    info "Installed ${EXTSUSER}/${_n}"
    python3 "${INSTALL_DIR}/scripts/patch_kit.py" "${ISAACSIM_PATH}/apps" "${_n}" \
        || { err "Could not patch the Isaac Sim .kit files for ${_n}."; exit 1; }
done

# ── 4. Done ───────────────────────────────────────────────────────────────────
cat <<EOF

[SUCCESS] e-con NetraVis6L_USB installed (auto-loads on every launch).

  If Isaac Sim is open, fully close and reopen it. Launch normally — no special command.
  Then: Create -> Sensors -> Camera and Depth Sensors -> e-con -> NetraVis6L_USB

  Uninstall (reverts everything): ./uninstall.sh
EOF
