import os
import subprocess
from pathlib import Path
from typing import Final

import pytest
from conftest import WORKFLOWS, at, load_yaml, run, step, step_list, steps, text
from pytest_httpserver import HTTPServer

ROOT: Final = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def publish_scripts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    scripts = tmp_path_factory.mktemp("publish-steps")
    for item in steps(load_yaml(WORKFLOWS / "upgrade-release-tools.yaml"), "publish"):
        if "run" in item:
            label = text(item.get("id", text(item["name"]).split(" ", 1)[1])).replace(" ", "-").lower()
            (scripts / f"publish-{label}.sh").write_text(text(item["run"]))
    return scripts


@pytest.fixture
def lock_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "example"\nversion = "0.1.0"\nrequires-python = ">=3.15"\n'
        "[dependency-groups]\nrelease = []\ntest = []\n"
        '[tool.nab]\nmode = "universal"\nuploaded-prior-to = "P7D"\n'
        'decision-order = "stable"\nbase-group = "project-runtime"\ndefault-groups = []\n'
        '[tool.nab.matrix]\npython = ">=3.15,<3.16"\n'
        'platforms = ["linux_x86_64", "linux_aarch64", "macos_arm64", "windows_amd64"]\n',
    )
    run(repository, "git", "init", "-b", "main")
    run(repository, "git", "config", "user.name", "Release test")
    run(repository, "git", "config", "user.email", "release@example.org")
    run(repository, "git", "add", ".")
    run(repository, "git", "commit", "-m", "Initial files")
    return repository


def test_upgrade_emits_patch_for_lock_change(lock_repository: Path, tmp_path: Path, action_scripts: Path) -> None:
    (lock_repository / "pylock.toml").write_text('lock-version = "1.0"\n')
    run(lock_repository, "git", "add", ".")
    run(lock_repository, "git", "commit", "-m", "Add lock")
    (lock_repository / "pylock.toml").write_text((lock_repository / "pylock.toml").read_text() + "\n")
    result = execute(
        lock_repository,
        refresh_script(action_scripts, "lock"),
        tmp_path,
        MODE="refresh",
        GITHUB_OUTPUT=str(tmp_path / "output"),
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "output").read_text() == "changed=true\n"
    assert "diff --git a/pylock.toml b/pylock.toml" in (tmp_path / "lock.patch").read_text()


@pytest.mark.parametrize(
    ("path", "additional_lock", "accepted"),
    [
        pytest.param("pylock.toml", "", True, id="lock"),
        pytest.param("pyproject.toml", "", False, id="project"),
        pytest.param("pylock.zipapp.toml", "pylock.zipapp.toml", True, id="secondary-lock"),
        pytest.param(".pre-commit-config.yaml", "", False, id="hook-config"),
        pytest.param("uv.lock", "", False, id="uv-lock"),
        pytest.param("other.txt", "", False, id="unrelated-file"),
    ],
)
def test_upgrade_checks_lock_patch_path(
    lock_repository: Path,
    tmp_path: Path,
    publish_scripts: Path,
    path: str,
    additional_lock: str,
    accepted: bool,
) -> None:
    (lock_repository / path).write_text("before\n")
    run(lock_repository, "git", "add", ".")
    run(lock_repository, "git", "commit", "-m", "Add file")
    (lock_repository / path).write_text("after\n")
    _save_patch(lock_repository, tmp_path, path)
    result = execute(
        lock_repository,
        publish_scripts / "publish-check-artifact-patch-paths.sh",
        tmp_path,
        ADDITIONAL_LOCK=additional_lock,
    )
    assert (result.returncode == 0) == accepted
    assert (f"unexpected lock patch path: {path}" in result.stderr) == (not accepted)
    assert run(lock_repository, "git", "status", "--porcelain").stdout == ""


