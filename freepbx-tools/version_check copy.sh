# version_check.sh
policy_json="${VERSION_POLICY_JSON:-./version_policy.json}"

major_of() {
  ver=$(echo "$1" | grep -oE '[0-9]+(\.[0-9]+)+' | head -n1)
  echo "${ver%%.*}"
}

version_ok() {
  component="$1"   # freepbx | asterisk
  version="$2"
  major=$(major_of "$version")
  jq -e --arg comp "$component" --argjson m "${major:--1}" \
     '.[$comp].accepted_majors | index($m) != null' "$policy_json" >/dev/null
}
