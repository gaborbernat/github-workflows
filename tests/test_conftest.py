from pathlib import Path

import pytest
from conftest import load_yaml, mapping, run, run_workflow_step, steps, text


def test_run_reports_failed_command(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="false failed with exit code 1"):
        run(tmp_path, "false")


def test_run_workflow_step_expands_values_into_declared_env(tmp_path: Path) -> None:
    (tmp_path / "gradle.properties").write_text("pluginVersion=1.2.2\n")
    result, _ = run_workflow_step(
        "jetbrains-plugin-check.yaml",
        "build",
        "🏷️ Set plugin version",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={"inputs.plugin-version": "v1.2.3"},
        env={},
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "gradle.properties").read_text() == "pluginVersion=1.2.3\n"


def test_run_workflow_step_skips_expansion_of_overridden_variables(tmp_path: Path) -> None:
    (tmp_path / "gradle.properties").write_text("pluginVersion=1.2.2\n")
    result, _ = run_workflow_step(
        "jetbrains-plugin-check.yaml",
        "build",
        "🏷️ Set plugin version",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={"PLUGIN_VERSION": "v1.2.3"},
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "gradle.properties").read_text() == "pluginVersion=1.2.3\n"


def test_load_yaml_rejects_a_top_level_sequence(tmp_path: Path) -> None:
    path = tmp_path / "workflow.yaml"
    path.write_text("- one\n")
    with pytest.raises(TypeError, match="is not a YAML mapping"):
        load_yaml(path)


def test_mapping_rejects_a_sequence() -> None:
    with pytest.raises(TypeError, match="expected a mapping"):
        mapping(["one"])


def test_text_rejects_a_sequence() -> None:
    with pytest.raises(TypeError, match="expected text"):
        text(["one"])


def test_steps_rejects_a_job_without_a_step_list(tmp_path: Path) -> None:
    path = tmp_path / "workflow.yaml"
    path.write_text("jobs:\n  build:\n    steps: none\n")
    with pytest.raises(TypeError, match="expected a step list"):
        steps(load_yaml(path), "build")
