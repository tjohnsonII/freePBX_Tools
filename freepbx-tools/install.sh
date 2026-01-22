
#!/usr/bin/env bash
# ============================================================================
# VARIABLE LEGEND (Map)
# ---------------------
# INSTALL_ROOT     - Parent directory for all 123NET tools (default: /usr/local/123net)
# INSTALL_DIR      - Main install directory for FreePBX tools (default: /usr/local/123net/freepbx-tools)
# BIN_DIR          - Directory for system-wide symlinks (default: /usr/local/bin)
# CALLFLOWS_DIR    - Output directory for call flow SVG/JSON (default: /home/123net/callflows)
# src_dir          - Source directory of the install script (used for relative paths)
# pip_cmd          - Python package installer command (pip3, pip, or python3 -m pip)
# policy_file      - Path to version_policy.json
# FWC              - Path to fwconsole binary
# FPBX_MAJ         - Detected FreePBX major version
# AST_MAJ          - Detected Asterisk major version
# ok, fail         - Counters for smoke test results
# c                - Loop variable for dependency checks
# rel              - Relative path for script normalization
# d                - Directory path for patching Python scripts
# f                - File path for patching Python scripts
# n                - Loop variable for tool names in symlink creation
# $@, $#           - All/number of command-line arguments
# ============================================================================
# 123NET FreePBX Tools - Installer
# --------------------------------------------------------------------------
# This script installs the FreePBX tools suite, sets up all dependencies,
# normalizes scripts, and creates symlinks for easy CLI access.
#
# MAIN STEPS:
# 1. Ensures root privileges for all install actions.
# 2. Detects OS type (EL7/8/9, Debian) for package management.
# 3. Installs required system packages: jq, graphviz (dot), mariadb/mysql client, python3.
# 4. Handles EL7 python36u/IUS repo edge cases for python3.
# 5. Installs Python packages for optional GUI tools (beautifulsoup4, requests).
# 6. Copies all scripts to the install directory, normalizes line endings and shebangs.
# 7. Makes all scripts executable.
# 8. Creates symlinks in /usr/local/bin for both friendly and legacy tool names.
# 9. Patches subprocess.run(..., text=True) to universal_newlines=True for Python <3.7.
# 10. Creates output directory for callflows and sets permissions.
# 11. Prints version policy banner and runs a post-install smoke test.
#
# SAFETY:
# - set -Eeuo pipefail: Exit on error, unset variable, or failed pipeline.
# - All destructive actions are guarded by checks.
# - Idempotent: safe to re-run, will not duplicate symlinks or fail if already installed.
# ============================================================================


# Exit on error, error on unset variables, error on failed pipeline
set -Eeuo pipefail


# Define main install and output directories
INSTALL_ROOT="/usr/local/123net"         # Parent directory for all 123NET tools
INSTALL_DIR="$INSTALL_ROOT/freepbx-tools" # Main install directory for FreePBX tools
BIN_DIR="/usr/local/bin"                 # Directory for system-wide symlinks
CALLFLOWS_DIR="/home/123net/callflows"   # Output directory for call flow SVG/JSON


# Utility logging functions
log()  { printf '%s\n' "$*"; }   # Print a log message
warn() { printf 'WARN: %s\n' "$*" >&2; } # Print a warning to stderr
have() { command -v "$1" >/dev/null 2>&1; } # Check if a command exists


# OS detection helpers
is_el()  { [[ -f /etc/redhat-release ]]; } # True if RHEL/CentOS/Alma/Rocky
is_el7() { is_el && grep -qE 'release 7\.' /etc/redhat-release; } # True if EL7
is_el8() { is_el && grep -qE 'release 8\.' /etc/redhat-release; } # True if EL8
is_el9() { is_el && grep -qE 'release 9\.' /etc/redhat-release; } # True if EL9
is_deb() { [[ -f /etc/debian_version ]] || have apt-get; } # True if Debian/Ubuntu


# Ensure script is run as root
require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This installer needs root. Try: sudo $0" >&2
    exit 1
  fi
}


