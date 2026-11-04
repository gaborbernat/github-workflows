import json
from pathlib import Path
from typing import Final

import pytest
from conftest import WORKFLOWS, JsonObject, load_yaml, mapping, run_workflow_step, steps, text

_GUARD: Final[str] = "🚫 Refuse untrusted caller event"
_WRITERS: Final[tuple[tuple[str, str], ...]] = (
    ("open-maintenance-pr.yaml", "open"),
    ("prepare-release-creator.yaml", "push"),
    ("prepare-towncrier-release.yaml", "push"),
    ("github-release.yaml", "github-release"),
    ("publish-pre-commit-mirror.yaml", "mirror"),
    ("latex-to-pages.yaml", "deploy"),
)
_REFUSED: Final[tuple[str, ...]] = ("pull_request", "pull_request_target", "workflow_run", "issue_comment", "merge_group")
_ALLOWED: Final[tuple[str, ...]] = ("push", "schedule", "workflow_dispatch", "release")


def _holds_write_token(job: JsonObject) -> bool:
    permissions = mapping(job.get("permissions", {}))
    return any(permissions.get(scope) == "write" for scope in ("contents", "pull-requests")) or (
        "secrets.RELEASE_APP_PRIVATE_KEY" in json.dumps(job)
    )


def _writer_jobs() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in WORKFLOWS.glob("*.yaml"):
        document = load_yaml(path)
        if "workflow_call" not in mapping(document["on"]):
            continue
        for name, job in mapping(document["jobs"]).items():
            if "uses" not in mapping(job) and _holds_write_token(mapping(job)):
                found.add((path.name, name))
    return found


def test_writers_are_the_guarded_jobs() -> None:
    assert _writer_jobs() == set(_WRITERS)


@pytest.mark.parametrize(("workflow", "job"), _WRITERS)
def test_guard_is_the_first_step(workflow: str, job: str) -> None:
    first = steps(load_yaml(WORKFLOWS / workflow), job)[0]
    assert first["name"] == _GUARD
    assert "if" not in first
    assert first["env"] == {"EVENT_NAME": "${{ github.event_name }}"}


@pytest.mark.parametrize(("workflow", "job"), _WRITERS)
@pytest.mark.parametrize("event", _REFUSED)
def test_refused_event_fails_with_error(workflow: str, job: str, event: str, tmp_path: Path) -> None:
    result, _ = run_workflow_step(
        workflow, job, _GUARD, cwd=tmp_path, runner_temp=tmp_path, values={}, env={"EVENT_NAME": event}
    )
    assert result.returncode != 0
    assert f"::error::writer job refuses {event} callers" in result.stdout


@pytest.mark.parametrize(("workflow", "job"), _WRITERS)
@pytest.mark.parametrize("event", _ALLOWED)
def test_allowed_event_passes(workflow: str, job: str, event: str, tmp_path: Path) -> None:
    result, _ = run_workflow_step(
        workflow, job, _GUARD, cwd=tmp_path, runner_temp=tmp_path, values={}, env={"EVENT_NAME": event}
    )
    assert result.returncode == 0
    assert "::error::" not in result.stdout
