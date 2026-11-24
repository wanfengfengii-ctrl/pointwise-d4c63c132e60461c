from dataclasses import dataclass

from rounds.tile_grid import resolve_tile_window
from surveys.registry import resolve_revision
from surveys.revisions import RevisionRef


@dataclass(frozen=True, slots=True)
class TileBinding:
    tile_id: str
    references: tuple[RevisionRef, ...]

    @property
    def footprint_refs(self):
        return tuple(reference for reference in self.references if reference.kind == 'footprint')

    @property
    def zone_refs(self):
        return tuple(reference for reference in self.references if reference.kind == 'zone')


def bind_inputs(field_db, tile_id, references):
    resolve_tile_window(tile_id)
    references = tuple(references)
    objects = set()
    for reference in references:
        if not isinstance(reference, RevisionRef):
            raise ValueError('瓦片须绑定确切修订引用')
        object_key = reference.kind, reference.object_id
        if object_key in objects:
            raise ValueError(f'瓦片存在重复的业务编号 {object_key!r}')
        objects.add(object_key)
        resolve_revision(field_db, reference)
    return TileBinding(tile_id, tuple(sorted(references)))


def binding_matches(expected, candidate):
    return isinstance(candidate, TileBinding) and expected == candidate


def binding_record(binding):
    return {
        'tile_id': binding.tile_id,
        'references': [reference.key for reference in binding.references],
    }


def binding_from_record(record):
    references = tuple(RevisionRef(*values) for values in record['references'])
    return TileBinding(record['tile_id'], references)
