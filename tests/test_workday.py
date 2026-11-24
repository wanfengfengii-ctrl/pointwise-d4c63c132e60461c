from dispatch.readback import read
from lake.application import EXAMPLES, initialize, run_workday
from surveys.registry import resolve_revision
from surveys.revisions import RevisionRef
from tests.fixtures import EAST, WEST, Workspace, hit_pairs
from tiles.staging import load_clearance, load_staged
from workdb import read_database


class WorkdayTests(Workspace):
    def test_complete_workday_and_repeat_on_existing_database(self):
        private_ref = self.revision('zone', 'C', 'field-only', [-2, 1, 4, 9])
        sources, workday = EXAMPLES / 'sources.json', EXAMPLES / 'workday.json'
        report = run_workday(self.lake, self.field, sources, workday)
        self.assertEqual([row['round_id'] for row in report], ['morning', 'midday', 'evening'])
        self.assertEqual([[attempt['status'] for attempt in row['attempts']] for row in report],
                         [['pending', 'published'], ['pending', 'published'], ['published']])
        self.assertEqual(report[0]['attempts'][0]['missing'], (WEST,))
        self.assertEqual(report[1]['attempts'][0]['missing'], (EAST,))
        ids = ['lake-morning', 'lake-midday', 'lake-evening']
        morning, midday, evening = [read(self.lake, version_id) for version_id in ids]
        self.assertEqual([hit_pairs(sheet.hits) for sheet in (morning, midday, evening)],
                         [[('S', 'A')], [('S', 'A')], [('S', 'B')]])
        self.assertEqual([(o.tile_id, o.area) for o in morning.origins], [(WEST, 12)])
        self.assertEqual([(o.tile_id, o.area) for o in midday.origins], [(EAST, 12)])
        self.assertEqual((midday.delta.added, midday.delta.removed), ((), ()))
        self.assertEqual(hit_pairs(evening.delta.added), [('S', 'B')])
        self.assertEqual(hit_pairs(evening.delta.removed), [('S', 'A')])
        self.assertEqual(evening.removed_origins, midday.origins)
        self.assertEqual(evening.added_origins, evening.origins)
        self.assertEqual(evening.added_origins[0].area, 15)
        clearances = [item for row in report for item in row['clearances']]
        self.assertEqual(len(clearances), 5)
        with read_database(self.field) as db:
            for result in clearances:
                self.assertEqual(result['status'], 'cleared')
                self.assertIsNone(load_staged(db, result['source_id']))
                self.assertEqual(load_clearance(db, result['source_id']).receipt_id, result['receipt_id'])
        initialize(self.lake, self.field)
        replay = run_workday(self.lake, self.field, sources, workday)
        self.assertEqual([row['dispatch'] for row in replay], [row['dispatch'] for row in report])
        self.assertEqual([row['clearances'] for row in replay], [row['clearances'] for row in report])
        with read_database(self.field) as db:
            self.assertEqual(resolve_revision(db, private_ref).source, '外业 C field-only')
            self.assertEqual(resolve_revision(db, RevisionRef('footprint', 'S', 'r1')).bounds.right, 8)
        self.assertEqual([read(self.lake, version_id) for version_id in ids], [morning, midday, evening])
