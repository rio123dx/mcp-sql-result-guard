# Regression test report

Date: 2026-07-12
Version: unreleased after `0.2.0`

## Results

- pytest: **209 passed / 209**
- SQL policy scenarios: **164 passed / 164**
  - base scenario matrix: 156
  - INSERT scenario matrix: 8
  - expected allow: 93
  - expected deny: 71
- wheel build: passed
- sdist build: passed

## INSERT input coverage

- direct `INSERT ... SELECT` of a configured sensitive column
- transformed sensitive values used as INSERT input
- raw values routed through a CTE
- multi-stage CTE aliases routed into INSERT
- unresolved CTE `SELECT *` used only as INSERT input
- `INSERT ... VALUES`
- multiple configured sensitive columns routed through a CTE into INSERT
- non-sensitive `INSERT ... RETURNING` output
- sensitive `INSERT ... RETURNING` output remains denied

INSERT source rows are treated as writes rather than MCP result columns. The output boundary remains the DML `RETURNING` clause.

## Existing coverage groups

- direct and aliased projections
- quoted and case-varied identifiers
- hashes, casts, substrings, concatenation, arithmetic, JSON-like transforms
- filters, joins, grouping, ordering, `HAVING`, and `QUALIFY`
- count masks and aggregate filters
- allowed final reductions: sum, average, standard deviation, variance, correlation, covariance, and boolean reductions (`BOOL_AND`, `BOOL_OR`)
- value-selection and value-collection aggregates
- CTEs, subqueries, alias chains, and explicit column lists
- `UNION`, `INTERSECT`, and `EXCEPT`
- `CASE`/`IF` condition-versus-result behavior
- window control clauses and value-returning window functions
- base-table and derived-table stars
- DML and `RETURNING`
- malformed hook JSON and malformed SQL
- TSV parsing, wildcards, disabled rules, warnings, and fail-open/fail-closed
- package distribution build

The executable scenario matrices are stored in `tests/data/sql_scenarios.tsv` and `tests/data/insert_scenarios.tsv`.
