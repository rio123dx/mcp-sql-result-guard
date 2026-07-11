#!/usr/bin/env python3
"""Codex PreToolUse hook that blocks sensitive values from SQL result sets.

The policy is intentionally output-oriented:

* Sensitive columns may be used internally in WHERE, JOIN, GROUP BY, ORDER BY,
  CTEs, and subqueries.
* A query is blocked only when a final result column (or RETURNING column)
  exposes a sensitive value directly or through a value-preserving transform.
* COUNT masks and configured statistical reduction aggregates are treated as
  safe outputs; value-selecting and value-collecting aggregates are not.
* Predicates, EXISTS, CASE conditions, and window partition/order clauses are
  control-only and do not expose the underlying value.

Rules are stored in a TSV file so new column names can be added without editing
Python. This is a lightweight guardrail, not a database security boundary.
"""

from __future__ import annotations

import csv
import fnmatch
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.tokens import TokenType, Tokenizer
from sqlglot.optimizer.scope import Scope, build_scope


DEFAULT_RULES_PATH = Path(__file__).with_name("default_rules.tsv")
SQL_ARGUMENT_KEYS = {"sql", "query", "statement"}
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}
AGGREGATE_REDUCTION_USAGE = "aggregate_reduction"
COUNT_USAGES = {"count", "count_distinct", "approx_count"}
SUPPORTED_USAGES = COUNT_USAGES | {AGGREGATE_REDUCTION_USAGE}
SUPPORTED_ACTIONS = {"deny", "warn"}

# These aggregate classes return a scalar statistical/logical reduction rather
# than selecting or collecting source values. The TSV must still opt a column
# into aggregate_reduction. Unknown aggregates remain value-preserving by
# default and are therefore denied when a sensitive value reaches final output.
SAFE_REDUCTION_AGGREGATE_TYPES = tuple(
    aggregate_type
    for aggregate_type in (
        getattr(exp, "Sum", None),
        getattr(exp, "Avg", None),
        getattr(exp, "Stddev", None),
        getattr(exp, "StddevPop", None),
        getattr(exp, "StddevSamp", None),
        getattr(exp, "Variance", None),
        getattr(exp, "VariancePop", None),
        getattr(exp, "Corr", None),
        getattr(exp, "CovarPop", None),
        getattr(exp, "CovarSamp", None),
        getattr(exp, "LogicalAnd", None),
        getattr(exp, "LogicalOr", None),
    )
    if isinstance(aggregate_type, type)
)


@dataclass(frozen=True)
class Rule:
    pattern: str
    allowed_usages: frozenset[str]
    action: str
    note: str
    line_number: int


@dataclass(frozen=True)
class Finding:
    column_name: str
    output_expression: str
    usage: str
    action: str
    note: str
    path: str
    allowed_usages: frozenset[str]

    @property
    def message(self) -> str:
        base = (
            f"Final output `{self.output_expression}` may expose sensitive column "
            f"`{self.column_name}`"
        )
        if self.path:
            base += f" (path: {self.path})"
        if self.note:
            base += f" — {self.note}"
        return base


@dataclass(frozen=True)
class Decision:
    kind: str  # allow / deny / warn
    messages: tuple[str, ...] = ()


class RuleConfigError(ValueError):
    """Raised when the TSV rule file is malformed."""


class AnalysisError(RuntimeError):
    """Raised when an output query cannot be analysed safely."""


