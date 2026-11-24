from dataclasses import replace
import sqlite3

from dispatch.readback import read
from lake.evidence import load_round_evidence
from lake.intake import accept_tile
from lake.publish import publish
from lake.receipts import TileReceipt, find_receipt
from rounds.input_bindings import TileBinding
from tests.fixtures import EAST, WEST, Workspace, hit_pairs, observe
from tiles.packets import packet_identity
from tiles.release import release_tile
from tiles.staging import load_clearance, load_staged
from workdb import read_database, write_database


def with_digest(packet):
    return replace(packet, digest=packet_identity(packet))


class DeliveryTests(Workspace):
    def test_overlap_and_edge_touch(self):
        strip_bounds = [2, 2, 18, 6]
        zone_bounds = [4, 3, 16, 7]
        strip = self.revision('footprint', 'S', 'r1', strip_bounds)
        twin = self.revision('footprint', 'T', 'r1', strip_bounds)
        zone = self.revision('zone', 'A', 'r1', zone_bounds)
        zone_twin = self.revision('zone', 'AA', 'r1', zone_bounds)
        edge = self.revision('zone', 'edge', 'r1', [8, 6, 11, 9])
        outside = self.revision('zone', 'outside', 'r1', [12, 3, 16, 5])
        corner = self.revision('zone', 'corner', 'r1', [18, 6, 20, 8])
        self.plan('clip', 'origin', {
            WEST: (outside, twin, zone_twin, strip, edge, zone),
            EAST: (strip, corner),
        })
        with self.assertRaisesRegex(ValueError, '名单'):
            self.seal('clip', '2,0')
        west = self.seal('clip', WEST)
        east = self.seal('clip', EAST)
        rows = [(*hit.named_key, hit.area) for hit in west.hits]
        expected = [('S', 'A', 18), ('S', 'AA', 18), ('T', 'A', 18), ('T', 'AA', 18)]
        self.assertEqual(rows, expected)
        self.assertEqual(east.hits, ())
        self.assertEqual(self.seal('clip', WEST), west)
        for packet in (east, west):
            accept_tile(self.lake, 'clip', packet)
        sheet = read(self.lake, publish(self.lake, 'clip').version_id)
        expected_keys = [('S', 'A'), ('S', 'AA'), ('T', 'A'), ('T', 'AA')]
        actual_keys = hit_pairs(sheet.delta.added)
        self.assertEqual(actual_keys, expected_keys)
        self.assertEqual(sheet.delta.removed, ())
        observe('t3', {'west_window': [0, 0, 10, 10], 'strips': {'S': strip_bounds, 'T': strip_bounds},
                       'zones': {'A': zone_bounds, 'AA': zone_bounds, 'edge': [8, 6, 11, 9],
                                 'outside': [12, 3, 16, 5], 'corner_east': [18, 6, 20, 8]}},
                {'west': expected, 'east': []}, {'west': rows, 'east': [hit.named_key for hit in east.hits]},
                expected_keys, actual_keys,
                ['surveys/bounds.py', 'tiles/intersections.py', 'tiles/packets.py', 'dispatch/readback.py'],
                '手算西窗口内交集宽 6、高 3。共边、东窗口内共点和窗口外相交均为零。')

    def test_wrong_parent_then_valid(self):
        strip, zone = self.seed(east_support=False)
        self.plan('review', 'lake-first', {WEST: (strip, zone)})
        packet = self.seal('review', WEST)
        wrong_parent = with_digest(replace(packet, parent_id='origin'))
        wrong_round = with_digest(replace(packet, round_id='first'))
        wrong_binding = with_digest(replace(packet, binding=TileBinding(WEST, (strip,))))
        undecorated = replace(packet, hits=())
        for wrong, message in ((wrong_parent, '父版'), (wrong_round, '轮次'),
                               (wrong_binding, '修订'), (undecorated, '摘要')):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    accept_tile(self.lake, 'review', wrong)
        with read_database(self.lake) as db:
            self.assertEqual(load_round_evidence(db, 'review'), {})
            self.assertIsNone(find_receipt(db, packet.source_id))
        receipt = accept_tile(self.lake, 'review', packet)
        self.assertEqual(accept_tile(self.lake, 'review', packet), receipt)
        conflict = with_digest(replace(packet, hits=(replace(packet.hits[0], area=19),)))
        with self.assertRaisesRegex(ValueError, '不同封存内容'):
            accept_tile(self.lake, 'review', conflict)
        with read_database(self.lake) as db:
            self.assertEqual(load_round_evidence(db, 'review')[WEST].packet, packet)
            self.assertEqual(find_receipt(db, packet.source_id), receipt)

    def test_release_after_receipt(self):
        strip = self.revision('footprint', 'S', 'r1', [2, 2, 18, 6])
        zone = self.revision('zone', 'A', 'r1', [4, 3, 16, 7])
        self.plan('delivery', 'origin', {WEST: (strip, zone), EAST: (strip, zone)})
        west, east = self.seal('delivery', WEST), self.seal('delivery', EAST)
        east_receipt = accept_tile(self.lake, 'delivery', east)
        uncommitted = TileReceipt('receipt-' + west.digest, west.source_id, 'delivery',
                                  'origin', WEST, west.digest)
        for proof in (None, west, east_receipt, uncommitted):
            with self.subTest(proof=type(proof).__name__):
                with self.assertRaisesRegex(ValueError, '收据'):
                    release_tile(self.lake, self.field, west.source_id, proof)
                with read_database(self.field) as db:
                    self.assertIsNotNone(load_staged(db, west.source_id))
                    self.assertIsNone(load_clearance(db, west.source_id))
        receipt = accept_tile(self.lake, 'delivery', west)
        result = release_tile(self.lake, self.field, west.source_id, receipt)
        self.assertEqual((result.status, result.receipt_id), ('cleared', receipt.receipt_id))
        with read_database(self.field) as db:
            self.assertIsNone(load_staged(db, west.source_id))
            self.assertEqual(load_clearance(db, west.source_id).digest, west.digest)
            self.assertIsNotNone(load_staged(db, east.source_id))
        with read_database(self.lake) as db:
            restored = load_round_evidence(db, 'delivery')[WEST].packet
        self.assertEqual(restored, west)
        self.assertEqual(restored.hits[0].area, 18)
        self.assertEqual(accept_tile(self.lake, 'delivery', restored), receipt)
        self.assertEqual(release_tile(self.lake, self.field, west.source_id, receipt), result)
        with self.assertRaisesRegex(LookupError, '已清理'):
            self.seal('delivery', WEST)

    def test_failed_receipt_write_leaves_no_evidence(self):
        self.plan('intake-failure', 'origin', {WEST: ()})
        packet = self.seal('intake-failure', WEST)
        with write_database(self.lake) as db:
            db.execute('''
                CREATE TRIGGER deny_receipt BEFORE INSERT ON tile_receipts
                BEGIN SELECT RAISE(ABORT, 'receipt write refused'); END
            ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt write refused'):
            accept_tile(self.lake, 'intake-failure', packet)
        with read_database(self.lake) as db:
            self.assertIsNone(find_receipt(db, packet.source_id))
            self.assertEqual(load_round_evidence(db, 'intake-failure'), {})
        self.assertEqual(publish(self.lake, 'intake-failure').missing, (WEST,))
        with read_database(self.field) as db:
            self.assertIsNotNone(load_staged(db, packet.source_id))
        with write_database(self.lake) as db:
            db.execute('DROP TRIGGER deny_receipt')
        receipt = accept_tile(self.lake, 'intake-failure', packet)
        self.assertEqual(receipt.source_id, packet.source_id)
        self.assertEqual(publish(self.lake, 'intake-failure').status, 'published')
