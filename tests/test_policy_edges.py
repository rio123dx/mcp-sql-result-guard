from __future__ import annotations

from pathlib import Path

from mcp_sql_result_guard.guard import inspect_sql, load_rules


def test_count_can_be_disabled_per_tsv(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tuser_id\t\tdeny\tno masks\n",
        encoding="utf-8",
    )
    findings = inspect_sql("SELECT COUNT(user_id) FROM users", load_rules(path))
    assert findings
    assert findings[0].usage == "count"


def test_count_distinct_can_be_independently_disabled(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tuser_id\tcount\tdeny\tonly normal count\n",
        encoding="utf-8",
    )
    findings = inspect_sql("SELECT COUNT(DISTINCT user_id) FROM users", load_rules(path))
    assert findings
    assert findings[0].usage == "count_distinct"


def test_warn_action_does_not_become_deny(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tuser_id\tcount\twarn\twarn only\n",
        encoding="utf-8",
    )
    findings = inspect_sql("SELECT user_id FROM users", load_rules(path))
    assert findings[0].action == "warn"


def test_internal_star_is_allowed_when_not_returned(rules_one):
    assert inspect_sql("SELECT COUNT(*) FROM (SELECT * FROM users) x", rules_one) == []


def test_alias_named_sensitive_does_not_false_positive(rules_one):
    assert inspect_sql("SELECT 1 AS user_id", rules_one) == []


def test_sensitive_alias_from_constant_through_two_ctes(rules_one):
    sql = "WITH a AS (SELECT 1 AS user_id), b AS (SELECT user_id FROM a) SELECT user_id FROM b"
    assert inspect_sql(sql, rules_one) == []
