import argparse
import csv
import json
import random
from contextlib import closing
from pathlib import Path

from revenue_ledger.ledger import ingest, open_ledger


def demo_files(folder: Path) -> None:
    rng = random.Random(15)
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError("Use a new or empty directory for generated input")
    batches = [[], [], []]
    for n in range(120):
        account = f"acct_{n:04}"
        first = rng.randint(1, 3)
        second = rng.randint(4, 9)
        cents = rng.choice([3900, 7900, 15900, 24900])
        row = dict(account=account,
                   effective=f"2026-{first:02}-01", version=1, cents=cents, currency="EUR")
        batches[0].append(row)
        batches[1].append(
            dict(row, effective=f"2026-{second:02}-10", cents=rng.choice([0, 3900, 15900])))
        if n % 9 == 0:
            batches[2].extend([dict(row, version=2, cents=cents+1000), row])
    batches[2].append({"currency": "USD"})
    for i, rows in enumerate(batches):
        (folder/f"{i+1:02}.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("ledger.sqlite"))
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["generate", "load", "export"]:
        sub.add_parser(name).add_argument("folder", type=Path)
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "generate":
        demo_files(args.folder)
        return
    with closing(open_ledger(args.db)) as db:
        if args.command == "load":
            files = sorted(args.folder.glob("*.jsonl"))
            if not files:
                raise ValueError("No JSONL batches found")
            for path in files:
                print(json.dumps(dict(batch=path.name, **ingest(db, path.name, path.read_bytes()))))
        elif args.command == "export":
            args.folder.mkdir(parents=True, exist_ok=True)
            for table, order in [('account_month', 'account,month_end'), ('bridge', 'month_end')]:
                rows = db.execute(f"SELECT * FROM {table} ORDER BY {order}")
                with (args.folder/f"{table}_input.csv").open("w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([col[0] for col in rows.description])
                    writer.writerows(rows)
        else:
            print(json.dumps([dict(r) for r in db.execute("SELECT * FROM bridge ORDER BY month_end")],
                             indent=2))


if __name__ == "__main__":
    main()
