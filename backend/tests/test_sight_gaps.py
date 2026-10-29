from app.services.in_game import shooting
from app.services.in_game.deployment import Base

# Terrain areas next to each other count as touching: sight can't pass
# through the gap between them.

def _square(x0, y0, size=4.0):
    return [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]


def _base(x, y):
    return Base(x=x, y=y, width_mm=32, height_mm=32)


def test_a_narrow_gap_between_areas_blocks_sight():
    # Two 4" squares 0.3" apart (x 10-14 and 14.3-18), a model either side.
    areas = [_square(10, 10), _square(14.3, 10)]
    viewer, target = _base(14.15, 4), _base(14.15, 20)
    assert shooting.can_see(viewer, target, areas)
    [(i, j, bridge)] = shooting._bridges(areas)
    assert (i, j) == (0, 1)
    assert not shooting.can_see(viewer, target, areas + [bridge])


def test_areas_touching_along_an_edge_block_sight_along_the_seam():
    areas = [_square(10, 10), _square(14, 10)]
    viewer, target = _base(14, 4), _base(14, 20)
    [(_, _, bridge)] = shooting._bridges(areas)
    assert not shooting.can_see(viewer, target, areas + [bridge])


def test_areas_further_apart_leave_a_gap_to_see_through():
    areas = [_square(10, 10), _square(15.5, 10)]
    assert shooting._bridges(areas) == []
    assert shooting.can_see(_base(14.75, 4), _base(14.75, 20), areas)
