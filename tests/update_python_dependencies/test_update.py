import os
import re
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from conftest import WORKFLOWS, JsonObject, JsonValue, at, load_yaml, run, run_workflow_step, workflow_env

if TYPE_CHECKING:
    import subprocess

_WORKFLOW: Final[str] = "update-python-dependencies.yaml"
_PATCH: Final[str] = "📝 Write maintenance patch"
_DEFAULTS: Final[dict[str, str]] = {
    "inputs.allowed-paths": "docs/*.md",
    "inputs.cooldown": "7 days",
    "inputs.exclude-newer": "7 days",
    "inputs.exclude-newer-package": "",
    "inputs.expedite": "",
    "inputs.files": "pyproject.toml tox.toml",
    "inputs.fresh-groups": "project test",
    "inputs.kind": "app",
}


@pytest.fixture
def workflow() -> JsonObject:
    return load_yaml(WORKFLOWS / _WORKFLOW)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repository"
    repo.mkdir()
    run(repo, "git", "init", "-b", "main")
    run(repo, "git", "config", "user.name", "Release test")
    run(repo, "git", "config", "user.email", "release@example.org")
    (repo / "pylock.toml").write_text("lock-version = '1.0'\n")
    (repo / "pyproject.toml").write_text('[project]\nname = "example"\n')
    run(repo, "git", "add", ".")
    run(repo, "git", "commit", "-m", "Initial files")
    return repo


def test_cutoff_is_a_utc_timestamp(repository: Path, tmp_path: Path) -> None:
    result, outputs = validate(repository, tmp_path)
    assert result.returncode == 0, result.stderr
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", outputs["cutoff"])


def validate(
    repository: Path, tmp_path: Path, **inputs: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    values = _DEFAULTS | {f"inputs.{key.replace('_', '-')}": value for key, value in inputs.items()}
    return run_workflow_step(
        _WORKFLOW,
        "generate",
        "⚙️ Validate inputs and set the cutoffs",
        cwd=repository,
        runner_temp=tmp_path,
        values=values,
        env={"ALLOWED_EXTRA": values["inputs.allowed-paths"]},
    )


def test_allowed_paths_extend_the_lock_and_config_files(repository: Path, tmp_path: Path) -> None:
    result, outputs = validate(repository, tmp_path)
    assert result.returncode == 0, result.stderr
    assert outputs["allowed-paths"].splitlines() == ["pylock.toml", "pyproject.toml", "tox.toml", "docs/*.md"]


def test_validated_inputs_are_handed_to_later_steps(repository: Path, tmp_path: Path) -> None:
    result, _ = validate(repository, tmp_path, expedite="release-creator\nnab", files="pyproject.toml tox.toml\n")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "expedite").read_text() == "release-creator\nnab\n"
    assert (tmp_path / "file-groups").read_text() == "pyproject.toml tox.toml\n"
    assert (tmp_path / "fresh-groups").read_text() == ""


def test_library_keeps_fresh_groups(repository: Path, tmp_path: Path) -> None:
    result, _ = validate(repository, tmp_path, kind="library", fresh_groups="project\ntest")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "fresh-groups").read_text() == "project\ntest\n"


def test_zero_days_turns_the_bump_cooldown_off(repository: Path, tmp_path: Path) -> None:
    result, outputs = validate(repository, tmp_path, cooldown="0 days")
    assert result.returncode == 0, result.stderr
    assert outputs["cutoff"] == "none"


def test_empty_extra_paths_add_no_pattern(repository: Path, tmp_path: Path) -> None:
    result, outputs = validate(repository, tmp_path, allowed_paths="")
    assert result.returncode == 0, result.stderr
    assert outputs["allowed-paths"].splitlines() == ["pylock.toml", "pyproject.toml", "tox.toml"]


