# Limitations and threat model

## Intended protection

This project reduces accidental disclosure of configured column values to an LLM through the normal result set or DML `RETURNING` of a matched MCP SQL execution tool.

It is designed for workflows in which identifiers still need to participate in filtering, joins, grouping, ordering, CTEs, subqueries, and explicitly allowed reductions, while raw or value-derived identifier output should be denied.

## Protection boundary

The guard performs static analysis before execution. It does not connect to the database, inspect catalog metadata by default, or filter the result after execution. It only runs for tool calls matched by the configured Codex `PreToolUse` hook.

The guard does not prevent:

- writes, deletes, exports, `UNLOAD`, stored-procedure side effects, or arbitrary SQL side effects
- equivalent access through another MCP tool, shell command, service, or database client
- values emitted by UDFs, stored procedures, dynamic SQL, macros, or code the parser cannot inspect
- sensitive values hidden behind column names that are not covered by the TSV policy
- disclosures already present in prompts, errors, logs, or MCP metadata
- database or MCP behavior that changes after the hook decision
- bypasses caused by an overly broad, missing, or incorrect matcher

## Aggregate inference risk

`aggregate_reduction` is a usability policy, not differential privacy. `SUM`, `AVG`, standard deviation, variance, correlation, covariance, boolean reductions, and even counts can reveal information when:

- a group contains one or very few rows
- queries are repeated with slightly different filters
- an observer knows all but one contributor
- aggregate outputs are combined with external knowledge
- differences between query results isolate a record

Use minimum group-size enforcement, query budgeting, noise, or database-side privacy controls when inference matters.

The aggregate allowlist is intentionally narrow. Unknown aggregate functions are treated as value-carrying rather than trusted automatically. This may reject a safe custom reduction, but avoids silently allowing a value-selection or collection function.

## Static-analysis trade-offs

The analyzer has no database catalog by default. It cannot know which columns are present in a base-table `SELECT *`; an unresolved star that reaches final output is therefore controlled by `__SELECT_STAR__`.

An intermediate unresolved star does not trigger that special rule when no value from it reaches final output. If an outer query references a configured sensitive name through the star, the analyzer treats that path as potentially sensitive.

Ambiguous or dialect-specific SQL may parse differently from the target database. Redshift is the primary regression-tested dialect. Add representative syntax to `tests/data/sql_scenarios.tsv` before relying on another SQLGlot dialect.

## Failure behavior

The default is fail-open:

```text
MCP_SQL_RESULT_GUARD_FAIL_OPEN=true
```

On a parse or configuration failure, the hook warns and allows the tool call. Environments that require denial on analysis failure can set:

```text
MCP_SQL_RESULT_GUARD_FAIL_OPEN=false
```

Fail-closed operation should be tested against the target dialect and expected error paths to avoid unexpected availability impact.

## Codex hook boundary

A Codex `PreToolUse` hook is a guardrail, not a complete enforcement boundary. Match the exact MCP SQL execution tool and review the trusted hook definition. Other tool paths can provide equivalent access unless controlled separately.

## Recommended complementary controls

- least-privilege database roles
- views that exclude raw identifiers
- column masking and row/column security
- query and result audit logs
- MCP server-side authorization and statement policy
- minimum group-size or privacy-budget policy
- post-execution result filtering for stricter enforcement
- version pinning and regression tests for SQLGlot and this package

See [Architecture](architecture.md), [Security policy](../SECURITY.md), and the [production checklist](ja/manual.md#11-本番導入チェックリスト).
