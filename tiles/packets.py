from dataclasses import dataclass, replace
import hashlib
import json

from rounds.input_bindings import TileBinding, binding_from_record, binding_record
from rounds.plans import get_round
from rounds.tile_grid import resolve_tile_window
from surveys.footprints import resolve_footprints
from surveys.zones import resolve_zones
from tiles.intersections import (
    FootprintCoverage, TileHit, ZoneExtent, compute_coverage, compute_intersections,
    compute_zone_extents, coverage_from_record, coverage_record, hit_from_record, hit_record,
    zone_extent_from_record, zone_extent_record,
)
from tiles.staging import load_clearance, load_staged, save_staged
from workdb import write_database


@dataclass(frozen=True, slots=True)
class TilePacket:
    source_id: str
    round_id: str
    parent_id: str
    binding: TileBinding
    hits: tuple[TileHit, ...]
    digest: str
    coverage: tuple[FootprintCoverage, ...] = ()
    zones: tuple[ZoneExtent, ...] = ()

    @property
    def tile_id(self):
        return self.binding.tile_id


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def canonical_packet_bytes(packet):
    return _canonical_json({
        'source_id': packet.source_id,
        'round_id': packet.round_id,
        'parent_id': packet.parent_id,
        'binding': binding_record(packet.binding),
        'hits': [hit_record(hit) for hit in packet.hits],
        'coverage': [coverage_record(piece) for piece in packet.coverage],
        'zones': [zone_extent_record(piece) for piece in packet.zones],
    })


def packet_identity(packet):
    return hashlib.sha256(canonical_packet_bytes(packet)).hexdigest()


def tile_source_id(round_id, parent_id, tile_id):
    slot = _canonical_json((round_id, parent_id, tile_id))
    return 'tile-' + hashlib.sha256(slot).hexdigest()


def restore_packet(body, digest):
    record = json.loads(body)
    packet = TilePacket(
        record['source_id'], record['round_id'], record['parent_id'],
        binding_from_record(record['binding']),
        tuple(hit_from_record(item) for item in record['hits']),
        digest,
        tuple(coverage_from_record(item) for item in record.get('coverage', [])),
        tuple(zone_extent_from_record(item) for item in record.get('zones', [])),
    )
    if packet_identity(packet) != digest:
        raise ValueError('存储件的内容摘要不符')
    return packet


def seal_tile(lake_path, field_path, round_id, tile_id):
    plan = get_round(lake_path, round_id)
    binding = plan.binding_for(tile_id)
    source_id = tile_source_id(round_id, plan.parent_id, tile_id)
    with write_database(field_path) as field_db:
        if load_clearance(field_db, source_id) is not None:
            raise LookupError(f'源件暂存已清理 {source_id!r}')
        staged = load_staged(field_db, source_id)
        if staged is not None:
            return restore_packet(staged.body, staged.digest)
        footprints = resolve_footprints(field_db, binding.footprint_refs)
        zones = resolve_zones(field_db, binding.zone_refs)
        window = resolve_tile_window(tile_id)
        hits = compute_intersections(window, footprints, zones)
        coverage = compute_coverage(window, footprints)
        extents = compute_zone_extents(window, zones)
        content = TilePacket(source_id, round_id, plan.parent_id, binding, hits, '',
                             coverage, extents)
        packet = replace(content, digest=packet_identity(content))
        save_staged(field_db, source_id, canonical_packet_bytes(packet), packet.digest)
        return packet
