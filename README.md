# mcp-sql-result-guard

[![test](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml/badge.svg)](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight Codex `PreToolUse` hook that statically checks SQL before an MCP tool runs and blocks queries whose **final result columns may expose configured sensitive values**.

The guard is output-oriented. Sensitive columns may be used internally for filters, joins, grouping, ordering, CTEs, subqueries, intermediate aggregates, and intermediate stars when those values do not flow into the top-level result set or `RETURNING`.

- Japanese: [README.ja.md](README.ja.md)
- Japanese installation and operations manual: [docs/ja/manual.md](docs/ja/manual.md)

## Why this exists

A rule such as “reject every query that mentions `user_id`” is often too restrictive for analytics. This project distinguishes internal computation from value exposure.

```sql
-- Allowed: user_id is only a predicate input.
SELECT amount
FROM orders
WHERE user_id = 'u1';
```

```sql
-- Blocked: the sensitive value reaches the final result.
SELECT user_id
FROM orders;
```

```sql
-- Allowed: a value-collecting aggregate exists only inside the CTE.
WITH scoped AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT COUNT(*)
FROM scoped;
```

```sql
-- Blocked: the collected values are returned through a CTE alias.
WITH scoped AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT ids
FROM scoped;
```

## Policy model

### Configured reduction aggregates

The `aggregate_reduction` rule mask allows the following scalar statistical or logical reductions when they reach final output:

- `COUNT`, `COUNT(DISTINCT ...)`, and approximate distinct count
- `SUM`, `AVG`
- `STDDEV`, `STDDEV_POP`, `STDDEV_SAMP`
- `VARIANCE`, `VAR_POP`, `VAR_SAMP`
- `CORR`, `COVAR_POP`, `COVAR_SAMP`
- `BOOL_AND`, `BOOL_OR`

Legacy masks `count`, `count_distinct`, and `approx_count` remain supported. `aggregate_reduction` is an umbrella that also permits those count forms.

### Value-carrying aggregates

These remain blocked when a configured sensitive value reaches final output:

- `MIN`, `MAX`, `ANY_VALUE`
- `LISTAGG`, `GROUP_CONCAT`, `STRING_AGG`
- `ARRAY_AGG` and JSON/object collection aggregates
- `MEDIAN`, `PERCENTILE_CONT`, `PERCENTILE_DISC`, `MODE`
- approximate percentile/top-k functions
- `MIN_BY`, `MAX_BY`, `ARG_MIN`, `ARG_MAX`
- unknown aggregate functions and UDF-like calls

This classification is deliberately allowlist-based. A newly encountered aggregate is not assumed safe.

### Final-output rule

The classification is applied only when the expression can reach a top-level result column or DML `RETURNING`.

- An unsafe aggregate used only inside a CTE is allowed if its output is discarded.
- A base-table `SELECT *` used only inside a CTE is allowed if no unknown star reaches final output.
- A derived-table final `SELECT *` is expanded through known projections and checked column by column.
- An unresolved final base-table `SELECT *` can be denied with `__SELECT_STAR__`.

Predicates, `EXISTS`, `CASE` conditions, window partition/order clauses, aggregate `FILTER` predicates, and other control-only uses are allowed by the lightweight policy. See [docs/limitations.md](docs/limitations.md) for the security boundary.

## Installation

Requires Python 3.10 or later.

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e ".[dev]"
```

## Rules

Rules are tab-separated values so policy owners can add columns without editing Python.

```tsv
enabled	column_pattern	allow	action	note
1	user_id	aggregate_reduction	deny	User identifiers must not be returned to the model
1	email_address	aggregate_reduction	deny	Email addresses must not be returned to the model
1	phone_*	aggregate_reduction	deny	Phone-number columns must not be returned to the model
1	__SELECT_STAR__		deny	Block unresolved final SELECT * projections
```

| Field | Meaning |
|---|---|
| `enabled` | `1`, `true`, `yes`, or `on` enables the row. |
| `column_pattern` | Case-insensitive column name pattern. Shell-style `*` wildcards are supported. |
| `allow` | Comma-separated masks: `aggregate_reduction`, `count`, `count_distinct`, `approx_count`. |
| `action` | `deny` blocks the MCP call; `warn` adds model-visible context and allows it. |
| `note` | Human-readable explanation included in the hook result. |

Rules are evaluated from top to bottom; the first matching column rule wins. `__SELECT_STAR__` is a special rule for unresolved final stars from base tables.

## Codex setup

Codex command hooks receive one JSON object on standard input. A `PreToolUse` hook can match MCP tool names, inspect MCP arguments under `tool_input`, deny a tool call with `permissionDecision: "deny"`, or add non-blocking context with `additionalContext`.

1. Install this package in an environment visible to Codex.
2. Copy [examples/rules/sensitive_columns.tsv](examples/rules/sensitive_columns.tsv) to a project-controlled path.
3. Adapt [examples/codex/config.toml](examples/codex/config.toml) to the MCP server and SQL tool names used in your environment.
4. Review and trust the project hook in Codex.

```toml
[features]
hooks = true

[[hooks.PreToolUse]]
matcher = "^mcp__warehouse__execute_sql$"

[[hooks.PreToolUse.hooks]]
type = "command"
command = 'MCP_SQL_RESULT_GUARD_RULES="$(git rev-parse --show-toplevel)/.codex/hooks/sensitive_columns.tsv" MCP_SQL_RESULT_GUARD_DIALECT=redshift mcp-sql-result-guard'
timeout = 10
statusMessage = "Checking the final SQL result for sensitive values"
```

Official Codex hook documentation: <https://developers.openai.com/codex/hooks>

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `MCP_SQL_RESULT_GUARD_RULES` | packaged `default_rules.tsv` | Path to the TSV rule file. |
| `MCP_SQL_RESULT_GUARD_DIALECT` | `redshift` | SQLGlot read dialect. Redshift is the regression-tested dialect in this repository. |
| `MCP_SQL_RESULT_GUARD_FAIL_OPEN` | `true` | On parse/config errors, warn and allow. Set `false` to deny. |

## Hook input discovery

The hook recursively looks for non-empty string values under keys named `sql`, `query`, or `statement`. Narrow the Codex matcher to the actual SQL execution tool so unrelated tools are not inspected unnecessarily.

## Test coverage

The current regression suite contains:

- **194 pytest cases**
- **151 SQL policy scenarios**

The matrix covers direct projections, transforms, safe reduction aggregates, value-collecting aggregates, ordered-set aggregates, CTEs, nested subqueries, aliases, set operations, window functions, stars, DML, `RETURNING`, malformed input, TSV parsing, and Codex hook JSON integration.

```bash
python -m pip check
python -m pytest
python scripts/run_scenarios.py
python -m build
```

## Supported scope

The code accepts a SQLGlot dialect through `MCP_SQL_RESULT_GUARD_DIALECT`, but the committed regression suite is centered on Amazon Redshift syntax. Other SQLGlot-supported dialects may work; add dialect-specific tests before relying on them.

## Security boundary

This is a best-effort, pre-execution guardrail. Statistical reductions can still leak information through small groups, repeated queries, differencing, or auxiliary knowledge. It is not a substitute for database permissions, dynamic masking, row/column security, MCP-side enforcement, minimum group-size rules, audit logging, or post-execution result filtering.

See [SECURITY.md](SECURITY.md), [docs/architecture.md](docs/architecture.md), and [docs/limitations.md](docs/limitations.md).

## License

MIT. See [LICENSE](LICENSE).
