"""有效测带覆盖与巡测区范围的湖端留档。

新发湖版按瓦片保存随件实收的测带覆盖（几何裁剪到瓦片）与负责班组，
以及巡测区在本瓦片的有效范围。调度核查只读这份湖端事实，源库关闭后仍可复查。
"""

from dataclasses import dataclass

from surveys.bounds import Rectangle
from surveys.revisions import RevisionRef


@dataclass(frozen=True, slots=True)
class VersionCoverage:
    version_id: str
    tile_id: str
    footprint: RevisionRef
    crew: str | None
    bounds: Rectangle

    @property
    def sort_key(self):
        return (self.tile_id, self.footprint.object_id,
                self.footprint.revision, self.crew or '',
                self.bounds.coordinates)


@dataclass(frozen=True, slots=True)
class VersionZone:
    version_id: str
    tile_id: str
    zone: RevisionRef
    bounds: Rectangle

    @property
    def sort_key(self):
        return (self.tile_id, self.zone.object_id,
                self.zone.revision, self.bounds.coordinates)


def initialize_coverage(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS version_tile_coverage (
            version_id TEXT NOT NULL REFERENCES lake_versions(version_id),
            tile_id TEXT NOT NULL,
            footprint_id TEXT NOT NULL,
            footprint_revision TEXT NOT NULL,
            crew TEXT,
            left_bound INTEGER NOT NULL,
            bottom_bound INTEGER NOT NULL,
            right_bound INTEGER NOT NULL,
            top_bound INTEGER NOT NULL,
            PRIMARY KEY (version_id, tile_id, footprint_id, footprint_revision)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS version_tile_zones (
            version_id TEXT NOT NULL REFERENCES lake_versions(version_id),
            tile_id TEXT NOT NULL,
            zone_id TEXT NOT NULL,
            zone_revision TEXT NOT NULL,
            left_bound INTEGER NOT NULL,
            bottom_bound INTEGER NOT NULL,
            right_bound INTEGER NOT NULL,
            top_bound INTEGER NOT NULL,
            PRIMARY KEY (version_id, tile_id, zone_id, zone_revision)
        )
    ''')


def store_version_coverage(db, version_id, support):
    coverage_rows = []
    zone_rows = []
    for tile_id in sorted(support):
        contribution = support[tile_id]
        for piece in contribution.coverage:
            bounds = piece.bounds
            coverage_rows.append((
                version_id, tile_id, piece.footprint.object_id, piece.footprint.revision,
                piece.crew, *bounds.coordinates,
            ))
        for extent in contribution.zones:
            bounds = extent.bounds
            zone_rows.append((
                version_id, tile_id, extent.zone.object_id, extent.zone.revision,
                *bounds.coordinates,
            ))
    if coverage_rows:
        db.executemany('INSERT INTO version_tile_coverage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       coverage_rows)
    if zone_rows:
        db.executemany('INSERT INTO version_tile_zones VALUES (?, ?, ?, ?, ?, ?, ?, ?)', zone_rows)


def load_version_coverage(db, version_id):
    rows = db.execute('''
        SELECT version_id, tile_id, footprint_id, footprint_revision, crew,
               left_bound, bottom_bound, right_bound, top_bound
        FROM version_tile_coverage WHERE version_id = ?
    ''', (version_id,))
    pieces = [
        VersionCoverage(
            version_id, tile_id, RevisionRef('footprint', footprint_id, footprint_revision),
            crew, Rectangle(left, bottom, right, top),
        )
        for version_id, tile_id, footprint_id, footprint_revision, crew, left, bottom, right, top in rows
    ]
    return tuple(sorted(pieces, key=lambda piece: piece.sort_key))


def load_version_zones(db, version_id):
    rows = db.execute('''
        SELECT version_id, tile_id, zone_id, zone_revision,
               left_bound, bottom_bound, right_bound, top_bound
        FROM version_tile_zones WHERE version_id = ?
    ''', (version_id,))
    pieces = [
        VersionZone(version_id, tile_id, RevisionRef('zone', zone_id, zone_revision),
                    Rectangle(left, bottom, right, top))
        for version_id, tile_id, zone_id, zone_revision, left, bottom, right, top in rows
    ]
    return tuple(sorted(pieces, key=lambda piece: piece.sort_key))
