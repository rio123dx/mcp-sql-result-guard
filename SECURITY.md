# Security policy

## Reporting a vulnerability

Use a private GitHub security advisory for a vulnerability that could cause the guard to allow a configured sensitive value to reach a final projection or `RETURNING` unexpectedly.

Do not include credentials, personal data, production query text, or proprietary schema details. Provide the smallest synthetic SQL and TSV policy that reproduce the behavior.

Use a normal issue for false positives, dialect-support requests, documentation problems, or behavior that does not expose configured values.

## Supported versions

While the project is in alpha, the latest tagged release and the current default branch are supported. Pin both this package and SQLGlot in operational deployments, and rerun the regression suite before upgrading.

## Security boundary

This package is a static, pre-execution guardrail. It does not guarantee confidentiality and is not a substitute for database authorization, least-privilege roles, masking, row/column security, MCP server-side controls, or post-execution filtering.

Allowed reductions can still support inference through small groups, repeated queries, differencing, or auxiliary knowledge. UDFs, stored procedures, `UNLOAD`, external outputs, side effects, and unmatched tool paths are outside the reliable protection boundary.

Review [Limitations and threat model](docs/limitations.md), [Architecture](docs/architecture.md), and the [production checklist](docs/ja/manual.md#11-本番導入チェックリスト) before deployment.
