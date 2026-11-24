import sqlite3

from dispatch.readback import read
from lake.evidence import load_round_evidence
from lake.intake import accept_tile
from lake.publish import publish
from lake.versions import find_round_publication
from tests.fixtures import EAST, WEST, Workspace, hit_pairs, observe
from tiles.release import release_tile
from tiles.staging import load_staged
from workdb import read_database, write_database


class PublicationTests(Workspace):
    def test_cross_tile_delta(self):
        _, zone = self.seed()
        parent = read(self.lake, 'lake-first')
        self.assertEqual(hit_pairs(parent.hits), [('S', 'A')])
        self.assertEqual([(o.tile_id, o.area, o.footprint_revision) for o in parent.origins],
                         [(WEST, 18, 'r1'), (EAST, 18, 'r1')])
        moved = self.revision('footprint', 'S', 'r2', [12, 2, 18, 6])
        self.plan('west-empty', 'lake-first', {WEST: (moved, zone)})
        west = self.seal('west-empty', WEST)
        self.assertEqual(west.hits, ())
        receipt = accept_tile(self.lake, 'west-empty', west)
        release_tile(self.lake, self.field, west.source_id, receipt)
        first = read(self.lake, publish(self.lake, 'west-empty').version_id)
        self.assertEqual(hit_pairs(first.hits), [('S', 'A')])
        self.assertEqual((first.delta.added, first.delta.removed), ((), ()))
        self.assertEqual(first.origins, (parent.origins[1],))
        self.assertEqual(first.origins[0].source_round, 'first')
        self.plan('east-empty', first.version_id, {EAST: ()})
        accept_tile(self.lake, 'east-empty', self.seal('east-empty', EAST))
        second = read(self.lake, publish(self.lake, 'east-empty').version_id)
        self.assertEqual((second.hits, second.delta.added), ((), ()))
        self.assertEqual(hit_pairs(second.delta.removed), [('S', 'A')])
        self.assertEqual(second.removed_origins, first.origins)
        self.assertEqual(read(self.lake, parent.version_id), parent)

    def test_same_global_parent_with_only_west_support(self):
        _, zone = self.seed(east_support=False)
        moved = self.revision('footprint', 'S', 'r2', [12, 2, 18, 6])
        self.plan('west-empty', 'lake-first', {WEST: (moved, zone)})
        west = self.seal('west-empty', WEST)
        self.assertEqual(west.hits, ())
        receipt = accept_tile(self.lake, 'west-empty', west)
        release_tile(self.lake, self.field, west.source_id, receipt)
        self.assertEqual(hit_pairs(read(self.lake, 'lake-first').hits), [('S', 'A')])
        current = read(self.lake, publish(self.lake, 'west-empty').version_id)
        self.assertEqual((current.hits, current.delta.added), ((), ()))
        self.assertEqual(hit_pairs(current.delta.removed), [('S', 'A')])
        self.assertEqual([origin.tile_id for origin in current.removed_origins], [WEST])

    def test_late_tile_publication(self):
        for zone_name in ('A', 'B'):
            by_order = []
            for order in ((WEST, EAST), (EAST, WEST)):
                with self.subTest(zone=zone_name, first=order[0]):
                    self.start_workspace(self.root / f'{zone_name}-{order[0]}')
                    _, zone_a = self.seed(east_support=False)
                    before = read(self.lake, 'lake-first')
                    shifted = self.revision('footprint', 'S', 'r2', [12, 2, 18, 6])
                    zone_b = self.revision('zone', 'B', 'r1', [13, 3, 19, 7])
                    target = zone_a if zone_name == 'A' else zone_b
                    self.plan('shift', before.version_id, {WEST: (shifted, zone_a), EAST: (shifted, target)})

                    early = self.seal('shift', order[0])
                    early_receipt = accept_tile(self.lake, 'shift', early)
                    release_tile(self.lake, self.field, early.source_id, early_receipt)
                    with read_database(self.field) as db:
                        self.assertIsNone(load_staged(db, early.source_id))
                    with read_database(self.lake) as db:
                        self.assertEqual(load_round_evidence(db, 'shift')[order[0]].packet, early)
                    pending = publish(self.lake, 'shift')
                    self.assertEqual((pending.status, pending.missing, pending.version_id), ('pending', (order[1],), None))
                    self.assertEqual(read(self.lake, before.version_id), before)
                    self.assertIsNone(read(self.lake, 'lake-shift'))
                    with read_database(self.lake) as db:
                        self.assertIsNone(find_round_publication(db, 'shift'))

                    late = self.seal('shift', order[1])
                    accept_tile(self.lake, 'shift', late)
                    issued = publish(self.lake, 'shift')
                    self.assertEqual((issued.status, issued.version_id), ('published', 'lake-shift'))
                    current = read(self.lake, issued.version_id)
                    expected_hits = [('S', zone_name)]
                    expected_added = [] if zone_name == 'A' else [('S', 'B')]
                    expected_removed = [] if zone_name == 'A' else [('S', 'A')]
                    self.assertEqual(hit_pairs(current.hits), expected_hits)
                    self.assertEqual(hit_pairs(current.delta.added), expected_added)
                    self.assertEqual(hit_pairs(current.delta.removed), expected_removed)
                    self.assertEqual([(o.tile_id, o.footprint_revision, o.area) for o in current.origins],
                                     [(EAST, 'r2', 12 if zone_name == 'A' else 15)])
                    self.assertEqual(current.added_origins, () if zone_name == 'A' else current.origins)
                    self.assertEqual(current.removed_origins, () if zone_name == 'A' else before.origins)
                    self.assertEqual(read(self.lake, before.version_id), before)
                    self.assertEqual(accept_tile(self.lake, 'shift', early), early_receipt)
                    self.assertEqual(publish(self.lake, 'shift'), issued)
                    by_order.append(current)
                    if zone_name == 'A' and order[0] == WEST:
                        observe('t7', {'order': order, 'parent_hit': ['S', 'A'], 'new_strip': [12, 2, 18, 6],
                                       'zone_a': [4, 3, 16, 7]},
                                {'first_status': 'pending', 'missing': [EAST]},
                                {'first_status': pending.status, 'missing': pending.missing},
                                {'hits': expected_hits, 'added': [], 'removed': []},
                                {'hits': hit_pairs(current.hits), 'added': hit_pairs(current.delta.added),
                                 'removed': hit_pairs(current.delta.removed)},
                                ['tiles/release.py', 'lake/evidence.py', 'lake/publish.py', 'dispatch/readback.py'],
                                '西窗口无共同面积，东窗口内新测带与 A 相交 12 平方格。具名键与父版相同。')
            self.assertEqual(len(by_order), 2)
            self.assertEqual(by_order[0], by_order[1])

    def test_publish_failure_and_retry(self):
        _, zone = self.seed(east_support=False)
        before = read(self.lake, 'lake-first')
        self.plan('second', before.version_id, {WEST: (), EAST: (
            self.revision('footprint', 'S', 'r2', [12, 2, 18, 6]), zone,
        )})
        west = self.seal('second', WEST)
        west_receipt = accept_tile(self.lake, 'second', west)
        release_tile(self.lake, self.field, west.source_id, west_receipt)
        self.assertEqual(publish(self.lake, 'second').missing, (EAST,))
        east = self.seal('second', EAST)
        east_receipt = accept_tile(self.lake, 'second', east)
        with write_database(self.lake) as db:
            db.execute('CREATE TABLE commit_guard (id INTEGER PRIMARY KEY)')
            db.execute('''
                CREATE TABLE commit_fault (
                    version_id TEXT PRIMARY KEY,
                    guard_id INTEGER REFERENCES commit_guard(id) DEFERRABLE INITIALLY DEFERRED
                )
            ''')
            db.execute('''
                CREATE TRIGGER fail_second_commit AFTER INSERT ON dispatch_sheets
                WHEN NEW.version_id = 'lake-second'
                BEGIN INSERT INTO commit_fault VALUES (NEW.version_id, 99); END
            ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            publish(self.lake, 'second')
        self.assertEqual(read(self.lake, before.version_id), before)
        self.assertIsNone(read(self.lake, 'lake-second'))
        with read_database(self.field) as db:
            self.assertIsNone(load_staged(db, west.source_id))
        with read_database(self.lake) as db:
            self.assertIsNone(find_round_publication(db, 'second'))
            for table in ('lake_versions', 'lake_signoffs', 'version_tile_support', 'dispatch_sheets', 'commit_fault'):
                with self.subTest(table=table):
                    count = db.execute(f'SELECT count(*) FROM {table} WHERE version_id = ?', ('lake-second',)).fetchone()
                    self.assertEqual(count, (0,))
            evidence = load_round_evidence(db, 'second')
            self.assertEqual({tile: value.packet for tile, value in evidence.items()}, {WEST: west, EAST: east})
        with write_database(self.lake) as db:
            db.execute('DROP TRIGGER fail_second_commit')
        self.assertEqual(accept_tile(self.lake, 'second', west), west_receipt)
        self.assertEqual(accept_tile(self.lake, 'second', east), east_receipt)
        retried = publish(self.lake, 'second')
        self.assertEqual(retried.status, 'published')
        self.assertEqual(publish(self.lake, 'second'), retried)
        current = read(self.lake, retried.version_id)
        self.assertEqual(hit_pairs(current.hits), [('S', 'A')])
        self.assertEqual((current.delta.added, current.delta.removed), ((), ()))
        self.assertEqual([(origin.tile_id, origin.footprint_revision) for origin in current.origins], [(EAST, 'r2')])
        self.assertEqual(read(self.lake, before.version_id), before)

    def test_sorted_multiple_keys_and_origins(self):
        strip = self.revision('footprint', 'S', 'r2', [2, 2, 18, 6])
        twin = self.revision('footprint', 'T', 'r1', [2, 2, 18, 6])
        zone_a = self.revision('zone', 'A', 'r1', [4, 3, 16, 7])
        zone_b = self.revision('zone', 'B', 'r3', [4, 3, 16, 7])
        self.plan('many', 'origin', {EAST: (zone_b, twin, zone_a, strip), WEST: (zone_b, strip)})
        for tile in (EAST, WEST):
            accept_tile(self.lake, 'many', self.seal('many', tile))
        sheet = read(self.lake, publish(self.lake, 'many').version_id)
        keys = [('S', 'A'), ('S', 'B'), ('T', 'A'), ('T', 'B')]
        self.assertEqual(hit_pairs(sheet.hits), keys)
        self.assertEqual(hit_pairs(sheet.delta.added), keys)
        self.assertEqual([(o.key.footprint_id, o.key.zone_id, o.tile_id, o.footprint_revision, o.zone_revision)
                          for o in sheet.origins],
                         [('S', 'A', EAST, 'r2', 'r1'), ('S', 'B', WEST, 'r2', 'r3'),
                          ('S', 'B', EAST, 'r2', 'r3'), ('T', 'A', EAST, 'r1', 'r1'),
                          ('T', 'B', EAST, 'r1', 'r3')])
        self.assertEqual(sheet.added_origins, sheet.origins)
