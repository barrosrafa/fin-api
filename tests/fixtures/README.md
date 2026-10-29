# Isolated CI data

`public_market_snapshot.json.gz` contains the structure and a bounded sample of **public market/reference tables**, captured on 2026-10-29. The allowlist excludes users, portfolios, custody and billing. Support-ticket structure is included with zero rows. No connection strings, credentials or customer records belong in this file.

`scenarios.sql` adds explicitly synthetic test inputs for industrial/bank financial fields, the -18.82% equity-return regression and four complete historical backtest series. These inputs exist only to exercise contracts and calculations. They are **not market facts** and must never be published as real data or loaded into production.

The loader refuses targets outside local hosts and the disposable database named `fin_ci`, refuses to replace an existing dataset, and creates all objects in one transaction. It does not run production migrations or modify a real ledger. The separate PostgreSQL isolation/idempotency test uses `fin_audit_test` and the actual fin-db migration.

Run locally with PostgreSQL 16 and Redis 7.2:

```sh
DATABASE_URL=postgresql+asyncpg://postgres:ci-only-password@127.0.0.1:5432/fin_ci uv run --extra dev python scripts/load_ci_fixture.py
TEST_POSTGRES_URL=postgresql://postgres:ci-only-password@127.0.0.1:5432/fin_audit_test TEST_REDIS_URL=redis://127.0.0.1:6379/15 uv run --extra dev pytest
```

Refresh public data deliberately with `PUBLIC_FIXTURE_DATABASE_URL` pointing to the approved source and `python scripts/refresh_public_ci_fixture.py`. The exporter opens a read-only transaction and queries only its allowlist. Review the data diff and run the complete suite before committing the updated snapshot. The synthetic scenario file remains separate.
