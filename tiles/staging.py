from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StagedMaterial:
    source_id: str
    body: bytes
    digest: str


@dataclass(frozen=True, slots=True)
class Clearance:
    source_id: str
    digest: str
    receipt_id: str


def initialize_staging(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS staged_packets (
            source_id TEXT PRIMARY KEY,
            packet_body BLOB NOT NULL,
            packet_digest TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS stage_clearances (
            source_id TEXT PRIMARY KEY,
            packet_digest TEXT NOT NULL,
            receipt_id TEXT NOT NULL
        )
    ''')


def save_staged(db, source_id, body, digest):
    db.execute('INSERT INTO staged_packets VALUES (?, ?, ?)', (source_id, body, digest))


def load_staged(db, source_id):
    row = db.execute('''
        SELECT source_id, packet_body, packet_digest FROM staged_packets WHERE source_id = ?
    ''', (source_id,)).fetchone()
    return StagedMaterial(*row) if row is not None else None


def load_clearance(db, source_id):
    row = db.execute('''
        SELECT source_id, packet_digest, receipt_id FROM stage_clearances WHERE source_id = ?
    ''', (source_id,)).fetchone()
    return Clearance(*row) if row is not None else None


def clear_staged(db, material, receipt_id):
    removed = db.execute('''
        DELETE FROM staged_packets WHERE source_id = ? AND packet_digest = ?
    ''', (material.source_id, material.digest))
    if removed.rowcount != 1:
        raise LookupError(f'待清暂存已不存在 {material.source_id!r}')
    clearance = Clearance(material.source_id, material.digest, receipt_id)
    db.execute('INSERT INTO stage_clearances VALUES (?, ?, ?)', (
        clearance.source_id, clearance.digest, clearance.receipt_id,
    ))
    return clearance
