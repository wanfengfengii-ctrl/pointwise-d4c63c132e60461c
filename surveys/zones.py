from dataclasses import dataclass

from surveys.bounds import Rectangle, validate_bounds
from surveys.revisions import RevisionRef, SourceRevision, load_revision


@dataclass(frozen=True, slots=True)
class SurveyZone:
    reference: RevisionRef
    source: str
    bounds: Rectangle


def make_zone_revision(object_id, revision, source, bounds):
    reference = RevisionRef('zone', object_id, revision)
    return SourceRevision(reference, source, validate_bounds(bounds))



def resolve_zones(db, references):
    zones = []
    for reference in references:
        if reference.kind != 'zone':
            raise ValueError('巡测区加工需要巡测区修订')
        record = load_revision(db, reference)
        if record is None:
            raise LookupError(f'缺少巡测区修订 {reference.key!r}')
        zones.append(SurveyZone(record.ref, record.source, record.bounds))
    return tuple(zones)
