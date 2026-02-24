"""Attach argument parsing helpers for webscraper CLI."""

from __future__ import annotations

from typing import Optional, Tuple


def _parse_port(raw_port: str, *, source_flag: str) -> int:
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{source_flag} expected an integer port, got '{raw_port}'."
        ) from exc
    if port <= 0 or port > 65535:
        raise ValueError(f"{source_flag} port must be between 1 and 65535, got {port}.")
    return port


def normalize_attach_args(
    attach: Optional[str],
    attach_host: str,
    attach_debugger: Optional[str],
) -> Tuple[Optional[int], str]:
    """Normalize attach arguments into ``(attach_port, attach_host)``.

    ``--attach`` remains an integer port by contract, but to make CLI use more
    forgiving we also accept ``host:port`` and split it automatically.
    """

    resolved_host = (attach_host or "127.0.0.1").strip() or "127.0.0.1"
    resolved_attach: Optional[int] = None

    if attach is not None:
        raw_attach = str(attach).strip()
        if not raw_attach:
            raise ValueError("--attach requires a port value.")
        if ":" in raw_attach:
            host_part, port_part = raw_attach.rsplit(":", 1)
            resolved_host = host_part.strip() or resolved_host
            resolved_attach = _parse_port(port_part.strip(), source_flag="--attach")
        else:
            resolved_attach = _parse_port(raw_attach, source_flag="--attach")

    if attach_debugger:
        raw_debugger = str(attach_debugger).strip()
        if ":" not in raw_debugger:
            raise ValueError(
                "--attach-debugger must be host:port (example 127.0.0.1:9222)."
            )
        host_part, port_part = raw_debugger.rsplit(":", 1)
        resolved_host = host_part.strip() or resolved_host
        resolved_attach = _parse_port(port_part.strip(), source_flag="--attach-debugger")

    return resolved_attach, resolved_host


__all__ = ["normalize_attach_args"]
