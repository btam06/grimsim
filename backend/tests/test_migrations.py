from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.migrations import run_all
from app.models import Condition, Disposition, Effect, Stratagem


async def test_reconnaissance_renamed_in_place(session: AsyncSession):
    old = Disposition(name="Reconnaisance")
    session.add(old)
    await session.commit()
    old_id = old.id

    await run_all(session)
    # Again: nothing more to do.
    await run_all(session)

    rows = (
        await session.execute(
            select(Disposition.id, Disposition.name).where(
                Disposition.name.in_(["Reconnaisance", "Reconnaissance"])
            )
        )
    ).all()
    assert rows == [(old_id, "Reconnaissance")]


async def test_hellfire_rounds_loses_its_old_condition(session: AsyncSession):
    old = Condition(keyword="hellfire_anti_non_vehicle_4", name="Old", description="Old")
    effect = Effect(keyword="force_critical_wound", name="Force", description="Force")
    stratagem = Stratagem(name="Hellfire Rounds", cp=1, is_core=True)
    stratagem.conditions = [old]
    stratagem.effects = [effect]
    session.add(stratagem)
    await session.commit()

    await run_all(session)

    session.expire_all()
    stratagem = (
        await session.execute(
            select(Stratagem)
            .options(selectinload(Stratagem.conditions), selectinload(Stratagem.effects))
            .where(Stratagem.name == "Hellfire Rounds")
        )
    ).scalar_one()
    # Cleared, for the stratagem seed to fill in again.
    assert stratagem.conditions == [] and stratagem.effects == []
    keywords = (await session.execute(select(Condition.keyword))).scalars().all()
    assert "hellfire_anti_non_vehicle_4" not in keywords


async def test_kit_counts_rise_to_the_data_files(session: AsyncSession, monkeypatch):
    from app.migrations import kit_counts
    from app.models import TerrainFeatureShape

    shape = TerrainFeatureShape(name="Ruin wall L (2.75 x 6.25)", kind="ruin_wall", count=2)
    shape.parts = []
    other = TerrainFeatureShape(name="Obstacle bar (4.5)", kind="obstacle", count=3)
    other.parts = []
    session.add_all([shape, other])
    await session.commit()
    monkeypatch.setattr(
        kit_counts.terrain_seed, "load",
        lambda path=None: {
            "area_shapes": [],
            "feature_shapes": [
                {"name": "Ruin wall L (2.75 x 6.25)", "count": 4},
                # Never lowered.
                {"name": "Obstacle bar (4.5)", "count": 2},
            ],
        },
    )
    await run_all(session)
    await session.refresh(shape)
    await session.refresh(other)
    assert (shape.count, other.count) == (4, 3)


async def test_core_rule_texts_follow_the_seed_data(session: AsyncSession):
    from app.models import DatasheetAbility
    from app.seeds import datasheet_abilities

    old = DatasheetAbility(name="Deep Strike", description="more than 9 inches")
    session.add(old)
    await session.commit()
    await run_all(session)
    await session.refresh(old)
    expected = {e[0]: e[1] for e in datasheet_abilities.CORE_ENTRIES}["Deep Strike"]
    assert old.description == expected and '8"' in expected


async def test_core_stratagems_follow_the_core_rules(session: AsyncSession, monkeypatch):
    from sqlalchemy import select

    from app.models import Keyword, Stratagem, StratagemTiming

    grenades = Keyword(name="GRENADES")
    session.add_all([
        Stratagem(name="Grenade", cp=1, is_core=True, description="old", keywords=[grenades],
                  timings=[StratagemTiming(phase="shooting", turn="your_turn")]),
        Stratagem(name="Go to Ground", cp=1, is_core=True),
        Stratagem(name="Heroic Intervention", cp=2, is_core=True, description="old"),
    ])
    await session.commit()
    entries = [
        {"name": "Explosives", "cp": 1, "core": True, "description": "8 inches",
         "keyword_options": [["EXPLOSIVES"], ["GRENADES"]]},
        {"name": "Heroic Intervention", "cp": 1, "core": True, "description": "new",
         "timings": [{"phase": "charge", "turn": "opponent_turn"}]},
    ]
    monkeypatch.setattr("app.seeds.stratagems.load", lambda path=None: entries)
    await run_all(session)
    session.expire_all()
    names = {
        s.name: s
        for s in (await session.execute(select(Stratagem).where(Stratagem.is_core))).scalars()
    }
    assert "Go to Ground" not in names and "Grenade" not in names
    assert (names["Explosives"].description, names["Heroic Intervention"].cp) == ("8 inches", 1)
