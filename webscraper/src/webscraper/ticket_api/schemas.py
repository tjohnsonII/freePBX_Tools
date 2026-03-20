from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel


class StartScrapeRequest(BaseModel):
    mode: Literal["all", "one"] = "all"
    handle: str | None = None
    rescrape: bool = False
    refresh_handles: bool = True


class BatchScrapeRequest(BaseModel):
    handles: list[str]
    mode: Literal["latest", "full"] = "latest"
    limit: int = 50


class ScrapeHandlesRequest(BaseModel):
    handles: list[str]
    mode: Literal["refresh_handles", "normal"] = "normal"
    options: dict[str, Any] | None = None


class ValidateAuthRequest(BaseModel):
    targets: list[str] = ["secure.123.net", "123.net", "noc-tickets.123.net"]
    timeoutSeconds: int = 10


class BrowserImportRequest(BaseModel):
    browser: str = "chrome"
    profile: str = "Default"
    domain: str = "secure.123.net"


class BrowserDetectRequest(BaseModel):
    browser: str | None = None
    cdp_port: int | None = None


class ImportTextRequest(BaseModel):
    text: str | None = None
    cookies: list[dict[str, Any]] | None = None
    cookie: str | None = None


class LaunchBrowserRequest(BaseModel):
    url: str | None = None
    profile: str = "ticketing"
    new_window: bool = True


class LaunchSeededRequest(BaseModel):
    target_url: str = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
    chrome_profile_dir: str | None = None
    seed_domains: list[str] = ["secure.123.net", "123.net"]


class ImportFromProfileRequest(BaseModel):
    browser: str | None = None
    domain: str | None = None
    profile: str = ""
    temp_profile_dir: str
    seed_domains: list[str] = ["secure.123.net", "123.net"]


class AuthSeedRequest(BaseModel):
    mode: Literal["auto", "disk", "cdp"] = "auto"
    chrome_profile_dir: str | None = None
    chrome_user_data_dir: str | None = None
    seed_domains: list[str] = ["secure.123.net", "123.net"]
    cdp_port: int = 9222


class HybridAuthRequest(BaseModel):
    target_url: str = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"
    profile: str | None = "ticketing"
    timeoutSeconds: int = 300


class LaunchDebugChromeRequest(BaseModel):
    cdp_port: int = 9222
    profile_name: str = "Default"


@dataclass
class QueueJob:
    job_id: str
    run_id: str
    mode: str
    handle: str | None
    rescrape: bool
    refresh_handles: bool
    scrape_mode: str = "incremental"
    ticket_limit: int = 50
    handles: list[str] | None = None


@dataclass
class AuthState:
    authenticated: bool = False
    mode: str = "unknown"
    detail: str = "Auth status not checked yet"
    last_check_ts: str | None = None
    last_error: str | None = None
    profile_dir: str | None = None
    suggestion: str = "Open Chrome using profile dir and login once"
