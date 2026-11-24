from dataclasses import dataclass

from tiles.packets import TilePacket, canonical_packet_bytes, restore_packet


@dataclass(frozen=True, slots=True)
class AcceptedTile:
    packet: TilePacket

    @property
    def tile_id(self):
        return self.packet.tile_id


def initialize_evidence(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS accepted_tiles (
            round_id TEXT NOT NULL,
            tile_id TEXT NOT NULL,
            source_id TEXT NOT NULL UNIQUE,
            packet_body BLOB NOT NULL,
            packet_digest TEXT NOT NULL,
            PRIMARY KEY (round_id, tile_id),
            FOREIGN KEY (round_id, tile_id) REFERENCES round_bindings(round_id, tile_id)
        )
    ''')


def store_evidence(db, packet):
    db.execute('''
        INSERT INTO accepted_tiles (round_id, tile_id, source_id, packet_body, packet_digest)
        VALUES (?, ?, ?, ?, ?)
    ''', (packet.round_id, packet.tile_id, packet.source_id,
          canonical_packet_bytes(packet), packet.digest))
    return AcceptedTile(packet)


def load_round_evidence(db, round_id):
    rows = db.execute('''
        SELECT tile_id, packet_body, packet_digest
        FROM accepted_tiles WHERE round_id = ? ORDER BY tile_id
    ''', (round_id,))
    return {tile_id: AcceptedTile(restore_packet(body, digest)) for tile_id, body, digest in rows}
