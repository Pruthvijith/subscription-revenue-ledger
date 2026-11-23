"""Ingest the same revisions twice, then compare the ledger with a reverse-order replay."""
import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from revenue_ledger.cli import demo_files
from revenue_ledger.ledger import ingest, open_ledger


def main() -> None:
    with TemporaryDirectory() as folder:
        root = Path(folder)
        demo_files(root/'inputs')
        files = sorted((root/'inputs').glob('*.jsonl'))
        snapshots = []
        for name, paths in [('forward', files), ('reverse', list(reversed(files)))]:
            with closing(open_ledger(root/(name+'.sqlite'))) as db:
                for path in paths:
                    ingest(db, path.name, path.read_bytes())
                for path in paths:
                    assert ingest(db, path.name, path.read_bytes())['replayed']
                snapshots.append([dict(r) for r in db.execute(
                    'SELECT * FROM bridge ORDER BY month_end')])
                counts = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                          for table in ('changes', 'account_month', 'rejects', 'receipts')}
        assert snapshots[0] == snapshots[1] and len(snapshots[0]) == 12
        print(json.dumps(
            dict(**counts, december=snapshots[0][-1], reordered_replay_equal=True), indent=2))


if __name__ == '__main__':
    main()
