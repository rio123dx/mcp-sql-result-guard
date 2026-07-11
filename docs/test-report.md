# Regression test report

Date: 2026-07-11
Version: 0.2.0

## Results

- pytest: **199 passed / 199**
- SQL policy scenarios: **156 passed / 156**
  - one sensitive-column ruleset: 131
  - two sensitive-column ruleset: 25
  - expected allow: 86
  - expected deny: 70
- wheel build: passed
- sdist build: passed

## New 0.2.0 coverage

- `aggregate_reduction` TSV parsing and count-mask compatibility
- allowed final reductions: sum, average, standard deviation, variance, correlation, covariance, and boolean reductions (`BOOL_AND`, `BOOL_OR`)
- reduction aggregates through CTEs, aliases, filters, and windows
- value-selection aggregates: min, max, any-value, arg-min/max
- value-collection aggregates: list/string/array/JSON aggregation
- ordered-set values: percentile and mode
- Redshift `APPROXIMATE PERCENTILE_DISC` parser normalization and internal-only behavior
- approximate percentile and top-k results
- unknown aggregate functions defaulting to deny
- unsafe aggregates allowed when their intermediate output is discarded
- unresolved internal stars allowed when they do not reach final output
- package distribution build

## Existing coverage groups

- direct and aliased projections
- quoted and case-varied identifiers
- hashes, casts, substrings, concatenation, arithmetic, JSON-like transforms
- filters, joins, grouping, ordering, `HAVING`, and `QUALIFY`
- count masks and aggregate filters
- CTEs, subqueries, alias chains, and explicit column lists
- `UNION`, `INTERSECT`, and `EXCEPT`
- `CASE`/`IF` condition-versus-result behavior
- window control clauses and value-returning window functions
- base-table and derived-table stars
- DML and `RETURNING`
- malformed hook JSON and malformed SQL
- TSV parsing, wildcards, disabled rules, warnings, and fail-open/fail-closed

The executable scenario matrix is stored in `tests/data/sql_scenarios.tsv`.