@pytest.mark.parametrize(
    "change",
    [
        pytest.param("chmod 755 pylock.toml", id="executable"),
        pytest.param("rm pylock.toml && ln -s other.txt pylock.toml", id="symlink"),
    ],
)
def test_upgrade_rejects_unsafe_file_mode(
    lock_repository: Path, tmp_path: Path, publish_scripts: Path, change: str
) -> None:
    (lock_repository / "pylock.toml").write_text("before\n")
    run(lock_repository, "git", "add", "pylock.toml")
    run(lock_repository, "git", "commit", "-m", "Add lock")
    run(lock_repository, "bash", "-c", change)
    _save_patch(lock_repository, tmp_path, "pylock.toml")
    applied = execute(lock_repository, publish_scripts / "publish-apply-lock-patch.sh", tmp_path)
    assert applied.returncode == 0, applied.stderr
    result = execute(lock_repository, publish_scripts / "publish-check-dependency-patch-file-mode.sh", tmp_path)
    assert result.returncode != 0
    assert "unexpected dependency file mode" in result.stderr


def test_upgrade_preserves_requested_pull_request_body(
    lock_repository: Path, tmp_path: Path, publish_scripts: Path
) -> None:
    result = execute(
        lock_repository,
        publish_scripts / "publish-write-dependency-pull-request-body.sh",
        tmp_path,
        PR_BODY="Refresh release tools.",
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "pull-request.md").read_text() == "Refresh release tools.\n"


def test_upgrade_finds_only_own_dependency_pull_request(
    lock_repository: Path,
    tmp_path: Path,
    publish_scripts: Path,
    github_api: tuple[HTTPServer, dict[str, str]],
) -> None:
    server, environment = github_api
    server.expect_request(
        "/api/v3/repos/tox-dev/fixture/pulls",
        method="GET",
        query_string="base=main&head=tox-dev%3Aautomation%2Fupdate-release-tools&state=open",
    ).respond_with_json(
        [
            {
                "number": 17,
                "head": {"repo": {"full_name": "attacker/fork"}, "ref": "automation/update-release-tools"},
                "base": {"ref": "main"},
            },
            {
                "number": 18,
                "head": {"repo": {"full_name": "tox-dev/fixture"}, "ref": "automation/update-release-tools"},
                "base": {"ref": "main"},
            },
        ]
    )
    result = execute(
        lock_repository,
        publish_scripts / "publish-pr.sh",
        tmp_path,
        **environment,
        GITHUB_REPOSITORY="tox-dev/fixture",
        GITHUB_OUTPUT=str(tmp_path / "output"),
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "output").read_text() == "number=18\n"


def test_upgrade_checks_cutoff_exceptions_before_refreshing_the_lock() -> None:
    workflow = load_yaml(WORKFLOWS / "upgrade-release-tools.yaml")
    names = [item["name"] for item in steps(workflow, "generate-lock")]

    assert step(workflow, "generate-lock", "📅 Check cutoff exception expiry")["uses"] == "$/check-nab-exceptions"
    assert names.index("📅 Check cutoff exception expiry") < names.index("🔒 Refresh release lock")


def _save_patch(repository: Path, tmp_path: Path, path: str) -> None:
    patch = run(repository, "git", "diff", "--binary", "--", path).stdout
    run(repository, "git", "restore", path)
    patch_dir = tmp_path / "release-tools-lock"
    patch_dir.mkdir()
    (patch_dir / "lock.patch").write_text(patch)


def execute(repository: Path, script: Path, tmp_path: Path, **environment: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script)],
        cwd=repository,
        env=os.environ
        | {
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_ACTION_PATH": str(ROOT / "refresh-release-lock"),
            "ADDITIONAL_LOCK": "",
            "ADDITIONAL_GROUPS": "",
            "ADDITIONAL_SELECTION": "build-or-groups",
            "MATRIX_PYTHON": "",
            "MATRIX_PLATFORMS": "",
            "MATRIX_IMPLEMENTATIONS": "",
        }
        | environment,
        text=True,
        capture_output=True,
        check=False,
    )


def refresh_script(scripts: Path, name: str) -> Path:
    action_steps = step_list(at(load_yaml(ROOT / "refresh-release-lock/action.yml"), "runs", "steps"))
    index = next(index for index, item in enumerate(action_steps) if item.get("id") == name)
    return scripts / f"refresh-release-lock-{index}.sh"
