# Examples

These files are starting points for a project-local installation. Copy them into your own repository and replace the synthetic column patterns and MCP tool matcher.

## Files

- [`rules/sensitive_columns.tsv`](rules/sensitive_columns.tsv): minimal TSV policy with `aggregate_reduction` and `__SELECT_STAR__`.
- [`codex/config.toml`](codex/config.toml): `PreToolUse` matcher and commands for WSL/Linux and Windows.
- [`codex/run-sql-guard.ps1`](codex/run-sql-guard.ps1): Windows wrapper used by `command_windows`.

## Expected project layout

```text
<repo>/
  .venv/
  .codex/
    config.toml
    hooks/
      sensitive_columns.tsv
      run-sql-guard.ps1   # Windows only
```

Keep the matcher limited to the MCP SQL execution tool. Choose `MCP_SQL_RESULT_GUARD_FAIL_OPEN=true` or `false` according to the deployment's availability and disclosure requirements.

Follow the [English quick start](../README.md#quick-start) or [Japanese manual](../docs/ja/manual.md#4-quick-start) for copy and smoke-test commands.
