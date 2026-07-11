# mcp-sql-result-guard

[![test](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml/badge.svg)](https://github.com/rio123dx/mcp-sql-result-guard/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight Codex `PreToolUse` guardrail that blocks configured sensitive values from reaching an LLM through the final result of an MCP SQL tool.

Documentation for version `0.2.0`. [日本語](README.ja.md)

## The problem it solves

You may want an LLM to analyze data with SQL without returning raw identifiers to the model. At the same time, blocking every query that mentions an identifier is too restrictive: identifiers are often required for filtering, joining, grouping, ordering, and counting.

`mcp-sql-result-guard` distinguishes **internal SQL use** from **value exposure**. It starts at the top-level result columns or DML `RETURNING`, traces value flow backward, and applies a TSV policy to configured column names.

It is designed for data engineers, analytics engineers, data platform engineers, and developers connecting LLM agents to data warehouses through MCP.

## Representative decisions

Assume `user_id` is configured as sensitive with `aggregate_reduction` allowed.

| SQL pattern | Decision | Reason |
|---|---|---|
| `SELECT order_total FROM orders WHERE user_id IS NOT NULL` | Allow | `user_id` controls filtering but is not returned. |
| `SELECT SUM(user_id) FROM orders` | Allow | `SUM` is an explicitly allowed reduction. |
| `SELECT MIN(user_id) FROM orders` | Deny | `MIN` selects an input value. |
| `SELECT MD5(user_id) FROM orders` | Deny | A value derived from `user_id` reaches the result. |
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

## Quick start

The project is currently installed from a cloned source tree; this guide does not assume a PyPI release. Replace the example matcher with the exact MCP SQL tool name shown by Codex in your environment.

### WSL or Linux

Clone the repository, create a Python 3.10+ virtual environment, install from source, and copy the example policy and hook configuration:

```bash
git clone https://github.com/rio123dx/mcp-sql-result-guard.git
cd mcp-sql-result-guard

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .

mkdir -p .codex/hooks
cp examples/rules/sensitive_columns.tsv .codex/hooks/sensitive_columns.tsv
cp examples/codex/config.toml .codex/config.toml
```

Edit `.codex/config.toml` and replace this placeholder with the exact MCP SQL execution tool name:

```toml
matcher = "^mcp__warehouse__execute_sql$"
```

Smoke-test an allowed query and a denied query through standard input:

```bash
export MCP_SQL_RESULT_GUARD_RULES="$PWD/.codex/hooks/sensitive_columns.tsv"
export MCP_SQL_RESULT_GUARD_DIALECT=redshift
export MCP_SQL_RESULT_GUARD_FAIL_OPEN=true

printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT order_total FROM orders WHERE user_id IS NOT NULL"}}' \
  | ./.venv/bin/mcp-sql-result-guard

printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT user_id FROM orders"}}' \
  | ./.venv/bin/mcp-sql-result-guard
```

The first command should produce no stdout. The second should return JSON containing `permissionDecision: "deny"`.

### Windows PowerShell

```powershell
git clone https://github.com/rio123dx/mcp-sql-result-guard.git
Set-Location mcp-sql-result-guard

py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install .

New-Item -ItemType Directory -Force .codex\hooks | Out-Null
Copy-Item examples\rules\sensitive_columns.tsv .codex\hooks\sensitive_columns.tsv
Copy-Item examples\codex\config.toml .codex\config.toml
Copy-Item examples\codex\run-sql-guard.ps1 .codex\hooks\run-sql-guard.ps1
```

Edit `.codex\config.toml` and replace the matcher with the exact MCP SQL execution tool name. Then smoke-test both decisions:

```powershell
$env:MCP_SQL_RESULT_GUARD_RULES = (Resolve-Path .codex\hooks\sensitive_columns.tsv)
$env:MCP_SQL_RESULT_GUARD_DIALECT = "redshift"
$env:MCP_SQL_RESULT_GUARD_FAIL_OPEN = "true"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$allow = '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT order_total FROM orders WHERE user_id IS NOT NULL"}}'
$allow | & .\.venv\Scripts\mcp-sql-result-guard.exe

$deny = '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT user_id FROM orders"}}'
$deny | & .\.venv\Scripts\mcp-sql-result-guard.exe
```

The first command should produce no stdout; the second should return a deny decision.

### Enable and review the hook

Project hooks are discovered from `.codex/config.toml`. Review and trust the copied hook definition in Codex before relying on it. The matcher is a regular expression over the tool name, so keep it limited to the SQL execution tool rather than every MCP tool.

Choose the failure policy explicitly:

- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=true` (default): warn and allow when SQL or rules cannot be parsed.
- `MCP_SQL_RESULT_GUARD_FAIL_OPEN=false`: deny when analysis cannot complete.

See the [Codex hooks documentation](https://developers.openai.com/codex/hooks) for hook discovery, trust review, matcher behavior, and `PreToolUse` output.

## Minimal TSV policy

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
| DML `RETURNING` | Inspected like a final result set. |
| Multiple configured columns | Each matching value path is reported. |
| Parse or configuration failure | Warn/allow or deny according to `MCP_SQL_RESULT_GUARD_FAIL_OPEN`. |

The full executable matrix is in [tests/data/sql_scenarios.tsv](tests/data/sql_scenarios.tsv): 156 scenarios, including 86 allow and 70 deny decisions.

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

- pytest: **199 passed / 199**
- SQL scenarios: **156 passed / 156**
- expected allow: **86**
- expected deny: **70**

## License

MIT. See [LICENSE](LICENSE).
