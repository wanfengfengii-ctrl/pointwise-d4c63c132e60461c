from dataclasses import dataclass

from surveys.bounds import intersect_rectangles
from surveys.revisions import RevisionRef


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


def hit_record(hit):
    return hit.footprint.key, hit.zone.key, hit.area


def hit_from_record(record):
    footprint, zone, area = record
    return TileHit(RevisionRef(*footprint), RevisionRef(*zone), area)
