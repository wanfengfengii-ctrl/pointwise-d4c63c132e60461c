from dataclasses import dataclass

from lake.evidence import AcceptedTile
from tiles.intersections import TileHit
from tiles.packets import restore_packet


@dataclass(frozen=True, slots=True)
class TileContribution:
    tile_id: str
    source_round: str
    source_id: str
    hits: tuple[TileHit, ...]


def _contribution(accepted: AcceptedTile):
    packet = accepted.packet
    return TileContribution(packet.tile_id, packet.round_id, packet.source_id, packet.hits)


def compose_tile_support(plan, parent_support, accepted_tiles):
    tiles = {binding.tile_id for binding in plan.bindings}
    if set(accepted_tiles) != tiles:
        raise ValueError('瓦片实收与改写名单不完整匹配')
    support = dict(parent_support)
    for tile_id, accepted in accepted_tiles.items():
        support[tile_id] = _contribution(accepted)
    return support


def initialize_tile_support(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS version_tile_support (
            version_id TEXT NOT NULL REFERENCES lake_versions(version_id),
            tile_id TEXT NOT NULL,
            source_round TEXT NOT NULL,
            PRIMARY KEY (version_id, tile_id),
            FOREIGN KEY (source_round, tile_id) REFERENCES accepted_tiles(round_id, tile_id)
        )
    ''')


def load_tile_support(db, version_id):
    rows = db.execute('''
        SELECT s.tile_id, e.packet_body, e.packet_digest
        FROM version_tile_support AS s
        JOIN accepted_tiles AS e ON e.round_id = s.source_round AND e.tile_id = s.tile_id
        WHERE s.version_id = ? ORDER BY s.tile_id
    ''', (version_id,))
    support = {}
    for tile_id, body, digest in rows:
        support[tile_id] = _contribution(AcceptedTile(restore_packet(body, digest)))
    return support


def store_tile_support(db, version_id, support):
    db.executemany('INSERT INTO version_tile_support VALUES (?, ?, ?)', (
        (version_id, tile_id, support[tile_id].source_round) for tile_id in sorted(support)
    ))
