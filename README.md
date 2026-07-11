# mcp-sql-result-guard

[![test](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml/badge.svg)](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight Codex `PreToolUse` hook that statically checks SQL before an MCP tool runs and blocks queries whose **final result columns may expose configured sensitive values**.

The guard is output-oriented. Sensitive columns may still be used internally for filtering, joins, grouping, ordering, CTEs, and subqueries when their values do not flow into the final result set.

- Japanese: [README.ja.md](README.ja.md)
- Japanese installation and operations manual: [docs/ja/manual.md](docs/ja/manual.md)

## Why this exists

A rule such as “reject every query that mentions `user_id`” is often too restrictive for analytics. This project instead distinguishes between internal use and value exposure.

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
-- Allowed: the CTE contains user_id, but the final result only returns SUM(amount).
WITH scoped AS (
    SELECT user_id, amount
    FROM orders
)
SELECT SUM(amount)
FROM scoped;
```

```sql
-- Blocked: the alias is traced through the CTE.
WITH scoped AS (
    SELECT user_id AS internal_key
    FROM orders
)
SELECT internal_key
FROM scoped;
```

## Policy model

By default, the included TSV example treats these as safe masks:

- `COUNT(column)`
- `COUNT(DISTINCT column)`
- approximate distinct count

The following are treated as value exposure and are blocked when they reach a final output column:

- direct projection
- aliases, including multi-stage CTE aliases
- casts, hashes, substrings, concatenation, and arithmetic
- `MIN`, `MAX`, `LISTAGG`, arrays, JSON extraction, and similar transforms
- value-returning window functions such as `FIRST_VALUE`, `LAG`, and `LEAD`
- DML `RETURNING`
- unresolved final `SELECT *`, when enabled by the special TSV rule

Predicates, `EXISTS`, `CASE` conditions, window partition/order clauses, and other control-only uses are allowed by the lightweight policy. See [docs/limitations.md](docs/limitations.md) for the security boundary.

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

Rules are tab-separated values so that policy owners can add columns without editing Python.

```tsv
enabled	column_pattern	allow	action	note
1	user_id	count,count_distinct,approx_count	deny	User identifiers must not be returned to the model
1	email_address	count,count_distinct,approx_count	deny	Email addresses must not be returned to the model
1	phone_*	count,count_distinct	deny	Phone-number columns must not be returned to the model
1	__SELECT_STAR__		deny	Block unresolved final SELECT * projections
```

| Field | Meaning |
|---|---|
| `enabled` | `1`, `true`, `yes`, or `on` enables the row. |
| `column_pattern` | Case-insensitive column name pattern. Shell-style `*` wildcards are supported. |
| `allow` | Comma-separated masks allowed for this column: `count`, `count_distinct`, `approx_count`. |
| `action` | `deny` blocks the MCP call; `warn` adds model-visible context and allows it. |
| `note` | Human-readable explanation included in the hook result. |

Rules are evaluated from top to bottom; the first matching column rule wins. `__SELECT_STAR__` is a special rule for unresolved final stars from base tables.

## Codex setup

Codex command hooks receive one JSON object on standard input. A `PreToolUse` hook can match MCP tool names, inspect all MCP arguments under `tool_input`, deny a tool call with `permissionDecision: "deny"`, or add non-blocking context with `additionalContext`.

1. Install this package in an environment visible to Codex.
2. Copy [examples/rules/sensitive_columns.tsv](examples/rules/sensitive_columns.tsv) to a project-controlled path.
3. Adapt [examples/codex/config.toml](examples/codex/config.toml) to the MCP server and SQL tool names used in your environment.
4. Review and trust the project hook in Codex.

Example:

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

The hook recursively looks for non-empty string values under keys named:

- `sql`
- `query`
- `statement`

This makes it usable with MCP tools that nest their SQL arguments. Narrow the Codex matcher to the actual SQL execution tool so unrelated tools are not inspected unnecessarily.

## Test coverage

The current regression suite contains:

- **150 pytest cases**
- **117 SQL policy scenarios**

The scenario matrix covers direct projections, transforms, joins, filters, CTEs, nested subqueries, aliases, set operations, window functions, stars, DML, `RETURNING`, malformed input, TSV parsing, and Codex hook JSON integration.

Run:

```bash
python -m pytest
python scripts/run_scenarios.py
```

The scenario runner writes ignored local files `scenario-results.tsv` and `scenario-summary.txt`.

## Supported scope

The code accepts a SQLGlot dialect through `MCP_SQL_RESULT_GUARD_DIALECT`, but the committed regression suite is centered on Amazon Redshift syntax. Other SQLGlot-supported dialects may work; add dialect-specific tests before relying on them.

## Security boundary

This is a best-effort, pre-execution guardrail. It is not a substitute for:

- database permissions
- dynamic data masking
- column-level or row-level security
- MCP-side enforcement
- audit logging
- a post-execution result filter

Codex `PreToolUse` hooks are themselves guardrails rather than complete enforcement boundaries. See [SECURITY.md](SECURITY.md), [docs/architecture.md](docs/architecture.md), and [docs/limitations.md](docs/limitations.md).

## License

MIT. See [LICENSE](LICENSE).
