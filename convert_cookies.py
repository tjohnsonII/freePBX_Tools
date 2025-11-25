import json

input_file = "cookies.txt"
output_file = "cookies.json"
target_domains = {".123.net", "secure.123.net"}

cookies = {}

with open(input_file, "r") as f:
    for line in f:
        if line.startswith("#") or not line.strip():
            continue
        parts = line.strip().split("\t")
        if len(parts) < 7:
            continue
        domain, _, _, _, _, name, value = parts
        if domain in target_domains:
            cookies[name] = value

with open(output_file, "w") as f:
    json.dump(cookies, f, indent=2)

print(f"Extracted {len(cookies)} cookies to {output_file}")
