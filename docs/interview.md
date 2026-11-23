# Interview preparation · Incremental subscription revenue ledger

Use first-person wording after you have run the demo and can explain or change the code yourself. Describe this as a portfolio implementation. Quantities below refer to the synthetic fixture.

## 30-second introduction

I built a small subscription ledger around a finance question: could we explain a monthly close after a backdated correction? It stores revisions, rebuilds affected accounts and reconciles every cent. Reversing the order of the synthetic batches produced exactly the same twelve monthly balances. I can demonstrate both safe retry behavior and rollback on a conflicting revision.

## Two-minute technical explanation

Ledger.py starts one immediate write transaction per batch. It remembers the batch hash, validates each row and records revisions keyed by account, effective date and version. Latest resolves event order independently from arrival order. Rebuild materializes only touched accounts across the calendar. SQL LAG compares month-end balances to classify changes. CLI exports balances and reference results for a second dbt model with bidirectional parity tests.

Grain is one EUR account balance per calendar month end. For each effective date use the highest revision and carry the most recent balance forward. A zero balance ends recurring revenue. The bridge reconciles opening + starts + expansion − contraction − churn to closing. Starts include reactivations. Calendar year 2026 is fixed in the sample. The opening balance before January is assumed zero.

The demo processed 254 distinct revisions for 120 synthetic accounts, quarantined one malformed row and produced 1,440 account-month balances. Reversing the order of all three batches produced identical monthly bridges. December closed at €8,433 recurring revenue in this fixture.

The fixed calendar and one balance per account exclude multi-currency conversion, per-subscription proration and booked opening balances. A serial writer and a twelve-month rebuild per touched account have predictable local costs. A high-volume ledger would need partitioned writes, retention and a versioned calendar.

## Architecture walkthrough

Open the files in this order and follow one record through the system.

[ledger.py](../src/revenue_ledger/ledger.py) · [cli.py](../src/revenue_ledger/cli.py)

Ledger.py starts one immediate write transaction per batch. It remembers the batch hash, validates each row and records revisions keyed by account, effective date and version. Latest resolves event order independently from arrival order. Rebuild materializes only touched accounts across the calendar. SQL LAG compares month-end balances to classify changes. CLI exports balances and reference results for a second dbt model with bidirectional parity tests.

## Five technical questions

**1. Why keep two identities?**

The batch digest handles transport retries. Account, effective date and version carry business identity across batches.

**2. Why rebuild twelve months?**

A correction may affect later balances until the next effective change. At this scale a bounded full-account rebuild is simpler to verify.

**3. What happens to malformed lines?**

Store a reason category and line number, then commit other valid records. A contradictory revision aborts the batch because the correct balance is ambiguous.

**4. How do you prove parity?**

The dbt tests compare both result-set directions with EXCEPT and check the signed movement equation. The local suite runs these queries in SQLite.

**5. How would concurrency change the design?**

SQLite serializes writers with BEGIN IMMEDIATE. Partition accounts across workers in a warehouse and make receipt ownership transactional.

## Five product and business questions

**1. Is recurring revenue cash received?**

It is the recurring contract balance at month end. Billing, cash collections and revenue recognition need their own ledgers.

**2. Does a return after churn count as new?**

This MVP groups returns with starts. Agree a separate reactivation definition before acquisition reporting.

**3. Which metric is non-negotiable?**

A zero-cent movement reconciliation difference for every month.

**4. How would you handle a restated close?**

Persist an as-published close and separately produce the restated view. The demo currently recomputes current truth.

**5. What would justify a broker?**

Continuous feeds with many producers, high concurrency and retention requirements. Closed micro-batches are adequate for this fixture.

## What to demonstrate live

Run `python scripts/demo.py`. Point to one input, the relevant transformation and the output that supports your decision. Add a second revision effective before a cancellation. Predict the affected month-end balances and verify the bridge after reversing delivery order.

## Main trade-off and next test

Python’s standard library and SQLite handle contracts, transactions and an inspectable warehouse. A second SQL implementation in dbt reads exported seeds for parity checks. The dbt SQL and assertions were exercised in SQLite after resolving relation names. The DuckDB adapter build is configured for CI and awaits execution.

The fixed calendar and one balance per account exclude multi-currency conversion, per-subscription proration and booked opening balances. A serial writer and a twelve-month rebuild per touched account have predictable local costs. A high-volume ledger would need partitioned writes, retention and a versioned calendar.

## CV wording for a portfolio section

- Built an incremental EUR subscription ledger with revision-aware processing, transactional replay and SQL reconciliation across 1,440 synthetic account-months.
