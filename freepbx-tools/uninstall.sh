#!/usr/bin/env bash
# 123NET FreePBX Tools — Uninstaller
# Removes symlinks, install dir, and (optionally) callflows and CLI convenience links.

set -Eeuo pipefail

INSTALL_ROOT="/usr/local/123net"
INSTALL_DIR="$INSTALL_ROOT/freepbx-tools"
BIN_DIR="/usr/local/bin"
CALLFLOWS_DIR="/home/123net/callflows"

PURGE_CALLFLOWS=0
PURGE_CLI_LINKS=0

usage() {
  cat <<USAGE
Usage: $0 [--purge-callflows] [--purge-cli-links]
  --purge-callflows   Also remove ${CALLFLOWS_DIR}
  --purge-cli-links   Remove convenience CLI links if we created them
USAGE
}

while (( "$#" )); do
  case "$1" in
    --purge-callflows) PURGE_CALLFLOWS=1 ;;
    --purge-cli-links) PURGE_CLI_LINKS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 2 ;;
  esac
  shift
done

log()   { printf '%s\n' "$*"; }
ok()    { printf '%s\n' "$*"; }
warn()  { printf 'WARN: %s\n' "$*" >&2; }

rm_link() {
  local p="$1"
  if [[ -L "$p" || -e "$p" ]]; then
    rm -f -- "$p" 2>/dev/null || true
    ok "Removed symlink: $p"
  fi
}

rm_link_if_points() {
  # remove only if link points at expected target
  local link="$1" target="$2"
  if [[ -L "$link" ]]; then
    local dst
    dst="$(readlink -f "$link" 2>/dev/null || true)"
    if [[ "$dst" == "$target" ]]; then
      rm -f -- "$link" && ok "Removed CLI symlink: $link -> $dst"
    fi
  fi
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This uninstaller needs root. Try: sudo $0" >&2
    exit 1
  fi
}

main() {
  require_root

  log "Removing command symlinks under ${BIN_DIR}…"
  rm_link "${BIN_DIR}/freepbx-diagnostic"
  rm_link "${BIN_DIR}/freepbx-dump"
  rm_link "${BIN_DIR}/freepbx-version-check"
  rm_link "${BIN_DIR}/freepbx-install"
  rm_link "${BIN_DIR}/freepbx-uninstall"

  if (( PURGE_CLI_LINKS )); then
    # Remove convenience links we may have created during install
    rm_link_if_points "${BIN_DIR}/asterisk"  "/usr/sbin/asterisk"
    rm_link_if_points "${BIN_DIR}/fwconsole" "/var/lib/asterisk/bin/fwconsole"
  else
    log "Keeping any existing CLI symlinks (use --purge-cli-links to remove)."
  fi

  if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf -- "$INSTALL_DIR"
    ok "Removed install dir: $INSTALL_DIR"
  fi

  # remove parent if now empty
  if [[ -d "$INSTALL_ROOT" ]] && rmdir "$INSTALL_ROOT" 2>/dev/null; then
    ok "Removed empty parent dir: $INSTALL_ROOT"
  fi

  if (( PURGE_CALLFLOWS )); then
    if [[ -d "$CALLFLOWS_DIR" ]]; then
      rm -rf -- "$CALLFLOWS_DIR"
      ok "Removed callflows dir: $CALLFLOWS_DIR"
    fi
  else
    log "Preserving callflows dir: $CALLFLOWS_DIR (use --purge-callflows to remove)."
  fi

  echo
  ok "Uninstall complete."

  if (( ! PURGE_CALLFLOWS )); then
    echo
    echo "If you kept ${CALLFLOWS_DIR}, you can remove it later with:"
    echo "  sudo rm -rf \"${CALLFLOWS_DIR}\""
  fi

  echo
  echo "Reinstall anytime by running your repo copy of install.sh, e.g.:"
  echo "  sudo ./install.sh"
}

main "$@"
exit 0
# - Removes symlinks from /usr/local/bin
# - Leaves /home/123net/callflows intact by default (use --purge-callflows to remove)
# - No dependencies are uninstalled (mysql/python/jq/dot/etc. stay)
### ---------- arg parse ----------

#!/usr/bin/env bash
# 123NET FreePBX Tools - Uninstaller
# Removes symlinks and install dir. Keeps callflows/ unless --purge-callflows.
# Optionally removes convenience CLI symlinks with --purge-cli-links.

set -u

