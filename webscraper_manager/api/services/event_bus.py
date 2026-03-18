from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Event:
    timestamp: str
    level: str
    category: str
    event_type: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "category": self.category,
            "event_type": self.event_type,
            "message": self.message,
            "details": self.details,
        }


class EventBus:
    def __init__(self, max_events: int = 500, jsonl_path: Path | None = None) -> None:
        self._events: deque[Event] = deque(maxlen=max_events)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()
        self._jsonl_path = jsonl_path
        if self._jsonl_path:
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    async def emit(self, level: str, category: str, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
        event = Event(
            timestamp=datetime.now(UTC).isoformat(),
            level=level,
            category=category,
            event_type=event_type,
            message=message,
            details=details or {},
        )
        async with self._lock:
            self._events.append(event)
            if self._jsonl_path:
                self._jsonl_path.write_text("", encoding="utf-8") if not self._jsonl_path.exists() else None
                with self._jsonl_path.open("a", encoding="utf-8") as fp:
                    fp.write(json.dumps(event.to_dict()) + "\n")
            for queue in list(self._subscribers):
                if queue.full():
                    _ = queue.get_nowait()
                queue.put_nowait(event.to_dict())

    async def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        async with self._lock:
            return [e.to_dict() for e in list(self._events)[-limit:]]

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)
