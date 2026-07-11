# Examples

These files are starting points for a project-local installation. Install the `mcp-sql-result-guard` CLI in a Python environment available to Codex, then copy the policy and hook configuration into the project that uses the MCP SQL tool.

## Files

- [`rules/sensitive_columns.tsv`](rules/sensitive_columns.tsv): minimal TSV policy with `aggregate_reduction` and `__SELECT_STAR__`.
- [`codex/config.toml`](codex/config.toml): `PreToolUse` matcher and commands for WSL/Linux and Windows.
- [`codex/run-sql-guard.ps1`](codex/run-sql-guard.ps1): optional Windows wrapper that resolves the installed CLI from `PATH`.

## Expected project layout

```text
<repo>/
  .codex/
    config.toml
    hooks/
      sensitive_columns.tsv
      run-sql-guard.ps1   # Windows only
```

Install the tagged release without cloning the source:

```bash
python -m pip install "git+https://github.com/rio123dx/mcp-sql-result-guard.git@v0.2.0"
```

A virtual environment is optional. If `.codex/config.toml` already exists, merge the example hook into it instead of overwriting other settings. Keep the matcher limited to the MCP SQL execution tool. Choose `MCP_SQL_RESULT_GUARD_FAIL_OPEN=true` or `false` according to the deployment's availability and disclosure requirements.

Follow the [English quick start](../README.md#quick-start) or [Japanese manual](../docs/ja/manual.md#4-quick-start) for setup and smoke-test details.
