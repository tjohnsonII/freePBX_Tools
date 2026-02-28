from pathlib import Path

from webscraper_manager import cli
from webscraper_manager.cli import AppState, EXIT_OK, _load_webscraper_pids, _save_webscraper_pids


def test_save_webscraper_pids_creates_runtime_dir(tmp_path: Path) -> None:
    root = tmp_path
    payload = {"api": {"pid": 1234}}

    _save_webscraper_pids(root, payload)

    pids_path = root / "webscraper" / "var" / "runtime" / "pids.json"
    assert pids_path.is_file()
    assert pids_path.read_text(encoding="utf-8").strip().startswith("{")


def test_load_webscraper_pids_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    root = tmp_path

    loaded = _load_webscraper_pids(root)

    assert loaded == {}


def test_start_webscraper_stack_skips_ui_when_port_3004_in_use(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    py = root / "python"
    py.write_text("", encoding="utf-8")

    launched: list[list[str]] = []

    class _Proc:
        def __init__(self, cmd):
            self.pid = 100 + len(launched)
            launched.append(cmd)

    monkeypatch.setattr(cli, "find_repo_root", lambda: root)
    monkeypatch.setattr(cli, "run_doctor", lambda *args, **kwargs: (cli.EXIT_OK, []))
    monkeypatch.setattr(cli, "get_runtime_python", lambda *args, **kwargs: py)
    monkeypatch.setattr(cli, "resolve_npm_cmd", lambda: "npm")
    monkeypatch.setattr(cli, "_wait_for_health", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "_is_pid_alive", lambda pid: pid > 0)
    monkeypatch.setattr(cli, "_is_port_open", lambda host, port: port == 3004)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda cmd, **kwargs: _Proc(cmd))

    rc = cli._start_webscraper_stack(AppState(quiet=True), console=None, detach=True)

    assert rc == EXIT_OK
    flattened = [" ".join(cmd) for cmd in launched]
    assert any("uvicorn" in cmd for cmd in flattened)
    assert any("--mode incremental" in cmd for cmd in flattened)
    assert not any("dev:ui" in cmd for cmd in flattened)


def test_start_webscraper_stack_ui_exit_non_strict_does_not_stop_api_worker(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path
    py = root / "python"
    py.write_text("", encoding="utf-8")

    class _Proc:
        def __init__(self, pid: int):
            self.pid = pid

    proc_map = {
        "api": _Proc(101),
        "ui": _Proc(102),
        "worker": _Proc(103),
    }

    alive_calls = {101: 0, 102: 0, 103: 0}

    def _fake_is_pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        alive_calls[pid] = alive_calls.get(pid, 0) + 1
        if pid == 102 and alive_calls[pid] >= 1:
            return False
        return True

    def _fake_popen(cmd, **kwargs):
        cmd_str = " ".join(cmd)
        if "uvicorn" in cmd_str:
            return proc_map["api"]
        if "dev:ui" in cmd_str:
            return proc_map["ui"]
        return proc_map["worker"]

    sleep_calls = {"count": 0}

    def _fake_sleep(seconds: float) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] > 1:
            raise KeyboardInterrupt

    shutdown_reasons: list[str] = []

    def _fake_shutdown(root_path, pids, reason: str):
        shutdown_reasons.append(reason)
        return []

    monkeypatch.setattr(cli, "find_repo_root", lambda: root)
    monkeypatch.setattr(cli, "run_doctor", lambda *args, **kwargs: (cli.EXIT_OK, []))
    monkeypatch.setattr(cli, "get_runtime_python", lambda *args, **kwargs: py)
    monkeypatch.setattr(cli, "resolve_npm_cmd", lambda: "npm")
    monkeypatch.setattr(cli, "_wait_for_health", lambda *args, **kwargs: True)
    monkeypatch.setattr(cli, "_is_port_open", lambda host, port: False)
    monkeypatch.setattr(cli, "_is_pid_alive", _fake_is_pid_alive)
    monkeypatch.setattr(cli.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(cli.time, "sleep", _fake_sleep)
    monkeypatch.setattr(cli, "_shutdown_webscraper_children", _fake_shutdown)

    rc = cli._start_webscraper_stack(AppState(quiet=True), console=None, detach=False)

    assert rc == EXIT_OK
    assert shutdown_reasons == ["ctrl-c"]
