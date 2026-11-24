from dataclasses import dataclass

from dispatch.membership import HitKey
from dispatch.net_changes import DispatchDelta
from lake.tile_support import TileContribution


@dataclass(frozen=True, order=True, slots=True)
class HitOrigin:
    key: HitKey
    tile_id: str
    footprint_revision: str
    zone_revision: str
    source_round: str
    source_id: str
    area: int


def build_origin_index(support: dict[str, TileContribution]):
    by_key = {}
    for contribution in support.values():
        for hit in contribution.hits:
            key = HitKey(*hit.named_key)
            origin = HitOrigin(key, contribution.tile_id, hit.footprint.revision, hit.zone.revision,
                               contribution.source_round, contribution.source_id, hit.area)
            by_key.setdefault(key, []).append(origin)
    return {key: tuple(sorted(by_key[key])) for key in sorted(by_key)}


def resolve_delta_origins(delta: DispatchDelta, parent_index, current_index):
    added = tuple(origin for key in delta.added for origin in current_index[key])
    removed = tuple(origin for key in delta.removed for origin in parent_index[key])
    return added, removed
