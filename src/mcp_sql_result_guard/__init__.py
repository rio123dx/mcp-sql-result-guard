"""Public API for mcp-sql-result-guard."""

from .guard import (
    AnalysisError,
    Decision,
    Finding,
    Rule,
    RuleConfigError,
    evaluate_hook,
    inspect_sql,
    load_rules,
)

__all__ = [
    "AnalysisError",
    "Decision",
    "Finding",
    "Rule",
    "RuleConfigError",
    "evaluate_hook",
    "inspect_sql",
    "load_rules",
]

__version__ = "0.2.0"
