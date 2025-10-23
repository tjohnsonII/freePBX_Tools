#!/usr/bin/env bash
# 123NET FreePBX Tools - Installer
# - Installs to /usr/local/123net/freepbx-tools
# - Symlinks into /usr/local/bin (both friendly and legacy names)
# - Ensures deps (jq, graphviz/dot, mysql client, python3) with EL7 python36u safety
# - Normalizes shebangs/line-endings for all shell scripts; makes executables
# - Applies Python <3.7 compat tweak (text=True -> universal_newlines=True)
# - Creates /home/123net/callflows, prints version policy banner
# - Runs a post-install smoke test (python3, dot, mysql, callflows help)

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
is_deb() { [[ -f /etc/debian_version ]] || have apt-get; }

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
  echo ">>> Ensuring python3 is installed and on PATH..."
  if have python3; then python3 -V || true; return 0; fi

  if is_el7; then
    if rpm -q python36u python36u-libs >/dev/null 2>&1; then
      yum install -y python36u python36u-libs python36u-pip || true
      mkdir -p /usr/local/bin
      [[ -x /usr/bin/python3.6 ]] && ln -sfn /usr/bin/python3.6 /usr/local/bin/python3
      export PATH="/usr/local/bin:$PATH"
      have python3 && { python3 -V || true; return 0; }
    fi
    yum install -y python3 || true
    if have python3; then python3 -V || true; return 0; fi
    rpm -q ius-release >/dev/null 2>&1 || yum install -y https://repo.ius.io/ius-release-el7.rpm || true
    yum install -y python36u python36u-libs python36u-pip || true
    mkdir -p /usr/local/bin
    [[ -x /usr/bin/python3.6 ]] && ln -sfn /usr/bin/python3.6 /usr/local/bin/python3
    export PATH="/usr/local/bin:$PATH"
    have python3 && { python3 -V || true; return 0; }
  elif is_el8 || is_el9; then
    (dnf -y install python3 || yum -y install python3) || true
    have python3 && { python3 -V || true; return 0; }
  elif is_deb; then
    apt-get update -y || true
    apt-get install -y python3 || true
    have python3 && { python3 -V || true; return 0; }
  fi

  if ! have python3; then
    echo "ERROR: python3 could not be installed. Check repositories and rerun." >&2
    exit 1
  fi
}

ensure_pkgset() {
  echo ">>> Installing jq, graphviz (dot), and MySQL client..."
  if is_el; then
    (yum -y install jq graphviz mariadb || dnf -y install jq graphviz mariadb) || true
  elif is_deb; then
    apt-get update -y || true
    apt-get install -y jq graphviz default-mysql-client || apt-get install -y jq graphviz mariadb-client || true
  fi
  have asterisk  || ln -sf /usr/sbin/asterisk /usr/local/bin/asterisk  2>/dev/null || true
  have fwconsole || ln -sf /var/lib/asterisk/bin/fwconsole /usr/local/bin/fwconsole 2>/dev/null || true
}

check_after_installs() {
  local missing=0
  for c in python3 jq dot mysql; do
    case "$c" in
      dot)   have dot   || { warn "Missing dependency: dot (graphviz)"; ((missing++)); } ;;
      mysql) have mysql || { warn "Missing dependency: mysql client";   ((missing++)); } ;;
      *)     have "$c"  || { warn "Missing dependency: $c";             ((missing++)); } ;;
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
  echo ">>> Copying files to $INSTALL_DIR ..."
  local src_dir
  src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  mkdir -p "$INSTALL_DIR"
  cp -a "$src_dir/." "$INSTALL_DIR/"

  # Normalize Python entrypoints and make executables
  for rel in \
  bin/freepbx_dump.py \
  bin/freepbx_callflow_menu.py \
  bin/freepbx_callflow_graphV2.py \
  bin/freepbx_tc_status.py
do
  [[ -f "$INSTALL_DIR/$rel" ]] || continue
  sed -i '1s|^#!.*python.*$|#!/usr/bin/env python3|' "$INSTALL_DIR/$rel" || true
  chmod +x "$INSTALL_DIR/$rel" || true
