import os
import unittest

from webscraper.auth.orchestrator import _default_cookie_candidates
from webscraper.auth.strategies import manual
from webscraper.auth.types import AuthContext


class AuthAutoModeTests(unittest.TestCase):
    def test_default_cookie_candidates_prioritize_var_auth_path(self) -> None:
        candidates = _default_cookie_candidates("/repo")
        expected = os.path.join("/repo", "webscraper", "var", "auth", "cookies.json")
        self.assertEqual(candidates[0], expected)

    def test_auth_context_defaults_to_chrome(self) -> None:
        ctx = AuthContext(base_url="https://example.com", auth_check_url=None)
        self.assertEqual(ctx.preferred_browser, "chrome")

    def test_wait_mode_and_timeout_env_parsing(self) -> None:
        os.environ["WEBSCRAPER_AUTH_WAIT_MODE"] = "enter"
        os.environ["WEBSCRAPER_AUTH_WAIT_TIMEOUT_SEC"] = "42"
        self.assertEqual(manual._wait_mode(), "enter")
        self.assertEqual(manual._wait_timeout_sec(), 42)

        os.environ["WEBSCRAPER_AUTH_WAIT_MODE"] = "invalid"
        os.environ["WEBSCRAPER_AUTH_WAIT_TIMEOUT_SEC"] = "bad"
        self.assertEqual(manual._wait_mode(), "auto")
        self.assertEqual(manual._wait_timeout_sec(), 180)


if __name__ == "__main__":
    unittest.main()
