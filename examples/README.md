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

A virtual environment is optional, but the environment's scripts directory must be on the `PATH` seen by Codex. Confirm the installation with `command -v mcp-sql-result-guard` on WSL/Linux or `Get-Command mcp-sql-result-guard` on Windows.

If `.codex/config.toml` already exists, merge the example hook into it instead of overwriting other settings. Add `hooks = true` to the existing `[features]` table, or create that table only when absent, append the `[[hooks.PreToolUse]]` group, and preserve every unrelated setting and hook.

Keep the matcher limited to the MCP SQL execution tool. Choose `MCP_SQL_RESULT_GUARD_FAIL_OPEN=true` or `false` according to the deployment's availability and disclosure requirements.

## Smoke test

Run these commands from the project root after installing the CLI and creating `.codex/hooks/sensitive_columns.tsv`. The allowed query should produce no stdout; the denied query should return JSON containing `permissionDecision: "deny"`.

### WSL or Linux

```bash
export MCP_SQL_RESULT_GUARD_RULES="$PWD/.codex/hooks/sensitive_columns.tsv"
export MCP_SQL_RESULT_GUARD_DIALECT=redshift
export MCP_SQL_RESULT_GUARD_FAIL_OPEN=true

printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT order_total FROM orders WHERE user_id IS NOT NULL"}}' \
  | mcp-sql-result-guard

printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT user_id FROM orders"}}' \
  | mcp-sql-result-guard
```

### Windows PowerShell

Save [`codex/run-sql-guard.ps1`](codex/run-sql-guard.ps1) as `.codex/hooks/run-sql-guard.ps1`, then test the same path used by `command_windows`:

```powershell
Get-Command mcp-sql-result-guard

$allow = '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT order_total FROM orders WHERE user_id IS NOT NULL"}}'
$allow | powershell -NoProfile -ExecutionPolicy Bypass -File .codex\hooks\run-sql-guard.ps1

$deny = '{"hook_event_name":"PreToolUse","tool_name":"mcp__warehouse__execute_sql","tool_input":{"sql":"SELECT user_id FROM orders"}}'
$deny | powershell -NoProfile -ExecutionPolicy Bypass -File .codex\hooks\run-sql-guard.ps1
```

Follow the [English quick start](../README.md#quick-start) or [Japanese manual](../docs/ja/manual.md#4-quick-start) for setup and smoke-test details.
