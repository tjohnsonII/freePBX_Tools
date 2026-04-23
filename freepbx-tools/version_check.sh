
# ============================================================================
# version_check.sh - FreePBX/Asterisk Version Policy Compliance Checker
# --------------------------------------------------------------------------
# This script checks the installed FreePBX and Asterisk versions against a
# version policy JSON file (default: ./version_policy.json or $VERSION_POLICY_JSON).
# It is intended to be run as part of install or diagnostic workflows.
#
# HOW IT WORKS:
# 1. Detects installed versions using CLI tools (fwconsole, asterisk).
# 2. Extracts the major version number from each version string.
# 3. Loads the policy JSON and checks if the detected major version is accepted.
# 4. Prints a simple pass/fail result for each component.
#
# VARIABLES:
#   policy_json   - Path to the version policy JSON file (env or default)
#
# FUNCTIONS:
#   major_of      - Extracts the major version number from a version string.
#   version_ok    - Checks if a component's major version is accepted by policy.
# ============================================================================

# Set the policy file path, using env override if present
policy_json="${VERSION_POLICY_JSON:-./version_policy.json}"

# major_of: Extract the major version number from a version string
# Usage: major_of "16.0.40.13"  => 16
major_of() {
  # Use grep to extract the first version-like string, then cut off after the first dot
  ver=$(echo "$1" | grep -oE '[0-9]+(\.[0-9]+)+' | head -n1)
  echo "${ver%%.*}"
}

# version_ok: Check if a component's major version is accepted by policy
# Usage: version_ok freepbx "16.0.40.13"
version_ok() {
  component="$1"   # freepbx | asterisk
  version="$2"     # Full version string
  major=$(major_of "$version")  # Extract major version
  # Use jq to check if the major version is in the accepted_majors array for the component
  jq -e --arg comp "$component" --argjson m "${major:--1}" \
     '.[$comp].accepted_majors | index($m) != null' "$policy_json" >/dev/null
}
