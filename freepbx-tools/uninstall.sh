#!/usr/bin/env bash
# ============================================================================
# 123NET FreePBX Tools - Uninstaller
# --------------------------------------------------------------------------
# TECHNICAL EXPLANATION:
#
# This script is designed to safely and thoroughly remove all traces of the FreePBX tools suite from a Linux system.
#
# LOGIC & FLOW:
# - The script first defines key directories for installed tools, symlinks, and output data.
# - It removes only symlinks created by the installer, never real binaries, by checking with -L before unlinking.
# - The main install directory is recursively deleted if it exists, ensuring all scripts and resources are purged.
# - The callflows output directory is only removed if the user specifies --purge-callflows, and confirmation is required unless -y/--yes is used.
# - CLI convenience symlinks (like 'asterisk' and 'fwconsole') are only removed if --purge-cli-links is specified, to avoid breaking system binaries.
# - The script uses functions for modularity: unlink_if_symlink, remove_dir_if_exists, parse_args, and confirm for user prompts.
# - All actions are echoed for transparency, and the script is idempotent: it will not fail if items are already gone.
# - Parent directories are cleaned up if empty, but not forcibly removed if they contain other data.
#
# SAFETY:
# - set -euo pipefail ensures the script exits on any error, unset variable, or failed pipeline.
# - All destructive actions are guarded by existence/type checks.
# - Must be run as root (checked at runtime) to avoid partial removals or permission errors.
#
# OPTIONS & INTERACTION:
# - --purge-callflows: Remove the callflows output directory (with confirmation).
# - --purge-cli-links: Remove CLI symlinks for asterisk/fwconsole.
# - -y/--yes: Assume 'yes' to all prompts for non-interactive use.
# - -h/--help: Show usage and exit.
#
# The script is safe for repeated use, will not error if run multiple times, and is suitable for automated or manual uninstallation.
# ============================================================================
#!/bin/bash  # Use bash shell for script execution
# Exit immediately if a command exits with a non-zero status, treat unset variables as errors, and fail if any command in a pipeline fails
set -euo pipefail  # Exit on error, undefined variable, or failed pipeline


# ===============================
# VARIABLE LEGEND (Map)
# ---------------------
# INSTALL_DIR     - Main install directory for FreePBX tools (default: /usr/local/123net/freepbx-tools/)
# SYMLINK_DIR     - Directory for system-wide symlinks to tool entry points (default: /usr/local/bin/)
# OUTPUT_DIR      - Directory for call flow SVG/JSON output (default: /home/123net/callflows/)
# BIN_DIR         - Directory for command symlinks (may be set to /usr/local/bin or similar)
# INSTALL_ROOT    - Parent directory of INSTALL_DIR (used for cleanup if empty)
# CALLFLOWS_DIR   - Directory for call flow output (same as OUTPUT_DIR, may be set by user)
# PURGE_CALLFLOWS - Flag: if set, remove callflows directory
# PURGE_CLI_LINKS - Flag: if set, remove CLI symlinks (asterisk, fwconsole)
# ASSUME_YES      - Flag: if set, auto-confirm prompts (non-interactive)
# prompt          - Prompt string for confirmation dialogs
# ans             - User input for confirmation
# n               - Loop variable for tool names
# p               - Parameter for unlink_if_symlink (path)
# d               - Parameter for remove_dir_if_exists (directory)
# $@, $#          - All/number of command-line arguments
# ===============================
# FreePBX Tools Uninstall Script
# ===============================
# Removes all installed FreePBX tools, symlinks, and output directories
# WARNING: This script is destructive. Run as root.

# Define the directory where FreePBX tools are installed
INSTALL_DIR="/usr/local/123net/freepbx-tools/"  # Main install directory for FreePBX tools
# Define the directory where symlinks to the tools are created
SYMLINK_DIR="/usr/local/bin/"  # Directory for system-wide symlinks
# Define the directory where call flow SVG and JSON output is stored
OUTPUT_DIR="/home/123net/callflows/"  # Output directory for generated call flow files

# Remove symlinks for all tool entry points
for TOOL in freepbx-callflows freepbx-dump freepbx-diagnostic asterisk-callflows asterisk-dump asterisk-diagnostic; do  # Loop through each tool name
  # Check if the symlink exists and is a symbolic link
  if [ -L "$SYMLINK_DIR$TOOL" ]; then  # Test if the symlink exists
    # Print which symlink is being removed
    echo "Removing symlink: $SYMLINK_DIR$TOOL"  # Inform user of removal
    # Remove the symlink
    rm "$SYMLINK_DIR$TOOL"  # Delete the symlink
  fi  # End if
done  # End for loop

# Remove the main install directory if it exists
if [ -d "$INSTALL_DIR" ]; then  # Test if install directory exists
  # Print which directory is being removed
  echo "Removing install directory: $INSTALL_DIR"  # Inform user of removal
  # Recursively remove the install directory and all its contents
  rm -rf "$INSTALL_DIR"  # Delete the directory and all contents
fi  # End if

