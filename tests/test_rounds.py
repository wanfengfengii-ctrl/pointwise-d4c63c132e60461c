from dispatch.readback import read
from lake.application import initialize
from lake.publish import publish
from rounds.plans import get_round
from surveys.bounds import Rectangle
from surveys.registry import register, resolve_revision
from surveys.revisions import RevisionRef
from tests.fixtures import EAST, WEST, Workspace
from workdb import read_database


class RoundTests(Workspace):
    def test_repeat_setup_and_freeze(self):
        strip = self.revision('footprint', 'S', 'r1', [2, 2, 8, 6])
        zone = self.revision('zone', 'A', 'r1', [4, 3, 16, 7])
        plan = self.plan('survey', 'origin', {EAST: (), WEST: (zone, strip)})
        initialize(self.lake, self.field)
        origin = read(self.lake, 'origin')
        self.assertEqual((origin.hits, origin.delta.added, origin.delta.removed), ((), (), ()))
        newer = self.revision('footprint', 'S', 'r2', [12, 2, 18, 6])
        initialize(self.lake, self.field)
        self.assertEqual(get_round(self.lake, 'survey'), plan)
        self.assertEqual(plan.binding_for(WEST).references, (strip, zone))
        self.assertEqual(self.plan('survey', 'origin', {WEST: (strip, zone), EAST: ()}), plan)
        self.assertEqual(self.seal('survey', WEST).hits[0].footprint, strip)
        self.plan('next', 'origin', {WEST: (newer, zone)})
        self.assertEqual(self.seal('next', WEST).hits, ())
        with self.assertRaisesRegex(ValueError, '冻结'):
            self.plan('survey', 'origin', {WEST: (newer, zone), EAST: ()})
        self.assertEqual(get_round(self.lake, 'survey'), plan)

    def test_conflicting_revision(self):
        original = register(self.field, 'footprint', 'S', 'r1', '外业原表', [2, 2, 8, 6])
        self.plan('survey', 'origin', {WEST: (original.ref,)})
        self.assertEqual(register(self.field, 'footprint', 'S', 'r1', '外业原表', [2, 2, 8, 6]), original)
        conflicts = [('外业原表', [2, 2, 9, 6]), ('另一上游来源', [2, 2, 8, 6])]
        for source, bounds in conflicts:
            with self.subTest(source=source, bounds=bounds):
                with self.assertRaisesRegex(ValueError, '冲突'):
                    register(self.field, 'footprint', 'S', 'r1', source, bounds)
        initialize(self.lake, self.field)
        with read_database(self.field) as db:
            self.assertEqual(resolve_revision(db, original.ref).bounds, Rectangle(2, 2, 8, 6))
            self.assertEqual(resolve_revision(db, original.ref), original)
        self.assertEqual(get_round(self.lake, 'survey').binding_for(WEST).references, (original.ref,))

    def test_invalid_bounds_and_identifiers(self):
        for bounds in ([0, 0, 0, 8], [0, 8, 9, 8], [0, 0, 5.0, 8], [0, 0, True, 8], [0, 3, 5], None):
            with self.subTest(bounds=bounds):
                with self.assertRaises(ValueError):
                    register(self.field, 'zone', 'A', 'r1', '原表', bounds)
        with self.assertRaises(ValueError):
            register(self.field, 'zone', '', 'r1', '原表', [0, 0, 5, 8])
        with read_database(self.field) as db:
            with self.assertRaises(LookupError):
                resolve_revision(db, RevisionRef('zone', 'A', 'r1'))
        self.assertEqual(self.revision('zone', 'A', 'r1', [-4, -2, 5, 8]).object_id, 'A')

    def test_incomplete_or_invalid_plan_does_not_freeze(self):
        strip = self.revision('footprint', 'S', 'r1', [2, 2, 18, 6])
        missing = RevisionRef('zone', 'A', 'r1')
        with self.assertRaisesRegex(LookupError, '修订'):
            self.plan('refresh', 'origin', {WEST: (strip,), EAST: (missing,)})
        with self.assertRaisesRegex(LookupError, '父版'):
            self.plan('refresh', 'lake-missing', {WEST: (strip,)})
        with self.assertRaisesRegex(ValueError, '瓦片号'):
            self.plan('refresh', 'origin', {'01,0': (strip,)})
        with self.assertRaisesRegex(ValueError, '重复'):
            self.plan('refresh', 'origin', {WEST: (strip, strip)})
        with self.assertRaises(LookupError):
            get_round(self.lake, 'refresh')
        plan = self.plan('refresh', 'origin', {WEST: (strip,)})
        self.assertEqual(get_round(self.lake, 'refresh'), plan)

    def test_empty_manifest_can_publish(self):
        self.seed()
        parent = read(self.lake, 'lake-first')
        self.plan('no-rewrite', 'lake-first', {})
        result = publish(self.lake, 'no-rewrite')
        current = read(self.lake, result.version_id)
        self.assertEqual((current.hits, current.origins), (parent.hits, parent.origins))
        self.assertEqual((current.delta.added, current.delta.removed), ((), ()))
