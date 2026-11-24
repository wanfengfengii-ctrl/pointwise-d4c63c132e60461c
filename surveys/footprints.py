from dataclasses import dataclass

from surveys.bounds import Rectangle, validate_bounds
from surveys.revisions import RevisionRef, SourceRevision, load_revision


@dataclass(frozen=True, slots=True)
class Footprint:
    reference: RevisionRef
    source: str
    bounds: Rectangle


def make_footprint_revision(object_id, revision, source, bounds):
    reference = RevisionRef('footprint', object_id, revision)
    return SourceRevision(reference, source, validate_bounds(bounds))


def resolve_footprints(db, references):
    footprints = []
    for reference in references:
        if reference.kind != 'footprint':
            raise ValueError('测带加工需要测带修订')
        record = load_revision(db, reference)
        if record is None:
            raise LookupError(f'缺少测带修订 {reference.key!r}')
        footprints.append(Footprint(record.ref, record.source, record.bounds))
    return tuple(footprints)
