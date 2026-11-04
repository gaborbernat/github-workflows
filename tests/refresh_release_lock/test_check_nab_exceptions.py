import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

_SCRIPT: Final = Path(__file__).resolve().parents[2] / "tools/check_nab_exceptions.py"
_FUTURE: Final = "2999-01-01"
_PAST: Final = "2000-01-01"


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        pytest.param("pyproject.toml", '[tool.nab]\nmode = "universal"\n', id="no-exceptions"),
        pytest.param(
            "pyproject.toml",
            f"[tool.nab]\n# expires {_FUTURE}\n[tool.nab.packages.release-creator]\n"
            "uploaded-prior-to = 2026-11-02T21:45:00Z\n",
            id="table-header",
        ),
        pytest.param(
            "pyproject.toml",
            f'[tool.nab]\n# expires {_FUTURE}\n[tool.nab.packages."release-creator"]\nuploaded-prior-to = 2026-11-02\n',
            id="quoted-table-header",
        ),
        pytest.param(
            "pyproject.toml",
            f"[tool.nab]\n# expires {_FUTURE}\npackages.sphinx.uploaded-prior-to = 2026-10-21T00:05:13Z\n",
            id="dotted-key",
        ),
        pytest.param(
            "nab.toml",
            f"# expires {_FUTURE}\n[packages.sphinx]\nuploaded-prior-to = 2026-10-21T00:05:13Z\n",
            id="standalone-nab-toml",
        ),
        pytest.param(
            "pyproject.toml",
            "[tool.nab.packages.sphinx]\nassume-universal-deps = true\n",
            id="override-without-cutoff",
        ),
    ],
)
def test_nab_exception_expiry_accepts_dated_exception(tmp_path: Path, filename: str, content: str) -> None:
    path = tmp_path / filename
    path.write_text(content)

    result = subprocess.run([sys.executable, str(_SCRIPT), str(path)], text=True, capture_output=True, check=False)

    assert (result.returncode, result.stderr) == (0, "")


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        pytest.param(
            "[tool.nab]\n# expires 2999-01-01\n\n[tool.nab.packages.sphinx]\nuploaded-prior-to = 2026-10-21\n",
            "packages.sphinx uploaded-prior-to exception needs a '# expires YYYY-MM-DD' comment directly above it",
            id="comment-separated-by-blank-line",
        ),
        pytest.param(
            "[tool.nab.packages.sphinx]\nuploaded-prior-to = 2026-10-21\n",
            "packages.sphinx uploaded-prior-to exception needs a '# expires YYYY-MM-DD' comment directly above it",
            id="header-on-first-line",
        ),
        pytest.param(
            f"[tool.nab]\n# expires {_PAST}\n[tool.nab.packages.release-creator]\nuploaded-prior-to = 2026-10-26\n",
            "packages.release-creator uploaded-prior-to exception expired on 2000-01-01; "
            "remove it or extend its expiry",
            id="expired",
        ),
        pytest.param(
            "[tool.nab]\n# expires 2026-13-01\n[tool.nab.packages.sphinx]\nuploaded-prior-to = 2026-10-21\n",
            "packages.sphinx has an invalid expiry date 2026-13-01",
            id="invalid-date",
        ),
        pytest.param(
            f"[tool.nab]\n# expires {_FUTURE}\npackages = {{ sphinx = {{ uploaded-prior-to = 2026-10-21 }} }}\n",
            "packages.sphinx is not a table or dotted key that the expiry check can locate",
            id="inline-table",
        ),
        pytest.param(
            '[tool.nab]\n[[tool.nab.package-rules]]\nmatch = ["sphinx"]\nuploaded-prior-to = 2026-10-21\n',
            "[[package-rules]] ['sphinx'] sets uploaded-prior-to, which expiry is not checked for; "
            "move it to a packages.<name> table",
            id="package-rule",
        ),
    ],
)
def test_nab_exception_expiry_rejects_undated_or_expired_exception(tmp_path: Path, content: str, problem: str) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(content)

    result = subprocess.run([sys.executable, str(_SCRIPT), str(path)], text=True, capture_output=True, check=False)

    assert (result.returncode, result.stderr) == (1, f"::error::{path}: {problem}\n")


def test_nab_exception_expiry_reports_each_failing_package(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        "[tool.nab]\n[tool.nab.packages.sphinx]\nuploaded-prior-to = 2026-10-21\n"
        f"# expires {_PAST}\n[tool.nab.packages.vcrpy]\nuploaded-prior-to = 2026-10-25\n"
    )

    result = subprocess.run([sys.executable, str(_SCRIPT), str(path)], text=True, capture_output=True, check=False)

    assert (result.returncode, result.stderr) == (
        1,
        (
            f"::error::{path}: packages.sphinx uploaded-prior-to exception needs a '# expires YYYY-MM-DD' comment "
            f"directly above it\n::error::{path}: packages.vcrpy uploaded-prior-to exception expired on 2000-01-01; "
            "remove it or extend its expiry\n"
        ),
    )


def test_nab_exception_expiry_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"

    result = subprocess.run([sys.executable, str(_SCRIPT), str(path)], text=True, capture_output=True, check=False)

    assert (result.returncode, result.stderr) == (
        1,
        f"::error::[Errno 2] No such file or directory: '{path}'\n",
    )


def test_nab_exception_expiry_rejects_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text("[tool.nab\n")

    result = subprocess.run([sys.executable, str(_SCRIPT), str(path)], text=True, capture_output=True, check=False)

    assert (result.returncode, result.stderr) == (
        1,
        "::error::Expected ']' at the end of a table declaration (at line 1, column 10)\n",
    )


def test_nab_exception_expiry_import_has_no_cli_side_effect() -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import runpy; runpy.run_path({str(_SCRIPT)!r}, run_name='imported')"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
