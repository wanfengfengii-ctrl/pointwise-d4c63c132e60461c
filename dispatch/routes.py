"""路线交班核查。

沿一条自带里程的折线，从起点核查指定正式湖版里的有效测带覆盖。
只有持有该路段实测、且在路线巡测区内的班组可以领跑；两名班组即便覆盖相连，
也只有双方都测过、且连续长度达到交班要求的区间才允许换组。
换组前的那段共同覆盖须由当前班组领跑，并且不得与上一次交班的共同覆盖重叠。

核查只读取湖库中随瓦片实收的覆盖与巡测区范围，源库关闭后仍可复查。
"""

from dataclasses import dataclass
from decimal import Decimal
import math
from fractions import Fraction

from lake.coverage import load_version_coverage, load_version_zones
from lake.versions import find_signed_version
from surveys.revisions import RevisionRef, require_text
from workdb import read_database

ZERO = Fraction(0)
ONE = Fraction(1)


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label}必须为数值')
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, Decimal):
        return Fraction(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f'{label}必须为有限数值')
        return Fraction(str(value))
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError(f'{label}必须为数值') from error
    raise ValueError(f'{label}必须为数值')


@dataclass(frozen=True, slots=True)
class Route:
    """一条沿整数或精确数值折点、自带里程的巡查路线。"""

    points: tuple[tuple[Fraction, Fraction], ...]
    zone: str

    def __post_init__(self):
        if isinstance(self.zone, RevisionRef):
            if self.zone.kind != 'zone':
                raise ValueError('路线巡测区须为巡测区编号')
            zone = self.zone.object_id
        else:
            zone = self.zone
        require_text(zone, '路线巡测区')
        points = []
        for point in self.points:
            if not isinstance(point, (tuple, list)) or len(point) != 2:
                raise ValueError('路线折点须为二维坐标')
            points.append((_number(point[0], '折点横坐标'), _number(point[1], '折点纵坐标')))
        if len(points) < 2:
            raise ValueError('路线至少需要两个折点')
        object.__setattr__(self, 'points', tuple(points))
        object.__setattr__(self, 'zone', zone)

    @property
    def zone_id(self):
        return self.zone


@dataclass(frozen=True, slots=True)
class HandoverPolicy:
    """可用班组、最多交班次数及每次交班所需的连续共同覆盖长度。"""

    crews: tuple[str, ...]
    max_handovers: int
    common_length: Fraction

    def __post_init__(self):
        crews = []
        for crew in self.crews:
            require_text(crew, '班组编号')
            if crew in crews:
                raise ValueError(f'班组重复 {crew!r}')
            crews.append(crew)
        if not crews:
            raise ValueError('至少需要一个可用班组')
        object.__setattr__(self, 'crews', tuple(crews))
        if isinstance(self.max_handovers, bool) or not isinstance(self.max_handovers, int):
            raise ValueError('最多交班次数必须为整数')
        if self.max_handovers < 0:
            raise ValueError('最多交班次数不能为负')
        length = _number(self.common_length, '共同覆盖长度')
        if length <= ZERO:
            raise ValueError('共同覆盖长度必须为正')
        object.__setattr__(self, 'common_length', length)


@dataclass(frozen=True, slots=True)
class RouteStrip:
    tile_id: str
    footprint: RevisionRef
    crew: str
    start: Fraction
    end: Fraction

    @property
    def length(self):
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class RouteSegment:
    crew: str
    start: Fraction
    end: Fraction
    strips: tuple[RouteStrip, ...]

    @property
    def length(self):
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class RouteHandover:
    position: Fraction
    outgoing: str
    incoming: str
    common_start: Fraction
    common_end: Fraction

    @property
    def common_length(self):
        return self.common_end - self.common_start


@dataclass(frozen=True, slots=True)
class RoutePlan:
    version_id: str
    reachable: Fraction
    route_length: Fraction
    handovers: tuple[RouteHandover, ...]
    segments: tuple[RouteSegment, ...]

    @property
    def handover_count(self):
        return len(self.handovers)

    @property
    def completed(self):
        return self.reachable >= self.route_length


