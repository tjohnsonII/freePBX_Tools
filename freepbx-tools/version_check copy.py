# version_check.py
import json, re, os, pathlib
POLICY = json.load(open(pathlib.Path(
    os.getenv("VERSION_POLICY_JSON", "version_policy.json")
)))

def major_of(s: str|None):
    if not s: return None
    m = re.search(r"\d+(?:\.\d+)+", s)
    return int(m.group(0).split(".")[0]) if m else None

def version_ok(component: str, version: str) -> bool:
    m = major_of(version)
    return m in POLICY[component]["accepted_majors"] if m is not None else False
