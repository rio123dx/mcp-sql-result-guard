# Architecture

## Purpose and scope

`mcp-sql-result-guard` is a static, pre-execution guardrail for an MCP SQL tool. It lets a query use configured sensitive columns for analysis while inspecting whether those values, value-derived expressions, or value-carrying aggregates can reach the top-level result set or DML `RETURNING`.

The design is output-oriented rather than reference-oriented: mentioning a configured column does not by itself cause a denial.

## Data flow

```text
Codex
  -> PreToolUse hook input JSON
      -> recursively extract sql/query/statement arguments
          -> normalize supported Redshift parser gaps
              -> SQLGlot parse and scope construction
                  -> start at top-level projections or RETURNING
                      -> trace value flow backward through expressions and scopes
                          -> classify aggregate usage
                              -> match base column names against ordered TSV rules
                                  -> allow, warn, or deny JSON
  -> MCP SQL tool runs only when the hook allows it
```

The hook never connects to the database and does not inspect an executed result set.

## Output-oriented value tracing

The analyzer starts from each final projection and follows value-producing inputs backward.

Value-producing paths include:

- direct columns, aliases, casts, operators, and ordinary functions
- CTE and derived-table projections
- scalar subquery result columns
- every output branch of `UNION`, `INTERSECT`, and `EXCEPT`
- value-returning window functions
- value-selecting, value-collecting, and ordered-set aggregates
- DML `RETURNING`
- known columns expanded from a derived `SELECT *`

Control-only inputs are not treated as returned values:

- `WHERE`, `JOIN ON`, and `JOIN USING`
- grouping and ordinary ordering
- predicates and `EXISTS`
- `CASE` and `IF` conditions
- window partition/order/frame clauses
- aggregate `FILTER` predicates
- `LISTAGG` ordering when the ordered column is not the collected value

This distinction allows an identifier to participate in analysis without returning it to the model.

## Scope and alias propagation

SQLGlot scopes connect outer projections to CTEs, subqueries, and set-operation branches. A value is inspected if a final expression references it through any number of aliases. An intermediate value is not inspected merely because it exists; if the outer query discards it, the path ends.

Consequences:

- A `LISTAGG` inside a CTE is allowed when only `COUNT(*)` from that CTE reaches final output.
- The same `LISTAGG` is denied when its alias is selected by the outer query.
- An intermediate base-table star can be used and discarded.
- A derived star is expanded when its projections are known and is denied if a configured value reaches output.

## Aggregate classification

Aggregate safety is allowlist-based.

`aggregate_reduction` recognizes:

- counts and approximate distinct counts
- `SUM`, `AVG`
- standard-deviation and variance families
- correlation and covariance families
- boolean AND/OR aggregates

The reduction mask is applied after tracing the aggregate's value arguments. A finding is suppressed only when the first matching TSV rule permits the relevant reduction usage.

Value-selecting, value-collecting, rank-value, and unknown aggregates remain value-carrying. This includes `MIN`, `MAX`, `ANY_VALUE`, string/array/JSON collections, percentiles, mode, top-k, arg-min/max, and unknown functions.

Legacy `count`, `count_distinct`, and `approx_count` masks remain available for policies that should permit counts without permitting the broader reduction allowlist.

## Ordered-set aggregates

A `WITHIN GROUP` order expression has function-specific semantics:

- For `LISTAGG`, the collected expression carries the output value; ordering is control-only.
- For percentile, mode, and unknown ordered-set aggregates, the ordered expression represents the value distribution and is traced.

SQLGlot 26.x does not directly parse Redshift's two-keyword `APPROXIMATE PERCENTILE_DISC` spelling. Before parsing, executable occurrences are normalized to `PERCENTILE_DISC`. String literals, quoted identifiers, and comments are not rewritten.

## Star handling

A derived star can be expanded through known projections. A final base-table star cannot be resolved without schema metadata, so the special `__SELECT_STAR__` rule controls it.

The special rule is evaluated only when an unresolved star reaches final output. `COUNT(*)` is a row-count aggregate, not a star projection.

## Rule matching

Column patterns are matched case-insensitively with shell-style wildcards. Rules are ordered and the first matching column rule wins. `__SELECT_STAR__` is handled separately from ordinary column patterns.

## Hook input and response

The hook recursively searches MCP `tool_input` for non-empty strings under `sql`, `query`, or `statement`.

- Empty stdout means allow.
- A denial uses `hookSpecificOutput.permissionDecision = "deny"`.
- A warning uses `hookSpecificOutput.additionalContext` without a deny decision.

The Codex matcher should target the exact MCP SQL tool name. Project-local command hooks require review and trust before they run; see the [Codex hooks documentation](https://developers.openai.com/codex/hooks).

## Failure policy and dialect

`MCP_SQL_RESULT_GUARD_FAIL_OPEN=true` is the default. Parse and rule-loading failures produce a warning and allow the call. Set it to `false` to deny when analysis cannot complete.

`MCP_SQL_RESULT_GUARD_DIALECT` selects the SQLGlot read dialect. Redshift is the default and primary regression-tested dialect. Other dialects require representative scenario coverage before operational use.

## Security boundary

This architecture reduces one accidental-disclosure path; it does not create a database authorization boundary. Database roles, masking, row/column security, MCP-side policy, inference controls, audit logging, and result filtering remain separate layers.

See [Limitations and threat model](limitations.md), [Security policy](../SECURITY.md), and the [Japanese operations manual](ja/manual.md).