INSTALL_ROOT="/usr/local/123net"
INSTALL_DIR="$INSTALL_ROOT/freepbx-tools"
BIN_DIR="/usr/local/bin"
CALLFLOWS_DIR="/home/123net/callflows"

PURGE_CALLFLOWS=0
PURGE_CLI_LINKS=0
ASSUME_YES=0

log()  { printf "%s\n" "$*"; }
err()  { printf "ERROR: %s\n" "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

Options:
  --purge-callflows     Remove ${CALLFLOWS_DIR} as well (irreversible).
  --purge-cli-links     Also remove convenience symlinks for asterisk/fwconsole
                        IF they are symlinks pointing to standard locations.
  -y, --yes             Non-interactive (assume "yes" to prompts).
  -h, --help            Show this help.

This uninstaller removes:
  - Symlinks in ${BIN_DIR}: freepbx-diagnostic, freepbx-dump,
    freepbx-version-check, freepbx-install, freepbx-uninstall (only if they
    point into ${INSTALL_DIR})
  - The install directory ${INSTALL_DIR}
  - The parent ${INSTALL_ROOT} if it becomes empty

It leaves:
  - ${CALLFLOWS_DIR} (unless --purge-callflows)
EOF
}

confirm() {
  local prompt="$1"
  if (( ASSUME_YES )); then return 0; fi
  read -r -p "$prompt [y/N]: " ans
  [[ "$ans" =~ ^[Yy]([Ee][Ss])?$ ]]
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    err "This uninstaller needs root. Try: sudo $0"
    exit 1
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --purge-callflows) PURGE_CALLFLOWS=1 ;;
      --purge-cli-links) PURGE_CLI_LINKS=1 ;;
      -y|--yes)          ASSUME_YES=1 ;;
      -h|--help)         usage; exit 0 ;;
      *) err "Unknown option: $1"; usage; exit 2 ;;
    esac
    shift
  done
}

# Remove a symlink if it points into a given directory (safety guard)
remove_link_if_points_into() {
  local link="$1" base_dir="$2"
  if [[ -L "$link" ]]; then
    local tgt
    tgt="$(readlink -f -- "$link" 2>/dev/null || true)"
    if [[ -n "$tgt" && "$tgt" == "$base_dir"* ]]; then
      rm -f -- "$link" && log "Removed symlink: $link"
    else
      log "Skipped (not ours): $link -> ${tgt:-unknown}"
    fi
  elif [[ -e "$link" ]]; then
    log "Skipped (not a symlink): $link"
  else
    log "Already gone: $link"
  fi
}

# Remove a symlink only if it matches an exact expected target
remove_exact_link() {
  local link="$1" expected_target="$2"
  if [[ -L "$link" ]]; then
    local tgt
    tgt="$(readlink -f -- "$link" 2>/dev/null || true)"
    if [[ "$tgt" == "$expected_target" ]]; then
      rm -f -- "$link" && log "Removed CLI symlink: $link"
    else
      log "Skipped CLI link (target differs): $link -> ${tgt:-unknown}"
    fi
  else
    log "CLI link not present (or not a symlink): $link"
  fi
}

remove_symlinks() {
  log "Removing command symlinks under ${BIN_DIR}…"
  remove_link_if_points_into "$BIN_DIR/freepbx-diagnostic"     "$INSTALL_DIR"
  remove_link_if_points_into "$BIN_DIR/freepbx-dump"           "$INSTALL_DIR"
  remove_link_if_points_into "$BIN_DIR/freepbx-version-check"  "$INSTALL_DIR"
  remove_link_if_points_into "$BIN_DIR/freepbx-install"        "$INSTALL_DIR"
  remove_link_if_points_into "$BIN_DIR/freepbx-uninstall"      "$INSTALL_DIR"
}

remove_cli_convenience_links() {
  if (( PURGE_CLI_LINKS )); then
    log "Purging convenience CLI symlinks (if created by installer)…"
    # Only remove if they are symlinks to these exact targets
    remove_exact_link "$BIN_DIR/asterisk"  "/usr/sbin/asterisk"
    remove_exact_link "$BIN_DIR/fwconsole" "/var/lib/asterisk/bin/fwconsole"
  else
    log "Keeping any existing CLI symlinks (use --purge-cli-links to remove)."
  fi
}

