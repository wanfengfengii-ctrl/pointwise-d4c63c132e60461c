from dataclasses import dataclass

from workdb import read_database


@dataclass(frozen=True, slots=True)
class TileReceipt:
    receipt_id: str
    source_id: str
    round_id: str
    parent_id: str
    tile_id: str
    packet_digest: str


def initialize_receipts(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS tile_receipts (
            receipt_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL UNIQUE REFERENCES accepted_tiles(source_id),
            round_id TEXT NOT NULL,
            parent_id TEXT NOT NULL,
            tile_id TEXT NOT NULL,
            packet_digest TEXT NOT NULL
        )
    ''')


def find_receipt(db, source_id):
    row = db.execute('''
        SELECT receipt_id, source_id, round_id, parent_id, tile_id, packet_digest
        FROM tile_receipts WHERE source_id = ?
    ''', (source_id,)).fetchone()
    return TileReceipt(*row) if row is not None else None


def record_receipt(db, source_id, round_id, parent_id, tile_id, digest):
    receipt_id = 'receipt-' + digest
    values = receipt_id, source_id, round_id, parent_id, tile_id, digest
    db.execute('INSERT INTO tile_receipts VALUES (?, ?, ?, ?, ?, ?)', values)
    return TileReceipt(*values)


def verify_receipt(lake_path, receipt):
    if not isinstance(receipt, TileReceipt):
        return False
    with read_database(lake_path) as db:
        return find_receipt(db, receipt.source_id) == receipt
