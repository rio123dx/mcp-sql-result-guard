# Contributing

Contributions are welcome for SQL-dialect coverage, value-flow analysis, rule behavior, documentation, examples, and tests.

## Development setup

Requires Python 3.10 or later.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip check
python -m pytest
python scripts/run_scenarios.py
python -m build
```

Current expected totals are 199 pytest cases and 156 SQL scenarios.

## Pull requests

Describe:

- the problem and intended user impact
- a minimized synthetic SQL example
- the expected allow, warn, or deny result
- the SQL dialect used
- whether the expression carries a value, reduces it, selects it, collects it, or only controls computation
- the tests and documentation updated

Do not submit credentials, personal data, production identifiers, production query text, or proprietary schema details.

## Scenario tests

Add policy scenarios to `scripts/generate_scenarios.py`, then regenerate `tests/data/sql_scenarios.tsv`. Keep table and column names synthetic. Include both the expected result and a short reason.

When adding dialect-specific behavior, include the dialect context in the PR and test parser-failure behavior where relevant.

## Policy and threat-model changes

Changes to control-only inputs, value-producing paths, aggregate classification, star handling, or failure behavior can alter the threat model. Update these documents together when semantics change:

- `README.md` and `README.ja.md`
- `docs/architecture.md`
- `docs/limitations.md`
- `docs/ja/manual.md`
- `docs/test-report.md`

Documentation-only changes should keep English and Japanese terminology, examples, links, version numbers, and test totals consistent.
