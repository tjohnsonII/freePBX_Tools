from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


Action = Literal["deploy", "uninstall", "clean_deploy", "connect_only", "upload_only", "bundle"]


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / "deploy_freepbx_tools.py").exists() and (parent / "deploy_uninstall_tools.py").exists():
            return parent
    raise RuntimeError("Could not locate repo root (deploy scripts not found)")


REPO_ROOT = _find_repo_root()


def _parse_servers(raw: str) -> List[str]:
    if not raw:
        return []
    # Accept newline, comma, tab, and space separated.
    tokens: List[str] = []
    for line in raw.replace(",", "\n").splitlines():
        for part in line.strip().split():
            p = part.strip()
            if p:
                tokens.append(p)
    # De-dupe, preserve order
    seen = set()
    out: List[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


class JobCreate(BaseModel):
    action: Action
    servers: str = Field("", description="Newline/comma separated hosts")
    workers: int = Field(5, ge=1, le=50)
    username: str = "123net"
    password: str = ""
    root_password: str = ""
    bundle_name: str = "freepbx-tools-bundle.zip"


class JobInfo(BaseModel):
    id: str
    action: Action
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    return_code: Optional[int] = None
    servers: List[str] = []


@dataclass
class Job:
    id: str
    action: Action
    servers: List[str]
    workers: int
    username: str
    password: str
    root_password: str
    bundle_name: str

    status: str = "queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    return_code: Optional[int] = None

    lines: List[str] = field(default_factory=list)
    clients: Set[WebSocket] = field(default_factory=set)
    proc: Optional[subprocess.Popen[str]] = None


JOBS: Dict[str, Job] = {}
JOBS_LOCK = asyncio.Lock()


app = FastAPI(title="FreePBX Tools Deploy UI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3003",
        "http://127.0.0.1:3003",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _job_info(job: Job) -> JobInfo:
    return JobInfo(
        id=job.id,
        action=job.action,
        status=job.status,  # type: ignore[arg-type]
        created_at=_iso(job.created_at) or "",
        started_at=_iso(job.started_at),
        finished_at=_iso(job.finished_at),
        return_code=job.return_code,
        servers=job.servers,
    )


async def _append_line(job: Job, line: str) -> None:
    # keep bounded memory
    job.lines.append(line)
    if len(job.lines) > 5000:
        job.lines = job.lines[-5000:]

    dead: List[WebSocket] = []
    for ws in list(job.clients):
        try:
            await ws.send_text(line)
        except Exception:
            dead.append(ws)
    for ws in dead:
        job.clients.discard(ws)


def _build_env(job: Job) -> Dict[str, str]:
    env = os.environ.copy()
    # Pass creds via env to avoid exposing in process list/args.
    if job.username:
        env["FREEPBX_USER"] = job.username
    if job.password:
        env["FREEPBX_PASSWORD"] = job.password
    if job.root_password:
        env["FREEPBX_ROOT_PASSWORD"] = job.root_password

    # Make Python output deterministic for decode.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


def _python_exe() -> str:
    configured = os.environ.get("FREEPBX_DEPLOY_UI_PYTHON", "").strip()
    if configured:
        return configured

    # Prefer the repo's standard Python (has Paramiko, etc.) over the backend venv.
    candidates = [
        Path("E:/DevTools/Python/python.exe"),
        Path("E:/DevTools/Python/python3.exe"),
    ]
    for p in candidates:
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass

    return sys.executable


async def _run_one(job: Job, args: List[str], title: str) -> int:
    await _append_line(job, "\n" + ("=" * 70) + "\n")
    await _append_line(job, f"{title}\n")
    await _append_line(job, ("=" * 70) + "\n")
    await _append_line(job, "CMD: " + " ".join(args) + "\n\n")

    loop = asyncio.get_running_loop()

    def _emit(line: str) -> None:
        try:
            asyncio.run_coroutine_threadsafe(_append_line(job, line), loop)
        except Exception:
            # best-effort; job still completes
            pass

    def _reader(stream: Optional[object]) -> None:
        if stream is None:
            return
        try:
            while True:
                line = stream.readline()  # type: ignore[attr-defined]
                if not line:
                    break
                _emit(str(line))
        except Exception as e:
            _emit(f"\n[BACKEND STREAM ERROR] {type(e).__name__}: {e!r}\n")

    def _run_blocking() -> int:
        proc = subprocess.Popen(
            args,
            cwd=str(REPO_ROOT),
            env=_build_env(job),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            bufsize=1,
            universal_newlines=True,
        )
        job.proc = proc

        t_out = threading.Thread(target=_reader, args=(proc.stdout,), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr,), daemon=True)
        t_out.start()
        t_err.start()

        rc = proc.wait()
        try:
            t_out.join(timeout=2.0)
            t_err.join(timeout=2.0)
        except Exception:
            pass

        job.proc = None
        return int(rc)

    return await asyncio.to_thread(_run_blocking)


async def _run_job(job: Job) -> None:
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)

    try:
        if job.action == "bundle":
            args = [_python_exe(), "deploy_freepbx_tools.py", "--bundle", job.bundle_name]
            rc = await _run_one(job, args, "Create Offline Bundle")
        elif job.action in {"deploy", "connect_only", "upload_only"}:
            if not job.servers:
                raise RuntimeError("No servers provided")
            args = [_python_exe(), "deploy_freepbx_tools.py", "--workers", str(job.workers), "--servers", *job.servers]
            if job.action == "connect_only":
                args.insert(2, "--connect-only")
            elif job.action == "upload_only":
                args.insert(2, "--upload-only")
            rc = await _run_one(job, args, "Deploy FreePBX Tools")
        elif job.action == "uninstall":
            if not job.servers:
                raise RuntimeError("No servers provided")
            args = [_python_exe(), "deploy_uninstall_tools.py", "--servers", ",".join(job.servers)]
            rc = await _run_one(job, args, "Uninstall FreePBX Tools")
        elif job.action == "clean_deploy":
            if not job.servers:
                raise RuntimeError("No servers provided")
            rc1 = await _run_one(
                job,
                [_python_exe(), "deploy_uninstall_tools.py", "--servers", ",".join(job.servers)],
                "Step 1/2: Uninstall",
            )
            rc2 = await _run_one(
                job,
                [_python_exe(), "deploy_freepbx_tools.py", "--workers", str(job.workers), "--servers", *job.servers],
                "Step 2/2: Install",
            )
            rc = 0 if (rc1 == 0 and rc2 == 0) else (rc2 or rc1)
        else:
            raise RuntimeError(f"Unsupported action: {job.action}")

        job.return_code = rc
        if job.status != "cancelled":
            job.status = "succeeded" if rc == 0 else "failed"
    except asyncio.CancelledError:
        job.status = "cancelled"
        raise
    except Exception as e:
        job.return_code = 1
        job.status = "failed"
        await _append_line(
            job,
            f"\n[BACKEND ERROR] {type(e).__name__}: {e!r}\n" + traceback.format_exc() + "\n",
        )
    finally:
        job.finished_at = datetime.now(timezone.utc)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "repo_root": str(REPO_ROOT),
    }