@dataclass(frozen=True, slots=True)
class _Geometry:
    start: Fraction
    dx: Fraction
    dy: Fraction
    length: Fraction
    origin: tuple[Fraction, Fraction]


@dataclass(frozen=True, slots=True)
class _State:
    crew: str
    entry: Fraction
    end: Fraction
    parent: object
    handover: object


def _segment_length(dx, dy):
    if dy == 0:
        return abs(dx)
    if dx == 0:
        return abs(dy)
    return Fraction(math.hypot(float(dx), float(dy)))


def _route_geometry(route):
    geometry = []
    mileage = ZERO
    previous = route.points[0]
    for point in route.points[1:]:
        dx, dy = point[0] - previous[0], point[1] - previous[1]
        if dx == 0 and dy == 0:
            continue
        length = _segment_length(dx, dy)
        geometry.append(_Geometry(mileage, dx, dy, length, previous))
        mileage += length
        previous = point
    if not geometry:
        raise ValueError('路线折线长度必须为正')
    return tuple(geometry), mileage


def _clip(origin, delta, low, high, lo, hi):
    if delta == 0:
        if origin < low or origin > high:
            return None
        return lo, hi
    first = (Fraction(low) - origin) / delta
    second = (Fraction(high) - origin) / delta
    if first > second:
        first, second = second, first
    lo, hi = max(lo, first), min(hi, second)
    if lo > hi:
        return None
    return lo, hi


def _rectangle_spans(geometry, rectangle):
    spans = []
    for segment in geometry:
        params = _clip(segment.origin[0], segment.dx,
                       rectangle.left, rectangle.right, ZERO, ONE)
        if params is None:
            continue
        params = _clip(segment.origin[1], segment.dy,
                       rectangle.bottom, rectangle.top, *params)
        if params is None:
            continue
        lo, hi = params
        if hi <= lo:
            continue
        spans.append((segment.start + lo * segment.length,
                      segment.start + hi * segment.length))
    return spans


def _merge(intervals):
    merged = []
    for lo, hi in sorted((lo, hi) for lo, hi in intervals if hi > lo):
        if merged and lo <= merged[-1][1]:
            if hi > merged[-1][1]:
                merged[-1] = (merged[-1][0], hi)
        else:
            merged.append((lo, hi))
    return tuple(merged)


def _intersect(first, second):
    result = []
    left = right = 0
    while left < len(first) and right < len(second):
        lo = max(first[left][0], second[right][0])
        hi = min(first[left][1], second[right][1])
        if hi > lo:
            result.append((lo, hi))
        if first[left][1] < second[right][1]:
            left += 1
        else:
            right += 1
    return tuple(result)


def _component(components, point):
    for lo, hi in components:
        if lo <= point <= hi:
            return lo, hi
    return None


def _effective(route, geometry, coverage, zones, crews):
    zone_spans = []
    for extent in zones:
        if extent.zone.object_id == route.zone_id:
            zone_spans.extend(_rectangle_spans(geometry, extent.bounds))
    zone = _merge(zone_spans)
    components = {}
    for crew in crews:
        spans = []
        for piece in coverage:
            if piece.crew == crew:
                spans.extend(_rectangle_spans(geometry, piece.bounds))
        components[crew] = _intersect(_merge(spans), zone)
    return components


