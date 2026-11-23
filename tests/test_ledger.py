import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from revenue_ledger.ledger import ingest, open_ledger

ROW = dict(account="acct_0001", effective="2026-02-01", version=1, cents=2000, currency="EUR")


def encode(*rows):
    return "\n".join(json.dumps(r) for r in rows).encode()


class LedgerTests(TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.db = open_ledger(folder/"ledger.db")
        self.addCleanup(self.db.close)

    def test_late_revision_preserves_churn_and_identity(self):
        ingest(self.db, 'later', encode(dict(ROW, effective='2026-06-07', cents=0)))
        ingest(self.db, 'revision', encode(dict(ROW, version=2, cents=4000), ROW))
        results = self.db.execute('SELECT * FROM bridge ORDER BY month_end').fetchall()
        self.assertEqual([r['closing_cents'] for r in results[:6]], [0, 4000, 4000, 4000, 4000, 0])
        self.assertEqual(results[5]['churn_cents'], 4000)
        for r in results:
            self.assertEqual(r['opening_cents']+r['starts_cents']+r['expansion_cents']
                             - r['contraction_cents']-r['churn_cents'], r['closing_cents'])

    def test_conflict_rolls_back_batch_including_quarantine(self):
        ingest(self.db, 'base', encode(ROW))
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            ingest(self.db, 'bad', encode({}, dict(ROW, version=2), dict(ROW, cents=1)))
        for table, count in [('changes', 1), ('receipts', 1), ('rejects', 0)]:
            self.assertEqual(self.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0], count)

    def test_retries_and_invalid_payloads(self):
        batch = encode(ROW, {}, dict(ROW, cents=True), dict(ROW, effective='2025-12-31'))+b'\n{'
        result = ingest(self.db, '01', batch)
        self.assertEqual((result['inserted'], result['rejected']), (1, 4))
        self.assertTrue(ingest(self.db, '01', batch)['replayed'])
        with self.assertRaisesRegex(ValueError, 'different bytes'):
            ingest(self.db, '01', encode(ROW))

    def test_dbt_model_and_reference_ledger_agree(self):
        ingest(self.db, 'all', encode(ROW, dict(ROW, effective='2026-04-05', cents=4000),
                                      dict(ROW, effective='2026-05-05', cents=1000)))
        root = Path(__file__).resolve().parents[1]/'dbt'
        sql = (root/'models/fct_mrr_movements.sql').read_text()
        self.db.execute("CREATE VIEW readout AS " +
                        sql.replace("{{ ref('account_month_input') }}", "account_month"))
        for test in (root/'tests').glob('*.sql'):
            rendered = test.read_text().replace("{{ ref('fct_mrr_movements') }}", "readout").replace(
                "{{ ref('bridge_input') }}", "bridge")
            self.assertEqual(self.db.execute(rendered).fetchall(), [])
