from __future__ import annotations

from typing import Any


def switch_to_target_tab(driver: Any, target_url: str, url_contains: str | None = None) -> bool:
    if not driver:
        return False
    try:
        original = driver.current_window_handle
    except Exception:
        original = None
    for handle in driver.window_handles:
        try:
            driver.switch_to.window(handle)
            current = driver.current_url or ""
            if current == target_url or (url_contains and url_contains in current):
                return True
        except Exception:
            continue
    if original:
        try:
            driver.switch_to.window(original)
        except Exception:
            pass
    return False
