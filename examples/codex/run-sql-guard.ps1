# Copy this file to <repo>/.codex/hooks/run-sql-guard.ps1.
# Install mcp-sql-result-guard in a Python environment available on PATH.

$ErrorActionPreference = "Stop"

$root = (git rev-parse --show-toplevel).Trim()
if (-not $root) {
    throw "The SQL guard must run inside a Git working tree."
}

$guard = Get-Command "mcp-sql-result-guard" -ErrorAction Stop

$env:MCP_SQL_RESULT_GUARD_RULES = Join-Path $root ".codex\hooks\sensitive_columns.tsv"
$env:MCP_SQL_RESULT_GUARD_DIALECT = "redshift"
$env:MCP_SQL_RESULT_GUARD_FAIL_OPEN = "true"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& $guard.Source
exit $LASTEXITCODE
