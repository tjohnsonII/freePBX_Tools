import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "scrape_all_handles.py"


def load_module():
    spec = importlib.util.spec_from_file_location("scrape_all_handles", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_wrapper_and_get_cmd(monkeypatch, tmp_path: Path, extra_argv: list[str]) -> list[str]:
    module = load_module()

    out_dir = tmp_path / "out"
    db_path = tmp_path / "tickets.sqlite"
    captured_cmds: list[list[str]] = []

    argv = [
        "scrape_all_handles.py",
        "--handles",
        "KPM",
        "--batch-size",
        "1",
        "--db",
        str(db_path),
        "--out",
        str(out_dir),
        "--timeout-seconds",
        "5",
        *extra_argv,
    ]

    def fake_run(cmd, **_kwargs):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(module, "init_db", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "start_run", lambda *_args, **_kwargs: "run-1")
    monkeypatch.setattr(module, "finish_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "process_batch_output", lambda *_args, **_kwargs: ({"KPM"}, set()))
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    exit_code = module.main()
    assert exit_code == 0
    assert len(captured_cmds) == 1
    return captured_cmds[0]


def test_wrapper_never_adds_headless_and_omits_show_by_default(monkeypatch, tmp_path):
    cmd = run_wrapper_and_get_cmd(monkeypatch, tmp_path, extra_argv=[])
    assert "--headless" not in cmd
    assert "--show" not in cmd


def test_wrapper_adds_show_only_when_requested(monkeypatch, tmp_path):
    cmd = run_wrapper_and_get_cmd(monkeypatch, tmp_path, extra_argv=["--show"])
    assert "--headless" not in cmd
    assert "--show" in cmd


def test_wrapper_appends_child_extra_args_verbatim(monkeypatch, tmp_path):
    extra_args = ["--phase-logs", "--dump-dom-on-fail", "--max-tickets", "7"]
    cmd = run_wrapper_and_get_cmd(
        monkeypatch,
        tmp_path,
        extra_argv=["--child-extra-args", *extra_args],
    )

    assert "--headless" not in cmd
    assert "--child-extra-args" not in cmd
    assert cmd[-len(extra_args) :] == extra_args
