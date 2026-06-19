# fastapi_traceroute_server.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from pathlib import Path
import shutil
import socket
import subprocess
import json
import httpx

ALIASES_PATH = Path(__file__).resolve().parents[3] / "backend" / "ip_aliases.json"
IP_ALIASES: Dict[str, str] = {}


def load_aliases() -> None:
    global IP_ALIASES
    try:
        IP_ALIASES = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    except Exception:
        IP_ALIASES = {}


def label_for_ip(ip: str) -> str | None:
    return IP_ALIASES.get(ip)


load_aliases()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _geo(ip: str) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            data = (await client.get(f"http://ip-api.com/json/{ip}")).json()
            return {
                "city": data.get("city", ""),
                "country": data.get("country", ""),
                "lat": data.get("lat"),
                "lon": data.get("lon"),
            }
    except Exception:
        return {"city": "", "country": "", "lat": None, "lon": None}


def _hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ip


@app.post("/traceroute")
async def traceroute(request: Request):
    body = await request.json()
    target = body.get("target")

    if not target:
        return {"error": "Missing target"}

    mtr = shutil.which("mtr")
    if not mtr:
        return {"error": "mtr not installed — run: sudo apt-get install mtr-tiny"}

    try:
        result = subprocess.run(
            [mtr, "--json", "--no-dns", "--report-cycles", "3", target],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(result.stdout)
        hubs: List[Dict] = data["report"]["hubs"]

        hops = []
        for hub in hubs:
            ip = hub["host"]
            no_response = (ip == "???")
            latency = f"{hub['Last']:.1f} ms" if not no_response and hub["Last"] else "---"
            geo = await _geo(ip) if not no_response else {"city": "", "country": "", "lat": None, "lon": None}
            hops.append({
                "hop": hub["count"],
                "ip": ip if not no_response else "No response",
                "hostname": _hostname(ip) if not no_response else "No response",
                "latency": latency,
                "geo": geo,
                "label": label_for_ip(ip) if not no_response else None,
            })

        return hops

    except Exception as e:
        return {"error": str(e)}
