# Changelog

## 0.2.0

- Added the `aggregate_reduction` TSV mask.
- Allowed configured scalar reductions: count, sum, average, standard deviation, variance, correlation, covariance, and boolean reductions.
- Kept value-selecting and value-collecting aggregates blocked at final output, including min/max, list/string/array/JSON collections, percentiles, mode, top-k, arg-min/max, and unknown aggregates.
- Preserved output-oriented behavior: unsafe aggregates and unresolved stars remain allowed when their values are discarded before the top-level result.
- Added ordered-set value tracing so percentile and mode expressions cannot bypass checks through `WITHIN GROUP (ORDER BY sensitive_column)`.
- Added token-safe normalization for Redshift `APPROXIMATE PERCENTILE_DISC` so the SQLGlot 26.x parser gap does not become a fail-open bypass.
- Expanded regression coverage to 194 pytest cases and 151 SQL policy scenarios.
- Added package build verification to GitHub Actions.

## 0.1.0

- Initial public project structure.
- Output-oriented SQL value-flow analysis for Codex MCP calls.
- TSV-configurable sensitive columns and safe count masks.
- CTE, subquery, alias, set-operation, window, star, and `RETURNING` regression coverage.
- 150 pytest cases and 117 SQL scenarios.
- English README and Japanese installation/operations manual.
