from dataclasses import dataclass
import json

from rounds.input_bindings import TileBinding, binding_from_record, binding_record


@dataclass(frozen=True, slots=True)
class RoundPlan:
    round_id: str
    parent_id: str
    bindings: tuple[TileBinding, ...]

    def binding_for(self, tile_id):
        for binding in self.bindings:
            if binding.tile_id == tile_id:
                return binding
        raise ValueError(f'瓦片不在改写名单中 {tile_id!r}')


def initialize_rounds(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS round_plans (
            round_id TEXT PRIMARY KEY,
            parent_id TEXT NOT NULL REFERENCES lake_versions(version_id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS round_bindings (
            round_id TEXT NOT NULL REFERENCES round_plans(round_id),
            tile_id TEXT NOT NULL,
            binding TEXT NOT NULL,
            PRIMARY KEY (round_id, tile_id)
        )
    ''')


def insert_round(db, plan):
    db.execute('INSERT INTO round_plans VALUES (?, ?)', (plan.round_id, plan.parent_id))
    db.executemany('INSERT INTO round_bindings VALUES (?, ?, ?)', (
        (plan.round_id, binding.tile_id, json.dumps(binding_record(binding)))
        for binding in plan.bindings
    ))
    return plan


def load_round(db, round_id):
    parent = db.execute('SELECT parent_id FROM round_plans WHERE round_id = ?', (round_id,)).fetchone()
    if parent is None:
        return None
    bindings = db.execute('''
        SELECT binding FROM round_bindings WHERE round_id = ? ORDER BY tile_id
    ''', (round_id,))
    return RoundPlan(round_id, parent[0], tuple(
        binding_from_record(json.loads(data)) for (data,) in bindings
    ))
