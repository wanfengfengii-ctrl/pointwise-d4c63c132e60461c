import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lake.application import initialize
from lake.intake import accept_tile
from lake.publish import publish
from rounds.plans import open_round
from surveys.registry import register
from tiles.packets import seal_tile


WEST = '0,0'
EAST = '1,0'


def hit_pairs(keys):
    return [(key.footprint_id, key.zone_id) for key in keys]


def observe(case_id, inputs, expected, actual, downstream_expected, downstream_actual, paths, oracle):
    record = {
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': paths,
        'oracle': oracle,
    }
    print('POINTWISE_SCENARIO ' + json.dumps(record, sort_keys=True, ensure_ascii=False))


class Workspace(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='survey-tests-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.start_workspace(self.root)

    def start_workspace(self, home):
        home.mkdir(exist_ok=True)
        self.lake = home / 'lake.sqlite'
        self.field = home / 'field.sqlite'
        initialize(self.lake, self.field)

    def revision(self, kind, object_id, revision, bounds, source=None, crew=None):
        return register(self.field, kind, object_id, revision,
                        source or f'外业 {object_id} {revision}', bounds, crew=crew).ref

    def plan(self, round_id, parent_id, assignments):
        return open_round(self.lake, self.field, round_id, parent_id, assignments)

    def seal(self, round_id, tile_id):
        return seal_tile(self.lake, self.field, round_id, tile_id)

    def seed(self, *, east_support=True):
        strip = self.revision('footprint', 'S', 'r1', [2, 2, 18, 6])
        zone = self.revision('zone', 'A', 'r1', [4, 3, 16, 7])
        east = (strip, zone) if east_support else (strip,)
        self.plan('first', 'origin', {WEST: (strip, zone), EAST: east})
        for tile in (EAST, WEST):
            accept_tile(self.lake, 'first', self.seal('first', tile))
        result = publish(self.lake, 'first')
        self.assertEqual((result.status, result.version_id), ('published', 'lake-first'))
        return strip, zone
