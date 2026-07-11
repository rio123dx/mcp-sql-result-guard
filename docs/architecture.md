# Architecture

## Data flow

```text
Codex
  -> PreToolUse hook input JSON
      -> recursively extract SQL-like arguments
          -> SQLGlot parse and scope construction
              -> inspect only top-level result projections / RETURNING
                  -> trace derived columns through CTEs, subqueries and set operations
                      -> compare base column names with TSV rules
                          -> allow, warn, or deny JSON
  -> MCP SQL tool runs only when the hook allows it
```

## Output-oriented analysis

The analyzer intentionally does not reject a sensitive column merely because it appears in the SQL syntax tree. It starts from final result projections and follows value-producing expressions backward.

Control inputs are ignored by the lightweight policy:

- `WHERE`, `JOIN ON`, `JOIN USING`
- grouping and ordering
- predicates and `EXISTS`
- `CASE` and `IF` conditions
- window `PARTITION BY`, `ORDER BY`, and frame clauses
- aggregate `FILTER` predicates

Value-producing inputs are followed:

- direct columns and aliases
- ordinary functions and operators
- value-returning aggregates
- value-returning window functions
- scalar subquery result columns
- CTE and derived-table outputs
- every branch of `UNION`, `INTERSECT`, and `EXCEPT`
- DML `RETURNING`

## Star handling

A star from a derived relation can be expanded through that relation's known projections. A final star from a base table cannot be resolved without schema metadata, so the `__SELECT_STAR__` special rule can deny it.

## Rule matching

Column patterns are matched case-insensitively with shell-style wildcards. Rules are ordered, and the first matching rule wins. The special `__SELECT_STAR__` rule is handled separately.

## Hook response

- No stdout output means allow.
- A deny response uses Codex `hookSpecificOutput.permissionDecision = "deny"`.
- A warning uses `hookSpecificOutput.additionalContext` without a deny decision.

## Dialect

SQL is parsed with the dialect named by `MCP_SQL_RESULT_GUARD_DIALECT`. Redshift is the default and the dialect covered by the committed scenario suite.
