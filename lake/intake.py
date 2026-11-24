from lake.evidence import store_evidence
from lake.receipts import find_receipt, record_receipt
from rounds.input_bindings import TileBinding, binding_matches
from rounds.plans import get_round
from rounds.tile_grid import resolve_tile_window
from tiles.intersections import TileHit
from tiles.packets import TilePacket, packet_identity, tile_source_id
from workdb import write_database


def _validate_packet(plan, packet):
    if not isinstance(packet, TilePacket) or not isinstance(packet.binding, TileBinding):
        raise ValueError('点收需要有效的瓦片封存件')
    if packet.round_id != plan.round_id:
        raise ValueError('封存件轮次不符')
    if packet.parent_id != plan.parent_id:
        raise ValueError('封存件父版不符')
    expected = plan.binding_for(packet.tile_id)
    if not binding_matches(expected, packet.binding):
        raise ValueError('封存件与冻结修订不符')
    if packet.source_id != tile_source_id(plan.round_id, plan.parent_id, expected.tile_id):
        raise ValueError('封存件源件号不符')
    if not isinstance(packet.hits, tuple):
        raise ValueError('命中须按规范封存')
    references = set(expected.references)
    max_area = resolve_tile_window(expected.tile_id).bounds.area
    keys = []
    for hit in packet.hits:
        if not isinstance(hit, TileHit):
            raise ValueError('封存件含无效命中')
        if hit.footprint not in references or hit.zone not in references or hit.area > max_area:
            raise ValueError('命中不在瓦片或冻结来源范围内')
        keys.append(hit.named_key)
    if keys != sorted(set(keys)):
        raise ValueError('封存件含重复或乱序命中')
    if packet.digest != packet_identity(packet):
        raise ValueError('封存件内容摘要不符')


def accept_tile(lake_path, round_id, packet):
    plan = get_round(lake_path, round_id)
    _validate_packet(plan, packet)
    with write_database(lake_path) as lake_db:
        previous = find_receipt(lake_db, packet.source_id)
        if previous is not None:
            if previous.packet_digest != packet.digest:
                raise ValueError('同一源件号对应不同封存内容')
            return previous
        store_evidence(lake_db, packet)
        return record_receipt(lake_db, packet.source_id, packet.round_id, packet.parent_id,
                              packet.tile_id, packet.digest)
