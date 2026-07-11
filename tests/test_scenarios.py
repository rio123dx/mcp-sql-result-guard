from __future__ import annotations

from mcp_sql_result_guard.guard import inspect_sql


def split_columns(value: str) -> set[str]:
    return {item.strip().casefold() for item in value.split(",") if item.strip()}


def test_sql_scenario(scenario, rules_one, rules_two):
    rules = rules_one if scenario["rule_set"] == "one" else rules_two
    findings = inspect_sql(scenario["sql"], rules)
    actual_result = "deny" if any(item.action == "deny" for item in findings) else (
        "warn" if findings else "allow"
    )
    actual_columns = {item.column_name.casefold() for item in findings if item.action == "deny"}
    assert actual_result == scenario["expected_result"]
    assert actual_columns == split_columns(scenario["expected_columns"])
