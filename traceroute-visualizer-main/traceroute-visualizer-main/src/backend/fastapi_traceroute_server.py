# fastapi_traceroute_server.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import socket
import subprocess
import json
import re
import httpx

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/traceroute")
async def traceroute(request: Request):
    body = await request.json()
    target = body.get("target")

    if not target:
        return {"error": "Missing target"}

    try:
        result = subprocess.run(["traceroute", "-n", target], capture_output=True, text=True, timeout=30)
        lines = result.stdout.strip().split('\n')[1:]  # skip header
        hops = []
        hop_counter = 1

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if '* * *' in line:
                ip = "No response"
                latency = "---"
                hostname = "No response"
                geo = {"city": "", "country": "", "lat": None, "lon": None}
            else:
                match = re.match(r'^(\d+)\s+([\d.]+)\s+([\d.]+)\s+ms', line)
                if match:
                    ip = match.group(2)
                    latency = match.group(3) + " ms"

                    try:
                        hostname = socket.gethostbyaddr(ip)[0]
                    except:
                        hostname = ip

                    try:
                        geo_url = f"http://ip-api.com/json/{ip}"
                        async with httpx.AsyncClient(timeout=2) as client:
                            geo_response = await client.get(geo_url)
                            data = geo_response.json()
                            geo = {
                                "city": data.get("city", ""),
                                "country": data.get("country", ""),
                                "lat": data.get("lat"),
                                "lon": data.get("lon"),
                            }
                    except:
                        geo = {"city": "", "country": "", "lat": None, "lon": None}
                else:
                    ip = "No response"
                    latency = "---"
                    hostname = "No response"
                    geo = {"city": "", "country": "", "lat": None, "lon": None}

            hops.append({
                "hop": hop_counter,
                "ip": ip,
                "hostname": hostname,
                "latency": latency,
                "geo": geo,
            })

            hop_counter += 1

        return hops

    except Exception as e:
        return {"error": str(e)}