@pytest.mark.parametrize(
    ("options", "message"),
    [
        pytest.param({"kind": "tool"}, "kind must be app or library", id="unknown-kind"),
        pytest.param({"cooldown": "P7D"}, "cooldown must be N days", id="iso-duration"),
        pytest.param({"cooldown": "7 weeks"}, "cooldown must be N days", id="weeks"),
        pytest.param({"expedite": "bad name!"}, "is not a package name", id="expedite-name"),
        pytest.param({"kind": "library", "fresh_groups": "bad group!"}, "is not a dependency group", id="group-name"),
        pytest.param({"kind": "library", "fresh_groups": ""}, "needs at least one fresh-groups", id="no-groups"),
        pytest.param({"files": "../pyproject.toml"}, "is not a plain relative path", id="parent-path"),
        pytest.param({"files": "/etc/pyproject.toml"}, "is not a plain relative path", id="absolute-path"),
        pytest.param({"files": "a*.toml"}, "is not a plain relative path", id="glob-path"),
        pytest.param({"files": "\n\n"}, "lists no dependency file", id="no-files"),
    ],
)
def test_rejects_invalid_inputs(repository: Path, tmp_path: Path, options: dict[str, str], message: str) -> None:
    result, _ = validate(repository, tmp_path, **options)
    assert result.returncode != 0
    assert message in result.stderr


def test_bump_runs_each_group_with_expedite(repository: Path, tmp_path: Path) -> None:
    result, outputs = validate(
        repository, tmp_path, expedite="release-creator", files="pyproject.toml tox.toml\ndocs/a.toml"
    )
    assert result.returncode == 0, result.stderr
    result, calls = bump(repository, tmp_path, outputs)
    assert result.returncode == 0, result.stderr
    prefix = ["--exclude-newer", "7 days", "bump-deps-index>=1.19", "--exclude-newer", outputs["cutoff"]]
    assert calls == [
        "\t".join(
            [*prefix, "--exclude-newer-package", "release-creator=false", "--file", "pyproject.toml", "tox.toml"]
        ),
        "\t".join([*prefix, "--exclude-newer-package", "release-creator=false", "--file", "docs/a.toml"]),
    ]


def bump(
    repository: Path, tmp_path: Path, outputs: dict[str, str], **inputs: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = fake_uvx(bin_dir)
    values = _DEFAULTS | {"steps.inputs.outputs.cutoff": outputs["cutoff"]}
    values |= {f"inputs.{key.replace('_', '-')}": value for key, value in inputs.items()}
    result, _ = run_workflow_step(
        _WORKFLOW,
        "generate",
        "📦 Bump dependency floors",
        cwd=repository,
        runner_temp=tmp_path,
        values=values,
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "UVX_LOG": str(log)},
    )
    return result, (log.read_text().splitlines() if log.exists() else [])