remove_install_tree() {
  if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf -- "$INSTALL_DIR"
    log "Removed install dir: $INSTALL_DIR"
  else
    log "Install dir already absent: $INSTALL_DIR"
  fi

  # Remove parent if now empty
  if [[ -d "$INSTALL_ROOT" ]] && [[ -z "$(ls -A "$INSTALL_ROOT")" ]]; then
    rmdir -- "$INSTALL_ROOT" && log "Removed empty parent dir: $INSTALL_ROOT"
  fi
}

maybe_purge_callflows() {
  if (( PURGE_CALLFLOWS )); then
    if [[ -d "$CALLFLOWS_DIR" ]]; then
      if confirm "Really remove ${CALLFLOWS_DIR}? This deletes generated outputs."; then
        rm -rf -- "$CALLFLOWS_DIR"
        log "Removed: $CALLFLOWS_DIR"
      else
        log "Skipped removing: $CALLFLOWS_DIR"
      fi
    else
      log "Callflows dir not present: $CALLFLOWS_DIR"
    fi
  else
    log "Preserving callflows dir: $CALLFLOWS_DIR (use --purge-callflows to remove)."
  fi
}

summary() {
  cat <<EOF

Uninstall complete.

If you kept ${CALLFLOWS_DIR}, you can remove it later with:
  sudo rm -rf "${CALLFLOWS_DIR}"

Reinstall anytime with:
  sudo /usr/local/123net/freepbx-tools/install.sh
EOF
}

main() {
  require_root
  parse_args "$@"

  remove_symlinks
  remove_cli_convenience_links
  remove_install_tree
  maybe_purge_callflows
  summary
}

main "$@"
FILES=(
  freepbx_dump.py
  freepbx_callflow_graphV2.py
  freepbx_render_from_dump.sh
  asterisk-full-diagnostic.sh
  version_policy.json
  version_check.sh
  version_check.py
)

echo "Uninstall plan:"
echo "  PREFIX     : $PREFIX"
echo "  BINDIR     : $BINDIR"
echo "  CALLFLOWS  : $CALLFLOWS_DIR"
echo "  Purge callflows: $([[ $PURGE_CALLFLOWS -eq 1 ]] && echo YES || echo NO)"
echo "  Remove symlinks:"
for s in "${SYMLINKS[@]}"; do echo "    - $BINDIR/$s"; done
echo "  Remove files under PREFIX:"
for f in "${FILES[@]}"; do echo "    - $PREFIX/$f"; done
echo

if [[ $ASSUME_YES -ne 1 ]]; then
  read -r -p "Proceed with uninstall? [y/N] " ans
  [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]] || { ylw "Aborted."; exit 0; }
fi

### ---------- remove symlinks ----------
for s in "${SYMLINKS[@]}"; do
  p="$BINDIR/$s"
  if [[ -L "$p" ]]; then
    rm -f "$p" && grn "Removed symlink: $p" || ylw "Could not remove: $p"
  elif [[ -e "$p" ]]; then
    ylw "Skipping non-symlink at $p (not created by installer)."
  fi
done

### ---------- remove installed files ----------
if [[ -d "$PREFIX" ]]; then
  for f in "${FILES[@]}"; do
    [[ -e "$PREFIX/$f" ]] && rm -f "$PREFIX/$f" && grn "Removed: $PREFIX/$f"
  done
  # If empty, remove the directory (and possibly its parent if now empty)
  if [[ -z "$(ls -A "$PREFIX" 2>/dev/null || true)" ]]; then
    rmdir "$PREFIX" && grn "Removed empty dir: $PREFIX" || true
    PARENT_DIR="$(dirname "$PREFIX")"
    if [[ -d "$PARENT_DIR" && -z "$(ls -A "$PARENT_DIR" 2>/dev/null || true)" ]]; then
      rmdir "$PARENT_DIR" && grn "Removed empty dir: $PARENT_DIR" || true
    fi
  else
    ylw "Directory not empty: $PREFIX (left in place)."
  fi
else
  ylw "Prefix not found: $PREFIX (nothing to remove)."
fi

### ---------- optional: purge callflows ----------
if [[ $PURGE_CALLFLOWS -eq 1 ]]; then
  if [[ -d "$CALLFLOWS_DIR" ]]; then
    rm -rf "$CALLFLOWS_DIR"
    grn "Purged callflows directory: $CALLFLOWS_DIR"
  else
    ylw "Callflows directory not found: $CALLFLOWS_DIR"
  fi
else
  blu "Left callflows directory intact: $CALLFLOWS_DIR"
fi

grn "Uninstall complete."
