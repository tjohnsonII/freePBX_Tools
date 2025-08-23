# 123NET FreePBX Tools - Installer
# - Installs to /usr/local/123net/freepbx-tools
# - Symlinks into /usr/local/bin
# - Ensures deps (jq, graphviz/dot, mysql client, python3) with EL7 python36u safety
# - Creates /home/123net/callflows and prints version policy banner

set -Eeuo pipefail

INSTALL_ROOT="/usr/local/123net"
INSTALL_DIR="$INSTALL_ROOT/freepbx-tools"
BIN_DIR="/usr/local/bin"
CALLFLOWS_DIR="/home/123net/callflows"

log()  { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

is_el()  { [[ -f /etc/redhat-release ]]; }
is_el7() { is_el && grep -qE 'release 7\.' /etc/redhat-release; }
is_el8() { is_el && grep -qE 'release 8\.' /etc/redhat-release; }
is_el9() { is_el && grep -qE 'release 9\.' /etc/redhat-release; }
is_deb(){ [[ -f /etc/debian_version ]] || have apt-get; }

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This installer needs root. Try: sudo $0" >&2
    exit 1
  fi
}

enable_epel_if_needed() {
  if is_el; then
    (yum -y install epel-release || dnf -y install epel-release) >/dev/null 2>&1 || true
  fi
}

# Ensure a usable python3 without tripping EL7's IUS python36u conflicts
ensure_python3() {
  if have python3; then return 0; fi

  if is_el7; then
    # If IUS python36u already present, do NOT pull in base python3 (conflicts).
    if rpm -q python36u python36u-libs >/dev/null 2>&1; then
      yum install -y python36u python36u-libs python36u-pip || true
      [[ -x /usr/bin/python3 ]] || ln -sf /usr/bin/python3.6 /usr/bin/python3
      return 0
    fi
    # Try base/EPEL python3 first
    yum install -y python3 || true
    if have python3; then return 0; fi
    # Last resort: bring in IUS and python36u
    rpm -q ius-release >/dev/null 2>&1 || yum install -y https://repo.ius.io/ius-release-el7.rpm || true
    yum install -y python36u python36u-libs python36u-pip || true
    [[ -x /usr/bin/python3 ]] || ln -sf /usr/bin/python3.6 /usr/bin/python3
    return 0
  fi

  if is_el8 || is_el9; then
    (dnf -y install python3 || yum -y install python3) || true
    return 0
  fi

  if is_deb; then
    apt-get update -y || true
    apt-get install -y python3 || true
    return 0
  fi
}

ensure_pkgset() {
  # jq, graphviz (dot), mysql client
  if is_el; then
    (yum -y install jq graphviz mariadb || dnf -y install jq graphviz mariadb) || true
  elif is_deb; then
    apt-get update -y || true
    apt-get install -y jq graphviz default-mysql-client || apt-get install -y jq graphviz mariadb-client || true
  fi

  # Convenience symlinks if CLI tools exist at common locations
  have asterisk  || ln -sf /usr/sbin/asterisk /usr/local/bin/asterisk  2>/dev/null || true
  have fwconsole || ln -sf /var/lib/asterisk/bin/fwconsole /usr/local/bin/fwconsole 2>/dev/null || true
}

check_after_installs() {
  local missing=0
  for c in python3 jq dot mysql; do
    case "$c" in
      dot)
        have dot || { warn "Missing dependency: dot (graphviz)"; ((missing++)); }
        ;;
      mysql)
        have mysql || { warn "Missing dependency: mysql client"; ((missing++)); }
        ;;
      *)
        have "$c" || { warn "Missing dependency: $c"; ((missing++)); }
        ;;
    esac
  done

  if (( missing > 0 )); then
    warn "Some optional dependencies are missing."
    warn "  Required at runtime on most hosts: mysql, python3"
    warn "  For graphs: graphviz 'dot'"
    warn "  For bash tooling: jq"
    warn "  For PBX reads: asterisk, fwconsole"
  fi
}

