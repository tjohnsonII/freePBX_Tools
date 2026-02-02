from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AuthMode(str, Enum):
    PROFILE = "PROFILE"
    PROGRAMMATIC = "PROGRAMMATIC"
    MANUAL = "MANUAL"
    FAIL = "FAIL"


@dataclass
class AuthContext:
    base_url: str
    auth_check_url: Optional[str]
    preferred_browser: str = "edge"
    profile_dirs: List[str] = field(default_factory=list)
    profile_name: str = "Default"
    cookie_files: List[str] = field(default_factory=list)
    username: Optional[str] = None
    password: Optional[str] = None
    headless: bool = True
    timeout_sec: int = 30
    output_dir: str = ""
    edge_binary: Optional[str] = None
    edgedriver_path: Optional[str] = None


@dataclass
class AuthAttempt:
    mode: AuthMode
    ok: bool
    reason: str


@dataclass
class AuthResult:
    ok: bool
    mode: AuthMode
    reason: str
    attempts: List[AuthAttempt]
    driver: Optional[Any]
    need_user_input: Optional[Dict[str, object]]
