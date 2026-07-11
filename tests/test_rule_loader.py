from __future__ import annotations

from pathlib import Path

import pytest

from mcp_sql_result_guard.guard import RuleConfigError, find_rule, load_rules, parse_bool


def test_rules_load_utf8_bom(project_root):
    rules = load_rules(project_root / "tests" / "data" / "rules_two.tsv")
    assert find_rule("USER_ID", rules) is not None
    assert find_rule("email", rules) is not None


def test_wildcard_rule(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tphone_*\tcount\tdeny\tphone\n",
        encoding="utf-8",
    )
    rules = load_rules(path)
    assert find_rule("phone_mobile", rules).pattern == "phone_*"


def test_disabled_rule_is_ignored(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "0\tuser_id\tcount\tdeny\tdisabled\n",
        encoding="utf-8",
    )
    assert load_rules(path) == []


def test_invalid_enabled(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "maybe\tuser_id\tcount\tdeny\tx\n",
        encoding="utf-8",
    )
    with pytest.raises(RuleConfigError):
        load_rules(path)


def test_missing_header(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text("enabled\tcolumn_pattern\n1\tuser_id\n", encoding="utf-8")
    with pytest.raises(RuleConfigError):
        load_rules(path)


def test_unknown_allow(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tuser_id\tmagic\tdeny\tx\n",
        encoding="utf-8",
    )
    with pytest.raises(RuleConfigError):
        load_rules(path)


def test_unknown_action(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tuser_id\tcount\tblock\tx\n",
        encoding="utf-8",
    )
    with pytest.raises(RuleConfigError):
        load_rules(path)


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_parse_bool_true(value):
    assert parse_bool(value, field_name="x") is True


@pytest.mark.parametrize("value", ["0", "false", "NO", "off", ""])
def test_parse_bool_false(value):
    assert parse_bool(value, field_name="x") is False


def test_aggregate_reduction_allow_value(tmp_path: Path):
    path = tmp_path / "rules.tsv"
    path.write_text(
        "enabled\tcolumn_pattern\tallow\taction\tnote\n"
        "1\tuser_id\taggregate_reduction\tdeny\tstatistics\n",
        encoding="utf-8",
    )
    rule = find_rule("user_id", load_rules(path))
    assert rule is not None
    assert rule.allowed_usages == frozenset({"aggregate_reduction"})
