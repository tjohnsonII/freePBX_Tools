#!/bin/bash
# make_executable.sh
# Makes all .sh and .py files executable in the freePBX tools directory structure
# Run this script after copying from Windows development environment to Linux FreePBX server

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$SCRIPT_DIR"

log() { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

make_scripts_executable() {
    local dir="$1"
    local pattern="$2"
    local description="$3"
    local count=0
    
    if [[ ! -d "$dir" ]]; then
        warn "Directory $dir does not exist, skipping"
        return 0
    fi
    
    log ">>> Making $description executable in: $dir"
    
    # Find all files matching pattern and make them executable
    while IFS= read -r -d '' file; do
        if [[ -f "$file" ]] && [[ ! -x "$file" ]]; then
            log "  Making executable: $(basename "$file")"
            chmod +x "$file"
            ((count++))
        elif [[ -f "$file" ]]; then
            log "  Already executable: $(basename "$file")"
        fi
    done < <(find "$dir" -maxdepth 1 -name "$pattern" -type f -print0 2>/dev/null || true)
    
    if [[ $count -eq 0 ]]; then
        local existing_count
        existing_count=$(find "$dir" -maxdepth 1 -name "$pattern" -type f 2>/dev/null | wc -l)
        if [[ $existing_count -eq 0 ]]; then
            log "  No $description found in $dir"
        else
            log "  All $existing_count $description were already executable in $dir"
        fi
    else
        log "  Made $count $description executable in $dir"
    fi
    
    return 0
}

check_system_readiness() {
    log "🔍 Checking system readiness..."
    
    local issues=0
    
    # Check if we're on a Linux system
    if [[ ! -f /etc/os-release ]]; then
        warn "This doesn't appear to be a Linux system"
        ((issues++))
    fi
    
    # Check for required commands
    local required_commands=("python3" "mysql" "fwconsole")
    for cmd in "${required_commands[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            log "  ✓ $cmd found: $(which "$cmd")"
        else
            warn "  ✗ $cmd not found (may be installed during ./install.sh)"
            ((issues++))
        fi
    done
    
    # Check if we can detect FreePBX
    if command -v fwconsole >/dev/null 2>&1; then
        local fbpx_version
        fbpx_version=$(fwconsole --version 2>/dev/null | awk '{print $NF}' || echo "unknown")
        log "  ✓ FreePBX detected: $fbpx_version"
    else
        warn "  ✗ FreePBX not detected (fwconsole not found)"
    fi
    
    if [[ $issues -eq 0 ]]; then
        log "  ✅ System appears ready for FreePBX tools"
    else
        log "  ⚠️  Some dependencies may be missing (install.sh will attempt to resolve)"
    fi
    
    return 0
}

main() {
    log "🔧 FreePBX Tools - Make Scripts Executable"
    log "==========================================="
    log "Working directory: $TOOLS_DIR"
    log ""
    
    # Make shell scripts executable in main directory
    make_scripts_executable "$TOOLS_DIR" "*.sh" "shell scripts"
    
    # Make shell scripts executable in bin subdirectory
    if [[ -d "$TOOLS_DIR/bin" ]]; then
        make_scripts_executable "$TOOLS_DIR/bin" "*.sh" "shell scripts"
    fi
    
    # Make Python scripts executable
    log ""
    make_scripts_executable "$TOOLS_DIR" "*.py" "Python scripts"
    
    if [[ -d "$TOOLS_DIR/bin" ]]; then
        make_scripts_executable "$TOOLS_DIR/bin" "*.py" "Python scripts"
    fi
    
    log ""
    check_system_readiness
    
    log ""
    log "✅ Executable permissions set successfully!"
    log ""
    log "📋 Next steps:"
    log "   1. Run: sudo ./install.sh"
    log "   2. Test: freepbx-callflows (after installation)"
    log "   3. Analyze: freepbx-module-analyzer"
    log ""
    log "🔍 Verify permissions: ls -la *.sh bin/*.sh *.py bin/*.py"
    log "🗑️  Cleanup when done: sudo ./uninstall.sh"
}

# Check if we're being run from the correct directory
if [[ ! -f "$TOOLS_DIR/install.sh" ]]; then
    warn "This script should be run from the freepbx-tools directory"
    warn "Expected to find install.sh in: $TOOLS_DIR"
    log ""
    log "💡 If you just copied files from Windows:"
    log "   cd /path/to/freepbx-tools/"
    log "   ./make_executable.sh"
    exit 1
fi

main "$@"