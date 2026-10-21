from __future__ import annotations

from pathlib import Path

from conftest import action
from pytest_httpserver import HTTPServer


def test_bot_fragment_keeps_pr_without_bot_credit(
    repository: Path,
    tmp_path: Path,
    action_scripts: Path,
    github_api: tuple[HTTPServer, dict[str, str]],
) -> None:
    server, environment = github_api
    server.expect_request("/api/v3/repos/tox-dev/devpi-process/pulls/288").respond_with_json(
        {"user": {"login": "dependabot[bot]", "type": "Bot"}}
    )

    result = action(repository, tmp_path, action_scripts, "validate-bot-credits", version="0.2.0", **environment)

    assert result.returncode == 0, result.stderr
    notes = (tmp_path / "bot-notes.md").read_text()
    assert "[#288](https://github.com/tox-dev/devpi-process/pull/288)" in notes
    assert "@dependabot" not in notes
