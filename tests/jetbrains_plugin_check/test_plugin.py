import hashlib
import json
from pathlib import Path
from typing import Final

import pytest
from conftest import (
    WORKFLOWS,
    JsonObject,
    action,
    at,
    load_yaml,
    mapping,
    run_workflow_step,
    steps,
    text,
    workflow_step,
)

_WORKFLOW: Final[str] = "jetbrains-plugin-check.yaml"
_GATE_NEEDS: Final[list[str]] = ["build", "verify", "ui-test"]


@pytest.fixture
def workflow() -> JsonObject:
    return load_yaml(WORKFLOWS / _WORKFLOW)


@pytest.fixture
def distributions(tmp_path: Path) -> Path:
    (tmp_path / "gradle.properties").write_text("pluginVersion=1.2.3\n")
    directory = tmp_path / "build/distributions"
    directory.mkdir(parents=True)
    return directory


def test_build_records_name_and_digest_of_the_one_zip(tmp_path: Path, distributions: Path) -> None:
    (distributions / "Plugin-1.2.3.zip").write_bytes(b"zip bytes")
    result, outputs = run_workflow_step(
        _WORKFLOW,
        "build",
        "⚙️ Record unsigned ZIP digest",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={},
    )
    assert result.returncode == 0, result.stderr
    assert outputs == {"name": "Plugin-1.2.3.zip", "sha256": hashlib.sha256(b"zip bytes").hexdigest()}


@pytest.mark.parametrize(
    ("archives", "found"),
    [
        pytest.param([], 0, id="no-archive"),
        pytest.param(["Plugin-1.2.3.zip", "Other-1.2.3.zip"], 2, id="ambiguous"),
    ],
)
def test_build_rejects_missing_or_ambiguous_zip(
    tmp_path: Path, distributions: Path, archives: list[str], found: int
) -> None:
    for name in archives:
        (distributions / name).write_bytes(b"zip bytes")
    result, _ = run_workflow_step(
        _WORKFLOW,
        "build",
        "⚙️ Record unsigned ZIP digest",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={},
    )
    assert result.returncode != 0
    assert f"expected one plugin ZIP for version 1.2.3, found {found}" in result.stderr


def test_build_ignores_archives_of_other_versions(tmp_path: Path, distributions: Path) -> None:
    (distributions / "Plugin-1.2.2.zip").write_bytes(b"old")
    (distributions / "Plugin-1.2.3.zip").write_bytes(b"new")
    result, outputs = run_workflow_step(
        _WORKFLOW,
        "build",
        "⚙️ Record unsigned ZIP digest",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={},
    )
    assert result.returncode == 0, result.stderr
    assert outputs == {"name": "Plugin-1.2.3.zip", "sha256": hashlib.sha256(b"new").hexdigest()}


def test_plugin_version_input_overrides_committed_version(tmp_path: Path) -> None:
    (tmp_path / "gradle.properties").write_text("pluginVersion=1.2.2\nother=keep\n")
    result, _ = run_workflow_step(
        _WORKFLOW,
        "build",
        "🏷️ Set plugin version",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={"PLUGIN_VERSION": "v1.2.3"},
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "gradle.properties").read_text() == "pluginVersion=1.2.3\nother=keep\n"


def test_plugin_version_rejects_sed_metacharacters(tmp_path: Path) -> None:
    (tmp_path / "gradle.properties").write_text("pluginVersion=1.2.2\n")
    result, _ = run_workflow_step(
        _WORKFLOW,
        "build",
        "🏷️ Set plugin version",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={"PLUGIN_VERSION": "1&2"},
    )
    assert result.returncode != 0


def test_verify_matrix_default_checks_python_only(workflow: JsonObject) -> None:
    assert json.loads(text(at(workflow, "on", "workflow_call", "inputs", "verify-matrix", "default"))) == [
        {"label": "PY", "ide": "PY", "version": ""}
    ]


def test_ui_timeout_default_is_300_seconds(workflow: JsonObject) -> None:
    assert at(workflow, "on", "workflow_call", "inputs", "ui-test-timeout", "default") == "300"


def test_ui_timeout_input_reaches_the_ui_test_step() -> None:
    assert workflow_step(_WORKFLOW, "ui-test", "🧪 Run UI tests")["env"] == {
        "UI_TEST_TIMEOUT": "${{ inputs.ui-test-timeout }}"
    }


def test_ui_test_failure_uploads_reports() -> None:
    upload = workflow_step(_WORKFLOW, "ui-test", "📤 Upload UI test artifacts")
    assert upload["if"] == "${{ failure() }}"
    assert "build/idea-sandbox/**/log/idea.log" in text(mapping(upload["with"])["path"])


@pytest.mark.parametrize(
    ("job", "permissions"),
    [
        pytest.param("build", {"contents": "read"}, id="build"),
        pytest.param("verify", {"contents": "read"}, id="verify"),
        pytest.param("ui-test", {"contents": "read"}, id="ui-test"),
        pytest.param("gate", {}, id="gate"),
    ],
)
def test_job_holds_only_the_permissions_it_needs(workflow: JsonObject, job: str, permissions: JsonObject) -> None:
    assert at(workflow, "jobs", job, "permissions") == permissions


def test_workflow_grants_no_top_level_permissions(workflow: JsonObject) -> None:
    assert workflow["permissions"] == {}


@pytest.mark.parametrize("output", ["archive-sha256", "archive-name", "artifact-id"])
def test_workflow_output_comes_from_build_job(workflow: JsonObject, output: str) -> None:
    assert at(workflow, "on", "workflow_call", "outputs", output, "value") == f"${{{{ jobs.build.outputs.{output} }}}}"


def test_verify_step_passes_matrix_entries_through_env() -> None:
    assert workflow_step(_WORKFLOW, "verify", "🔍 Run verification")["env"] == {
        "IDE": "${{ matrix.ide }}",
        "VERSION": "${{ matrix.version }}",
    }


def test_gate_needs_build_verify_and_ui_test(workflow: JsonObject) -> None:
    assert at(workflow, "jobs", "gate", "needs") == _GATE_NEEDS


def test_gate_delegates_to_required_checks() -> None:
    assert workflow_step(_WORKFLOW, "gate", "🚦 Require all needed jobs to pass") == {
        "name": "🚦 Require all needed jobs to pass",
        "uses": "$/required-checks",
        "with": {"needs": "${{ toJSON(needs) }}"},
    }


@pytest.mark.parametrize(
    ("results", "accepted"),
    [
        pytest.param(("success", "success", "success"), True, id="all-succeeded"),
        pytest.param(("success", "success", "skipped"), False, id="skipped-job"),
        pytest.param(("failure", "success", "success"), False, id="failed-job"),
    ],
)
def test_gate_requires_every_job_to_succeed(
    tmp_path: Path,
    action_scripts: Path,
    results: tuple[str, str, str],
    accepted: bool,
) -> None:
    needs = {name: {"result": result} for name, result in zip(_GATE_NEEDS, results, strict=True)}
    result = action(tmp_path, tmp_path, action_scripts, "required-checks", version="", NEEDS=json.dumps(needs))
    assert (result.returncode == 0) is accepted, result.stderr


@pytest.mark.parametrize(
    "forbidden",
    [
        pytest.param("${{", id="expressions"),
        pytest.param("|| true", id="masked-failures"),
    ],
)
def test_run_blocks_avoid_forbidden_constructs(workflow: JsonObject, forbidden: str) -> None:
    offenders = [
        item.get("name")
        for job in mapping(at(workflow, "jobs"))
        for item in steps(workflow, job)
        if forbidden in text(item.get("run", ""))
    ]
    assert offenders == []
