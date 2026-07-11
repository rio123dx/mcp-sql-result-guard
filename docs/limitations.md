# Limitations and threat model

## Intended protection

This project reduces accidental disclosure of configured column values to an LLM through the normal result set of an MCP SQL execution tool.

It is designed for a workflow where analysts still need to filter, join, group, and aggregate using identifiers, but do not want identifier values returned to the model.

## Not protected

The guard does not prevent:

- writes, deletes, exports, `UNLOAD`, stored procedure side effects, or arbitrary SQL side effects
- equivalent access through another MCP tool, shell command, web service, or database client
- values emitted by UDFs, stored procedures, dynamic SQL, macros, or code the parser cannot inspect
- sensitive values hidden behind unconfigured column names
- inference from counts, booleans, grouping structure, timing, or repeated queries
- re-identification from small groups or combinations of safe-looking attributes
- disclosures already present in prompts, logs, error messages, or MCP metadata
- post-execution changes made by the database or MCP server

## Static analysis trade-offs

The analyzer has no database catalog by default. It cannot know which columns are contained in a base-table `SELECT *`, so that output is controlled by `__SELECT_STAR__`.

Ambiguous or dialect-specific SQL may parse differently from the database. The default fail-open behavior warns and allows on parse/config errors. Environments with stricter requirements should set:

```text
MCP_SQL_RESULT_GUARD_FAIL_OPEN=false
```

## Codex hook boundary

A Codex `PreToolUse` hook is a guardrail, not a complete enforcement boundary. Match the exact MCP SQL execution tool where possible, and keep database permissions and MCP-side policy as the authoritative controls for high-risk data.

## Recommended complementary controls

- least-privilege database roles
- views that exclude raw identifiers
- column masking and row-level security
- query and result audit logs
- MCP server-side statement policy
- minimum group-size policy where inference matters
- post-execution result filtering for strict enforcement
