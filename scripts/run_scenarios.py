#!/usr/bin/env python3
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcp_sql_result_guard.guard import inspect_sql, load_rules  # noqa: E402

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

RULES = {
    "one": load_rules(ROOT / "tests" / "data" / "rules_one.tsv"),
    "two": load_rules(ROOT / "tests" / "data" / "rules_two.tsv"),
}


def split_expected(value: str) -> set[str]:
    return {item.strip().casefold() for item in value.split(",") if item.strip()}


def main() -> int:
    scenario_path = ROOT / "tests" / "data" / "sql_scenarios.tsv"
    output_path = ROOT / "scenario-results.tsv"

    with scenario_path.open("r", encoding="utf-8-sig", newline="") as file:
        scenarios = list(csv.DictReader(file, delimiter="\t"))

    results: list[dict[str, str]] = []
    failed = 0

    for scenario in scenarios:
        try:
            findings = inspect_sql(scenario["sql"], RULES[scenario["rule_set"]])
            actual_result = "deny" if any(item.action == "deny" for item in findings) else (
                "warn" if findings else "allow"
            )
            actual_columns = {
                item.column_name.casefold()
                for item in findings
                if item.action == "deny"
            }
            messages = list(dict.fromkeys(item.message for item in findings))
            paths = list(dict.fromkeys(item.path for item in findings))
            error = ""
        except Exception as exc:
            actual_result = "error"
            actual_columns = set()
            messages = []
            paths = []
            error = f"{type(exc).__name__}: {exc}"

        expected_columns = split_expected(scenario["expected_columns"])
        status = (
            "PASS"
            if actual_result == scenario["expected_result"]
            and actual_columns == expected_columns
            else "FAIL"
        )
        if status == "FAIL":
            failed += 1

        results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "category": scenario["category"],
                "rule_set": scenario["rule_set"],
                "expected_result": scenario["expected_result"],
                "actual_result": actual_result,
                "expected_columns": ",".join(sorted(expected_columns)),
                "actual_columns": ",".join(sorted(actual_columns)),
                "status": status,
                "message": " | ".join(messages),
                "flow_path": " | ".join(paths),
                "error": error,
                "description": scenario["description"],
                "sql": scenario["sql"],
            }
        )

    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(results[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(results)

    passed = len(results) - failed
    summary = f"SQL scenarios: {len(results)}, PASS: {passed}, FAIL: {failed}"
    print(summary)
    print(output_path)
    (ROOT / "scenario-summary.txt").write_text(
        summary + "\n", encoding="utf-8"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
