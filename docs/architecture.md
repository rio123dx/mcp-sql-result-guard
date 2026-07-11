# Architecture

## Data flow

```text
Codex
  -> PreToolUse hook input JSON
      -> recursively extract SQL-like arguments
          -> SQLGlot parse and scope construction
              -> inspect only top-level result projections / RETURNING
                  -> trace derived columns through CTEs, subqueries and set operations
                      -> classify masks and aggregate outputs
                          -> compare base column names with TSV rules
                              -> allow, warn, or deny JSON
  -> MCP SQL tool runs only when the hook allows it
```

## Output-oriented analysis

The analyzer does not reject a sensitive column merely because it appears in the SQL syntax tree. It starts from top-level result projections or DML `RETURNING` and follows value-producing expressions backward.

Consequences:

- An unsafe aggregate inside a CTE is allowed when its output is not referenced by the final query.
- An unresolved base-table star inside a CTE is allowed when no column from that star reaches final output.
- The same expression is inspected when an outer projection, alias, derived star, or set operation carries it to the result set.

Control inputs are ignored by the lightweight policy:

- `WHERE`, `JOIN ON`, `JOIN USING`
- grouping and ordinary ordering
- predicates and `EXISTS`
- `CASE` and `IF` conditions
- window `PARTITION BY`, `ORDER BY`, and frame clauses
- aggregate `FILTER` predicates
- `LISTAGG` ordering when the ordered column is not the collected value

Value-producing inputs are followed:

- direct columns and aliases
- ordinary functions and operators
- value-selecting and value-collecting aggregates
- ordered-set aggregate value expressions, including percentile `ORDER BY` inputs
- value-returning window functions
- scalar subquery result columns
- CTE and derived-table outputs
- every branch of `UNION`, `INTERSECT`, and `EXCEPT`
- DML `RETURNING`

## Aggregate classification

Aggregate safety is allowlist-based.

`aggregate_reduction` currently recognizes:

- counts and approximate distinct counts
- `SUM`, `AVG`
- standard deviation and variance families
- correlation and covariance families
- boolean AND/OR aggregates

The reduction mask is applied after tracing the aggregate's value arguments. If the matching TSV rule permits `aggregate_reduction`, findings for those inputs are suppressed.

Value-selecting, collecting, rank-value, and unknown aggregates are not suppressed. They continue through ordinary value-flow inspection. This includes `MIN`, `MAX`, `ANY_VALUE`, string/array/JSON collections, percentiles, mode, top-k, arg-min/max, and unknown functions.

Legacy `count`, `count_distinct`, and `approx_count` masks remain supported. `aggregate_reduction` also permits those count usages.

## Ordered-set aggregates

A `WITHIN GROUP` order clause has different semantics depending on the function:

- For `LISTAGG`, the collected expression carries the output value; ordering is control-only.
- For percentile, mode, and unknown ordered-set aggregates, the ordered expression is the value distribution represented by the result and is therefore traced.

This distinction prevents a sensitive `LISTAGG` order key from causing a false positive while preventing percentile expressions from bypassing value-flow analysis.

For Redshift, SQLGlot 26.x does not directly parse the two-keyword `APPROXIMATE PERCENTILE_DISC` spelling. Before parsing, the tokenizer identifies executable occurrences of that keyword sequence and normalizes them to `PERCENTILE_DISC`. String literals, quoted identifiers, and comments are not rewritten.

## Star handling

A star from a derived relation can be expanded through that relation's known projections. A final star from a base table cannot be resolved without schema metadata, so the `__SELECT_STAR__` special rule can deny it.

The special rule is evaluated only when an unresolved star reaches final output. Internal stars that are discarded do not trigger it.

## Rule matching

Column patterns are matched case-insensitively with shell-style wildcards. Rules are ordered, and the first matching rule wins. The special `__SELECT_STAR__` rule is handled separately.

## Hook response

- No stdout output means allow.
- A deny response uses Codex `hookSpecificOutput.permissionDecision = "deny"`.
- A warning uses `hookSpecificOutput.additionalContext` without a deny decision.

## Dialect

SQL is parsed with the dialect named by `MCP_SQL_RESULT_GUARD_DIALECT`. Redshift is the default and the dialect covered by the committed scenario suite.
