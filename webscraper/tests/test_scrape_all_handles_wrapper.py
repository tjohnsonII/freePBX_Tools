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


def test_wrapper_timeout_writes_logs_and_continues(monkeypatch, tmp_path):
    module = load_module()

    out_dir = tmp_path / "out"
    db_path = tmp_path / "tickets.sqlite"
    argv = [
        "scrape_all_handles.py",
        "--handles",
        "KPM WS7",
        "--batch-size",
        "1",
        "--db",
        str(db_path),
        "--out",
        str(out_dir),
        "--timeout-seconds",
        "5",
    ]

    calls = {"count": 0}

    def fake_run(cmd, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=5, output="timed out stdout", stderr="timed out stderr")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    def fake_process_batch_output(_db, _run_id, _batch_out, batch_handles):
        if batch_handles == ["KPM"]:
            return set(), {"KPM"}
        return {"WS7"}, set()

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(module, "init_db", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "start_run", lambda *_args, **_kwargs: "run-1")
    monkeypatch.setattr(module, "finish_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "process_batch_output", fake_process_batch_output)
    monkeypatch.setattr(module, "upsert_handle", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    exit_code = module.main()

    assert calls["count"] == 2
    assert exit_code == 2

    child_stdout = next(out_dir.glob("*/batch_001/child_stdout.txt"))
    child_stderr = next(out_dir.glob("*/batch_001/child_stderr.txt"))
    assert child_stdout.read_text(encoding="utf-8") == "timed out stdout"
    assert child_stderr.read_text(encoding="utf-8") == "timed out stderr"