def parse_bool(value: str, *, field_name: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise RuleConfigError(
        f"{field_name} must be one of 1/0, true/false, yes/no, on/off: {value!r}"
    )


def load_rules(path: Path) -> list[Rule]:
    if not path.exists():
        raise FileNotFoundError(f"Rules file does not exist: {path}")

    rules: list[Rule] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        required = {"enabled", "column_pattern", "allow", "action", "note"}
        actual = set(reader.fieldnames or [])
        missing = required - actual
        if missing:
            raise RuleConfigError(f"Missing required TSV columns: {', '.join(sorted(missing))}")

        for line_number, row in enumerate(reader, start=2):
            enabled = parse_bool(row.get("enabled") or "", field_name=f"line {line_number} enabled")
            if not enabled:
                continue

            pattern = (row.get("column_pattern") or "").strip()
            if not pattern:
                raise RuleConfigError(f"line {line_number}: column_pattern is empty")

            allowed_usages = frozenset(
                item.strip().casefold()
                for item in (row.get("allow") or "").split(",")
                if item.strip()
            )
            unknown_usages = allowed_usages - SUPPORTED_USAGES
            if unknown_usages:
                raise RuleConfigError(
                    f"line {line_number}: unsupported allow value(s): {', '.join(sorted(unknown_usages))}"
                )

            action = (row.get("action") or "deny").strip().casefold()
            if action not in SUPPORTED_ACTIONS:
                raise RuleConfigError(f"line {line_number}: action must be deny or warn")

            rules.append(
                Rule(
                    pattern=pattern,
                    allowed_usages=allowed_usages,
                    action=action,
                    note=(row.get("note") or "").strip(),
                    line_number=line_number,
                )
            )

    return rules


def _normalize_sql_for_parser(sql: str, *, dialect: str) -> str:
    """Normalize parser gaps without rewriting literals or comments.

    SQLGlot 26.x does not parse Redshift's two-keyword
    ``APPROXIMATE PERCENTILE_DISC`` spelling. Token positions let us collapse
    only executable keyword occurrences to ``PERCENTILE_DISC`` while leaving
    string literals, quoted identifiers, and comments untouched. The guard
    treats the approximate form with the same value-flow semantics as the
    discrete percentile form.
    """
    if dialect.casefold() != "redshift":
        return sql

    try:
        tokens = Tokenizer(dialect=dialect).tokenize(sql)
    except Exception:
        return sql

    replacements: list[tuple[int, int, str]] = []
    for index in range(len(tokens) - 2):
        first, second, third = tokens[index : index + 3]
        if (
            first.token_type is TokenType.VAR
            and second.token_type is TokenType.VAR
            and third.token_type is TokenType.L_PAREN
            and first.text.casefold() == "approximate"
            and second.text.casefold() == "percentile_disc"
            and sql[first.end + 1 : second.start].strip() == ""
            and sql[second.end + 1 : third.start].strip() == ""
        ):
            replacements.append((first.start, second.end + 1, "PERCENTILE_DISC"))

    for start, end, replacement in reversed(replacements):
        sql = f"{sql[:start]}{replacement}{sql[end:]}"
    return sql


def extract_sql_strings(value: Any) -> list[str]:
    """Recursively find SQL-like arguments in an MCP tool_input object."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in SQL_ARGUMENT_KEYS and isinstance(child, str) and child.strip():
                found.append(child)
            else:
                found.extend(extract_sql_strings(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(extract_sql_strings(child))
    return found


def find_rule(column_name: str, rules: Iterable[Rule]) -> Rule | None:
    normalized_name = column_name.casefold()
    for rule in rules:
        if rule.pattern.casefold() == "__select_star__":
            continue
        if fnmatch.fnmatchcase(normalized_name, rule.pattern.casefold()):
            return rule
    return None


def find_star_rule(rules: Iterable[Rule]) -> Rule | None:
    for rule in rules:
        if rule.pattern.casefold() == "__select_star__":
            return rule
    return None


def _usage_is_allowed(finding: Finding, usage: str) -> bool:
    if usage in finding.allowed_usages:
        return True
    # aggregate_reduction is a convenience umbrella for count-like masks as
    # well as the explicitly allowlisted statistical reduction aggregates.
    return (
        AGGREGATE_REDUCTION_USAGE in finding.allowed_usages
        and usage in COUNT_USAGES
    )


def _deduplicate_findings(findings: Iterable[Finding]) -> list[Finding]:
    seen: set[tuple[str, str, str, str, str, str, str]] = set()
    result: list[Finding] = []
    for finding in findings:
        key = (
            finding.column_name.casefold(),
            finding.output_expression,
            finding.usage,
            finding.action,
            finding.note,
            finding.path,
            ",".join(sorted(finding.allowed_usages)),
        )
        if key not in seen:
            seen.add(key)
            result.append(finding)
    return result


def _iter_expressions(value: Any) -> Iterator[exp.Expression]:
    if isinstance(value, exp.Expression):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_expressions(item)


class OutputFlowAnalyzer:
    """Follow only value flow into the final result columns."""

    def __init__(self, rules: list[Rule], *, dialect: str = "redshift") -> None:
        self.rules = rules
        self.dialect = dialect
        self._active: set[tuple[int, int]] = set()

    def inspect_query(self, query: exp.Query) -> list[Finding]:
        scope = build_scope(query)
        if scope is None:
            raise AnalysisError("Could not build a scope for the query")
        findings: list[Finding] = []
        for index, output in enumerate(self._query_outputs(scope), start=1):
            output_sql = output.sql(dialect=self.dialect)
            findings.extend(
                self._inspect_value(
                    output,
                    scope,
                    output_expression=output_sql,
                    path=f"final output column {index}",
                )
            )
        return _deduplicate_findings(findings)

    def inspect_returning(self, statement: exp.Expression, returning: exp.Returning) -> list[Finding]:
        # DML RETURNING does not have a normal SELECT Scope. Treat referenced
        # columns as base-table columns and still apply expression masking rules.
        pseudo_select = exp.select(*[item.copy() for item in returning.expressions])
        scope = build_scope(pseudo_select)
        if scope is None:
            raise AnalysisError("Could not build a scope for the RETURNING clause")
        findings: list[Finding] = []
        for index, output in enumerate(pseudo_select.selects, start=1):
            output_sql = output.sql(dialect=self.dialect)
            findings.extend(
                self._inspect_value(
                    output,
                    scope,
                    output_expression=output_sql,
                    path=f"RETURNING column {index}",
                )
            )
        return _deduplicate_findings(findings)

    def _query_outputs(self, scope: Scope) -> list[exp.Expression]:
        expression = scope.expression
        if isinstance(expression, exp.SetOperation):
            # A UNION/INTERSECT/EXCEPT result can contain values from either side.
            # Return corresponding outputs from every branch so any sensitive
            # branch is caught.
            outputs: list[exp.Expression] = []
            for branch in scope.union_scopes:
                outputs.extend(self._query_outputs(branch))
            return outputs
        if isinstance(expression, exp.Select):
            return list(expression.selects)
        return list(getattr(expression, "selects", []) or [])

    def _inspect_value(
        self,
        node: exp.Expression,
        scope: Scope,
        *,
        output_expression: str,
        path: str,
    ) -> list[Finding]:
        node_key = (id(scope), id(node))
        if node_key in self._active:
            return []
        self._active.add(node_key)
        try:
            return self._inspect_value_inner(
                node,
                scope,
                output_expression=output_expression,
                path=path,
            )
        finally:
            self._active.remove(node_key)

    def _inspect_value_inner(
        self,
        node: exp.Expression,
        scope: Scope,
        *,
        output_expression: str,
        path: str,
    ) -> list[Finding]:
        if isinstance(node, exp.Alias):
            return self._inspect_value(
                node.this,
                scope,
                output_expression=output_expression,
                path=f"{path} → alias",
            )

        if isinstance(node, exp.Paren):
            return self._inspect_value(
                node.this,
                scope,
                output_expression=output_expression,
                path=f"{path} → parentheses",
            )

        if isinstance(node, exp.Column):
            if isinstance(node.this, exp.Star):
                return self._inspect_star(
                    scope,
                    qualifier=node.table or None,
                    output_expression=output_expression,
                    path=f"{path} → {node.sql(dialect=self.dialect)}",
                )
            return self._inspect_column(
                node,
                scope,
                output_expression=output_expression,
                path=path,
            )

        if isinstance(node, exp.Star):
            return self._inspect_star(
                scope,
                qualifier=None,
                output_expression=output_expression,
                path=f"{path} → *",
            )

        # Explicit masks. The rule TSV decides whether each mask is allowed.
        if isinstance(node, exp.Count):
            if isinstance(node.this, exp.Star):
                return []
            usage = "count_distinct" if isinstance(node.this, exp.Distinct) else "count"
            inner = self._inspect_value(
                node.this,
                scope,
                output_expression=output_expression,
                path=f"{path} → {usage}",
            )
            return [
                replace(finding, usage=usage)
                for finding in inner
                if not _usage_is_allowed(finding, usage)
            ]
        if isinstance(node, exp.ApproxDistinct):
            usage = "approx_count"
            inner = self._inspect_value(
                node.this,
                scope,
                output_expression=output_expression,
                path=f"{path} → {usage}",
            )
            return [
                replace(finding, usage=usage)
                for finding in inner
                if not _usage_is_allowed(finding, usage)
            ]
        if hasattr(exp, "CountIf") and isinstance(node, exp.CountIf):
            return []

        if SAFE_REDUCTION_AGGREGATE_TYPES and isinstance(
            node, SAFE_REDUCTION_AGGREGATE_TYPES
        ):
            usage = AGGREGATE_REDUCTION_USAGE
            findings: list[Finding] = []
            for key, value in node.args.items():
                if key in {"order", "partition_by", "spec", "where", "on"}:
                    continue
                for child in _iter_expressions(value):
                    findings.extend(
                        self._inspect_value(
                            child,
                            scope,
                            output_expression=output_expression,
                            path=f"{path} → {usage} → {type(node).__name__}.{key}",
                        )
                    )
            return [
                replace(finding, usage=usage)
                for finding in findings
                if not _usage_is_allowed(finding, usage)
            ]

        # A predicate/EXISTS returns a boolean rather than the source value.
        if isinstance(node, exp.Predicate):
            return []
        if isinstance(node, (exp.And, exp.Or, exp.Not)):
            return []

        # Conditions control which branch is chosen. Only branch values flow out.
        if isinstance(node, exp.Case):
            findings: list[Finding] = []
            for if_node in node.args.get("ifs") or []:
                true_value = if_node.args.get("true")
                if isinstance(true_value, exp.Expression):
                    findings.extend(
                        self._inspect_value(
                            true_value,
                            scope,
                            output_expression=output_expression,
                            path=f"{path} → CASE result",
                        )
                    )
            default = node.args.get("default")
            if isinstance(default, exp.Expression):
                findings.extend(
                    self._inspect_value(
                        default,
                        scope,
                        output_expression=output_expression,
                        path=f"{path} → CASE ELSE",
                    )
                )
            return findings

        if isinstance(node, exp.If):
            findings: list[Finding] = []
            for key in ("true", "false"):
                value = node.args.get(key)
                if isinstance(value, exp.Expression):
                    findings.extend(
                        self._inspect_value(
                            value,
                            scope,
                            output_expression=output_expression,
                            path=f"{path} → IF {key}",
                        )
                    )
            return findings

        # Window partition/order/frame clauses only control computation. The
        # window function itself may still expose a value (FIRST_VALUE, LAG...).
        if isinstance(node, exp.Window):
            return self._inspect_value(
                node.this,
                scope,
                output_expression=output_expression,
                path=f"{path} → window value",
            )

        # FILTER conditions do not become cell values.
        if isinstance(node, exp.Filter):
            return self._inspect_value(
                node.this,
                scope,
                output_expression=output_expression,
                path=f"{path} → filtered value",
            )
        if isinstance(node, exp.WithinGroup):
            findings = self._inspect_value(
                node.this,
                scope,
                output_expression=output_expression,
                path=f"{path} → aggregate value",
            )
            # LISTAGG/GROUP_CONCAT returns its first argument; WITHIN GROUP order
            # is only control metadata. For other ordered-set aggregates
            # (PERCENTILE_CONT/DISC, MODE, or unknown functions), the ORDER BY
            # expression is the value distribution being returned and must be
            # traced. Unknown ordered-set aggregates therefore fail safely.
            if not isinstance(node.this, exp.GroupConcat):
                order = node.args.get("expression")
                if isinstance(order, exp.Order):
                    for ordered in order.expressions:
                        value = ordered.this if isinstance(ordered, exp.Ordered) else ordered
                        if isinstance(value, exp.Expression):
                            findings.extend(
                                self._inspect_value(
                                    value,
                                    scope,
                                    output_expression=output_expression,
                                    path=f"{path} → ordered-set value",
                                )
                            )
            return findings

        if isinstance(node, exp.Subquery):
            sub_scope = build_scope(node.this)
            if sub_scope is None:
                raise AnalysisError("Could not build a scope for the scalar subquery")
            findings: list[Finding] = []
            for inner_index, inner_output in enumerate(self._query_outputs(sub_scope), start=1):
                findings.extend(
                    self._inspect_value(
                        inner_output,
                        sub_scope,
                        output_expression=output_expression,
                        path=f"{path} → scalar subquery column {inner_index}",
                    )
                )
            return findings

        if isinstance(node, exp.Query):
            sub_scope = build_scope(node)
            if sub_scope is None:
                raise AnalysisError("Could not build a scope for the nested query")
            findings: list[Finding] = []
            for inner_index, inner_output in enumerate(self._query_outputs(sub_scope), start=1):
                findings.extend(
                    self._inspect_value(
                        inner_output,
                        sub_scope,
                        output_expression=output_expression,
                        path=f"{path} → nested query column {inner_index}",
                    )
                )
            return findings

        # Literals and identifiers alone contain no table value.
        if isinstance(node, (exp.Literal, exp.Null, exp.Boolean, exp.Identifier, exp.Var)):
            return []

        # Other transforms and aggregates (CAST, hash, substring, MIN/MAX,
        # LISTAGG/ARRAY_AGG/JSON aggregates, quantiles, LAG/FIRST_VALUE, unknown
        # aggregate functions...) preserve, select, or collect source values.
        # Follow all expression-valued arguments and deny sensitive final output.
        findings: list[Finding] = []
        for key, value in node.args.items():
            # Generic ordering metadata is control-only. Value arguments are
            # inspected through the main function/aggregate node.
            if key in {"order", "partition_by", "spec", "where", "on"}:
                continue
            for child in _iter_expressions(value):
                findings.extend(
                    self._inspect_value(
                        child,
                        scope,
                        output_expression=output_expression,
                        path=f"{path} → {type(node).__name__}.{key}",
                    )
                )
        return findings

    def _inspect_column(
        self,
        column: exp.Column,
        scope: Scope,
        *,
        output_expression: str,
        path: str,
    ) -> list[Finding]:
        name = column.name
        qualifier = column.table

        if qualifier:
            source = scope.sources.get(qualifier)
            if isinstance(source, Scope):
                resolved = self._resolve_derived_column(
                    source,
                    name,
                    output_expression=output_expression,
                    path=f"{path} → {qualifier}.{name}",
                )
                if resolved is not None:
                    return resolved
            return self._base_column_finding(
                name,
                output_expression=output_expression,
                path=f"{path} → base column {column.sql(dialect=self.dialect)}",
            )

        derived_matches: list[Finding] = []
        matched_derived = False
        for source_name, source in scope.sources.items():
            if not isinstance(source, Scope):
                continue
            resolved = self._resolve_derived_column(
                source,
                name,
                output_expression=output_expression,
                path=f"{path} → {source_name}.{name}",
            )
            if resolved is not None:
                matched_derived = True
                derived_matches.extend(resolved)

        has_base_source = any(not isinstance(source, Scope) for source in scope.sources.values())
        if matched_derived and not has_base_source:
            return derived_matches

        # No derived alias matched, or the unqualified reference is ambiguous
        # because base and derived sources coexist. Check the literal column name.
        direct = self._base_column_finding(
            name,
            output_expression=output_expression,
            path=f"{path} → base/unqualified column {name}",
        )
        return derived_matches + direct

    def _resolve_derived_column(
        self,
        source_scope: Scope,
        column_name: str,
        *,
        output_expression: str,
        path: str,
    ) -> list[Finding] | None:
        names = self._output_names(source_scope)
        matching_positions = [
            index for index, name in enumerate(names) if name and name.casefold() == column_name.casefold()
        ]

        if matching_positions:
            findings: list[Finding] = []
            for position in matching_positions:
                for branch_scope, branch_output in self._outputs_at_position(source_scope, position):
                    findings.extend(
                        self._inspect_value(
                            branch_output,
                            branch_scope,
                            output_expression=output_expression,
                            path=f"{path} → derived output {position + 1}",
                        )
                    )
            return findings

        # If a derived query contains an unresolved star, an outer reference to
        # a configured sensitive name may have come through that star.
        if self._scope_has_unresolved_star(source_scope):
            direct = self._base_column_finding(
                column_name,
                output_expression=output_expression,
                path=f"{path} → unresolved derived *",
            )
            if direct:
                return direct

        return None

    def _output_names(self, scope: Scope) -> list[str]:
        if scope.outer_columns:
            return list(scope.outer_columns)
        expression = scope.expression
        return list(getattr(expression, "named_selects", []) or [])

    def _outputs_at_position(self, scope: Scope, position: int) -> list[tuple[Scope, exp.Expression]]:
        if scope.is_union:
            result: list[tuple[Scope, exp.Expression]] = []
            for branch in scope.union_scopes:
                outputs = self._query_outputs(branch)
                if position < len(outputs):
                    result.append((branch, outputs[position]))
            return result

        outputs = self._query_outputs(scope)
        if position < len(outputs):
            return [(scope, outputs[position])]
        return []

    def _scope_has_unresolved_star(self, scope: Scope) -> bool:
        if scope.is_union:
            return any(self._scope_has_unresolved_star(branch) for branch in scope.union_scopes)
        for output in self._query_outputs(scope):
            if isinstance(output, exp.Star):
                return True
            if isinstance(output, exp.Column) and isinstance(output.this, exp.Star):
                return True
        return False

    def _inspect_star(
        self,
        scope: Scope,
        *,
        qualifier: str | None,
        output_expression: str,
        path: str,
    ) -> list[Finding]:
        selected_sources: list[tuple[str, Any]] = []
        if qualifier:
            source = scope.sources.get(qualifier)
            if source is not None:
                selected_sources.append((qualifier, source))
        else:
            selected_sources.extend(scope.sources.items())

        findings: list[Finding] = []
        if not selected_sources:
            findings.extend(self._unknown_star_finding(output_expression=output_expression, path=path))
            return findings

        for source_name, source in selected_sources:
            if isinstance(source, Scope):
                for position, (branch_scope, output) in enumerate(
                    self._all_source_outputs(source), start=1
                ):
                    findings.extend(
                        self._inspect_value(
                            output,
                            branch_scope,
                            output_expression=output_expression,
                            path=f"{path} → {source_name}.* output {position}",
                        )
                    )
            else:
                findings.extend(
                    self._unknown_star_finding(
                        output_expression=output_expression,
                        path=f"{path} → base table {source_name}.*",
                    )
                )
        return findings

    def _all_source_outputs(self, scope: Scope) -> list[tuple[Scope, exp.Expression]]:
        if scope.is_union:
            result: list[tuple[Scope, exp.Expression]] = []
            for branch in scope.union_scopes:
                result.extend(self._all_source_outputs(branch))
            return result
        return [(scope, output) for output in self._query_outputs(scope)]

    def _base_column_finding(
        self,
        column_name: str,
        *,
        output_expression: str,
        path: str,
    ) -> list[Finding]:
        rule = find_rule(column_name, self.rules)
        if rule is None:
            return []
        return [
            Finding(
                column_name=column_name,
                output_expression=output_expression,
                usage="value_output",
                action=rule.action,
                note=rule.note,
                path=path,
                allowed_usages=rule.allowed_usages,
            )
        ]

    def _unknown_star_finding(self, *, output_expression: str, path: str) -> list[Finding]:
        rule = find_star_rule(self.rules)
        if rule is None:
            return []
        return [
            Finding(
                column_name="__SELECT_STAR__",
                output_expression=output_expression,
                usage="unknown_star_output",
                action=rule.action,
                note=rule.note,
                path=path,
                allowed_usages=rule.allowed_usages,
            )
        ]


def inspect_statement(
    tree: exp.Expression,
    rules: list[Rule],
    *,
    dialect: str = "redshift",
) -> list[Finding]:
    analyzer = OutputFlowAnalyzer(rules, dialect=dialect)

    # Only a top-level Query returns a normal result set to the MCP caller.
    if isinstance(tree, exp.Query):
        # SELECT ... INTO / CTAS-like query forms do not return result rows.
        if isinstance(tree, exp.Select) and tree.args.get("into") is not None:
            return []
        return analyzer.inspect_query(tree)

    returning = tree.args.get("returning")
    if isinstance(returning, exp.Returning):
        return analyzer.inspect_returning(tree, returning)

    # INSERT/UPDATE/DELETE without RETURNING, CREATE AS, UNLOAD, EXPLAIN, etc.
    # may use sensitive columns but do not place their values in the MCP result set.
    return []


def inspect_sql(
    sql: str,
    rules: list[Rule],
    *,
    dialect: str = "redshift",
) -> list[Finding]:
    normalized_sql = _normalize_sql_for_parser(sql, dialect=dialect)
    statements = sqlglot.parse(normalized_sql, read=dialect)
    findings: list[Finding] = []
    for statement in statements:
        if statement is not None:
            findings.extend(inspect_statement(statement, rules, dialect=dialect))
    return _deduplicate_findings(findings)


def _messages_from_findings(findings: Iterable[Finding]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(finding.message for finding in findings))


def evaluate_hook(
    hook_input: dict[str, Any],
    *,
    rules_path: Path = DEFAULT_RULES_PATH,
    fail_open: bool = True,
    dialect: str = "redshift",
) -> Decision:
    try:
        rules = load_rules(rules_path)
    except Exception as error:
        message = f"Could not load result-guard rules; skipping the check: {error}"
        return Decision("warn" if fail_open else "deny", (message,))

    sql_strings = extract_sql_strings(hook_input.get("tool_input", {}))
    if not sql_strings:
        return Decision("allow")

    all_findings: list[Finding] = []
    parse_messages: list[str] = []

    for sql in sql_strings:
        try:
            all_findings.extend(inspect_sql(sql, rules, dialect=dialect))
        except ParseError as error:
            parse_messages.append(f"Could not parse SQL; skipping result-flow analysis: {error}")
        except Exception as error:
            parse_messages.append(f"Unexpected result-flow analysis error: {error}")

    denied = [finding for finding in all_findings if finding.action == "deny"]
    warned = [finding for finding in all_findings if finding.action == "warn"]

    if denied:
        messages = list(_messages_from_findings(denied))
        messages.extend(parse_messages)
        return Decision("deny", tuple(dict.fromkeys(messages)))

    if warned or parse_messages:
        messages = list(_messages_from_findings(warned))
        messages.extend(parse_messages)
        return Decision("warn" if fail_open else "deny", tuple(dict.fromkeys(messages)))

    return Decision("allow")


def decision_to_payload(decision: Decision) -> dict[str, Any] | None:
    if decision.kind == "allow":
        return None

    detail = "\n".join(f"- {message}" for message in decision.messages)

    if decision.kind == "deny":
        reason = "The SQL was blocked because its final result may expose sensitive values."
        if detail:
            reason += f"\n{detail}"
        return {
            "systemMessage": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }

    warning = "The final SQL result may expose sensitive values. Execution is allowed with a warning."
    if detail:
        warning += f"\n{detail}"
    return {
        "systemMessage": warning,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": warning,
        },
    }


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return parse_bool(raw, field_name=name)


def main() -> int:
    rules_path = Path(
        os.environ.get("MCP_SQL_RESULT_GUARD_RULES", str(DEFAULT_RULES_PATH))
    )
    dialect = os.environ.get("MCP_SQL_RESULT_GUARD_DIALECT", "redshift").strip() or "redshift"
    try:
        fail_open = _env_bool("MCP_SQL_RESULT_GUARD_FAIL_OPEN", True)
    except RuleConfigError as error:
        fail_open = True
        payload = decision_to_payload(Decision("warn", (str(error),)))
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError as error:
        decision = Decision(
            "warn" if fail_open else "deny",
            (f"Could not parse the hook input JSON: {error}",),
        )
    else:
        decision = evaluate_hook(
            hook_input,
            rules_path=rules_path,
            fail_open=fail_open,
            dialect=dialect,
        )

    payload = decision_to_payload(decision)
    if payload is not None:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
