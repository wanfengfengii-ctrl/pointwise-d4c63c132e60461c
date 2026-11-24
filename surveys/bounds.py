from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rectangle:
    left: int
    bottom: int
    right: int
    top: int

    def __post_init__(self):
        if any(type(coordinate) is not int for coordinate in self.coordinates):
            raise ValueError('矩形边界必须是整数')
        if self.left >= self.right or self.bottom >= self.top:
            raise ValueError('矩形宽高必须为正')

    @property
    def coordinates(self):
        return self.left, self.bottom, self.right, self.top

    @property
    def area(self):
        return (self.right - self.left) * (self.top - self.bottom)


def validate_bounds(value):
    if isinstance(value, Rectangle):
        return value
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError('矩形需要四条边界')
    return Rectangle(*value)


def intersect_rectangles(first, *others):
    rectangles = (first, *others)
    left = max(rect.left for rect in rectangles)
    bottom = max(rect.bottom for rect in rectangles)
    right = min(rect.right for rect in rectangles)
    top = min(rect.top for rect in rectangles)
    if left >= right or bottom >= top:
        return None
    return Rectangle(left, bottom, right, top)
