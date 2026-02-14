import subprocess
import sys
import unittest


class CliHelpSmokeTests(unittest.TestCase):
    def test_cli_module_help_exits_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "webscraper.cli.main", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("Selenium ticket scraper", proc.stdout)


if __name__ == "__main__":
    unittest.main()
