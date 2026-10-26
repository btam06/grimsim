import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.migrations import run_all
from app.models import BaseSize, Faction, FactionUnit, Model
from app.services.in_game import deployment
from app.services.in_game.terrain import (
    MM_PER_INCH,
    Base,
    base_dimensions,
    is_box,
    within,
    wholly_within,
)

# Box bases: hulls measured as a rectangle (e.g. a Skorpius: 155 x 90mm).

LENGTH, WIDTH = 155 / MM_PER_INCH, 90 / MM_PER_INCH  # about 6.10" x 3.54"


def _box(x, y, rotation=0):
    return Base(x=x, y=y, width_mm=155, height_mm=90, rotation=rotation, box=True)


def test_box_base_sizes():
    assert base_dimensions("155 x 90mm box") == (155.0, 90.0)
    assert is_box("155 x 90mm box")
    assert not is_box("105 x 70mm") and not is_box("Use model")


def test_boxes_overlap_and_gap():
    a = _box(10, 10)
    # Side by side, just touching: not overlapping, no gap.
    touching = _box(10 + LENGTH, 10)
    assert not deployment.overlaps(a, touching)
    assert deployment.gap(a, touching) == pytest.approx(0, abs=1e-6)
    # 2" apart, end to end.
    apart = _box(10 + LENGTH + 2, 10)
    assert deployment.gap(a, apart) == pytest.approx(2, abs=1e-3)
    # Crossed like a plus sign: no corner of either is inside the other, but
    # they overlap.
    assert deployment.overlaps(a, _box(10, 10, rotation=90))
    # A box's corner reaches further than an oval's edge would.
    corner = Base(x=10 + LENGTH / 2 + 0.6, y=10 + WIDTH / 2 + 0.6, width_mm=25, height_mm=25)
    assert deployment.gap(a, corner) == pytest.approx(
        ((0.6**2) * 2) ** 0.5 - 12.5 / MM_PER_INCH, abs=0.05
    )


def test_box_and_polygons():
    a = _box(10, 10)
    big = [(0, 0), (20, 0), (20, 20), (0, 20)]
    assert wholly_within(a, big) and within(a, big)
    assert deployment.wholly_inside(a, big)
    # A square the box's corner pokes into, but its oval wouldn't.
    cx, cy = 10 + LENGTH / 2, 10 + WIDTH / 2
    nook = [(cx - 0.1, cy - 0.1), (cx + 1, cy - 0.1), (cx + 1, cy + 1), (cx - 0.1, cy + 1)]
    assert within(a, nook) and deployment.overlaps_polygon(a, nook)
    assert deployment.distance_to_polygon(a, nook) == 0
    far = [(x + 3, y + 3) for x, y in nook]
    # (Its nearest corner is 2.9" across and down from the box's.)
    assert deployment.distance_to_polygon(a, far) == pytest.approx(2.9 * 2**0.5, abs=1e-3)


async def test_migrations_move_hulls_to_the_box_and_fix_the_marshal(session):
    faction = Faction(name="Adeptus Mechanicus")
    use_model, round_100 = BaseSize(name="Use model"), BaseSize(name="100mm")
    session.add_all([faction, use_model, round_100])
    await session.flush()
    stats = dict(faction_id=faction.id, save=3, toughness=9, oc=2, movement=12, wounds=11,
                 leadership=7)
    session.add_all([
        Model(name="Skorpius Dunerider", base_size=use_model, **stats),
        Model(name="Impulsor", base_size=round_100, **stats),
        FactionUnit(name="Skitarii Marshall", faction_id=faction.id),
    ])
    await session.commit()
    await run_all(session)
    session.expire_all()
    models = (
        await session.execute(
            select(Model).options(selectinload(Model.base_size)).where(
                Model.name.in_(["Skorpius Dunerider", "Impulsor"])
            )
        )
    ).scalars().all()
    assert {m.base_size.name for m in models} == {"155 x 90mm box"} and len(models) == 2
    names = (await session.execute(select(FactionUnit.name))).scalars().all()
    assert "Skitarii Marshal" in names and "Skitarii Marshall" not in names