def fake_uvx(bin_dir: Path) -> Path:
    script = bin_dir / "uvx"
    script.write_text('#!/usr/bin/env bash\n(IFS=$\'\\t\'; echo "$*") >>"$UVX_LOG"\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return bin_dir / "uvx.log"


def test_tool_install_takes_the_exclude_newer_inputs(repository: Path, tmp_path: Path) -> None:
    result, outputs = validate(repository, tmp_path, cooldown="0 days")
    assert result.returncode == 0, result.stderr
    result, calls = bump(
        repository,
        tmp_path,
        outputs,
        exclude_newer="2026-10-01T00:00:00Z",
        exclude_newer_package="bump-deps-index=2026-11-01T00:00:00Z",
    )
    assert result.returncode == 0, result.stderr
    assert calls == [
        "--exclude-newer\t2026-10-01T00:00:00Z\t--exclude-newer-package\tbump-deps-index=2026-11-01T00:00:00Z\tbump-deps-index>=1.19\t--no-exclude-newer\t--file\tpyproject.toml\ttox.toml"
    ]


def test_library_bump_keeps_fresh_groups_fresh(repository: Path, tmp_path: Path) -> None:
    result, outputs = validate(repository, tmp_path, kind="library")
    assert result.returncode == 0, result.stderr
    result, calls = bump(repository, tmp_path, outputs)
    assert result.returncode == 0, result.stderr
    assert calls == [
        "\t".join(
            [
                "--exclude-newer",
                "7 days",
                "bump-deps-index>=1.19",
                "--exclude-newer",
                outputs["cutoff"],
                "--exclude-newer-group",
                "project=false",
                "--exclude-newer-group",
                "test=false",
                "--file",
                "pyproject.toml",
                "tox.toml",
            ]
        )
    ]


def test_bump_without_cooldown_passes_no_cutoff(repository: Path, tmp_path: Path) -> None:
    result, outputs = validate(repository, tmp_path, cooldown="0 days")
    assert result.returncode == 0, result.stderr
    result, calls = bump(repository, tmp_path, outputs)
    assert result.returncode == 0, result.stderr
    assert calls[0].split("\t")[-4:] == ["--no-exclude-newer", "--file", "pyproject.toml", "tox.toml"]
    assert len(calls) == 1


def test_bump_uses_the_workflow_requirement_constant() -> None:
    assert workflow_env(_WORKFLOW) == {"BUMP_DEPS_INDEX": "bump-deps-index>=1.19"}


def test_patch_step_reports_no_change(repository: Path, tmp_path: Path) -> None:
    result, outputs = run_workflow_step(
        _WORKFLOW, "generate", _PATCH, cwd=repository, runner_temp=tmp_path, values=_DEFAULTS, env={}
    )
    assert result.returncode == 0, result.stderr
    assert outputs == {"changed": "false"}
    assert not (tmp_path / "maintenance.patch").exists()


def test_patch_step_writes_every_change_including_new_files(repository: Path, tmp_path: Path) -> None:
    (repository / "pylock.toml").write_text("lock-version = '2.0'\n")
    (repository / "docs").mkdir()
    (repository / "docs/new.md").write_text("New.\n")
    result, outputs = run_workflow_step(
        _WORKFLOW, "generate", _PATCH, cwd=repository, runner_temp=tmp_path, values=_DEFAULTS, env={}
    )
    assert result.returncode == 0, result.stderr
    assert outputs == {"changed": "true"}
    patch = (tmp_path / "maintenance.patch").read_text()
    assert "diff --git a/pylock.toml b/pylock.toml" in patch
    assert "diff --git a/docs/new.md b/docs/new.md" in patch


def test_generate_job_is_read_only(workflow: JsonObject) -> None:
    assert at(workflow, "jobs", "generate", "permissions") == {"contents": "read"}


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        pytest.param("needs", "generate", id="needs"),
        pytest.param("if", "needs.generate.outputs.changed == 'true'", id="if"),
        pytest.param("uses", "$/.github/workflows/open-maintenance-pr.yaml", id="uses"),
        pytest.param(
            "secrets",
            {"RELEASE_APP_PRIVATE_KEY": "${{ secrets.RELEASE_APP_PRIVATE_KEY }}"},
            id="secrets",
        ),
    ],
)
def test_open_job_hands_off_from_generate(workflow: JsonObject, key: str, expected: JsonValue) -> None:
    assert at(workflow, "jobs", "open", key) == expected


def test_external_actions_are_pinned_to_commit_shas() -> None:
    workflow_text = (WORKFLOWS / _WORKFLOW).read_text()
    unpinned = [
        reference
        for reference in re.findall(r"uses: (\S+)", workflow_text)
        if not (reference.startswith("$/") or re.search(r"@[0-9a-f]{40}$", reference))
    ]
    assert unpinned == []


@pytest.mark.parametrize(
    "forbidden",
    [
        pytest.param("peter-evans", id="peter-evans"),
        pytest.param("uv lock", id="uv-lock"),
        pytest.param("cargo", id="cargo"),
    ],
)
def test_workflow_avoids_forbidden_tools(forbidden: str) -> None:
    assert forbidden not in (WORKFLOWS / _WORKFLOW).read_text()
