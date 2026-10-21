from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml


def test_action_shell_coverage() -> None:
    if not (merged := os.getenv("KCOV_MERGED")):
        pytest.skip("kcov merge is available only in the runner coverage job")
    reports = list(Path(merged).rglob("codecov.json"))
    assert len(reports) == 1
    coverage: dict[str, dict[str, bool]] = json.loads(reports[0].read_text())["coverage"]
    expected = {
        f"{path.parent.name}-{index}.sh"
        for path in Path().glob("*/action.yml")
        for index, _ in enumerate(yaml.safe_load(path.read_text())["runs"]["steps"])
    }
    assert set(coverage) == expected
    assert all(lines and all(lines.values()) for lines in coverage.values())
