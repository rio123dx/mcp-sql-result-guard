# Regression test report

Date: 2026-07-11

## Results

- pytest: **150 passed / 150**
- SQL policy scenarios: **117 passed / 117**
  - one sensitive-column ruleset: 95
  - two sensitive-column ruleset: 22
  - expected allow: 63
  - expected deny: 54

## Coverage groups

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
