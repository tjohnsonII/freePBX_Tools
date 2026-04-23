from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TicketUrlEntry:
    ticket_id: Optional[str]
    url: str
    label: str = ""
    source: str = "unknown"


@dataclass
class TicketDetails:
    ticket_id: Optional[str]
    fields: Dict[str, Any] = field(default_factory=dict)
