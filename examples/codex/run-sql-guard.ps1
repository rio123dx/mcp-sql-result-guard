# Copy this file to <repo>/.codex/hooks/run-sql-guard.ps1.
# Keep the TSV policy and virtual environment under the same repository root.

$ErrorActionPreference = "Stop"

$root = (git rev-parse --show-toplevel).Trim()
if (-not $root) {
    throw "The SQL guard must run inside a Git working tree."
}

$env:MCP_SQL_RESULT_GUARD_RULES = Join-Path $root ".codex\hooks\sensitive_columns.tsv"
$env:MCP_SQL_RESULT_GUARD_DIALECT = "redshift"
$env:MCP_SQL_RESULT_GUARD_FAIL_OPEN = "true"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& (Join-Path $root ".venv\Scripts\mcp-sql-result-guard.exe")
exit $LASTEXITCODE
