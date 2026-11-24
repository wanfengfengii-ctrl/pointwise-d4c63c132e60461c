from dataclasses import dataclass

from lake.tile_support import TileContribution


@dataclass(frozen=True, order=True, slots=True)
class HitKey:
    footprint_id: str
    zone_id: str


def build_membership(support: dict[str, TileContribution]):
    keys = {
        HitKey(*hit.named_key)
        for contribution in support.values()
        for hit in contribution.hits
    }
    return tuple(sorted(keys))
