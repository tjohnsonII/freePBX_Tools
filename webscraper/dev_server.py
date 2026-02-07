from __future__ import annotations

import argparse
from datetime import datetime, timezone


def _extracted_at() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _run_fastapi(host: str, port: int, reload: bool) -> None:
    from fastapi import FastAPI
    import uvicorn

    app = FastAPI()
    globals()["app"] = app

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"ok": True, "extracted_at": _extracted_at()}

    @app.on_event("startup")
    def _announce_ready() -> None:
        print("Webscraper dev server ready", flush=True)

    print("Webscraper dev server starting", flush=True)
    uvicorn.run("webscraper.dev_server:app", host=host, port=port, reload=reload)


def _run_flask(host: str, port: int, reload: bool) -> None:
    from flask import Flask, jsonify

    app = Flask(__name__)

    @app.get("/health")
    def health() -> object:
        return jsonify({"ok": True, "extracted_at": _extracted_at()})

    print("Webscraper dev server starting", flush=True)
    print("Webscraper dev server ready", flush=True)
    app.run(host=host, port=port, debug=reload, use_reloader=reload)


def _run_fallback(host: str, port: int) -> None:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import json

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"ok": True, "extracted_at": _extracted_at()}).encode(
                "utf-8"
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer((host, port), Handler)
    print("Webscraper dev server starting", flush=True)
    print("Webscraper dev server ready", flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Webscraper dev server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    try:
        _run_fastapi(args.host, args.port, args.reload)
        return
    except ModuleNotFoundError:
        pass

    try:
        _run_flask(args.host, args.port, args.reload)
        return
    except ModuleNotFoundError:
        pass

    _run_fallback(args.host, args.port)


if __name__ == "__main__":
    main()