install_files() {
  local src_dir
  src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  mkdir -p "$INSTALL_DIR"
  cp -a "$src_dir/." "$INSTALL_DIR/"

  chmod +x "$INSTALL_DIR"/install.sh                2>/dev/null || true
  chmod +x "$INSTALL_DIR"/uninstall.sh              2>/dev/null || true
  chmod +x "$INSTALL_DIR"/version_check.sh          2>/dev/null || true
  chmod +x "$INSTALL_DIR"/freepbx_full_diagnostic.sh 2>/dev/null || true

  if [[ -f "$INSTALL_DIR/freepbx_dump.py" ]]; then
    sed -i '1s|^#!.*python.*$|#!/usr/bin/env python3|' "$INSTALL_DIR/freepbx_dump.py" || true
    chmod +x "$INSTALL_DIR/freepbx_dump.py" || true
  fi

  mkdir -p "$CALLFLOWS_DIR"
  if id asterisk >/dev/null 2>&1; then
    chown -R asterisk:asterisk "$CALLFLOWS_DIR" || true
  fi
}

install_symlinks() {
  mkdir -p "$BIN_DIR"
  ln -sf "$INSTALL_DIR/freepbx_full_diagnostic.sh" "$BIN_DIR/freepbx-diagnostic"      2>/dev/null || true
  ln -sf "$INSTALL_DIR/freepbx_dump.py"            "$BIN_DIR/freepbx-dump"            2>/dev/null || true
  ln -sf "$INSTALL_DIR/version_check.sh"           "$BIN_DIR/freepbx-version-check"   2>/dev/null || true
  ln -sf "$INSTALL_DIR/install.sh"                 "$BIN_DIR/freepbx-install"         2>/dev/null || true
  ln -sf "$INSTALL_DIR/uninstall.sh"               "$BIN_DIR/freepbx-uninstall"       2>/dev/null || true
}

print_policy_banner() {
  local policy_file="$INSTALL_DIR/version_policy.json"
  # Create a minimal policy if missing
  if [[ ! -f "$policy_file" ]]; then
    local FWC AST_MAJ FPBX_MAJ
    FWC="$(command -v fwconsole || echo /var/lib/asterisk/bin/fwconsole)"
    FPBX_MAJ="$("$FWC" --version 2>/dev/null | awk '{print $NF}' | cut -d. -f1)"
    AST_MAJ="$(asterisk -rx 'core show version' 2>/dev/null | sed -n 's/^Asterisk \([0-9.]+\).*/\1/p' | cut -d. -f1)"
    [[ -z "$AST_MAJ" ]] && AST_MAJ="$(asterisk -V 2>/dev/null | sed -n 's/^Asterisk \([0-9.]+\).*/\1/p' | cut -d. -f1)"
    cat > "$policy_file" <<EOF
{
  "FreePBX": { "allowed_majors": [${FPBX_MAJ:-16}] },
  "Asterisk": { "allowed_majors": [${AST_MAJ:-16}, 18] }
}
EOF
    warn "Created default version_policy.json at $policy_file"
  fi

  # Prefer bash checker; then python
  if [[ -x "$INSTALL_DIR/version_check.sh" ]]; then
    "$INSTALL_DIR/version_check.sh" || true
  fi
  if have python3 && [[ -f "$INSTALL_DIR/version_check.py" ]]; then
    python3 "$INSTALL_DIR/version_check.py" --quiet || true
  fi
}

main() {
  require_root
  enable_epel_if_needed
  ensure_python3
  ensure_pkgset
  check_after_installs
  install_files
  install_symlinks

  log "Installed 123NET FreePBX Tools to $INSTALL_DIR"
  log "Symlinks created in $BIN_DIR:"
  ls -l "$BIN_DIR"/freepbx-* 2>/dev/null || true
  log "Output directory: $CALLFLOWS_DIR"
  print_policy_banner
  log "Done."
}

main "$@"
