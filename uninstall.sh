#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# e-con NetraVis6L_USB stereo camera — Isaac Sim uninstaller (Linux)
#
# Reverts what build.sh did:
#   - removes this package's dependency line from the Full app .kit files (other e-con
#     packages patched into the same files are left alone),
#   - removes the extension from <isaac>/extsUser.
# Finds Isaac Sim the same way build.sh does.
#
# Usage:
#   ./uninstall.sh                          # auto-detect Isaac Sim
#   ISAACSIM_PATH=/path/to/isaacsim ./uninstall.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_NAMES="${EXT_NAMES:-econ.netravis.menu}"
info() { printf '[INFO] %s\n'  "$*"; }
err()  { printf '[ERROR] %s\n' "$*" >&2; }

# ── Locate the Isaac Sim install (holds isaac-sim.sh) ─────────────────────────
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
            printf "Uninstall from which one? [1-%d], or blank to abort: " "${#CANDIDATES[@]}"
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

# ── Revert ────────────────────────────────────────────────────────────────────
for _n in ${EXT_NAMES}; do
    if command -v python3 >/dev/null 2>&1; then
        python3 "${SCRIPT_DIR}/scripts/patch_kit.py" "${ISAACSIM_PATH}/apps" "${_n}" --uninstall \
            || err "Could not update .kit files for ${_n} (continuing)."
    else
        err "python3 not found — cannot update .kit files automatically."
    fi
    rm -rf "${ISAACSIM_PATH}/extsUser/${_n}"
    info "Removed ${ISAACSIM_PATH}/extsUser/${_n}"
done

cat <<EOF

[SUCCESS] e-con NetraVis6L_USB removed.
  Re-install anytime with ./build.sh
EOF
