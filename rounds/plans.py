from collections.abc import Mapping

from lake.versions import find_signed_version
from rounds.input_bindings import bind_inputs
from rounds.store import RoundPlan, insert_round, load_round
from surveys.revisions import require_text
from workdb import read_database, write_database


def open_round(lake_path, field_path, round_id, parent_id, assignments):
    require_text(round_id, '轮次号')
    require_text(parent_id, '父版号')
    if not isinstance(assignments, Mapping):
        raise ValueError('改写名单须提供瓦片到来源引用的映射')
    with read_database(field_path) as field_db:
        bindings = [bind_inputs(field_db, tile, refs) for tile, refs in assignments.items()]
    plan = RoundPlan(round_id, parent_id, tuple(sorted(bindings, key=lambda binding: binding.tile_id)))
    with write_database(lake_path) as lake_db:
        if find_signed_version(lake_db, parent_id) is None:
            raise LookupError(f'未签发的父版 {parent_id!r}')
        previous = load_round(lake_db, round_id)
        if previous is None:
            return insert_round(lake_db, plan)
        if previous != plan:
            raise ValueError(f'轮次已经按其他计划冻结 {round_id!r}')
        return previous


def get_round(lake_path, round_id):
    require_text(round_id, '轮次号')
    with read_database(lake_path) as db:
        plan = load_round(db, round_id)
    if plan is None:
        raise LookupError(f'未知轮次 {round_id!r}')
    return plan