@app.get("/api/jobs", response_model=List[JobInfo])
async def list_jobs() -> List[JobInfo]:
    async with JOBS_LOCK:
        return [_job_info(j) for j in JOBS.values()]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> Dict[str, Any]:
    async with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "job": _job_info(job).model_dump(),
            "tail": job.lines[-300:],
        }


@app.post("/api/jobs", response_model=JobInfo)
async def create_job(req: JobCreate) -> JobInfo:
    job_id = uuid.uuid4().hex
    servers = _parse_servers(req.servers)
    job = Job(
        id=job_id,
        action=req.action,
        servers=servers,
        workers=req.workers,
        username=req.username,
        password=req.password,
        root_password=req.root_password,
        bundle_name=req.bundle_name,
    )

    async with JOBS_LOCK:
        JOBS[job_id] = job

    asyncio.create_task(_run_job(job))
    return _job_info(job)


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> Dict[str, Any]:
    async with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in {"queued", "running"}:
        return {"ok": True, "status": job.status}

    job.status = "cancelled"
    if job.proc and job.proc.poll() is None:
        try:
            job.proc.terminate()
        except Exception:
            pass
    await _append_line(job, "\n[BACKEND] Cancel requested.\n")
    return {"ok": True, "status": job.status}


@app.websocket("/api/jobs/{job_id}/ws")
async def job_ws(ws: WebSocket, job_id: str) -> None:
    await ws.accept()

    async with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            await ws.send_text("[BACKEND] Job not found\n")
            await ws.close(code=1008)
            return
        job.clients.add(ws)
        # send backlog
        for line in job.lines[-500:]:
            await ws.send_text(line)

    try:
        while True:
            # Keep connection alive; client doesn't need to send.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id].clients.discard(ws)


# Optional: serve built frontend if present.
_dist = (REPO_ROOT / "freepbx-deploy-ui" / "dist")
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="ui")
