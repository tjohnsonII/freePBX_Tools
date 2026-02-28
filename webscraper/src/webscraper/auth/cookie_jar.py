from __future__ import annotations

import http.cookiejar
import logging

LOGGER = logging.getLogger(__name__)


class CookieJarExtractionError(RuntimeError):
    """Raised when browser cookies cannot be extracted/decrypted."""


def get_cookiejar(domain: str = "secure.123.net", browser: str = "chrome") -> http.cookiejar.CookieJar:
    """Extract cookies from the selected browser profile via browser_cookie3."""
    try:
        import browser_cookie3
    except Exception as exc:  # pragma: no cover - import guard
        raise CookieJarExtractionError(
            "browser_cookie3 is not installed; install it to enable requests-based auth fallback"
        ) from exc

    browser_name = (browser or "chrome").strip().lower()
    try:
        if browser_name == "chrome":
            jar = browser_cookie3.chrome(domain_name=domain)
        elif browser_name == "edge":
            jar = browser_cookie3.edge(domain_name=domain)
        else:
            raise CookieJarExtractionError(f"Unsupported browser '{browser}'. Expected 'chrome' or 'edge'.")
    except Exception as exc:
        raise CookieJarExtractionError(
            f"Unable to read/decrypt {browser_name} cookies for domain '{domain}'. "
            "Ensure browser is installed, profile is accessible, and OS keyring permissions are available."
        ) from exc

    cookie_names = sorted({cookie.name for cookie in jar})
    LOGGER.info("Extracted cookie names via browser_cookie3: %s", cookie_names)
    return jar
