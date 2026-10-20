from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from conftest import run


@pytest.fixture(scope="session")
def upgrade_scripts(action_scripts: Path) -> Path:
    return action_scripts


@pytest.fixture(scope="session")
def publish_scripts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    source = Path(__file__).resolve().parents[2]
    scripts = tmp_path_factory.mktemp("publish-steps")
    workflow = yaml.safe_load((source / ".github/workflows/upgrade-release-tools.yaml").read_text())
    for step in workflow["jobs"]["publish"]["steps"]:
        if "run" in step:
            name = step.get("id", step.get("name", "step")).replace(" ", "-").lower()
            (scripts / f"publish-{name}.sh").write_text(step["run"])
    return scripts


@pytest.fixture
def lock_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\nrequires-python = ">=3.15"\n'
        "[dependency-groups]\nrelease = []\ntest = []\n"
    )
    run(repository, "git", "init", "-b", "main")
    run(repository, "git", "config", "user.name", "Release test")
    run(repository, "git", "config", "user.email", "release@example.org")
    run(repository, "git", "add", ".")
    run(repository, "git", "commit", "-m", "Initial files")
    return repository


@pytest.mark.parametrize(
    ("groups", "accepted"),
    [
        pytest.param("release", True, id="release"),
        pytest.param("release,test", True, id="release-and-test"),
        pytest.param("release,$bad", False, id="invalid-group"),
        pytest.param("test", False, id="missing-release-group"),
    ],
)
def test_upgrade_compiles_selected_groups(
    lock_repository: Path, tmp_path: Path, upgrade_scripts: Path, groups: str, accepted: bool
) -> None:
    result = execute(
        lock_repository,
        upgrade_scripts / "refresh-release-lock-0.sh",
        tmp_path,
        LOCK="pylock.toml",
        DEP_GROUPS=groups,
        PYTHON_VERSION="3.15",
    )
    assert (result.returncode == 0) == accepted
    if accepted:
        assert (lock_repository / "pylock.toml").read_text().count("--group pyproject.toml:") == groups.count(",") + 1
    else:
        assert "::error::" in result.stderr


@pytest.mark.parametrize("changed", [False, True], ids=["unchanged", "changed"])
def test_upgrade_emits_patch_only_for_change(
    lock_repository: Path, tmp_path: Path, upgrade_scripts: Path, changed: bool
) -> None:
    lock = lock_repository / "pylock.toml"
    lock.write_text('lock-version = "1.0"\n')
    run(lock_repository, "git", "add", ".")
    run(lock_repository, "git", "commit", "-m", "Add lock")
    if changed:
        lock.write_text('lock-version = "1.0"\ncreated-by = "uv"\n')
    result = execute(
        lock_repository,
        upgrade_scripts / "refresh-release-lock-2.sh",
        tmp_path,
        LOCK="pylock.toml",
        GITHUB_OUTPUT=str(tmp_path / "output"),
    )
    assert result.returncode == 0
    assert (tmp_path / "output").read_text() == f"changed={str(changed).lower()}\n"
    assert (tmp_path / "lock.patch").exists() == changed


@pytest.mark.parametrize("unrelated", [False, True], ids=["clean", "unrelated-file"])
def test_upgrade_checks_refreshed_lock(
    lock_repository: Path, tmp_path: Path, upgrade_scripts: Path, unrelated: bool
) -> None:
    project = lock_repository / "pyproject.toml"
    project.write_text(project.read_text().replace("release = []", 'release = ["prek"]'))
    (lock_repository / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks:\n      - id: check\n"
        "        name: check\n        entry: 'true'\n        language: system\n        pass_filenames: false\n"
    )
    (lock_repository / "other.txt").write_text("before\n")
    run(
        lock_repository,
        "uv",
        "pip",
        "compile",
        "--preview-features",
        "pylock",
        "--group",
        "pyproject.toml:release",
        "--python-version",
        "3.15",
        "--output-file",
        "pylock.toml",
    )
    run(lock_repository, "git", "add", ".")
    run(lock_repository, "git", "commit", "-m", "Add release tools")
    if unrelated:
        (lock_repository / "other.txt").write_text("after\n")
    result = execute(
        lock_repository,
        upgrade_scripts / "refresh-release-lock-1.sh",
        tmp_path,
        LOCK="pylock.toml",
        PYTHON_VERSION="3.15",
    )
    assert (result.returncode == 0) != unrelated, result.stderr
    assert ("prek changed file outside pylock.toml" in result.stderr) == unrelated


@pytest.mark.parametrize("path", ["pylock.toml", "other.txt"], ids=["lock-only", "unrelated-file"])
def test_upgrade_rejects_unrelated_patch(
    lock_repository: Path, tmp_path: Path, publish_scripts: Path, path: str
) -> None:
    (lock_repository / path).write_text("before\n")
    run(lock_repository, "git", "add", ".")
    run(lock_repository, "git", "commit", "-m", "Add file")
    (lock_repository / path).write_text("after\n")
    patch = run(lock_repository, "git", "diff", "--binary", "--", path).stdout
    run(lock_repository, "git", "restore", path)
    patch_dir = tmp_path / "release-tools-lock"
    patch_dir.mkdir()
    (patch_dir / "lock.patch").write_text(patch)
    result = execute(
        lock_repository, publish_scripts / "publish-validate-and-apply-lock-patch.sh", tmp_path, LOCK="pylock.toml"
    )
    assert (result.returncode == 0) == (path == "pylock.toml")
    assert ("unexpected lock paths" in result.stderr) == (path != "pylock.toml")


def execute(repository: Path, script: Path, tmp_path: Path, **environment: str) -> subprocess.CompletedProcess[str]:
    command = ["bash", str(script)]
    if script.name.startswith("refresh-release-lock-") and (coverage_binary := os.environ.get("KCOV_BIN")):
        output = Path(os.environ["KCOV_OUTPUT"])
        output.mkdir(parents=True, exist_ok=True)
        command = [coverage_binary, f"--include-path={script.parent}", str(output / uuid4().hex), str(script)]
    return subprocess.run(
        command,
        cwd=repository,
        env=os.environ | {"RUNNER_TEMP": str(tmp_path)} | environment,
        text=True,
        capture_output=True,
        check=False,
    )
