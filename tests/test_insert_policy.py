from __future__ import annotations

from mcp_sql_result_guard.guard import inspect_sql


def test_insert_inputs_are_not_mcp_result_columns(rules_one, rules_two):
    one_column_sql = [
        "INSERT INTO archive(user_id) SELECT user_id FROM users",
        "INSERT INTO archive(user_hash) SELECT MD5(user_id) FROM users",
        (
            "WITH x AS (SELECT user_id FROM users) "
            "INSERT INTO archive(user_id) SELECT user_id FROM x"
        ),
        (
            "WITH a AS (SELECT user_id AS x FROM users), "
            "b AS (SELECT x AS y FROM a) "
            "INSERT INTO archive(user_id) SELECT y FROM b"
        ),
        (
            "WITH x AS (SELECT * FROM users) "
            "INSERT INTO archive SELECT * FROM x"
        ),
        "INSERT INTO archive(user_id) VALUES ('u1')",
    ]
    for sql in one_column_sql:
        assert inspect_sql(sql, rules_one) == []

    two_column_sql = (
        "WITH x AS (SELECT user_id, email FROM users) "
        "INSERT INTO archive(user_id, email) SELECT user_id, email FROM x"
    )
    assert inspect_sql(two_column_sql, rules_two) == []


def test_insert_returning_is_the_output_boundary(rules_one):
    safe_sql = (
        "INSERT INTO archive(user_id) SELECT user_id FROM users "
        "RETURNING archive_id"
    )
    assert inspect_sql(safe_sql, rules_one) == []

    denied_sql = (
        "INSERT INTO archive(user_id) SELECT user_id FROM users "
        "RETURNING user_id"
    )
    findings = inspect_sql(denied_sql, rules_one)
    assert {finding.column_name.casefold() for finding in findings} == {"user_id"}
    assert all("RETURNING" in finding.path for finding in findings)
