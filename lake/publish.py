from dataclasses import dataclass

from dispatch.membership import build_membership
from dispatch.net_changes import compute_net_changes
from dispatch.origins import build_origin_index, resolve_delta_origins
from dispatch.readback import DispatchSheet, store_dispatch_sheet
from lake.evidence import load_round_evidence
from lake.tile_support import compose_tile_support, load_tile_support, store_tile_support
from lake.versions import LakeVersion, find_round_publication, store_signed_version
from rounds.closure import check_readiness
from rounds.plans import get_round
from workdb import write_database


@dataclass(frozen=True, slots=True)
class PublishResult:
    round_id: str
    status: str
    version_id: str | None = None
    missing: tuple[str, ...] = ()


def publish(lake_path, round_id):
    plan = get_round(lake_path, round_id)
    with write_database(lake_path) as lake_db:
        existing = find_round_publication(lake_db, round_id)
        if existing is not None:
            return PublishResult(round_id, 'published', existing.version_id)
        evidence = load_round_evidence(lake_db, round_id)
        received = {tile: accepted.packet.binding for tile, accepted in evidence.items()}
        readiness = check_readiness(plan, received)
        if not readiness.ready:
            return PublishResult(round_id, 'pending', missing=readiness.missing)

        parent = load_tile_support(lake_db, plan.parent_id)
        current = compose_tile_support(plan, parent, evidence)
        hits = build_membership(current)
        delta = compute_net_changes(build_membership(parent), hits)
        origin_index = build_origin_index(current)
        added, removed = resolve_delta_origins(delta, build_origin_index(parent), origin_index)

        version_id = 'lake-' + round_id
        version = LakeVersion(version_id, plan.parent_id, round_id)
        sheet = DispatchSheet(
            version_id, plan.parent_id, hits, delta,
            tuple(origin for key in hits for origin in origin_index[key]), added, removed,
        )
        store_signed_version(lake_db, version)
        store_tile_support(lake_db, version_id, current)
        store_dispatch_sheet(lake_db, sheet)
        return PublishResult(round_id, 'published', version_id)
