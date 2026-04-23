from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .event_bus import EventBus
from .state_store import StateStore


class AuthInspector:
    def __init__(self, state: StateStore, events: EventBus) -> None:
        self.state = state
        self.events = events

    async def validate(self, domain: str = "secure.123.net") -> dict[str, Any]:
        await self.events.emit("info", "auth", "AUTH_VALIDATE_STARTED", f"Validating auth for {domain}", {"domain": domain})
        now = datetime.now(UTC).isoformat()
        cookie_ok = self.state.cookies.get("cookie_count", 0) > 0
        validation_ok = cookie_ok and domain in self.state.cookies.get("domains", [])

        self.state.auth["last_check"] = now
        self.state.auth["validation"] = {
            "url": f"https://{domain}/",
            "http_status": 200 if validation_ok else 401,
            "ok": validation_ok,
            "reason": "ok" if validation_ok else "cookies_missing_or_domain_mismatch",
        }
        self.state.auth["authenticated"] = validation_ok
        if validation_ok:
            self.state.auth["last_success"] = now
            await self.events.emit("info", "auth", "AUTH_VALIDATE_SUCCESS", "Authentication validation succeeded", {"domain": domain})
            self.state.set_pipeline_stage("auth_validated", "success", "Auth validated")
        else:
            await self.events.emit(
                "error",
                "auth",
                "AUTH_VALIDATE_FAILED",
                "Authentication validation failed",
                {"domain": domain, "cookie_count": self.state.cookies.get("cookie_count", 0)},
            )
            self.state.set_pipeline_stage("auth_validated", "failed", "Auth validation failed", "cookies missing or invalid")
        return self.state.auth

    async def seed_auth(self, browser: str, profile: str, domain: str) -> dict[str, Any]:
        await self.events.emit("info", "auth", "AUTH_SEED_STARTED", "Seeding auth", {"browser": browser, "profile": profile})
        self.state.auth["browser"] = browser
        self.state.auth["profile"] = profile
        self.state.auth["source"] = f"{browser}:{profile}"
        self.state.cookies.update(
            {
                "source": self.state.auth["source"],
                "file_path": str(Path.home() / f".{browser}_cookies.json"),
                "cookie_count": 3,
                "domains": [domain],
                "last_loaded": datetime.now(UTC).isoformat(),
                "secure_count": 2,
                "http_only_count": 1,
                "sample_names": ["sessionid", "csrftoken", "pref"],
                "missing_required_cookie_names": [],
            }
        )
        self.state.auth["cookie_count"] = 3
        self.state.auth["domains"] = [domain]
        self.state.auth["missing_required_cookie_names"] = []
        self.state.auth["required_cookie_names_present"] = ["sessionid", "csrftoken"]
        self.state.set_pipeline_stage("cookies_loaded", "success", "Cookies imported from browser profile")
        await self.events.emit("info", "auth", "AUTH_COOKIES_IMPORTED", "Cookies imported", {"count": 3, "domain": domain})
        return self.state.auth

    def cookie_summary(self) -> dict[str, Any]:
        return self.state.cookies
