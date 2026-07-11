# Contributing

## Development setup

```bash
python -m pip install -e ".[dev]"
python -m pip check
python -m pytest
python scripts/run_scenarios.py
python -m build
```

## Pull requests

Please include:

- a synthetic SQL reproduction
- the expected allow/warn/deny result
- a regression test or scenario row
- the SQL dialect used
- an explanation of whether the expression carries a value, reduces it, selects it, collects it, or only controls computation

Do not submit real production identifiers, table names, query text, credentials, or user data.

## Policy changes

Changes to what is considered control-only or value-producing can alter the threat model. Update `docs/limitations.md` and the Japanese manual when changing those semantics.
