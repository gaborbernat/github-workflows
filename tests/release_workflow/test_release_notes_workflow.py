from pathlib import Path
from typing import Final

import pytest
from conftest import WORKFLOWS, JsonObject, at, load_yaml, mapping, step, steps, text

ROOT: Final = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def workflow() -> JsonObject:
    return load_yaml(WORKFLOWS / "release-notes.yaml")


def test_release_notes_declares_its_inputs(workflow: JsonObject) -> None:
    inputs = mapping(at(workflow, "on", "workflow_call", "inputs"))

    assert {name: mapping(definition).get("required") for name, definition in inputs.items()} == {
        "tag": "true",
        "changelog": None,
        "artifact-url": None,
        "artifact-label": None,
        "package": None,
        "exclude-newer": None,
        "exclude-newer-package": None,
    }


def test_release_notes_exposes_artifact_id(workflow: JsonObject) -> None:
    assert at(workflow, "on", "workflow_call", "outputs", "artifact-id", "value") == (
        "${{ jobs.notes.outputs.artifact-id }}"
    )


def test_release_notes_job_reads_contents_only(workflow: JsonObject) -> None:
    assert at(workflow, "permissions") == {}
    assert at(workflow, "jobs", "notes", "permissions") == {"contents": "read"}


def test_release_notes_render_without_a_separate_previous_tag_step(workflow: JsonObject) -> None:
    names = [item["name"] for item in steps(workflow, "notes")]

    assert names == [
        "📥 Check out repository",
        "🐍 Install uv and Python",
        "⚙️ Read Towncrier configuration",
        "📦 Install locked release tools",
        "📝 Render release notes",
        "📤 Upload release notes",
    ]
    assert all("select-previous-tag" not in text(item.get("uses", "")) for item in steps(workflow, "notes"))


def test_release_notes_default_changelog_comes_from_towncrier_config(workflow: JsonObject) -> None:
    assert step(workflow, "notes", "📝 Render release notes")["with"] == {
        "tag": "${{ inputs.tag }}",
        "changelog": "${{ inputs.changelog || steps.towncrier.outputs.changelog }}",
        "artifact-url": "${{ inputs.artifact-url }}",
        "artifact-label": "${{ inputs.artifact-label }}",
        "package": "${{ inputs.package }}",
    }


def test_towncrier_config_is_read_only_without_changelog_input(workflow: JsonObject) -> None:
    assert step(workflow, "notes", "⚙️ Read Towncrier configuration")["if"] == "inputs.changelog == ''"


def test_release_notes_uploads_artifact_per_run_attempt(workflow: JsonObject) -> None:
    upload = step(workflow, "notes", "📤 Upload release notes")

    assert at(upload, "with", "name") == "github-release-notes-${{ github.run_attempt }}"
    assert at(upload, "with", "if-no-files-found") == "error"


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.y*ml")), ids=lambda path: path.name)
def test_local_action_references_resolve(path: Path) -> None:
    references = [line.split("uses: $/", 1)[1].strip() for line in path.read_text().splitlines() if "uses: $/" in line]

    assert all((ROOT / reference / "action.yml").is_file() or (ROOT / reference).is_file() for reference in references)
