from dataclasses import dataclass

from dispatch.membership import HitKey


@dataclass(frozen=True, slots=True)
class DispatchDelta:
    added: tuple[HitKey, ...]
    removed: tuple[HitKey, ...]


def compute_net_changes(parent, current):
    before = set(parent)
    after = set(current)
    return DispatchDelta(tuple(sorted(after - before)), tuple(sorted(before - after)))
