from dataclasses import dataclass

from surveys.bounds import Rectangle, intersect_rectangles
from surveys.revisions import RevisionRef, require_text


@dataclass(frozen=True, order=True, slots=True)
class TileHit:
    footprint: RevisionRef
    zone: RevisionRef
    area: int

    def __post_init__(self):
        if not isinstance(self.footprint, RevisionRef) or self.footprint.kind != 'footprint':
            raise ValueError('命中需要测带修订')
        if not isinstance(self.zone, RevisionRef) or self.zone.kind != 'zone':
            raise ValueError('命中需要巡测区修订')
        if type(self.area) is not int or self.area <= 0:
            raise ValueError('命中面积必须为正整数')

    @property
    def named_key(self):
        return self.footprint.object_id, self.zone.object_id


@dataclass(frozen=True, slots=True)
class FootprintCoverage:
    """A strip revision's effective coverage inside one tile, with its crew."""

    footprint: RevisionRef
    crew: str | None
    bounds: Rectangle

    def __post_init__(self):
        if not isinstance(self.footprint, RevisionRef) or self.footprint.kind != 'footprint':
            raise ValueError('测带覆盖需要测带修订')
        if not isinstance(self.bounds, Rectangle):
            raise ValueError('测带覆盖需要有效矩形')
        if self.crew is not None:
            require_text(self.crew, '班组编号')

    @property
    def sort_key(self):
        return self.footprint.key, self.crew or '', self.bounds.coordinates


@dataclass(frozen=True, slots=True)
class ZoneExtent:
    """A zone revision's effective extent inside one tile."""

    zone: RevisionRef
    bounds: Rectangle

    def __post_init__(self):
        if not isinstance(self.zone, RevisionRef) or self.zone.kind != 'zone':
            raise ValueError('巡测区范围需要巡测区修订')
        if not isinstance(self.bounds, Rectangle):
            raise ValueError('巡测区范围需要有效矩形')

    @property
    def sort_key(self):
        return self.zone.key, self.bounds.coordinates


def compute_intersections(window, footprints, zones):
    zones = tuple(zones)
    hits = []
    for footprint in footprints:
        clipped = intersect_rectangles(footprint.bounds, window.bounds)
        if clipped is None:
            continue
        for zone in zones:
            overlap = intersect_rectangles(clipped, zone.bounds)
            if overlap is not None:
                hits.append(TileHit(footprint.reference, zone.reference, overlap.area))
    return tuple(sorted(hits))


def compute_coverage(window, footprints):
    coverage = []
    for footprint in footprints:
        clipped = intersect_rectangles(footprint.bounds, window.bounds)
        if clipped is None:
            continue
        coverage.append(FootprintCoverage(footprint.reference, footprint.crew, clipped))
    return tuple(sorted(coverage, key=lambda piece: piece.sort_key))


def compute_zone_extents(window, zones):
    extents = []
    for zone in zones:
        clipped = intersect_rectangles(zone.bounds, window.bounds)
        if clipped is None:
            continue
        extents.append(ZoneExtent(zone.reference, clipped))
    return tuple(sorted(extents, key=lambda piece: piece.sort_key))


def coverage_record(piece):
    return piece.footprint.key, piece.crew, piece.bounds.coordinates


def coverage_from_record(record):
    footprint, crew, bounds = record
    return FootprintCoverage(RevisionRef(*footprint), crew, Rectangle(*bounds))


def zone_extent_record(piece):
    return piece.zone.key, piece.bounds.coordinates


def zone_extent_from_record(record):
    zone, bounds = record
    return ZoneExtent(RevisionRef(*zone), Rectangle(*bounds))



def hit_record(hit):
    return hit.footprint.key, hit.zone.key, hit.area


def hit_from_record(record):
    footprint, zone, area = record
    return TileHit(RevisionRef(*footprint), RevisionRef(*zone), area)