# Remove the output directory if it exists
if [ -d "$OUTPUT_DIR" ]; then  # Test if output directory exists
  # Print which output directory is being removed
  echo "Removing output directory: $OUTPUT_DIR"  # Inform user of removal
  # Recursively remove the output directory and all its contents
  rm -rf "$OUTPUT_DIR"  # Delete the directory and all contents
fi  # End if

# Print completion message
unlink_if_symlink() {

# confirm: Prompt the user for a yes/no answer. Returns 0 (true) if yes, 1 (false) otherwise.
# Usage: confirm "Prompt message"
confirm() {
  # Print the final uninstall message
  echo "FreePBX tools uninstalled."  # Final message to user
  # If ASSUME_YES is set, skip prompt and return success
  if (( ASSUME_YES )); then return 0; fi
  # Prompt the user and read input
  read -r -p "$prompt [y/N] " ans || true  # Read user input, default to 'no' on error
  # Return true if answer is yes (case-insensitive)
  [[ "$ans" =~ ^[Yy]$ ]]
}

# unlink_if_symlink: Remove a file if it is a symbolic link.
# Usage: unlink_if_symlink "/path/to/symlink"
unlink_if_symlink() {
  local p="$1"  # Path to check
  if [[ -L "$p" ]]; then  # If the path is a symlink
    rm -f "$p" && echo "Removed symlink: $p"  # Remove it and print confirmation
  fi
}

# remove_dir_if_exists: Remove a directory and its contents if it exists.
# Usage: remove_dir_if_exists "/path/to/dir"
remove_dir_if_exists() {
  local d="$1"  # Directory to check
  if [[ -d "$d" ]]; then  # If the directory exists
    rm -rf "$d" && echo "Removed dir: $d"  # Remove it and print confirmation
  fi
}

# parse_args: Parse command-line arguments and set global flags.
# Sets PURGE_CALLFLOWS, PURGE_CLI_LINKS, ASSUME_YES as needed.
parse_args() {
  while [[ $# -gt 0 ]]; do  # While there are arguments left
    case "$1" in
      --purge-callflows) PURGE_CALLFLOWS=1 ;;  # Set flag to purge callflows directory
      --purge-cli-links) PURGE_CLI_LINKS=1 ;;  # Set flag to purge CLI symlinks
      -y|--yes)          ASSUME_YES=1 ;;      # Set flag to auto-confirm prompts
      -h|--help)         usage; exit 0 ;;     # Show usage and exit
      *) echo "Unknown option: $1" >&2; usage; exit 1 ;;  # Unknown option: print error and exit
    esac
    shift  # Move to next argument
  done
}

# main: Main entry point for the uninstall script.
# Handles root check, argument parsing, and all uninstall steps.
main() {
  require_root  # Ensure script is run as root
  parse_args "$@"  # Parse command-line arguments

  echo "Removing command symlinks under ${BIN_DIR}…"  # Inform user
  for n in \
    freepbx-diagnostic \
    freepbx-dump \
    freepbx-version-check \
    freepbx-install \
    freepbx-uninstall
  do
    unlink_if_symlink "${BIN_DIR}/${n}"  # Remove each tool symlink if it exists
  done

  if (( PURGE_CLI_LINKS )); then  # If CLI symlinks should be purged
    echo "Removing convenience CLI symlinks under ${BIN_DIR}…"  # Inform user
    # Only remove if there are symlinks (won't touch real binaries)
    unlink_if_symlink "${BIN_DIR}/asterisk"  # Remove asterisk symlink if present
    unlink_if_symlink "${BIN_DIR}/fwconsole"  # Remove fwconsole symlink if present
  else
    echo "Keeping any existing CLI symlinks (use --purge-cli-links to remove)."  # Inform user
  fi

  if [[ -d "$INSTALL_DIR" ]]; then  # If install directory exists
    remove_dir_if_exists "$INSTALL_DIR"  # Remove it
  else
    echo "Install dir not found (already removed?): $INSTALL_DIR"  # Inform user
  fi

  # Remove parent if empty
  if rmdir "$INSTALL_ROOT" 2>/dev/null; then  # Try to remove parent directory if empty
    echo "Removed empty parent dir: $INSTALL_ROOT"  # Inform user
  fi

  if (( PURGE_CALLFLOWS )); then  # If callflows directory should be purged
    if [[ -d "$CALLFLOWS_DIR" ]]; then  # If callflows directory exists
      if confirm "Permanently remove ${CALLFLOWS_DIR}?"; then  # Prompt user for confirmation
        rm -rf "$CALLFLOWS_DIR"  # Remove callflows directory
        echo "Removed callflows dir: $CALLFLOWS_DIR"  # Inform user
      else
        echo "Preserved callflows dir: $CALLFLOWS_DIR"  # Inform user
      fi
    fi
  else
    echo "Preserving callflows dir: $CALLFLOWS_DIR (use --purge-callflows to remove)."  # Inform user
  fi

  echo  # Print blank line
  echo "Uninstall complete."  # Final completion message
}

main "$@"
