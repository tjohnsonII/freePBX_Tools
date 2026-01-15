#!/bin/bash
# ============================================================================
# bootstrap.sh - The ultimate lazy solution to the chmod chicken-and-egg problem
# -----------------------------------------------------------------------------
# This script ensures that all shell and Python scripts in the current directory
# and the bin/ subdirectory are marked as executable. This is useful after
# cloning or copying the repo, especially if file permissions were lost.
#
# HOW IT WORKS:
# - Uses chmod +x to add execute permissions to all .sh and .py files in the
#   current directory and bin/ subdirectory.
# - Redirects errors to /dev/null to avoid noisy output if files are missing.
# - Prints a success message and a reminder to run the main installer.
# ============================================================================

# Add execute permission to all .sh and .py scripts in current and bin/ directory
chmod +x *.sh bin/*.sh *.py bin/*.py 2>/dev/null  # Ignore errors if files don't exist

# Inform the user that permissions have been set
echo "All scripts are now executable."

# Suggest the next step to the user
echo "Next: sudo ./install.sh"