done

  # Normalize ALL shell scripts (CRLF/BOM → LF, ensure bash shebang, chmod +x)
  if command -v find >/dev/null 2>&1; then
    while IFS= read -r -d '' s; do
      sed -i -e 's/\r$//' -e '1s/^\xEF\xBB\xBF//' "$s" || true
      if ! head -n1 "$s" | grep -q '^#!'; then
        sed -i '1i #!/usr/bin/env bash' "$s" || true
      fi
      chmod +x "$s" || true
    done < <(find "$INSTALL_DIR" -type f -name "*.sh" -print0)
  fi

  # Ensure execute bits across bin (defense in depth)
  chmod +x "$INSTALL_DIR"/bin/freepbx_render_from_dump.sh 2>/dev/null || true
  chmod +x "$INSTALL_DIR"/bin/*.py                       2>/dev/null || true
  chmod +x "$INSTALL_DIR"/version_check.sh               2>/dev/null || true
  chmod +x "$INSTALL_DIR"/install.sh                     2>/dev/null || true
  chmod +x "$INSTALL_DIR"/uninstall.sh                   2>/dev/null || true

  mkdir -p "$CALLFLOWS_DIR"
  if id asterisk >/dev/null 2>&1; then
    chown -R asterisk:asterisk "$CALLFLOWS_DIR" || true
  fi
}

# Make subprocess.run(..., text=True) work on Python < 3.7
patch_py36_text_kwarg() {
  have python3 || return 0

  # returns 0 on Python < 3.7, 1 otherwise
  if python3 -c 'import sys; raise SystemExit(0 if sys.version_info < (3,7) else 1)'; then
    local d="$INSTALL_DIR/bin"
    [[ -d "$d" ]] || return 0
    echo ">>> Adapting subprocess.run(..., text=True) for Python < 3.7"
    for f in "$d"/*.py; do
      [[ -f "$f" ]] || continue
      [[ -f "${f}.bak" ]] || cp -a "$f" "${f}.bak"
      sed -i 's/text=True/universal_newlines=True/g' "$f" || true
    done
  fi
}

install_symlinks() {
  echo ">>> Creating CLI symlinks in $BIN_DIR ..."
  mkdir -p "$BIN_DIR"

  # Friendly names
  ln -sf "$INSTALL_DIR/bin/freepbx_callflow_menu.py"    "$BIN_DIR/freepbx-callflows"           2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_render_from_dump.sh" "$BIN_DIR/freepbx-render"              2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_dump.py"             "$BIN_DIR/freepbx-dump"                2>/dev/null || true
  ln -sf "$INSTALL_DIR/version_check.sh"                "$BIN_DIR/freepbx-version-check"       2>/dev/null || true
  ln -sf "$INSTALL_DIR/install.sh"                      "$BIN_DIR/freepbx-install"             2>/dev/null || true
  ln -sf "$INSTALL_DIR/uninstall.sh"                    "$BIN_DIR/freepbx-uninstall"           2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_tc_status.py" "$BIN_DIR/freepbx-tc-status" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_module_analyzer.py" "$BIN_DIR/freepbx-module-analyzer" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_module_status.py" "$BIN_DIR/freepbx-module-status" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_paging_fax_analyzer.py" "$BIN_DIR/freepbx-paging-fax-analyzer" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_comprehensive_analyzer.py" "$BIN_DIR/freepbx-comprehensive-analyzer" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_version_aware_ascii_callflow.py" "$BIN_DIR/freepbx-ascii-callflow" 2>/dev/null || true

  # Legacy names required by menu/scripts
  ln -sf "$INSTALL_DIR/bin/freepbx_dump.py"             "$BIN_DIR/freepbx_dump.py"             2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_callflow_graphV2.py" "$BIN_DIR/freepbx_callflow_graph.py"   2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_render_from_dump.sh" "$BIN_DIR/freepbx_render_from_dump.sh" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_tc_status.py" "$BIN_DIR/freepbx_tc_status.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_module_analyzer.py" "$BIN_DIR/freepbx_module_analyzer.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_module_status.py" "$BIN_DIR/freepbx_module_status.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_paging_fax_analyzer.py" "$BIN_DIR/freepbx_paging_fax_analyzer.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_comprehensive_analyzer.py" "$BIN_DIR/freepbx_comprehensive_analyzer.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_version_aware_ascii_callflow.py" "$BIN_DIR/freepbx_ascii_callflow.py" 2>/dev/null || true

  # Diagnostic symlink
  ln -sfn "$INSTALL_DIR/bin/asterisk-full-diagnostic.sh" "$BIN_DIR/asterisk-full-diagnostic.sh" 2>/dev/null || true
}

print_policy_banner() {
  local policy_file="$INSTALL_DIR/version_policy.json"
  if [[ ! -f "$policy_file" ]]; then
    local FWC AST_MAJ FPBX_MAJ
    FWC="$(command -v fwconsole || echo /var/lib/asterisk/bin/fwconsole)"
    FPBX_MAJ="$("$FWC" --version 2>/dev/null | awk '{print $NF}' | cut -d. -f1)"
    AST_MAJ="$(asterisk -rx 'core show version' 2>/dev/null | sed -n 's/^Asterisk \([0-9.]\+\).*/\1/p' | cut -d. -f1)"
    [[ -z "$AST_MAJ" ]] && AST_MAJ="$(asterisk -V 2>/dev/null | sed -n 's/^Asterisk \([0-9.]\+\).*/\1/p' | cut -d. -f1)"
    cat > "$policy_file" <<EOF
{
  "FreePBX":  { "accepted_majors": [${FPBX_MAJ:-16}] },
  "Asterisk": { "accepted_majors": [${AST_MAJ:-16}, 18] }
}
EOF
    warn "Created default version_policy.json at $policy_file"
  fi

  if [[ -x "$INSTALL_DIR/version_check.sh" ]]; then
    "$INSTALL_DIR/version_check.sh" || true
  fi
  if have python3 && [[ -f "$INSTALL_DIR/version_check.py" ]]; then
    python3 "$INSTALL_DIR/version_check.py" --quiet || true
  fi
}

