from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import auth, db, diagnostics, health, logs, manager, orders, services, system, tickets, webscraper
from .services.auth_inspector import AuthInspector
from .services.command_runner import CommandRunner
from .services.db_inspector import DBInspector
from .services.event_bus import EventBus
from .services.state_store import StateStore
from .services.system_inspector import SystemInspector
from .services.ticket_pipeline import TicketPipelineService


def create_app() -> FastAPI:
    repo_root = Path(__file__).resolve().parents[2]
    state = StateStore(repo_root=repo_root)
    event_bus = EventBus(jsonl_path=repo_root / ".webscraper_manager" / "events.jsonl")

    app = FastAPI(title="Webscraper Hosted Dashboard API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.state_store = state
    app.state.event_bus = event_bus
    app.state.command_runner = CommandRunner(repo_root)
    app.state.auth_inspector = AuthInspector(state, event_bus)
    app.state.ticket_pipeline = TicketPipelineService(state, event_bus)
    app.state.db_inspector = DBInspector(repo_root / "webscraper" / "var" / "db" / "tickets.sqlite")
    app.state.system_inspector = SystemInspector(repo_root)

    app.include_router(health.router)
    app.include_router(manager.router)
    app.include_router(auth.router)
    app.include_router(tickets.router)
    app.include_router(db.router)
    app.include_router(system.router)
    app.include_router(logs.router)
    app.include_router(diagnostics.router)
    app.include_router(webscraper.router)
    app.include_router(services.router)
    app.include_router(orders.router)
    return app


app = create_app()
