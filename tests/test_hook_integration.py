from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from mcp_sql_result_guard.guard import extract_sql_strings


def run_hook(project_root: Path, stdin_text: str, rules_path: Path, *, fail_open: bool = True):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")
    env["MCP_SQL_RESULT_GUARD_RULES"] = str(rules_path)
    env["MCP_SQL_RESULT_GUARD_FAIL_OPEN"] = "true" if fail_open else "false"
    return subprocess.run(
        [sys.executable, "-m", "mcp_sql_result_guard"],
        input=stdin_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def hook_json(sql=None, tool_input=None):
    if tool_input is None:
        tool_input = {"sql": sql}
    return json.dumps(
        {
            "session_id": "test-session",
            "turn_id": "test-turn",
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__warehouse__execute_sql",
            "tool_use_id": "tool-1",
            "tool_input": tool_input,
        },
        ensure_ascii=False,
    )


def test_internal_sensitive_use_allows_with_no_output(project_root):
    result = run_hook(
        project_root,
        hook_json("SELECT name FROM users WHERE user_id='u1'"),
        project_root / "tests" / "data" / "rules_one.tsv",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_sensitive_final_output_denies(project_root):
    result = run_hook(
        project_root,
        hook_json("WITH x AS (SELECT user_id AS uid FROM users) SELECT uid FROM x"),
        project_root / "tests" / "data" / "rules_one.tsv",
    )
    payload = json.loads(result.stdout)
    output = payload["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    assert "user_id" in output["permissionDecisionReason"]
    assert "path:" in output["permissionDecisionReason"]


def test_two_columns_are_both_reported(project_root):
    result = run_hook(
        project_root,
        hook_json("SELECT user_id, email FROM users"),
        project_root / "tests" / "data" / "rules_two.tsv",
    )
    reason = json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "user_id" in reason
    assert "email" in reason


def test_nested_mcp_arguments_are_searched(project_root):
    tool_input = {"request": {"payload": [{"query": "SELECT user_id FROM users"}]}}
    result = run_hook(
        project_root,
        hook_json(tool_input=tool_input),
        project_root / "tests" / "data" / "rules_one.tsv",
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_multiple_sql_arguments_deny_if_any_output_exposes(project_root):
    tool_input = {
        "primary": {"sql": "SELECT name FROM users WHERE user_id='u1'"},
        "fallback": {"statement": "SELECT user_id FROM users"},
    }
    result = run_hook(
        project_root,
        hook_json(tool_input=tool_input),
        project_root / "tests" / "data" / "rules_one.tsv",
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_non_sql_tool_input_passes(project_root):
    result = run_hook(
        project_root,
        hook_json(tool_input={"schema": "public", "table": "users"}),
        project_root / "tests" / "data" / "rules_one.tsv",
    )
    assert result.stdout == ""


def test_warn_action_returns_additional_context(project_root, tmp_path):
    rules_path = tmp_path / "warn.tsv"
    rules_path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tuser_id\tcount\twarn\twarning only\n",
        encoding="utf-8",
    )
    result = run_hook(project_root, hook_json("SELECT user_id FROM users"), rules_path)
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert "permissionDecision" not in output
    assert "additionalContext" in output


def test_malformed_json_warns_when_fail_open(project_root):
    result = run_hook(
        project_root,
        "{bad json",
        project_root / "tests" / "data" / "rules_one.tsv",
        fail_open=True,
    )
    assert "additionalContext" in json.loads(result.stdout)["hookSpecificOutput"]


def test_malformed_json_denies_when_fail_closed(project_root):
    result = run_hook(
        project_root,
        "{bad json",
        project_root / "tests" / "data" / "rules_one.tsv",
        fail_open=False,
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_parse_error_warns_fail_open(project_root):
    result = run_hook(
        project_root,
        hook_json("SELECT ( FROM"),
        project_root / "tests" / "data" / "rules_one.tsv",
        fail_open=True,
    )
    assert "additionalContext" in json.loads(result.stdout)["hookSpecificOutput"]


def test_extract_sql_strings_supports_expected_keys():
    value = {
        "sql": "SELECT 1",
        "nested": [{"query": "SELECT 2"}, {"statement": "SELECT 3"}, {"description": "SELECT 4"}],
    }
    assert extract_sql_strings(value) == ["SELECT 1", "SELECT 2", "SELECT 3"]
