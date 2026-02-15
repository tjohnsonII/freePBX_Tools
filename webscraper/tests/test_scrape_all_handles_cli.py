import importlib.util
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "scrape_all_handles.py"


def load_module():
    spec = importlib.util.spec_from_file_location("scrape_all_handles", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ScrapeAllHandlesCliTests(unittest.TestCase):
    def _build_args(self, **overrides) -> Namespace:
        defaults = {
            "profile_dir": None,
            "profile_name": None,
            "rate_limit": None,
            "max_tickets": None,
            "auth_profile_only": False,
            "show": False,
            "scrape_ticket_details": False,
            "save_html": False,
            "save_screenshot": False,
            "dump_dom_on_fail": False,
            "resume": False,
            "phase_logs": False,
            "child_extra_args": None,
        }
        defaults.update(overrides)
        return Namespace(**defaults)

    def test_parse_handles_values_splits_comma_and_whitespace(self) -> None:
        module = load_module()
        handles = module.parse_handles_values(["KPM,WS7 EO5", "  AB1 , CD2\tEF3  "])
        self.assertEqual(handles, ["KPM", "WS7", "EO5", "AB1", "CD2", "EF3"])

    def test_resolve_handles_applies_max_handles(self) -> None:
        module = load_module()
        args = Namespace(handles=["KPM,WS7", "EO5"], handles_file=None, max_handles=2)
        self.assertEqual(module.resolve_handles(args), ["KPM", "WS7"])

    def test_main_uses_handles_and_never_spawns_real_scraper(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out"
            db_path = Path(tmpdir) / "tickets.sqlite"
            argv = [
                "scrape_all_handles.py",
                "--handles",
                "KPM,WS7 EO5",
                "--max-handles",
                "2",
                "--batch-size",
                "1",
                "--db",
                str(db_path),
                "--out",
                str(out_dir),
                "--timeout-seconds",
                "5",
            ]

            captured_cmds = []

            def fake_run(cmd, **kwargs):
                captured_cmds.append((cmd, kwargs))
                return module.subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

            with patch.object(sys, "argv", argv), patch.object(module, "init_db"), patch.object(
                module, "start_run", return_value="run-1"
            ), patch.object(module, "finish_run"), patch.object(
                module, "process_batch_output", side_effect=lambda *_args, **_kwargs: ({"KPM", "WS7"}, set())
            ), patch.object(module, "subprocess") as mock_subprocess:
                mock_subprocess.run.side_effect = fake_run
                mock_subprocess.CompletedProcess = __import__("subprocess").CompletedProcess
                mock_subprocess.TimeoutExpired = __import__("subprocess").TimeoutExpired
                mock_subprocess.list2cmdline = __import__("subprocess").list2cmdline
                exit_code = module.main()

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(captured_cmds), 2)
            flattened = [item for cmd, _ in captured_cmds for item in cmd]
            self.assertIn("KPM", flattened)
            self.assertIn("WS7", flattened)
            self.assertNotIn("EO5", flattened)

    def test_build_scraper_cmd_does_not_include_headless(self) -> None:
        module = load_module()
        args = self._build_args()

        cmd = module.build_scraper_cmd(args, ["KPM"], Path("/tmp/out"))

        self.assertNotIn("--headless", cmd)
        self.assertNotIn("--show", cmd)

    def test_build_scraper_cmd_passes_show_flag_when_requested(self) -> None:
        module = load_module()
        args = self._build_args(show=True)

        cmd = module.build_scraper_cmd(args, ["KPM"], Path("/tmp/out"))

        self.assertIn("--show", cmd)
        self.assertNotIn("--headless", cmd)

    def test_build_scraper_cmd_appends_child_extra_args(self) -> None:
        module = load_module()
        extra_args = ["--phase-logs", "--dump-dom-on-fail"]
        args = self._build_args(child_extra_args=extra_args)

        cmd = module.build_scraper_cmd(args, ["KPM"], Path("/tmp/out"))

        self.assertEqual(cmd[-len(extra_args) :], extra_args)


if __name__ == "__main__":
    unittest.main()
