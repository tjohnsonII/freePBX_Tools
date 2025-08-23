#!/usr/bin/env bash
# 123NET FreePBX Tools - Uninstaller
# - Removes /usr/local/123net/freepbx-tools
# - Removes command symlinks in /usr/local/bin
# - Optionally purges /home/123net/callflows and CLI convenience links

set -Eeuo pipefail

INSTALL_ROOT="/usr/local/123net"
INSTALL_DIR="$INSTALL_ROOT/freepbx-tools"
BIN_DIR="/usr/local/bin"
CALLFLOWS_DIR="/home/123net/callflows"

PURGE_CALLFLOWS=0
PURGE_CLI_LINKS=0
ASSUME_YES=0

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --purge-callflows      Remove ${CALLFLOWS_DIR}
  --purge-cli-links      Remove convenience CLI symlinks (asterisk, fwconsole)
  -y, --yes              Do not prompt for confirmation
  -h, --help             Show this help
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
  if (( ASSUME_YES )); then return 0; fi
  read -r -p "$prompt [y/N] " ans || true
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
      -y|--yes)          ASSUME_YES=1 ;;
      -h|--help)         usage; exit 0 ;;
      *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
    shift
  done
}

main() {
  require_root
  parse_args "$@"

  echo "Removing command symlinks under ${BIN_DIR}…"
  for n in \
    freepbx-diagnostic \
    freepbx-dump \
    freepbx-version-check \
    freepbx-install \
    freepbx-uninstall
  do
    unlink_if_symlink "${BIN_DIR}/${n}"
  done

  if (( PURGE_CLI_LINKS )); then
    echo "Removing convenience CLI symlinks under ${BIN_DIR}…"
    # Only remove if they are symlinks (won't touch real binaries)
    unlink_if_symlink "${BIN_DIR}/asterisk"
    unlink_if_symlink "${BIN_DIR}/fwconsole"
  else
    echo "Keeping any existing CLI symlinks (use --purge-cli-links to remove)."
  fi

  if [[ -d "$INSTALL_DIR" ]]; then
    remove_dir_if_exists "$INSTALL_DIR"
  else
    echo "Install dir not found (already removed?): $INSTALL_DIR"
  fi

  # Remove parent if empty
  if rmdir "$INSTALL_ROOT" 2>/dev/null; then
    echo "Removed empty parent dir: $INSTALL_ROOT"
  fi

  if (( PURGE_CALLFLOWS )); then
    if [[ -d "$CALLFLOWS_DIR" ]]; then
      if confirm "Permanently remove ${CALLFLOWS_DIR}?"; then
        rm -rf "$CALLFLOWS_DIR"
        echo "Removed callflows dir: $CALLFLOWS_DIR"
      else
        echo "Preserved callflows dir: $CALLFLOWS_DIR"
      fi
    fi
  else
    echo "Preserving callflows dir: $CALLFLOWS_DIR (use --purge-callflows to remove)."
  fi

  echo
  echo "Uninstall complete."
}

main "$@"
