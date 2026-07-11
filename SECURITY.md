# Security policy

## Reporting a vulnerability

Please open a private GitHub security advisory for vulnerabilities that could cause the guard to allow a sensitive final projection unexpectedly. Do not include real credentials, personal data, production SQL, or proprietary schemas in a public issue.

For ordinary false positives, dialect support, and documentation problems, use a normal issue with a minimized synthetic SQL example.

## Supported versions

The latest tagged release and the current default branch are the supported versions while the project is in alpha.

## Scope reminder

This package is a static, pre-execution guardrail. It is not a database authorization layer and should not be treated as the sole control for confidential data.
