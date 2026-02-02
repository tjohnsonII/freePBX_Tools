from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from selenium.webdriver.remote.webdriver import WebDriver


class AuthMode(str, Enum):
    PROFILE = "PROFILE"
    PROGRAMMATIC = "PROGRAMMATIC"
    MANUAL = "MANUAL"
    FAIL = "FAIL"


@dataclass
class AuthContext:
    base_url: str
    preferred_browser: str = "edge"
    profile_dir: Optional[str] = None
    profile_fallback_dirs: List[str] = field(default_factory=list)
    cookie_files: List[str] = field(default_factory=list)
    username: Optional[str] = None
    password: Optional[str] = None
    user_agent: Optional[str] = None
    headless: bool = True
    timeout_sec: int = 30
    auth_check_url: Optional[str] = None
    login_markers: List[str] = field(default_factory=list)
    logged_in_markers: List[str] = field(default_factory=list)
    login_form_selectors: List[str] = field(default_factory=list)
    logged_in_selectors: List[str] = field(default_factory=list)


@dataclass
class AuthAttempt:
    mode: AuthMode
    ok: bool
    reason: str


@dataclass
class AuthResult:
    mode: AuthMode
    ok: bool
    reason: str
    driver: Optional[WebDriver]
    need_user_input: Optional[Dict[str, object]]
    attempts: List[AuthAttempt] = field(default_factory=list)


@dataclass
class StrategyOutcome:
    ok: bool
    reason: str
    driver: Optional[WebDriver]