def _explore(components, policy, total):
    required = policy.common_length
    crews = policy.crews
    cache = {}

    def common(first, second):
        key = (first, second) if first <= second else (second, first)
        if key not in cache:
            cache[key] = _intersect(components[key[0]], components[key[1]])
        return cache[key]

    layers = [{}]
    for crew in crews:
        interval = _component(components[crew], ZERO)
        if interval is None:
            continue
        key = (crew, interval)
        previous = layers[0].get(key)
        if previous is None:
            layers[0][key] = _State(crew, ZERO, interval[1], None, None)

    hands = 0
    while hands < policy.max_handovers and layers[-1]:
        following = {}
        for state in layers[-1].values():
            for incoming in crews:
                if incoming == state.crew:
                    continue
                for common_start, common_end in common(state.crew, incoming):
                    start = max(state.entry, common_start)
                    position = start + required
                    if position > common_end or position > state.end:
                        continue
                    interval = _component(components[incoming], position)
                    if interval is None:
                        continue
                    key = (incoming, interval)
                    previous = following.get(key)
                    if previous is not None and previous.entry <= position:
                        continue
                    following[key] = _State(
                        incoming, position, interval[1], state,
                        RouteHandover(position, state.crew, incoming, start, position),
                    )
        if not following:
            break
        layers.append(following)
        hands += 1

    best_reach, best_state = ZERO, None
    for layer in layers:
        for state in layer.values():
            reach = min(state.end, total)
            if reach > best_reach:
                best_reach, best_state = reach, state
    return best_reach, best_state

def _segment_strips(coverage, geometry, crew, start, end):
    strips = []
    for piece in coverage:
        if piece.crew != crew:
            continue
        for lo, hi in _rectangle_spans(geometry, piece.bounds):
            lo, hi = max(lo, start), min(hi, end)
            if hi <= lo:
                continue
            strips.append(RouteStrip(piece.tile_id, piece.footprint, crew, lo, hi))
    strips.sort(key=lambda item: (item.tile_id, item.footprint.key, item.start))
    return tuple(strips)


def _build_plan(version_id, coverage, geometry, total, reach, state):
    if state is None:
        return RoutePlan(version_id, ZERO, total, (), ())
    chain = []
    walker = state
    while walker is not None:
        chain.append(walker)
        walker = walker.parent
    chain.reverse()
    handovers = tuple(item.handover for item in chain[1:])
    segments = []
    for index, item in enumerate(chain):
        end = chain[index + 1].entry if index + 1 < len(chain) else reach
        segments.append(RouteSegment(
            item.crew, item.entry, end,
            _segment_strips(coverage, geometry, item.crew, item.entry, end),
        ))
    return RoutePlan(version_id, reach, total, handovers, tuple(segments))


def plan_route(lake_path, version_id, route, policy):
    """按指定正式湖版核查路线，返回可安全领跑的最长前缀及其交班安排。"""
    if not isinstance(route, Route):
        raise TypeError('route 须为 Route')
    if not isinstance(policy, HandoverPolicy):
        raise TypeError('policy 须为 HandoverPolicy')
    require_text(version_id, '湖版号')
    geometry, total = _route_geometry(route)
    with read_database(lake_path) as db:
        version = find_signed_version(db, version_id)
        if version is None:
            raise LookupError(f'未签发的湖版 {version_id!r}')
        coverage = load_version_coverage(db, version_id)
        zones = load_version_zones(db, version_id)
    components = _effective(route, geometry, coverage, zones, policy.crews)
    reach, state = _explore(components, policy, total)
    return _build_plan(version.version_id, coverage, geometry, total, reach, state)


def _mileage(value):
    return str(value)


def route_plan_record(plan):
    """把路线核查结果转成可序列化的净单记录（里程以精确文本表示）。"""
    return {
        'version_id': plan.version_id,
        'reachable': _mileage(plan.reachable),
        'route_length': _mileage(plan.route_length),
        'completed': plan.completed,
        'handover_count': plan.handover_count,
        'handovers': [
            {
                'position': _mileage(item.position),
                'outgoing': item.outgoing,
                'incoming': item.incoming,
                'common_start': _mileage(item.common_start),
                'common_end': _mileage(item.common_end),
                'common_length': _mileage(item.common_length),
            }
            for item in plan.handovers
        ],
        'segments': [
            {
                'crew': segment.crew,
                'start': _mileage(segment.start),
                'end': _mileage(segment.end),
                'length': _mileage(segment.length),
                'strips': [
                    {
                        'tile_id': strip.tile_id,
                        'footprint_id': strip.footprint.object_id,
                        'footprint_revision': strip.footprint.revision,
                        'start': _mileage(strip.start),
                        'end': _mileage(strip.end),
                    }
                    for strip in segment.strips
                ],
            }
            for segment in plan.segments
        ],
    }
