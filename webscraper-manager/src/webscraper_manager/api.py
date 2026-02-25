from __future__ import annotations

import time
from dataclasses import dataclass

import requests


@dataclass
class ApiResponse:
    url: str
    status_code: int
    latency_ms: int
    body_snippet: str


def ping(base_url: str, path: str) -> ApiResponse:
    url = f"{base_url.rstrip('/')}{path}"
    start = time.perf_counter()
    resp = requests.get(url, timeout=5)
    latency = int((time.perf_counter() - start) * 1000)
    return ApiResponse(url=url, status_code=resp.status_code, latency_ms=latency, body_snippet=resp.text[:180])


def health_check(base_url: str) -> list[ApiResponse]:
    paths = ["/", "/api/events/latest?limit=1"]
    return [ping(base_url, path) for path in paths]


def tail(base_url: str, path: str, seconds: int, interval: float) -> list[ApiResponse]:
    out: list[ApiResponse] = []
    end = time.time() + seconds
    while time.time() < end:
        out.append(ping(base_url, path))
        time.sleep(interval)
    return out
