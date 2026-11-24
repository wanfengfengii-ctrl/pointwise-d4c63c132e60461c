from dataclasses import asdict, dataclass
import json

from dispatch.membership import HitKey
from dispatch.net_changes import DispatchDelta
from dispatch.origins import HitOrigin
from lake.versions import ORIGIN_VERSION, find_signed_version
from surveys.revisions import require_text
from workdb import read_database


@dataclass(frozen=True, slots=True)
class DispatchSheet:
    version_id: str
    parent_id: str | None
    hits: tuple[HitKey, ...]
    delta: DispatchDelta
    origins: tuple[HitOrigin, ...]
    added_origins: tuple[HitOrigin, ...]
    removed_origins: tuple[HitOrigin, ...]


def _sheet_content(sheet):
    return json.dumps(asdict(sheet), ensure_ascii=True, sort_keys=True)


def _hit_origins(entries):
    origins = []
    for entry in entries:
        fields = dict(entry)
        fields['key'] = HitKey(**fields['key'])
        origins.append(HitOrigin(**fields))
    return tuple(origins)


def initialize_readback(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS dispatch_sheets (
            version_id TEXT PRIMARY KEY REFERENCES lake_versions(version_id),
            content TEXT NOT NULL
        )
    ''')
    origin = DispatchSheet(ORIGIN_VERSION, None, (), DispatchDelta((), ()), (), (), ())
    db.execute('''
        INSERT INTO dispatch_sheets (version_id, content) VALUES (?, ?)
        ON CONFLICT (version_id) DO NOTHING
    ''', (origin.version_id, _sheet_content(origin)))


def store_dispatch_sheet(db, sheet):
    db.execute('INSERT INTO dispatch_sheets (version_id, content) VALUES (?, ?)', (
        sheet.version_id, _sheet_content(sheet),
    ))


def read(lake_path, version_id):
    require_text(version_id, '湖版号')
    with read_database(lake_path) as db:
        version = find_signed_version(db, version_id)
        if version is None:
            return None
        row = db.execute('SELECT content FROM dispatch_sheets WHERE version_id = ?', (version_id,)).fetchone()
    if row is None:
        raise RuntimeError(f'已签湖版缺少调度净单 {version_id!r}')
    data = json.loads(row[0])
    delta = DispatchDelta(
        tuple(HitKey(**entry) for entry in data['delta']['added']),
        tuple(HitKey(**entry) for entry in data['delta']['removed']),
    )
    return DispatchSheet(
        version.version_id, version.parent_id,
        tuple(HitKey(**entry) for entry in data['hits']), delta,
        _hit_origins(data['origins']), _hit_origins(data['added_origins']),
        _hit_origins(data['removed_origins']),
    )
