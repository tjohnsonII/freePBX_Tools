from pathlib import Path

from webscraper_manager import cli
from webscraper_manager.cli import AppState


def test_preflight_kills_matching_repo_pid(monkeypatch, tmp_path: Path) -> None:
    killed: list[int] = []

    monkeypatch.setattr(cli, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "find_listening_pids", lambda port: {111} if port == 3004 and not killed else set())
    monkeypatch.setattr(cli, "describe_process", lambda pid: {"name": "node.exe", "cmdline_text": f"{tmp_path}\\webscraper\\ticket-ui"})
    monkeypatch.setattr(cli, "should_kill", lambda pid, scope, repo_root: True)
    monkeypatch.setattr(cli, "kill_process_tree", lambda pid: killed.append(pid))

    ok, err = cli._preflight_kill_ports(AppState(quiet=True), None, [3004], kill_ports=True, kill_scope="repo")

    assert ok is True
    assert err is None
    assert killed == [111]


def test_preflight_rejects_nonmatching_pid(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "find_listening_pids", lambda port: {999} if port == 8787 else set())
    monkeypatch.setattr(cli, "describe_process", lambda pid: {"name": "postgres.exe", "cmdline_text": "C:/other/app"})
    monkeypatch.setattr(cli, "should_kill", lambda pid, scope, repo_root: False)

    ok, err = cli._preflight_kill_ports(AppState(quiet=True), None, [8787], kill_ports=True, kill_scope="repo")

    assert ok is False
    assert "Refusing to kill PID 999" in str(err)
