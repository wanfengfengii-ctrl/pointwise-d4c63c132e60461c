from dataclasses import dataclass

from rounds.input_bindings import binding_matches


@dataclass(frozen=True, slots=True)
class RoundReadiness:
    round_id: str
    missing: tuple[str, ...]

    @property
    def ready(self):
        return not self.missing


def check_readiness(plan, received_bindings):
    missing = tuple(binding.tile_id for binding in plan.bindings
                    if not binding_matches(binding, received_bindings.get(binding.tile_id)))
    return RoundReadiness(plan.round_id, missing)
