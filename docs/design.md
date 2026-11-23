# Product requirements and operating notes

## User decision and opportunity

A billing feed can deliver a cancellation before its original contract or revise a backdated amount. Finance needs a monthly recurring revenue bridge where every movement reconciles and an engineer can replay corrections safely.

| Stakeholder | Priority and milestone | Acceptance criterion |
|---|---|---|
| Finance controller | P0 · reconcile close | Prove opening plus movements equals closing for every month. Use integer cents throughout. |
| Data engineering | P0 · recover retries | A conflicting revision rolls back facts, quarantine and receipt together. Reversed delivery order must produce identical balances. |
| Analytics engineering | P1 · share metric | Publish a model with explicit grain and compare every movement column against the exported source. |

## Metric definitions and validation

Grain is one EUR account balance per calendar month end. For each effective date use the highest revision and carry the most recent balance forward. A zero balance ends recurring revenue. The bridge reconciles opening + starts + expansion − contraction − churn to closing. Starts include reactivations. Calendar year 2026 is fixed in the sample. The opening balance before January is assumed zero.

The demo processed 254 distinct revisions for 120 synthetic accounts, quarantined one malformed row and produced 1,440 account-month balances. Reversing the order of all three batches produced identical monthly bridges. December closed at €8,433 recurring revenue in this fixture.

## Architecture decision record

**Accepted for this local workload.** Python’s standard library and SQLite handle contracts, transactions and an inspectable warehouse. A second SQL implementation in dbt reads exported seeds for parity checks. The dbt SQL and assertions were exercised in SQLite after resolving relation names. The DuckDB adapter build is configured for CI and awaits execution.

Ledger.py starts one immediate write transaction per batch. It remembers the batch hash, validates each row and records revisions keyed by account, effective date and version. Latest resolves event order independently from arrival order. Rebuild materializes only touched accounts across the calendar. SQL LAG compares month-end balances to classify changes. CLI exports balances and reference results for a second dbt model with bidirectional parity tests.

The implementation lives in [the Python package](../src/revenue_ledger). The boundaries are exercised by [the test suite](../tests).

## Operating procedure

Supply a closed UTF-8 JSONL file with a fresh batch name. Run the load command periodically to process new files. Same-name, same-byte batches are safe to retry. Reused names with different bytes and conflicting revisions abort the whole batch. Inspect `rejects` by name and line. Correct rejected records under a new receipt identity. For reconstruction, load all original batches into an empty database and compare the bridge. A proposed acceptance objective is zero unreconciled cents at close.

1. Reproduce the baseline with `python scripts/demo.py`. Compare the decision fields with the committed example.
2. Run the regression suite before changing input definitions or thresholds. Use the persistent example in the README to inspect intermediate state.
3. Replay the source and compare results across independent runs before releasing a new batch definition.

### Container example

From the repository root:

```shell
docker build -t portfolio-demo .
docker run --rm portfolio-demo
```

The container runs the isolated demo and exits.
This configuration awaits Docker execution. The same demo was exercised with the installed Python package.

## Constraints, reliability and delivery

The fixed calendar and one balance per account exclude multi-currency conversion, per-subscription proration and booked opening balances. A serial writer and a twelve-month rebuild per touched account have predictable local costs. A high-volume ledger would need partitioned writes, retention and a versioned calendar.

Begin with the contract and calendar. Add batch receipts and atomic account rebuilds. Then validate local SQL parity and review definition ownership with finance. Next run the DuckDB adapter in CI and test opening balances spanning two years.

Local demo data and code are independent of former employers. Cost scenarios use declared assumptions. Operational targets describe a proposed pilot.