# Enable EPEL repo if on RHEL/CentOS/Alma/Rocky
enable_epel_if_needed() {
  if is_el; then
    (yum -y install epel-release || dnf -y install epel-release) >/dev/null 2>&1 || true
  fi
}

# Ensure a usable python3 without tripping EL7's IUS python36u conflicts

# Ensure python3 is installed and available on PATH
# Handles EL7 python36u/IUS repo edge cases
ensure_python3() {
  echo ">>> Ensuring python3 is installed and on PATH..."
  if have python3; then python3 -V || true; return 0; fi

  if is_el7; then
    # Try to use python36u if available
    if rpm -q python36u python36u-libs >/dev/null 2>&1; then
      yum install -y python36u python36u-libs python36u-pip || true
      mkdir -p /usr/local/bin
      [[ -x /usr/bin/python3.6 ]] && ln -sfn /usr/bin/python3.6 /usr/local/bin/python3
      export PATH="/usr/local/bin:$PATH"
      have python3 && { python3 -V || true; return 0; }
    fi
    # Try system python3
    yum install -y python3 || true
    if have python3; then python3 -V || true; return 0; fi
    # Try IUS repo as last resort
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


# Ensure all required system packages are installed
# Installs jq, graphviz (dot), mariadb/mysql client, and symlinks asterisk/fwconsole if missing
ensure_pkgset() {
  echo ">>> Installing jq, graphviz (dot), and MySQL client..."
  if is_el; then
    (yum -y install jq graphviz mariadb || dnf -y install jq graphviz mariadb) || true
  elif is_deb; then
    apt-get update -y || true
    apt-get install -y jq graphviz default-mysql-client || apt-get install -y jq graphviz mariadb-client || true
  fi
  # Symlink asterisk/fwconsole if not present on PATH
  have asterisk  || ln -sf /usr/sbin/asterisk /usr/local/bin/asterisk  2>/dev/null || true
  have fwconsole || ln -sf /var/lib/asterisk/bin/fwconsole /usr/local/bin/fwconsole 2>/dev/null || true
}


# Ensure required Python packages for GUI comparison tool are installed
# Tries pip3, pip, or python3 -m pip, and installs from requirements.txt if present
ensure_python_packages() {
  echo ">>> Installing Python packages for GUI comparison tool..."
  
  # Try to find a working pip command
  local pip_cmd=""
  if have pip3; then
    pip_cmd="pip3"
  elif have pip; then
    pip_cmd="pip"
  elif python3 -m pip --version >/dev/null 2>&1; then
    pip_cmd="python3 -m pip"
  else
    warn "No pip found - GUI comparison tool may not work without manual package installation"
    warn "To use GUI comparison, install: pip3 install beautifulsoup4 requests"
    return 0
  fi
  
  # Try to install from requirements.txt if available, otherwise install directly
  local src_dir
  src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  
  if [[ -f "$src_dir/requirements.txt" ]]; then
    echo "  Installing from requirements.txt..."
    $pip_cmd install -r "$src_dir/requirements.txt" 2>/dev/null || {
      warn "Failed to install from requirements.txt"
      echo "  Falling back to direct package installation..."
      $pip_cmd install beautifulsoup4 requests 2>/dev/null || {
        warn "Failed to install Python packages (beautifulsoup4, requests)"
        warn "GUI comparison tool requires: pip3 install beautifulsoup4 requests"
      }
    }
  else
    # Install packages directly
    echo "  Installing beautifulsoup4 and requests..."
    $pip_cmd install beautifulsoup4 requests 2>/dev/null || {
      warn "Failed to install Python packages (beautifulsoup4, requests)"
      warn "GUI comparison tool requires: pip3 install beautifulsoup4 requests"
    }
  fi
}


# Check for all required dependencies after install
# Warns if any are missing, but does not fail install
check_after_installs() {
  local missing=0
  for c in python3 jq dot mysql; do
    case "$c" in
      dot)   have dot   || { warn "Missing dependency: dot (graphviz)"; ((missing++)) || true; } ;;
      mysql) have mysql || { warn "Missing dependency: mysql client";   ((missing++)) || true; } ;;
      *)     have "$c"  || { warn "Missing dependency: $c";             ((missing++)) || true; } ;;
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

