from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml
from conftest import run
from pytest_httpserver import HTTPServer


def test_fixture_creates_rst_fragments_without_directory(
    repository: Path, tmp_path: Path, github_api: tuple[HTTPServer, dict[str, str]]
) -> None:
    base = run(repository, "git", "rev-list", "--max-parents=0", "HEAD").stdout.strip()
    changelog = repository / "docs/changelog.rst"
    changelog.parent.mkdir()
    changelog.write_text("Changelog\n=========\n", encoding="utf-8")
    run(repository, "git", "add", ".")
    run(repository, "git", "commit", "-m", "Add reStructuredText changelog (#2)")
    head = run(repository, "git", "rev-parse", "HEAD").stdout.strip()
    server, environment = github_api
    server.expect_request("/api/v3/repos/tox-dev/fixture/pulls/2").respond_with_json(
        {"user": {"login": "maintainer", "type": "User"}}
    )
    workflow = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / ".github/workflows/validate-python-release.yaml").read_text()
    )
    fixture = next(step for step in workflow["jobs"]["validate"]["steps"] if step.get("id") == "fixture")
    output = tmp_path / "output"
    result = subprocess.run(
        ["bash", "-c", fixture["run"]],
        cwd=repository,
        env=os.environ
        | environment
        | {
            "BASE_SHA": base,
            "HEAD_SHA": head,
            "PR_NUMBER": "2",
            "FRAGMENTS": "docs/changelog",
            "CHANGELOG": "docs/changelog.rst",
            "GITHUB_SHA": head,
            "GITHUB_REPOSITORY": "tox-dev/fixture",
            "GITHUB_OUTPUT": str(output),
            "RUNNER_TEMP": str(tmp_path),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in (repository / "docs/changelog").iterdir()) == [
        "+validation-2.bugfix.rst",
        "2.bugfix.rst",
    ]
    assert "extension=rst" in output.read_text()
