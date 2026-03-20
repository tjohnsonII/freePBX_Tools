from pathlib import Path
import unittest


class NoDirectLoginCgiRefsTests(unittest.TestCase):
    def test_no_direct_login_cgi_references_in_auth_paths(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        login_token = "login" + ".cgi"
        paths = [
            repo_root / "webscraper" / "src" / "webscraper" / "auth" / "healthcheck.py",
            repo_root / "webscraper" / "src" / "webscraper" / "auth" / "strategies" / "manual.py",
            repo_root / "webscraper" / "src" / "webscraper" / "ticket_api" / "app.py",
        ]
        paths = [p for p in paths if p.exists()]

        offenders: list[str] = []
        for path in paths:
            content = path.read_text(encoding="utf-8")
            if login_token in content:
                offenders.append(str(path.relative_to(repo_root)))

        self.assertEqual([], offenders, f"Found forbidden direct {login_token} references: {offenders}")


if __name__ == "__main__":
    unittest.main()
