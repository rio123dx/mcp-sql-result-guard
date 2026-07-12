from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp_sql_result_guard.guard import load_rules  # noqa: E402


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def rules_one(project_root: Path):
    return load_rules(project_root / "tests" / "data" / "rules_one.tsv")


@pytest.fixture(scope="session")
def rules_two(project_root: Path):
    return load_rules(project_root / "tests" / "data" / "rules_two.tsv")


def pytest_generate_tests(metafunc):
    if "scenario" not in metafunc.fixturenames:
        return

    rows: list[dict[str, str]] = []
    for path in sorted((ROOT / "tests" / "data").glob("*_scenarios.tsv")):
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows.extend(csv.DictReader(file, delimiter="\t"))

    metafunc.parametrize("scenario", rows, ids=[row["scenario_id"] for row in rows])
