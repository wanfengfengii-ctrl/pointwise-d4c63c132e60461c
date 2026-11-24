from surveys.footprints import make_footprint_revision
from surveys.revisions import load_revision, store_revision
from surveys.zones import make_zone_revision
from workdb import write_database


def register(field_path, kind, object_id, revision, source, bounds, crew=None):
    if kind == 'footprint':
        record = make_footprint_revision(object_id, revision, source, bounds, crew)
    elif kind == 'zone':
        if crew is not None:
            raise ValueError('只有测带修订可以带负责班组')
        record = make_zone_revision(object_id, revision, source, bounds)
    else:
        raise ValueError('来源种类必须为 footprint 或 zone')
    with write_database(field_path) as db:
        return store_revision(db, record)


def resolve_revision(db, reference):
    record = load_revision(db, reference)
    if record is None:
        raise LookupError(f'未登记的来源修订 {reference.key!r}')
    return record
