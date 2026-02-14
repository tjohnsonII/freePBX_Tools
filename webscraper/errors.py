"""Custom exceptions for the webscraper package.

Single source of truth for scraper-specific exception types.
"""

from __future__ import annotations

from typing import Optional, Sequence


class EdgeStartupError(RuntimeError):
    """Raised when Edge WebDriver cannot be started/attached."""

    def __init__(
        self,
        message: str,
        edge_args: Sequence[str] | None = None,
        profile_dir: str | None = None,
        edge_binary: Optional[str] = None,
    ) -> None:
        details = [message]
        if edge_args is not None:
            details.append(f"Edge args: {list(edge_args)}")
        if profile_dir is not None:
            details.append(f"Profile dir: {profile_dir}")
        if edge_binary is not None:
            details.append(f"Edge binary: {edge_binary}")
        super().__init__("\n".join(details))
        self.edge_args = list(edge_args or [])
        self.profile_dir = profile_dir
        self.edge_binary = edge_binary


__all__ = ["EdgeStartupError"]
