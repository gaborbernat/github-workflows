import os
import subprocess
from pathlib import Path
from typing import Final

import pytest
from conftest import WORKFLOWS, JsonObject, at, load_yaml, mapping, step, steps, text

WORKFLOW: Final[JsonObject] = load_yaml(WORKFLOWS / "check.yaml")
INPUTS: Final[JsonObject] = mapping(at(WORKFLOW, "on", "workflow_call", "inputs"))


@pytest.mark.parametrize(
    ("name", "default"),
    [
        pytest.param("os", "ubuntu-26.04", id="os"),
        pytest.param("apt-packages", "", id="apt-packages"),
        pytest.param("tox-install", "tox --with tox-uv", id="tox-install"),
        pytest.param("exclude-newer", "7 days", id="exclude-newer"),
        pytest.param("exclude-newer-package", "", id="exclude-newer-package"),
        pytest.param("pytest-addopts", "-vv --durations=20", id="pytest-addopts"),
        pytest.param("diff-against", "HEAD", id="diff-against"),
        pytest.param("coverage", "false", id="coverage"),
    ],
)
def test_input_defaults(name: str, default: str) -> None:
    assert at(INPUTS, name, "default") == default


def test_include_input_is_required_json_rows() -> None:
    assert at(INPUTS, "include", "required") == "true"
    assert at(WORKFLOW, "jobs", "test", "strategy", "matrix") == {"include": "${{ fromJSON(inputs.include) }}"}
    assert at(WORKFLOW, "jobs", "test", "runs-on") == "${{ matrix.os || inputs.os }}"


def test_workflow_grants_no_token_scope_beyond_contents_read() -> None:
    assert at(WORKFLOW, "permissions") == {}
    assert at(WORKFLOW, "jobs", "test", "permissions") == {"contents": "read"}


def test_checkout_keeps_full_history_without_credentials() -> None:
    assert step(WORKFLOW, "test", "📥 Check out repository")["with"] == {
        "fetch-depth": "0",
        "persist-credentials": "false",
    }


def test_every_run_block_uses_bash_on_windows_rows() -> None:
    assert all(item.get("shell") == "bash" for item in steps(WORKFLOW, "test") if "run" in item)


def test_tox_environment_is_built_without_running_tests() -> None:
    assert step(WORKFLOW, "test", "📦 Set up test suite")["run"] == (
        'tox run -vv --notest --skip-missing-interpreters false -e "$MATRIX_ENV"'
    )


def test_test_run_reuses_built_environment_with_inputs() -> None:
    suite = step(WORKFLOW, "test", "🧪 Run test suite")
    assert suite["run"] == 'tox run --skip-pkg-install -e "$MATRIX_ENV"'
    assert at(suite, "env", "PYTEST_ADDOPTS") == "${{ inputs.pytest-addopts }}"
    assert at(suite, "env", "DIFF_AGAINST") == "${{ inputs.diff-against }}"


def test_python_is_installed_only_for_rows_that_name_one() -> None:
    install = step(WORKFLOW, "test", "🐍 Install Python")
    assert install["if"] == "${{ matrix.python }}"
    assert install["env"] == {"PYTHON": "${{ matrix.python }}"}


def test_apt_packages_install_on_linux_only() -> None:
    install = step(WORKFLOW, "test", "📦 Install apt packages")
    assert install["if"] == "${{ inputs.apt-packages != '' && runner.os == 'Linux' }}"
    assert install["env"] == {"APT_PACKAGES": "${{ inputs.apt-packages }}"}


def test_coverage_upload_is_opt_in_and_named_per_job() -> None:
    upload = step(WORKFLOW, "test", "📤 Upload coverage data")
    assert upload["if"] == "${{ inputs.coverage }}"
    assert at(upload, "with", "name") == ".coverage.${{ matrix.os || inputs.os }}.${{ matrix.env }}"
    assert at(upload, "with", "path") == ".tox/.coverage.*"
    assert at(upload, "with", "if-no-files-found") == "error"


def test_gate_requires_test_through_required_checks() -> None:
    assert at(WORKFLOW, "jobs", "gate") == {
        "name": "🚦 Required checks pass",
        "if": "${{ !cancelled() }}",
        "needs": ["test"],
        "runs-on": "ubuntu-26.04",
        "permissions": {},
        "steps": [
            {
                "name": "🚦 Require all needed jobs to pass",
                "uses": "$/required-checks",
                "with": {"needs": "${{ toJSON(needs) }}"},
            }
        ],
    }


@pytest.mark.parametrize(
    ("tox_install", "package_cutoffs", "expected"),
    [
        pytest.param(
            "tox --with tox-uv",
            "",
            ["tool", "install", "--python-preference", "only-managed", "--python", "3.15"]
            + ["--exclude-newer", "7 days", "tox", "--with", "tox-uv"],
            id="default",
        ),
        pytest.param(
            "tox --with .",
            "",
            ["tool", "install", "--python-preference", "only-managed", "--python", "3.15"]
            + ["--exclude-newer", "7 days", "tox", "--with", "."],
            id="local-tox-uv",
        ),
        pytest.param(
            "tox --with tox-uv",
            "nab=2026-10-24T00:00:00Z\nrelease-creator=2026-10-30T15:13:19Z\n",
            ["tool", "install", "--python-preference", "only-managed", "--python", "3.15"]
            + [
                "--exclude-newer",
                "7 days",
                "--exclude-newer-package",
                "nab=2026-10-24T00:00:00Z",
                "--exclude-newer-package",
                "release-creator=2026-10-30T15:13:19Z",
                "tox",
                "--with",
                "tox-uv",
            ],
            id="package-cutoffs",
        ),
    ],
)
def test_tox_install_passes_cutoffs_to_uv(
    tmp_path: Path, tox_install: str, package_cutoffs: str, expected: list[str]
) -> None:
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "uv").write_text('#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" >"$UV_ARGUMENTS"\n')
    (stub / "uv").chmod(0o755)
    arguments = tmp_path / "arguments"
    result = subprocess.run(
        ["bash", "-c", text(step(WORKFLOW, "test", "📦 Install tox")["run"])],
        env={
            "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
            "UV_ARGUMENTS": str(arguments),
            "TOX_INSTALL": tox_install,
            "EXCLUDE_NEWER": "7 days",
            "EXCLUDE_NEWER_PACKAGE": package_cutoffs,
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert arguments.read_text().splitlines() == expected
