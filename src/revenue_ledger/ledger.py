"""Transactional micro-batches for a versioned, single-currency subscription feed."""

import hashlib
import json
import re
import sqlite3
from calendar import monthrange
from datetime import date
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS months(month_end TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS changes (
  account TEXT NOT NULL, effective TEXT NOT NULL, version INTEGER NOT NULL, cents INTEGER NOT NULL,
  PRIMARY KEY(account,effective,version));
CREATE TABLE IF NOT EXISTS account_month (
  account TEXT NOT NULL, month_end TEXT NOT NULL, cents INTEGER NOT NULL,
  PRIMARY KEY(account,month_end));
CREATE TABLE IF NOT EXISTS rejects (
  batch TEXT NOT NULL, line INTEGER NOT NULL, reason TEXT NOT NULL,
  PRIMARY KEY(batch,line));
CREATE TABLE IF NOT EXISTS receipts (
  batch TEXT PRIMARY KEY, digest TEXT NOT NULL, inserted INTEGER NOT NULL, rejected INTEGER NOT NULL);
CREATE VIEW IF NOT EXISTS latest AS
  SELECT account,effective,cents FROM (
    SELECT *,row_number() OVER(PARTITION BY account,effective ORDER BY version DESC) AS seq FROM changes
  ) WHERE seq=1;
CREATE VIEW IF NOT EXISTS bridge AS
  WITH movements AS (SELECT *,coalesce(lag(cents) OVER(PARTITION BY account ORDER BY month_end),0) prior
    FROM account_month)
  SELECT month_end,sum(prior) AS opening_cents,
    sum(CASE WHEN prior=0 THEN cents ELSE 0 END) AS starts_cents,
    sum(CASE WHEN prior>0 AND cents>prior THEN cents-prior ELSE 0 END) AS expansion_cents,
    sum(CASE WHEN cents>0 AND cents<prior THEN prior-cents ELSE 0 END) AS contraction_cents,
    sum(CASE WHEN cents=0 THEN prior ELSE 0 END) AS churn_cents, sum(cents) AS closing_cents
  FROM movements GROUP BY month_end;
"""


def open_ledger(path: Path, year: int = 2026) -> sqlite3.Connection:
    """The calendar is part of this dataset's contract and is fixed at creation."""
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(DDL)
    months = [date(year, m, monthrange(year, m)[1]).isoformat() for m in range(1, 13)]
    with db:
        db.executemany("INSERT OR IGNORE INTO months VALUES (?)", [(m,) for m in months])
        if db.execute("SELECT count(*) FROM months").fetchone()[0] != 12:
            raise ValueError("Calendar differs from existing ledger")
    return db


def contract(line: str, year: str) -> tuple:
    row = json.loads(line)
    if not isinstance(row, dict) or set(row) != {"account", "effective", "version", "cents", "currency"}:
        raise ValueError("Invalid schema")
    if not isinstance(row["account"], str) or not re.fullmatch(r"acct_[0-9]{4,8}", row["account"]):
        raise ValueError("Invalid synthetic account key")
    if not isinstance(row["effective"], str):
        raise ValueError("Invalid effective date")
    day = date.fromisoformat(row["effective"])
    if day.isoformat() != row["effective"] or str(day.year) != year:
        raise ValueError("Date outside calendar")
    if row["currency"] != "EUR" or type(row["cents"]) is not int or not 0 <= row["cents"] <= 10**10:
        raise ValueError("Invalid EUR recurring value")
    if type(row["version"]) is not int or not 1 <= row["version"] <= 2**31-1:
        raise ValueError("Invalid version")
    return row["account"], day.isoformat(), row["version"], row["cents"]


def rebuild(db: sqlite3.Connection, account: str) -> None:
    """Recompute the affected account through the calendar, including zero months."""
    db.execute("DELETE FROM account_month WHERE account=?", (account,))
    db.execute("""
        INSERT INTO account_month SELECT ?,month_end,
          coalesce((SELECT cents FROM latest WHERE account=? AND effective<=months.month_end
          ORDER BY effective DESC LIMIT 1),0) FROM months
        """, (account, account))


def ingest(db: sqlite3.Connection, batch: str, payload: bytes) -> dict:
    digest = hashlib.sha256(payload).hexdigest()
    text = payload.decode('utf-8')
    with db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT * FROM receipts WHERE batch=?", (batch,)).fetchone()
        if previous:
            if previous["digest"] != digest:
                raise ValueError("Batch name reused with different bytes")
            return dict(replayed=True, inserted=0, rejected=previous["rejected"], rebuilt_accounts=0)
        year = db.execute("SELECT substr(min(month_end),1,4) FROM months").fetchone()[0]
        accounts = set()
        inserted = rejected = 0
        for number, line in enumerate(text.splitlines(), 1):
            try:
                account, day, version, cents = contract(line, year)
            except ValueError as exc:
                # Store only the reason category and line number. Source stays with feeder.
                reason = "Malformed JSON" if isinstance(
                    exc, json.JSONDecodeError) else "Invalid contract"
                db.execute("INSERT INTO rejects VALUES (?,?,?)", (batch, number, reason))
                rejected += 1
                continue
            known = db.execute("SELECT cents FROM changes WHERE account=? AND effective=? AND version=?",
                               (account, day, version)).fetchone()
            if known:
                if known[0] != cents:
                    raise ValueError(f"Conflicting revision at line {number}")
                continue
            db.execute("INSERT INTO changes VALUES (?,?,?,?)", (account, day, version, cents))
            accounts.add(account)
            inserted += 1
        for account in sorted(accounts):
            rebuild(db, account)
        db.execute("INSERT INTO receipts VALUES (?,?,?,?)", (batch, digest, inserted, rejected))
    return dict(replayed=False, inserted=inserted, rejected=rejected, rebuilt_accounts=len(accounts))
