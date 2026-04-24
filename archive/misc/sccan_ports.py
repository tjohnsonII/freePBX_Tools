import json
import re
from pathlib import Path

tasks_file = Path(".vscode/tasks.json")
data = json.loads(tasks_file.read_text(encoding="utf-8"))

results = []

def add_result(port, label, source, context):
    results.append({
        "port": int(port),
        "label": label,
        "source": source,
        "context": context
    })

def scan_string(text, label, source):
    patterns = [
        r'--port\s+(\d{2,5})',
        r'-p\s+(\d{2,5})',
        r'-Port\s+(\d{2,5})',
        r':(\d{2,5})\b',
        r'\bports?\b.*?\b(\d{2,5})\b',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            port = int(match.group(1))
            if 1 <= port <= 65535:
                add_result(port, label, source, text)

    # Special case: batch cleanup list like "(3000 3001 3002 8787 8002)"
    list_match = re.search(r'\(([\d\s]+)\)', text)
    if list_match:
        for token in list_match.group(1).split():
            if token.isdigit():
                port = int(token)
                if 1 <= port <= 65535:
                    add_result(port, label, source, text)

tasks = data.get("tasks", [])
for idx, task in enumerate(tasks):
    label = task.get("label", f"task[{idx}]")

    for field in ("command",):
        value = task.get(field)
        if isinstance(value, str):
            scan_string(value, label, f"{label}.{field}")

    args = task.get("args", [])
    if isinstance(args, list):
        for i, arg in enumerate(args):
            if isinstance(arg, str):
                scan_string(arg, label, f"{label}.args[{i}]")

    options = task.get("options", {})
    if isinstance(options, dict):
        env = options.get("env", {})
        if isinstance(env, dict):
            for k, v in env.items():
                if isinstance(v, str):
                    scan_string(v, label, f"{label}.options.env.{k}")

seen = set()
for item in sorted(results, key=lambda x: (x["port"], x["label"], x["source"])):
    key = (item["port"], item["label"], item["source"], item["context"])
    if key in seen:
        continue
    seen.add(key)
    print(f'{item["port"]:<5} {item["label"]} -> {item["source"]}')
    print(f'      {item["context"]}')