# Copy all files to install directory, normalize scripts, and set permissions
install_files() {
  echo ">>> Copying files to $INSTALL_DIR ..."
  local src_dir
  src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # Get script directory

  mkdir -p "$INSTALL_DIR"  # Ensure install directory exists
  cp -a "$src_dir/." "$INSTALL_DIR/"  # Copy all files


  # Normalize Python entrypoints and make executables
  for rel in bin/freepbx_dump.py bin/freepbx_callflow_menu.py bin/freepbx_callflow_graph.py bin/freepbx_tc_status.py; do
    [[ -f "$INSTALL_DIR/$rel" ]] || continue  # Skip if file missing
    sed -i '1s|^#!.*python.*$|#!/usr/bin/env python3|' "$INSTALL_DIR/$rel" || true  # Fix shebang
    chmod +x "$INSTALL_DIR/$rel" || true  # Make executable
  done

  # Normalize ALL shell scripts (CRLF/BOM → LF, ensure bash shebang, chmod +x)
  if command -v find >/dev/null 2>&1; then
    while IFS= read -r -d '' s; do
      sed -i -e 's/\r$//' -e '1s/^\xEF\xBB\xBF//' "$s" || true  # Remove CRLF/BOM
      if ! head -n1 "$s" | grep -q '^#!'; then
        sed -i '1i #!/usr/bin/env bash' "$s" || true  # Add shebang if missing
      fi
      chmod +x "$s" || true  # Make executable
    done < <(find "$INSTALL_DIR" -type f -name "*.sh" -print0)
  fi

  # Ensure execute bits across bin (defense in depth)
  chmod +x "$INSTALL_DIR"/bin/freepbx_render_from_dump.sh 2>/dev/null || true
  chmod +x "$INSTALL_DIR"/bin/*.py                       2>/dev/null || true
  chmod +x "$INSTALL_DIR"/version_check.sh               2>/dev/null || true
  chmod +x "$INSTALL_DIR"/install.sh                     2>/dev/null || true
  chmod +x "$INSTALL_DIR"/uninstall.sh                   2>/dev/null || true

  mkdir -p "$CALLFLOWS_DIR"  # Ensure output directory exists
  if id asterisk >/dev/null 2>&1; then
    chown -R asterisk:asterisk "$CALLFLOWS_DIR" || true  # Set ownership if asterisk user exists
  fi
}
# Make subprocess.run(..., text=True) work on Python < 3.7

# Patch subprocess.run(..., text=True) to universal_newlines=True for Python <3.7
patch_py36_text_kwarg() {
  have python3 || return 0

  # Only patch if Python <3.7
  if python3 -c 'import sys; raise SystemExit(0 if sys.version_info < (3,7) else 1)'; then
    local d="$INSTALL_DIR/bin"
    [[ -d "$d" ]] || return 0
    echo ">>> Adapting subprocess.run(..., text=True) for Python < 3.7"
    for f in "$d"/*.py; do
      [[ -f "$f" ]] || continue
      [[ -f "${f}.bak" ]] || cp -a "$f" "${f}.bak"  # Backup original
      sed -i 's/text=True/universal_newlines=True/g' "$f" || true  # Patch keyword
    done
  fi
}


# Create all CLI symlinks for tools in $BIN_DIR and legacy locations
install_symlinks() {
  echo ">>> Creating CLI symlinks in $BIN_DIR ..."
  mkdir -p "$BIN_DIR"

  # Friendly names for user CLI
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
  ln -sf "$INSTALL_DIR/bin/callflow_validator.py" "$BIN_DIR/callflow-validator" 2>/dev/null || true

  # Legacy names required by menu/scripts
  ln -sf "$INSTALL_DIR/bin/freepbx_dump.py"             "$BIN_DIR/freepbx_dump.py"             2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_callflow_graph.py" "$BIN_DIR/freepbx_callflow_graph.py"   2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_render_from_dump.sh" "$BIN_DIR/freepbx_render_from_dump.sh" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_tc_status.py" "$BIN_DIR/freepbx_tc_status.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_module_analyzer.py" "$BIN_DIR/freepbx_module_analyzer.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_module_status.py" "$BIN_DIR/freepbx_module_status.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_paging_fax_analyzer.py" "$BIN_DIR/freepbx_paging_fax_analyzer.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_comprehensive_analyzer.py" "$BIN_DIR/freepbx_comprehensive_analyzer.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/freepbx_version_aware_ascii_callflow.py" "$BIN_DIR/freepbx_ascii_callflow.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/callflow_validator.py" "$BIN_DIR/callflow_validator.py" 2>/dev/null || true

  # Diagnostic symlink for full system diagnostic script
  ln -sfn "$INSTALL_DIR/bin/asterisk-full-diagnostic.sh" "$BIN_DIR/asterisk-full-diagnostic.sh" 2>/dev/null || true

  # Call simulation tools (for load testing, etc)
  mkdir -p "$INSTALL_ROOT/call-simulation"
  ln -sf "$INSTALL_DIR/bin/call_simulator.py" "$INSTALL_ROOT/call-simulation/call_simulator.py" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/simulate_calls.sh" "$INSTALL_ROOT/call-simulation/simulate_calls.sh" 2>/dev/null || true
  ln -sf "$INSTALL_DIR/bin/callflow_validator.py" "$INSTALL_ROOT/call-simulation/callflow_validator.py" 2>/dev/null || true
}


# Verify key symlinks exist and are discoverable on PATH.
verify_symlinks() {
  echo ">>> Verifying CLI symlinks..."

  local expected
  expected="$BIN_DIR/freepbx-callflows"

  if [[ ! -L "$expected" ]]; then
    warn "Expected symlink not found: $expected"
    warn "Symlinks are created in: $BIN_DIR"
    return 0
  fi

  if have freepbx-callflows; then
    echo "  [OK] freepbx-callflows is on PATH"
    return 0
  fi

  # Symlink exists, but not on PATH
  warn "Symlink exists but command is not on PATH: freepbx-callflows"
  warn "Try: export PATH=$BIN_DIR:\$PATH"
  warn "Or run directly: $expected"
}


# Ensure /usr/local/bin is on PATH for interactive shells.
ensure_path_profile() {
  local pf="/etc/profile.d/123net-freepbx-tools.sh"
  # If the helper already exists, don't touch it.
  if [[ -f "$pf" ]]; then
    echo ">>> PATH helper already present: $pf"
    return 0
  fi

  if [[ ! -d /etc/profile.d ]]; then
    warn "/etc/profile.d not found; cannot write PATH helper."
    return 0
  fi

  # Only write the helper if we can detect that a login shell PATH is missing /usr/local/bin.
  # Prefer checking as the typical operator user (123net) when present.
  local login_path=""
  if have bash; then
    if id 123net >/dev/null 2>&1; then
      login_path="$(su - 123net -c 'bash -lc "printf %s \"\$PATH\""' 2>/dev/null || true)"
    else
      login_path="$(bash -lc 'printf %s "$PATH"' 2>/dev/null || true)"
    fi
  fi

  if [[ -z "$login_path" ]]; then
    warn "Could not reliably detect login-shell PATH; leaving /etc/profile.d untouched."
    warn "If freepbx-* commands are not found after reconnect, add /usr/local/bin to PATH or create $pf manually."
    return 0
  fi

  if [[ ":$login_path:" == *":/usr/local/bin:"* ]]; then
    echo ">>> Login shell PATH already includes /usr/local/bin; skipping $pf"
    return 0
  fi

  cat > "$pf" <<'EOF'
# Added by 123NET FreePBX Tools installer
# Ensure /usr/local/bin is in PATH so freepbx-* commands are found.
case ":$PATH:" in
  *:/usr/local/bin:*) ;;
  *) export PATH="/usr/local/bin:$PATH" ;;
esac
EOF
  chmod 0644 "$pf" || true
  echo ">>> Wrote PATH helper: $pf"
}


# Ensure UTF-8 locale data exists on the system.
ensure_utf8_locale_pkg() {
  echo ">>> Ensuring UTF-8 locale packages are installed..."

  if is_el; then
    (dnf -y install glibc-langpack-en glibc-common || yum -y install glibc-langpack-en glibc-common) >/dev/null 2>&1 || true
  elif is_deb; then
    apt-get update -y || true
    apt-get install -y locales || true
  fi

  if ! locale -a 2>/dev/null | grep -qiE 'en_US\.utf8|en_US\.UTF-8'; then
    echo ">>> Generating en_US.UTF-8 locale..."
    if have localedef; then
      localedef -i en_US -f UTF-8 en_US.UTF-8 || true
    elif have locale-gen; then
      locale-gen en_US.UTF-8 || true
    fi
  fi
}


# Ensure UTF-8 locale exports for FreePBX hosts (prevents UnicodeEncodeError)
ensure_utf8_locale() {
  echo ">>> Forcing UTF-8 locale exports for interactive shells..."

  local pf="/etc/profile.d/123net-freepbx-tools-locale.sh"
  if [[ -d /etc/profile.d ]]; then
    cat > "$pf" <<'EOF'
# Added by 123NET FreePBX Tools installer
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8
EOF
    chmod 0644 "$pf" || true
    echo "  [OK] Wrote locale helper: $pf"
  else
    warn "/etc/profile.d not found; locale helper not written."
  fi

  if [[ -f /etc/locale.conf ]]; then
    sed -i -e '/^\s*LANG=/d' -e '/^\s*LC_ALL=/d' /etc/locale.conf || true
    printf '\nLANG=en_US.UTF-8\nLC_ALL=en_US.UTF-8\n' >> /etc/locale.conf
    echo "  [OK] Ensured locale defaults in /etc/locale.conf"
  elif [[ -f /etc/default/locale ]]; then
    sed -i -e '/^\s*LANG=/d' -e '/^\s*LC_ALL=/d' /etc/default/locale || true
    printf '\nLANG=en_US.UTF-8\nLC_ALL=en_US.UTF-8\n' >> /etc/default/locale
    echo "  [OK] Ensured locale defaults in /etc/default/locale"
  else
    warn "No locale defaults file found; system locale defaults not updated."
  fi
# Ensure UTF-8 locale exports for FreePBX hosts (prevents UnicodeEncodeError)
ensure_utf8_locale() {
  echo ">>> Ensuring UTF-8 locale exports in shell profiles..."

  local profiles=()
  profiles+=(/root/.bashrc)
  if id 123net >/dev/null 2>&1; then
    profiles+=(/home/123net/.bashrc)
  fi

  for profile in "${profiles[@]}"; do
    if [[ ! -f "$profile" ]]; then
      warn "Profile not found: $profile (skipping)"
      continue
    fi

    if grep -qE '^\s*export\s+LANG=' "$profile"; then
      :
    else
      printf '\nexport LANG=en_US.UTF-8\n' >> "$profile"
    fi

    if grep -qE '^\s*export\s+LC_ALL=' "$profile"; then
      :
    else
      printf 'export LC_ALL=en_US.UTF-8\n' >> "$profile"
    fi

    echo "  [OK] Locale exports ensured in $profile"
  done
}


# Print version policy banner and create version_policy.json if missing
print_policy_banner() {
  local policy_file="$INSTALL_DIR/version_policy.json"
  if [[ ! -f "$policy_file" ]]; then
    # Try to auto-detect FreePBX and Asterisk major versions
    local FWC AST_MAJ FPBX_MAJ
    FWC="$(command -v fwconsole || echo /var/lib/asterisk/bin/fwconsole)"
    FPBX_MAJ="$($FWC --version 2>/dev/null | awk '{print $NF}' | cut -d. -f1)"
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

  # Run version check scripts if present
  if [[ -x "$INSTALL_DIR/version_check.sh" ]]; then
    "$INSTALL_DIR/version_check.sh" || true
  fi
  if have python3 && [[ -f "$INSTALL_DIR/version_check.py" ]]; then
    python3 "$INSTALL_DIR/version_check.py" --quiet || true
  fi
}

# -------- Post-install smoke test ----------
# -------- Post-install smoke test ----------

# Run a post-install smoke test to verify all major tools and dependencies
post_install_smoke() {
  echo ">>> Running post-install smoke test..."
  local ok=0 fail=0

  # Check python3
  if have python3; then
    echo "  [OK] python3: $(python3 -V 2>&1)"
    ((ok++)) || true
  else
    warn "  [FAIL] python3 not found on PATH"
    ((fail++)) || true
  fi

  # Check graphviz dot
  if have dot; then
    echo "  [OK] graphviz 'dot': $(dot -V 2>&1)"
    ((ok++)) || true
  else
    warn "  [FAIL] graphviz 'dot' not found"
    ((fail++)) || true
  fi

  # Check mysql client
  if have mysql; then
    echo "  [OK] mysql client present"
    ((ok++)) || true
  else
    warn "  [FAIL] mysql client not found"
    ((fail++)) || true
  fi

  # Syntax-check key Python entrypoints without executing them.
  # Running scripts (even with --help) can hang if they import modules that
  # touch the system or expect a TTY.
  if [[ -f "$INSTALL_DIR/bin/freepbx_callflow_menu.py" ]]; then
    if python3 -m py_compile "$INSTALL_DIR/bin/freepbx_callflow_menu.py" >/dev/null 2>&1; then
      echo "  [OK] freepbx-callflows script syntax OK"
      ((ok++)) || true
    else
      warn "  [WARN] freepbx-callflows script failed syntax check"
    fi
  fi

  # Check time-condition status tool syntax
  if [[ -f "$INSTALL_DIR/bin/freepbx_tc_status.py" ]]; then
    if python3 -m py_compile "$INSTALL_DIR/bin/freepbx_tc_status.py" >/dev/null 2>&1; then
      echo "  [OK] freepbx-tc-status script syntax OK"
      ((ok++)) || true
    else
      warn "  [WARN] freepbx-tc-status script failed syntax check"
    fi
  fi

  echo ">>> Smoke test summary: PASS=$ok, FAIL=$fail"
  if (( fail > 0 )); then
    warn "Some checks failed. Tools may still work, but you might want to install missing deps."
  fi
}

# -------------------------------------------


# Main install flow: calls all major steps in order
main() {
  require_root  # Ensure running as root
  enable_epel_if_needed  # Enable EPEL repo if needed
  ensure_python3         # Ensure python3 is installed
  ensure_pkgset          # Install system packages
  ensure_python_packages # Install Python packages for GUI tools
  check_after_installs   # Check for missing dependencies
  install_files          # Copy and normalize all scripts
  patch_py36_text_kwarg  # Patch subprocess.run for Python <3.7
  install_symlinks       # Create all CLI symlinks
  verify_symlinks         # Validate symlinks/PATH
  ensure_path_profile      # Persist PATH fix on hosts missing /usr/local/bin
  ensure_utf8_locale_pkg   # Install locale packages/generate UTF-8 locale
  ensure_utf8_locale       # Persist UTF-8 locale exports for FreePBX shells

  log "Installed 123NET FreePBX Tools to $INSTALL_DIR"
  log "Symlinks created in $BIN_DIR:"
  ls -l "$BIN_DIR"/freepbx-* "$BIN_DIR"/freepbx_* "$BIN_DIR"/asterisk-full-diagnostic.sh 2>/dev/null || true
  log "Output directory: $CALLFLOWS_DIR"
  print_policy_banner    # Print version policy and run version checks

  post_install_smoke     # Run post-install smoke test

  log "Done."
}

main "$@"
