from __future__ import annotations

import asyncio
import shlex
import time
from pathlib import Path
from typing import Any


class CommandRunner:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    async def run(self, command: list[str], timeout: int = 90) -> dict[str, Any]:
        start = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(self.repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            exit_code = proc.returncode
        except asyncio.TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            exit_code = 124
            stderr = (stderr or b"") + b"\nCommand timed out"

        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": (stdout or b"").decode("utf-8", errors="replace"),
            "stderr": (stderr or b"").decode("utf-8", errors="replace"),
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "command": command,
            "command_text": shlex.join(command),
        }
