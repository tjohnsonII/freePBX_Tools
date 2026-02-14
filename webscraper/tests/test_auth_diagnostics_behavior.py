import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webscraper.auth import AuthContext, AuthMode, authenticate
from webscraper.auth.strategies import profile
from webscraper import ultimate_scraper_legacy as legacy


class _DummyDriver:
    def __init__(self) -> None:
        self.calls = []

    def get(self, url: str) -> None:
        self.calls.append(("get", url))

    def quit(self) -> None:
        self.calls.append(("quit", None))


class AuthDiagnosticsBehaviorTests(unittest.TestCase):
    def test_missing_credentials_only_for_programmatic(self) -> None:
        ctx = AuthContext(
            base_url="https://example.com",
            auth_check_url="https://example.com",
            profile_dirs=["/does/not/exist"],
            profile_name="Default",
            output_dir=".",
        )

        profile_result = authenticate(ctx, modes=[AuthMode.PROFILE])
        self.assertNotIn("missing_credentials", profile_result.reason)

        programmatic_result = authenticate(ctx, modes=[AuthMode.PROGRAMMATIC])
        self.assertIn("missing_credentials", programmatic_result.reason)

    def test_profile_driver_failure_writes_traceback_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ctx = AuthContext(
                base_url="https://example.com",
                auth_check_url="https://example.com",
                profile_dirs=[td],
                profile_name="Default",
                output_dir=td,
            )

            with patch("webscraper.browser.edge_driver.create_edge_driver", side_effect=RuntimeError("boom")):
                ok, _driver, reason = profile.try_profile(ctx)

            self.assertFalse(ok)
            self.assertTrue(reason.startswith("driver_start_failed:"))
            trace_path = Path(td) / "debug" / "driver_start_failed.txt"
            self.assertTrue(trace_path.exists())
            self.assertIn("RuntimeError: boom", trace_path.read_text(encoding="utf-8"))

    def test_edge_smoke_test_bypasses_auth_orchestration(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with patch("webscraper.ultimate_scraper_legacy.create_edge_driver", return_value=(_DummyDriver(), True, False, td)):
                with patch("webscraper.ultimate_scraper_legacy._resolve_auth_symbols", side_effect=AssertionError("auth should not run")):
                    legacy.selenium_scrape_tickets(
                        url="https://example.com",
                        output_dir=td,
                        handles=["EXAMPLE"],
                        auth_orchestration=True,
                        edge_smoke_test=True,
                    )


if __name__ == "__main__":
    unittest.main()
