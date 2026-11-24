from dataclasses import dataclass


ORIGIN_VERSION = 'origin'


@dataclass(frozen=True, slots=True)
class LakeVersion:
    version_id: str
    parent_id: str | None
    round_id: str | None


def initialize_versions(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS lake_versions (
            version_id TEXT PRIMARY KEY,
            parent_id TEXT REFERENCES lake_versions(version_id),
            round_id TEXT UNIQUE REFERENCES round_plans(round_id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS lake_signoffs (
            round_id TEXT PRIMARY KEY REFERENCES round_plans(round_id),
            version_id TEXT NOT NULL UNIQUE REFERENCES lake_versions(version_id)
        )
    ''')
    db.execute('''
        INSERT INTO lake_versions (version_id, parent_id, round_id) VALUES (?, NULL, NULL)
        ON CONFLICT (version_id) DO NOTHING
    ''', (ORIGIN_VERSION,))


def find_signed_version(db, version_id):
    row = db.execute('''
        SELECT v.version_id, v.parent_id, v.round_id
        FROM lake_versions AS v
        LEFT JOIN lake_signoffs AS s ON s.version_id = v.version_id AND s.round_id = v.round_id
        WHERE v.version_id = ? AND (v.round_id IS NULL OR s.round_id IS NOT NULL)
    ''', (version_id,)).fetchone()
    return LakeVersion(*row) if row is not None else None


def find_round_publication(db, round_id):
    row = db.execute('''
        SELECT v.version_id, v.parent_id, v.round_id
        FROM lake_signoffs AS s
        JOIN lake_versions AS v ON v.version_id = s.version_id AND v.round_id = s.round_id
        WHERE s.round_id = ?
    ''', (round_id,)).fetchone()
    return LakeVersion(*row) if row is not None else None


def store_signed_version(db, version):
    db.execute('INSERT INTO lake_versions VALUES (?, ?, ?)', (
        version.version_id, version.parent_id, version.round_id,
    ))
    db.execute('INSERT INTO lake_signoffs VALUES (?, ?)', (version.round_id, version.version_id))
