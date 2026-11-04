import hashlib
import os
import subprocess
from pathlib import Path
from typing import Final

import pytest
from conftest import WORKFLOWS, JsonObject, at, load_yaml, mapping, run_workflow_step, step, steps, text

_WORKFLOW: Final[str] = "latex-to-pages.yaml"


@pytest.fixture
def workflow() -> JsonObject:
    return load_yaml(WORKFLOWS / _WORKFLOW)


@pytest.fixture
def stubs(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        (
            "gh",
            """\
#!/usr/bin/env bash
case "$*" in
*pages/builds*) echo "abc built" ;;
*) echo abc ;;
esac
""",
        ),
        ("curl", '#!/usr/bin/env bash\ncat "$SERVED_FILE"\n'),
        ("sleep", "#!/usr/bin/env bash\nexit 0\n"),
    ):
        script = bin_dir / name
        script.write_text(body)
        script.chmod(0o755)
    return bin_dir


def test_workflow_grants_no_top_level_permissions(workflow: JsonObject) -> None:
    assert workflow["permissions"] == {}


@pytest.mark.parametrize(
    ("job", "permissions"),
    [
        pytest.param("build", {"contents": "read"}, id="build"),
        pytest.param("deploy", {"contents": "write", "pages": "read"}, id="deploy"),
    ],
)
def test_job_holds_only_its_scope(workflow: JsonObject, job: str, permissions: JsonObject) -> None:
    assert at(workflow, "jobs", job, "permissions") == permissions


@pytest.mark.parametrize(
    ("job", "minutes"),
    [
        pytest.param("build", "20", id="build"),
        pytest.param("deploy", "30", id="deploy"),
    ],
)
def test_job_bounds_its_runtime(workflow: JsonObject, job: str, minutes: str) -> None:
    assert at(workflow, "jobs", job, "timeout-minutes") == minutes


def test_compile_step_pins_source_date_epoch(workflow: JsonObject) -> None:
    compile_step = mapping(step(workflow, "build", "📕 Compile LaTeX document")["with"])
    assert "SOURCE_DATE_EPOCH=${{ steps.epoch.outputs.epoch }}" in text(compile_step["pre_compile"])


def test_checkouts_keep_credentials_out_of_the_workspace(workflow: JsonObject) -> None:
    checkouts = [
        item
        for job in mapping(at(workflow, "jobs"))
        for item in steps(workflow, job)
        if text(item.get("uses", "")).startswith("actions/checkout@")
    ]
    assert [item["with"] for item in checkouts] == [{"persist-credentials": "false"}, {"persist-credentials": "false"}]


@pytest.mark.parametrize(
    ("root_file", "path", "name"),
    [
        pytest.param("main.tex", "main.pdf", "main.pdf", id="root"),
        pytest.param("doc/cv.tex", "doc/cv.pdf", "cv.pdf", id="nested"),
    ],
)
def test_records_pdf_path_name_and_digest(tmp_path: Path, root_file: str, path: str, name: str) -> None:
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_bytes(b"pdf bytes")
    result, outputs = run_workflow_step(
        _WORKFLOW,
        "build",
        "🔎 Record PDF name and digest",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={"ROOT_FILE": root_file},
    )
    assert result.returncode == 0, result.stderr
    assert outputs == {"path": path, "name": name, "sha256": hashlib.sha256(b"pdf bytes").hexdigest()}


def test_missing_pdf_fails_the_build(tmp_path: Path) -> None:
    result, _ = run_workflow_step(
        _WORKFLOW,
        "build",
        "🔎 Record PDF name and digest",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={"ROOT_FILE": "main.tex"},
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    ("content", "accepted"),
    [
        pytest.param(b"pdf bytes", True, id="matches-build"),
        pytest.param(b"tampered", False, id="tampered-download"),
    ],
)
def test_deploy_rejects_a_download_that_differs_from_the_build(
    tmp_path: Path,
    content: bytes,
    accepted: bool,
) -> None:
    (tmp_path / "built").mkdir()
    (tmp_path / "built/main.pdf").write_bytes(content)
    result, _ = run_workflow_step(
        _WORKFLOW,
        "deploy",
        "🔍 Check downloaded PDF digest",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={"PDF_NAME": "main.pdf", "PDF_SHA256": hashlib.sha256(b"pdf bytes").hexdigest()},
    )
    assert (result.returncode == 0) is accepted, result.stderr


def test_verify_loop_accepts_the_served_bytes_it_built(tmp_path: Path, stubs: Path) -> None:
    result = _verify(tmp_path, stubs, b"built pdf", hashlib.sha256(b"built pdf").hexdigest())
    assert result.returncode == 0, result.stderr
    assert "Pages serves the freshly built PDF" in result.stdout


def _verify(tmp_path: Path, stubs: Path, served: bytes, expected: str) -> subprocess.CompletedProcess[str]:
    served_file = tmp_path / "served.pdf"
    served_file.write_bytes(served)
    result, _ = run_workflow_step(
        _WORKFLOW,
        "deploy",
        "🔍 Verify published PDF",
        cwd=tmp_path,
        runner_temp=tmp_path,
        values={},
        env={
            "GH_TOKEN": "token",
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_RUN_ID": "1",
            "URL": "https://owner.github.io/repo/main.pdf",
            "PDF_SHA256": expected,
            "SERVED_FILE": str(served_file),
            "PATH": f"{stubs}:{os.environ['PATH']}",
        },
    )
    return result


def test_verify_loop_fails_when_pages_keeps_serving_other_bytes(tmp_path: Path, stubs: Path) -> None:
    result = _verify(tmp_path, stubs, b"stale pdf", hashlib.sha256(b"built pdf").hexdigest())
    assert result.returncode != 0
    assert "::error::" in result.stderr
