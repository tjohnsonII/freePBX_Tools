#!/usr/bin/env bash
# ============================================================================
# 123NET FreePBX Tools - Uninstaller
# --------------------------------------------------------------------------
# Removes the installed FreePBX tools suite and its symlinks.
#
# Safety defaults:
# - Only removes symlinks the installer created.
# - Does NOT delete /home/123net/callflows unless --purge-callflows.
# - Does NOT remove asterisk/fwconsole convenience symlinks unless --purge-cli-links.
# ============================================================================

set -euo pipefail

INSTALL_ROOT="/usr/local/123net"
INSTALL_DIR="${INSTALL_ROOT}/freepbx-tools"
BIN_DIR="/usr/local/bin"
CALLFLOWS_DIR="/home/123net/callflows"
CALL_SIM_DIR="${INSTALL_ROOT}/call-simulation"

PURGE_CALLFLOWS=0
PURGE_CLI_LINKS=0
ASSUME_YES=0

usage() {
  cat <<'EOF'
Usage: sudo ./uninstall.sh [options]

Options:
  --purge-callflows   Also remove /home/123net/callflows (prompts unless -y)
  --purge-cli-links   Also remove symlinked /usr/local/bin/asterisk and fwconsole
  -y, --yes           Assume "yes" for prompts (non-interactive)
  -h, --help          Show this help
EOF
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This uninstaller needs root. Try: sudo $0" >&2
    exit 1
  fi
}

confirm() {
  local prompt="$1"
  if (( ASSUME_YES )); then
    return 0
  fi
  local ans=""
  read -r -p "${prompt} [y/N] " ans || true
  [[ "$ans" =~ ^[Yy]$ ]]
}

unlink_if_symlink() {
  local p="$1"
  if [[ -L "$p" ]]; then
    rm -f "$p" && echo "Removed symlink: $p"
  fi
}

remove_dir_if_exists() {
  local d="$1"
  if [[ -d "$d" ]]; then
    rm -rf "$d" && echo "Removed dir: $d"
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --purge-callflows) PURGE_CALLFLOWS=1 ;;
      --purge-cli-links) PURGE_CLI_LINKS=1 ;;
      -y|--yes) ASSUME_YES=1 ;;
      -h|--help) usage; exit 0 ;;
      *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
    shift
  done
}

main() {
  require_root
  parse_args "$@"

  echo "Removing tool symlinks under ${BIN_DIR}…"
  # Friendly entrypoints
  for n in \
    freepbx-callflows \
    freepbx-render \
    freepbx-dump \
    freepbx-version-check \
    freepbx-install \
    freepbx-uninstall \
    freepbx-tc-status \
    freepbx-module-analyzer \
    freepbx-module-status \
    freepbx-paging-fax-analyzer \
    freepbx-comprehensive-analyzer \
    freepbx-ascii-callflow \
    callflow-validator
  do
    unlink_if_symlink "${BIN_DIR}/${n}"
  done

  # Legacy/helper symlinks
  for n in \
    freepbx_dump.py \
    freepbx_callflow_graph.py \
    freepbx_render_from_dump.sh \
    freepbx_tc_status.py \
    freepbx_module_analyzer.py \
    freepbx_module_status.py \
    freepbx_paging_fax_analyzer.py \
    freepbx_comprehensive_analyzer.py \
    freepbx_ascii_callflow.py \
    callflow_validator.py \
    asterisk-full-diagnostic.sh
  do
    unlink_if_symlink "${BIN_DIR}/${n}"
  done

  echo "Removing call-simulation symlinks under ${CALL_SIM_DIR}…"
  unlink_if_symlink "${CALL_SIM_DIR}/call_simulator.py"
  unlink_if_symlink "${CALL_SIM_DIR}/simulate_calls.sh"
  unlink_if_symlink "${CALL_SIM_DIR}/callflow_validator.py"
  rmdir "${CALL_SIM_DIR}" 2>/dev/null || true

  if (( PURGE_CLI_LINKS )); then
    echo "Removing convenience CLI symlinks under ${BIN_DIR}…"
    unlink_if_symlink "${BIN_DIR}/asterisk"
    unlink_if_symlink "${BIN_DIR}/fwconsole"
  else
    echo "Keeping any existing asterisk/fwconsole symlinks (use --purge-cli-links to remove)."
  fi

  if [[ -d "$INSTALL_DIR" ]]; then
    remove_dir_if_exists "$INSTALL_DIR"
  else
    echo "Install dir not found (already removed?): $INSTALL_DIR"
  fi

  # Remove parent if empty
  rmdir "${INSTALL_ROOT}" 2>/dev/null || true

  if (( PURGE_CALLFLOWS )); then
    if [[ -d "$CALLFLOWS_DIR" ]]; then
      if confirm "Permanently remove ${CALLFLOWS_DIR}?"; then
        rm -rf "$CALLFLOWS_DIR" && echo "Removed callflows dir: $CALLFLOWS_DIR"
      else
        echo "Preserved callflows dir: $CALLFLOWS_DIR"
      fi
    else
      echo "Callflows dir not found: $CALLFLOWS_DIR"
    fi
  else
    echo "Preserving callflows dir: $CALLFLOWS_DIR (use --purge-callflows to remove)."
  fi

  echo "Uninstall complete."
}

main "$@"
