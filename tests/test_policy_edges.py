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


def test_aggregate_reduction_can_be_disabled_per_tsv(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tuser_id\tcount,count_distinct,approx_count\tdeny\tcounts only\n",
        encoding="utf-8",
    )
    findings = inspect_sql("SELECT SUM(user_id) FROM users", load_rules(path))
    assert findings
    assert findings[0].usage == "aggregate_reduction"


def test_aggregate_reduction_is_count_umbrella(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tuser_id\taggregate_reduction\tdeny\treductions\n",
        encoding="utf-8",
    )
    rules = load_rules(path)
    assert inspect_sql("SELECT COUNT(user_id) FROM users", rules) == []
    assert inspect_sql("SELECT COUNT(DISTINCT user_id) FROM users", rules) == []
    assert inspect_sql("SELECT APPROXIMATE COUNT(DISTINCT user_id) FROM users", rules) == []


def test_value_collecting_aggregate_is_allowed_when_not_returned(rules_one):
    sql = (
        "WITH x AS ("
        "SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids "
        "FROM users"
        ") SELECT COUNT(*) FROM x"
    )
    assert inspect_sql(sql, rules_one) == []


def test_reduction_aggregate_is_traced_through_cte(rules_one):
    sql = "WITH x AS (SELECT SUM(user_id) AS total FROM users) SELECT total FROM x"
    assert inspect_sql(sql, rules_one) == []


def test_ordered_set_aggregate_traces_order_value(rules_one):
    sql = "SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY user_id) FROM users"
    findings = inspect_sql(sql, rules_one)
    assert findings
    assert findings[0].column_name == "user_id"


def test_redshift_approximate_percentile_is_denied(rules_one):
    sql = (
        "SELECT APPROXIMATE PERCENTILE_DISC(0.5) "
        "WITHIN GROUP (ORDER BY user_id) FROM users"
    )
    findings = inspect_sql(sql, rules_one)
    assert findings
    assert findings[0].column_name == "user_id"


def test_redshift_approximate_percentile_phrase_in_literal_is_unchanged(rules_one):
    sql = "SELECT 'APPROXIMATE PERCENTILE_DISC' AS label FROM users"
    assert inspect_sql(sql, rules_one) == []


def test_redshift_approximate_percentile_alias_is_not_rewritten(rules_one):
    sql = "SELECT approximate percentile_disc FROM users"
    assert inspect_sql(sql, rules_one) == []


def test_redshift_approximate_percentile_phrase_in_comment_is_unchanged(rules_one):
    sql = "SELECT 1 -- APPROXIMATE PERCENTILE_DISC(0.5)\nFROM users"
    assert inspect_sql(sql, rules_one) == []
