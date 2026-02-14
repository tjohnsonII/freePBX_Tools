import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from webscraper.auth import AuthContext, AuthMode, authenticate
from webscraper.auth.healthcheck import is_authenticated
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

    def test_auth_healthcheck_writes_diagnostics_bundle_on_failure(self) -> None:
        class _FailingAuthDriver:
            current_url = "https://secure.example.com/login"
            title = "Sign In"
            page_source = "<html><body>Please sign in</body></html>"

            def get(self, _url: str) -> None:
                return None

            def find_elements(self, _by: str, selector: str):
                if selector == "input[type='password']":
                    return [object()]
                return []

            def find_element(self, _by: str, _selector: str):
                class _Body:
                    text = "Please sign in to continue"

                return _Body()

            def get_cookies(self):
                return [{"name": "csrftoken", "value": "hidden"}]

            def save_screenshot(self, path: str) -> bool:
                Path(path).write_bytes(b"png")
                return True

        with tempfile.TemporaryDirectory() as td:
            ctx = AuthContext(base_url="https://secure.example.com", auth_check_url=None, output_dir=td)
            ok, reason = is_authenticated(_FailingAuthDriver(), ctx)
            self.assertFalse(ok)
            self.assertEqual(reason, "login_url_detected")

            report = Path(td) / "auth_failure_diagnostics.json"
            html = Path(td) / "auth_failure_page.html"
            screenshot = Path(td) / "auth_failure_screenshot.png"
            self.assertTrue(report.exists())
            self.assertTrue(html.exists())
            self.assertTrue(screenshot.exists())

            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(data["final_url"], "https://secure.example.com/login")
            self.assertEqual(data["cookie_count"], 1)
            self.assertEqual(data["cookie_names"], ["csrftoken"])

    def test_auth_healthcheck_heuristics_url_and_selector(self) -> None:
        class _UrlAuthedDriver:
            current_url = "https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"

            def get(self, _url: str) -> None:
                return None

            def find_elements(self, _by: str, _selector: str):
                return []

        class _SelectorAuthedDriver:
            current_url = "https://secure.example.com/dashboard"
            page_source = "<html><body>Dashboard</body></html>"

            def get(self, _url: str) -> None:
                return None

            def find_elements(self, _by: str, selector: str):
                if selector == "#search_results":
                    return [object()]
                return []

            def get_cookies(self):
                return []

        with tempfile.TemporaryDirectory() as td:
            ctx = AuthContext(base_url="https://secure.example.com", auth_check_url=None, output_dir=td)
            ok, reason = is_authenticated(_UrlAuthedDriver(), ctx)
            self.assertTrue(ok)
            self.assertEqual(reason, "authenticated_url_detected")

            ok2, reason2 = is_authenticated(_SelectorAuthedDriver(), ctx)
            self.assertTrue(ok2)
            self.assertEqual(reason2, "expected_logged_in_elements_present")


if __name__ == "__main__":
    unittest.main()
