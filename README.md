# mcp-sql-result-guard

[![test](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml/badge.svg)](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight Codex `PreToolUse` guardrail that blocks configured sensitive values from reaching an LLM through the final result of an MCP SQL tool.

Documentation for version `0.2.0`. [日本語](README.ja.md)

## The problem it solves

You may want an LLM to analyze data with SQL without returning raw identifiers to the model. At the same time, blocking every query that mentions an identifier is too restrictive: identifiers are often required for filtering, joining, grouping, ordering, and counting.

`mcp-sql-result-guard` distinguishes **internal SQL use** from **value exposure**. It starts at the top-level result columns or DML `RETURNING`, traces value flow backward, and applies a TSV policy to configured column names.

## Representative decisions

Assume `user_id` is configured as sensitive with `aggregate_reduction` allowed.

| SQL pattern | Decision | Reason |
|---|---|---|
| `SELECT order_total FROM orders WHERE user_id IS NOT NULL` | Allow | `user_id` controls filtering but is not returned. |
| `SELECT SUM(user_id) FROM orders` | Allow | `SUM` is an explicitly allowed reduction. |
| `SELECT MIN(user_id) FROM orders` | Deny | `MIN` selects an input value. |
| `SELECT MD5(user_id) FROM orders` | Deny | A value derived from `user_id` reaches the result. |
| `WITH x AS (SELECT user_id FROM users) INSERT INTO archive SELECT user_id FROM x` | Allow | INSERT input is written to the destination and is not returned in the MCP result set. |
| `UPDATE orders SET reviewed = true RETURNING user_id` | Deny | `RETURNING` exposes the configured value. |

The same output-oriented rule applies across CTEs:

```sql
-- Allow: the LISTAGG result is discarded before the final result.
WITH collected AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT COUNT(*)
FROM collected;
```

```sql
-- Deny: the collected values reach the final result through a CTE alias.
WITH collected AS (
    SELECT LISTAGG(user_id, ',') WITHIN GROUP (ORDER BY created_at) AS ids
    FROM orders
)
SELECT ids
FROM collected;
```

## Quick Start

1. Install the CLI into a Python 3.10+ environment whose scripts are available on the `PATH` seen by Codex. The hook invokes `mcp-sql-result-guard` by name.

   ```bash
   python -m pip install "git+https://github.com/rio123dx/mcp-sql-result-guard.git@v0.2.0"
   ```

   Before configuring the hook, confirm that the command can be resolved with `command -v mcp-sql-result-guard` on WSL/Linux or `Get-Command mcp-sql-result-guard` in Windows PowerShell.

2. Create `.codex/hooks/sensitive_columns.tsv` in the project where Codex runs.

   ```tsv
   enabled	column_pattern	allow	action	note
   1	user_id	aggregate_reduction	deny	Do not return user identifiers to the model
   1	__SELECT_STAR__		deny	Block unresolved final SELECT * projections
   ```

3. Add the hook to `.codex/config.toml`.

   ```toml
   [features]
   hooks = true

   [[hooks.PreToolUse]]
   matcher = "^mcp__warehouse__execute_sql$"

   [[hooks.PreToolUse.hooks]]
   type = "command"
   command = 'MCP_SQL_RESULT_GUARD_RULES="$(git rev-parse --show-toplevel)/.codex/hooks/sensitive_columns.tsv" MCP_SQL_RESULT_GUARD_DIALECT=redshift MCP_SQL_RESULT_GUARD_FAIL_OPEN=true mcp-sql-result-guard'
   command_windows = "powershell -NoProfile -ExecutionPolicy Bypass -Command \"& (Join-Path (git rev-parse --show-toplevel) '.codex\\hooks\\run-sql-guard.ps1')\""
   timeout = 10
   statusMessage = "Checking SQL result columns for configured sensitive values"
   ```

   On Windows, save the [sample wrapper](examples/codex/run-sql-guard.ps1) as `.codex/hooks/run-sql-guard.ps1`.

4. Replace the matcher with the exact MCP SQL execution tool name, then review and trust the project-local hook in Codex.

Codex runs the guard immediately before the matched MCP tool call. An allowed query proceeds to the MCP tool; a denied query stops before execution. Run the [English WSL/Linux or Windows smoke test](examples/README.md#smoke-test) before relying on the hook. The [Japanese installation and operations manual](docs/ja/manual.md) provides the full deployment procedure.

### Failure policy and hook scope

The matcher is a regular expression over the tool name, so keep it limited to the SQL execution tool rather than every MCP tool.

Choose the failure policy explicitly:

- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=true` (default): warn and allow when SQL or rules cannot be parsed.
- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=false`: deny when analysis cannot complete.

See the [Codex hooks documentation](https://developers.openai.com/codex/hooks) for hook discovery, trust review, matcher behavior, and `PreToolUse` output.

## TSV policy

Rules are UTF-8 tab-separated values. Copy [the example policy](examples/rules/sensitive_columns.tsv) into a path managed with your project and replace the synthetic patterns with the columns you need to protect.

```tsv
enabled	column_pattern	allow	action	note
1	user_id	aggregate_reduction	deny	Do not return user identifiers to the model
1	email_address	aggregate_reduction	deny	Do not return email addresses to the model
1	__SELECT_STAR__		deny	Block unresolved final SELECT * projections
```

| Field | Meaning |
|---|---|
| `enabled` | `1`, `true`, `yes`, or `on` enables the row. |
| `column_pattern` | Case-insensitive column name pattern; shell-style `*` wildcards are supported. |
| `allow` | Comma-separated masks: `aggregate_reduction`, `count`, `count_distinct`, `approx_count`. |
| `action` | `deny` blocks the tool call; `warn` allows it with model-visible context. |
| `note` | Explanation included in the hook response. |

Rules are evaluated from top to bottom; the first matching column rule wins. `__SELECT_STAR__` is a special policy for an unresolved final base-table star.

## Decision model

The analyzer parses SQL with SQLGlot, starts from final projections or `RETURNING`, and follows value-producing expressions backward through aliases, CTEs, subqueries, set operations, functions, and aggregates.

`aggregate_reduction` allows only known scalar reductions:

- `COUNT`, `COUNT(DISTINCT ...)`, and approximate distinct count
- `SUM`, `AVG`
- `STDDEV`, `STDDEV_POP`, `STDDEV_SAMP`
- `VARIANCE`, `VAR_POP`, `VAR_SAMP`
- `CORR`, `COVAR_POP`, `COVAR_SAMP`
- `BOOL_AND`, `BOOL_OR`

The following remain value-carrying and are denied when a configured input reaches final output:

- `MIN`, `MAX`, `ANY_VALUE`
- `LISTAGG`, `GROUP_CONCAT`, `STRING_AGG`
- `ARRAY_AGG` and JSON/object collection aggregates
- `MEDIAN`, `PERCENTILE_CONT`, `PERCENTILE_DISC`, `MODE`
- approximate percentile and top-k functions
- `MIN_BY`, `MAX_BY`, `ARG_MIN`, `ARG_MAX`
- unknown aggregate functions and UDF-like calls

The classification is allowlist-based: an unknown aggregate is not assumed safe. Legacy masks `count`, `count_distinct`, and `approx_count` remain available when a policy should allow counts but not broader reductions.

## Main supported cases

| Group | Behavior |
|---|---|
| `WHERE`, `JOIN`, `GROUP BY`, `ORDER BY`, predicates | Allowed when the configured value only controls computation. |
| CTEs and subqueries | Intermediate values may be used and discarded; aliases and projections are traced if they reach output. |
| Safe reductions | Allowed only when the matching TSV rule enables the required mask. |
| Raw, hashed, cast, concatenated, or substring output | Denied because value-derived information reaches the result. |
| Value-selecting or value-collecting aggregates | Denied at final output, even with `aggregate_reduction`. |
| `UNION`, `INTERSECT`, `EXCEPT` | Every output branch is inspected. |
| Derived `SELECT *` | Known projections are expanded and inspected. |
| Unresolved final base-table `SELECT *` | Controlled by `__SELECT_STAR__`. |
| INSERT input | Raw values, transforms, CTEs, subqueries, and `VALUES` are allowed when they are only written to the destination. |
| DML `RETURNING` | Inspected like a final result set. |
| Multiple configured columns | Each matching value path is reported. |
| Parse or configuration failure | Warn/allow or deny according to `MCP_SQL_RESULT_GUARD_FAIL_OPEN`. |

The executable matrices are [the base scenarios](tests/data/sql_scenarios.tsv) and [the INSERT scenarios](tests/data/insert_scenarios.tsv): 164 scenarios in total, including 93 allow and 71 deny decisions.

## Limitations and security boundary

This project is a best-effort, pre-execution guardrail. It does not guarantee confidentiality and does not replace:

- least-privilege database roles
- column masking or row/column security
- MCP server-side authorization and statement policy
- minimum group-size or privacy-budget enforcement
- query and result audit logging
- post-execution result filtering

Allowed aggregates can still reveal information through small groups, repeated queries, differencing, or auxiliary knowledge. UDFs, stored procedures, dynamic SQL, `UNLOAD`, external exports, side effects, and equivalent access through other tools are outside this guard's reliable boundary. Redshift is the default and primary regression-tested dialect; add dialect-specific scenarios before depending on another SQLGlot dialect.

Read [Limitations and threat model](docs/limitations.md) and [Security policy](SECURITY.md) before production use.

## Detailed documentation

- [Japanese installation and operations manual](docs/ja/manual.md)
- [Architecture](docs/architecture.md)
- [Limitations and threat model](docs/limitations.md)
- [Security policy](SECURITY.md)
- [Regression test report](docs/test-report.md)
- [Examples](examples/README.md)
- [Contributing](CONTRIBUTING.md)

## Development and tests

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip check
python -m pytest
python scripts/run_scenarios.py
python -m build
```

Current regression totals:

- pytest: **209 passed / 209**
- SQL scenarios: **164 passed / 164**
- expected allow: **93**
- expected deny: **71**

## License

MIT. See [LICENSE](LICENSE).
