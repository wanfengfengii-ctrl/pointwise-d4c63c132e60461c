from dataclasses import dataclass
import json

from surveys.bounds import Rectangle, validate_bounds


def require_text(value, label):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f'{label}必须为非空文本')
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise ValueError(f'{label}包含无效字符') from error
    return value


@dataclass(frozen=True, order=True, slots=True)
class RevisionRef:
    kind: str
    object_id: str
    revision: str

    def __post_init__(self):
        if self.kind not in ('footprint', 'zone'):
            raise ValueError('来源种类必须为 footprint 或 zone')
        require_text(self.object_id, '对象编号')
        require_text(self.revision, '来源修订')

    @property
    def key(self):
        return self.kind, self.object_id, self.revision


@dataclass(frozen=True, slots=True)
class SourceRevision:
    ref: RevisionRef
    source: str
    bounds: Rectangle

    def __post_init__(self):
        if not isinstance(self.ref, RevisionRef) or not isinstance(self.bounds, Rectangle):
            raise ValueError('需要确切来源引用和矩形')
        require_text(self.source, '来源说明')


def initialize_revisions(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS source_revisions (
            kind TEXT NOT NULL CHECK (kind IN ('footprint', 'zone')),
            object_id TEXT NOT NULL,
            revision TEXT NOT NULL,
            source TEXT NOT NULL,
            bounds TEXT NOT NULL,
            PRIMARY KEY (kind, object_id, revision)
        )
    ''')


def load_revision(db, reference):
    row = db.execute('''
        SELECT source, bounds FROM source_revisions
        WHERE kind = ? AND object_id = ? AND revision = ?
    ''', reference.key).fetchone()
    if row is None:
        return None
    source, bounds = row
    return SourceRevision(reference, source, validate_bounds(json.loads(bounds)))


def store_revision(db, record):
    previous = load_revision(db, record.ref)
    if previous is not None:
        if previous != record:
            raise ValueError(f'修订存在内容冲突 {record.ref.key!r}')
        return previous
    db.execute('''
        INSERT INTO source_revisions (kind, object_id, revision, source, bounds)
        VALUES (?, ?, ?, ?, ?)
    ''', (*record.ref.key, record.source, json.dumps(record.bounds.coordinates)))
    return record
