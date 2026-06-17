from __future__ import annotations

import os


def validate_path(label: str, path: str | None) -> str | None:
    if not path:
        return None
    if os.path.exists(path):
        return path
    print(f"[WARN] {label} not found at '{path}'. Falling back to auto-detect.")
    return None


def edge_binary_path() -> str | None:
    edge_binary_env = os.environ.get("EDGE_PATH") or os.environ.get("EDGE_BINARY_PATH")
    if edge_binary_env:
        resolved = validate_path("Edge binary (env)", edge_binary_env)
        if resolved:
            print(f"[INFO] Using Edge binary from env: {resolved}")
            return resolved
    pf86 = os.environ.get("ProgramFiles(x86)")
    pf = os.environ.get("ProgramFiles")
    preferred: list[str] = []
    if pf86:
        preferred.append(os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"))
    if pf:
        preferred.append(os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"))
    for candidate in preferred:
        resolved = validate_path("Edge binary", candidate)
        if resolved:
            print(f"[INFO] Using Edge binary: {resolved}")
            return resolved
    print("[INFO] Using Selenium Manager to locate Edge binary.")
    return None
