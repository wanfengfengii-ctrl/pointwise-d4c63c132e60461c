from dataclasses import dataclass
import re

from surveys.bounds import Rectangle


_TILE_NUMBER = re.compile(r'(0|-?[1-9][0-9]*),(0|-?[1-9][0-9]*)')


@dataclass(frozen=True, slots=True)
class TileGrid:
    side: int = 10

    def __post_init__(self):
        if type(self.side) is not int or self.side <= 0:
            raise ValueError('瓦片边长必须为正整数')


@dataclass(frozen=True, slots=True)
class TileWindow:
    tile_id: str
    column: int
    row: int
    bounds: Rectangle


def resolve_tile_window(tile_id, grid=TileGrid()):
    match = _TILE_NUMBER.fullmatch(tile_id) if isinstance(tile_id, str) else None
    if match is None:
        raise ValueError('瓦片号须为规范的列,行')
    column, row = map(int, match.groups())
    left, bottom = column * grid.side, row * grid.side
    bounds = Rectangle(left, bottom, left + grid.side, bottom + grid.side)
    return TileWindow(tile_id, column, row, bounds)