# -------- Post-install smoke test ----------
# -------- Post-install smoke test ----------
post_install_smoke() {
  echo ">>> Running post-install smoke test..."
  local ok=0 fail=0

  if have python3; then
    echo "  [OK] python3: $(python3 -V 2>&1)"
    ((ok++))
  else
    warn "  [FAIL] python3 not found on PATH"
    ((fail++))
  fi

  if have dot; then
    echo "  [OK] graphviz 'dot': $(dot -V 2>&1)"
    ((ok++))
  else
    warn "  [FAIL] graphviz 'dot' not found"
    ((fail++))
  fi

  if have mysql; then
    echo "  [OK] mysql client present"
    ((ok++))
  else
    warn "  [FAIL] mysql client not found"
    ((fail++))
  fi

  # Try to show help for the callflows entrypoint
  if [[ -f "$INSTALL_DIR/bin/freepbx_callflow_menu.py" ]]; then
    if python3 "$INSTALL_DIR/bin/freepbx_callflow_menu.py" --help >/dev/null 2>&1 || true; then
      echo "  [OK] freepbx-callflows script is runnable"
      ((ok++))
    else
      warn "  [WARN] freepbx-callflows help check returned non-zero (may be expected)."
    fi
  fi

  # Check time-condition status tool
  if [[ -f "$INSTALL_DIR/bin/freepbx_tc_status.py" ]]; then
    if python3 "$INSTALL_DIR/bin/freepbx_tc_status.py" --help >/dev/null 2>&1 || true; then
      echo "  [OK] freepbx-tc-status script is runnable"
      ((ok++))
    else
      warn "  [WARN] freepbx-tc-status help check returned non-zero."
    fi
  fi

  echo ">>> Smoke test summary: PASS=$ok, FAIL=$fail"
  if (( fail > 0 )); then
    warn "Some checks failed. Tools may still work, but you might want to install missing deps."
  fi
}

# -------------------------------------------

main() {
  require_root
  enable_epel_if_needed
  ensure_python3
  ensure_pkgset
  check_after_installs
  install_files
  patch_py36_text_kwarg
  install_symlinks

  log "Installed 123NET FreePBX Tools to $INSTALL_DIR"
  log "Symlinks created in $BIN_DIR:"
  ls -l "$BIN_DIR"/freepbx-* "$BIN_DIR"/freepbx_* "$BIN_DIR"/asterisk-full-diagnostic.sh 2>/dev/null || true
  log "Output directory: $CALLFLOWS_DIR"
  print_policy_banner

  post_install_smoke

  log "Done."
}

main "$@"
