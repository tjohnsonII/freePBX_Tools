from __future__ import annotations

import argparse
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from webscraper.ticket_api import db


DEFAULT_DB = os.path.join("webscraper", "output", "tickets.sqlite")
OUTPUT_ROOT = os.path.join("webscraper", "output")

app = FastAPI(title="Ticket History API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_path() -> str:
    return os.environ.get("TICKETS_DB_PATH", DEFAULT_DB)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "db_path": get_db_path()}


@app.get("/handles")
def handles(search: str = "", limit: int = 50, offset: int = 0):
    return db.list_handles(get_db_path(), search=search, limit=limit, offset=offset)


@app.get("/handles/{handle}")
def handle_detail(handle: str):
    row = db.get_handle(get_db_path(), handle)
    if not row:
        raise HTTPException(status_code=404, detail="Handle not found")
    return row


@app.get("/handles/{handle}/tickets")
def handle_tickets(
    handle: str,
    status: str | None = None,
    q: str | None = None,
    from_utc: str | None = Query(None, alias="from"),
    to_utc: str | None = Query(None, alias="to"),
    limit: int = 100,
    offset: int = 0,
):
    return db.list_tickets(
        get_db_path(),
        handle=handle,
        status=status,
        q=q,
        from_utc=from_utc,
        to_utc=to_utc,
        limit=limit,
        offset=offset,
    )


@app.get("/tickets/{ticket_id}")
def ticket(ticket_id: str, handle: str | None = None):
    row = db.get_ticket(get_db_path(), ticket_id, handle)
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    artifacts = db.get_artifacts(get_db_path(), row["ticket_id"], row["handle"])
    row["artifacts"] = artifacts
    return row


@app.get("/stats")
def stats():
    return db.get_stats(get_db_path())


@app.get("/artifacts")
def artifact(path: str):
    safe_path = db.safe_artifact_path(path, OUTPUT_ROOT)
    if not safe_path or not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(safe_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ticket API")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    os.environ["TICKETS_DB_PATH"] = args.db

    import uvicorn

    uvicorn.run("webscraper.ticket_api.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
