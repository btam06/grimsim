from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Condition,
    Detachment,
    Disposition,
    Effect,
    Faction,
    FactionUnit,
    WargearAbility,
    WeaponAbility,
)
from app.seeds import conditions, dispositions, effects, factions, run_all, wargear_abilities, weapon_abilities
from app.seeds.detachments import adeptus_mechanicus as adeptus_mechanicus_detachments
from app.seeds.faction_units import adeptus_mechanicus


async def test_seed_dispositions_inserts_all_names(session: AsyncSession):
    await dispositions.seed(session)

    result = await session.execute(select(Disposition.name))
    names = set(result.scalars().all())
    assert names == set(dispositions.NAMES)


async def test_seed_dispositions_is_idempotent(session: AsyncSession):
    await dispositions.seed(session)
    await dispositions.seed(session)

    result = await session.execute(select(Disposition.name))
    names = result.scalars().all()
    assert len(names) == len(dispositions.NAMES)


async def test_seed_factions_inserts_all_names(session: AsyncSession):
    await factions.seed(session)

    result = await session.execute(select(Faction.name))
    names = set(result.scalars().all())
    assert names == set(factions.NAMES)


async def test_seed_factions_is_idempotent(session: AsyncSession):
    await factions.seed(session)
    await factions.seed(session)

    result = await session.execute(select(Faction.name))
    names = result.scalars().all()
    assert len(names) == len(factions.NAMES)


async def test_seed_factions_does_not_duplicate_existing(session: AsyncSession, faction_id: int):
    await factions.seed(session)

    result = await session.execute(select(Faction.name))
    names = result.scalars().all()
    assert len(names) == len(factions.NAMES) + 1


async def test_seed_adeptus_mechanicus_units_has_no_duplicate_names():
    assert len(adeptus_mechanicus.NAMES) == len(set(adeptus_mechanicus.NAMES))


async def test_seed_adeptus_mechanicus_units_inserts_all_names(session: AsyncSession):
    await factions.seed(session)
    await adeptus_mechanicus.seed(session)

    result = await session.execute(select(FactionUnit.name))
    names = set(result.scalars().all())
    assert names == set(adeptus_mechanicus.NAMES)


async def test_seed_adeptus_mechanicus_units_is_idempotent(session: AsyncSession):
    await factions.seed(session)
    await adeptus_mechanicus.seed(session)
    await adeptus_mechanicus.seed(session)

    result = await session.execute(select(FactionUnit.name))
    names = result.scalars().all()
    assert len(names) == len(adeptus_mechanicus.NAMES)


async def test_seed_adeptus_mechanicus_units_skips_if_faction_missing(session: AsyncSession):
    await adeptus_mechanicus.seed(session)

    result = await session.execute(select(FactionUnit.name))
    assert result.scalars().all() == []


async def test_seed_adeptus_mechanicus_detachments_has_no_duplicate_names():
    names = [name for name, _, _ in adeptus_mechanicus_detachments.ENTRIES]
    assert len(names) == len(set(names))


async def test_seed_adeptus_mechanicus_detachments_inserts_all_entries(session: AsyncSession):
    await dispositions.seed(session)
    await factions.seed(session)
    await adeptus_mechanicus_detachments.seed(session)

    result = await session.execute(
        select(Detachment).options(selectinload(Detachment.dispositions))
    )
    detachments = result.scalars().all()
    names = {d.name for d in detachments}
    assert names == {name for name, _, _ in adeptus_mechanicus_detachments.ENTRIES}

    dp_by_name = {name: dp for name, _, dp in adeptus_mechanicus_detachments.ENTRIES}
    disposition_by_name = {
        name: disposition_name for name, disposition_name, _ in adeptus_mechanicus_detachments.ENTRIES
    }
    for d in detachments:
        assert d.dp == dp_by_name[d.name]
        assert [disp.name for disp in d.dispositions] == [disposition_by_name[d.name]]


async def test_seed_adeptus_mechanicus_detachments_is_idempotent(session: AsyncSession):
    await dispositions.seed(session)
    await factions.seed(session)
    await adeptus_mechanicus_detachments.seed(session)
    await adeptus_mechanicus_detachments.seed(session)

    result = await session.execute(select(Detachment.name))
    names = result.scalars().all()
    assert len(names) == len(adeptus_mechanicus_detachments.ENTRIES)


async def test_seed_adeptus_mechanicus_detachments_skips_if_faction_missing(
    session: AsyncSession,
):
    await dispositions.seed(session)
    await adeptus_mechanicus_detachments.seed(session)

    result = await session.execute(select(Detachment.name))
    assert result.scalars().all() == []


async def test_seed_conditions_inserts_all_entries(session: AsyncSession):
    await conditions.seed(session)

    result = await session.execute(select(Condition.keyword))
    keywords = set(result.scalars().all())
    assert keywords == {keyword for keyword, _, _ in conditions.ENTRIES}


async def test_seed_conditions_is_idempotent(session: AsyncSession):
    await conditions.seed(session)
    await conditions.seed(session)

    result = await session.execute(select(Condition.keyword))
    assert len(result.scalars().all()) == len(conditions.ENTRIES)


async def test_seed_effects_inserts_all_entries(session: AsyncSession):
    await effects.seed(session)

    result = await session.execute(select(Effect.keyword))
    keywords = set(result.scalars().all())
    assert keywords == {keyword for keyword, _, _ in effects.ENTRIES}


async def test_seed_effects_is_idempotent(session: AsyncSession):
    await effects.seed(session)
    await effects.seed(session)

    result = await session.execute(select(Effect.keyword))
    assert len(result.scalars().all()) == len(effects.ENTRIES)


async def test_seed_weapon_abilities_creates_all_entries(session: AsyncSession):
    await conditions.seed(session)
    await effects.seed(session)
    await weapon_abilities.seed(session)

    result = await session.execute(
        select(WeaponAbility).options(
            selectinload(WeaponAbility.conditions), selectinload(WeaponAbility.effects)
        )
    )
    abilities_by_name = {a.name: a for a in result.scalars().all()}
    assert set(abilities_by_name) == {name for name, _, _, _ in weapon_abilities.ENTRIES}

    for name, _, condition_keywords, effect_keywords in weapon_abilities.ENTRIES:
        ability = abilities_by_name[name]
        assert {c.keyword for c in ability.conditions} == set(condition_keywords)
        assert {e.keyword for e in ability.effects} == set(effect_keywords)


async def test_seed_weapon_abilities_is_idempotent(session: AsyncSession):
    await conditions.seed(session)
    await effects.seed(session)
    await weapon_abilities.seed(session)
    await weapon_abilities.seed(session)

    result = await session.execute(select(WeaponAbility.name))
    names = result.scalars().all()
    assert len(names) == len(weapon_abilities.ENTRIES)


async def test_seed_weapon_abilities_skips_if_conditions_or_effects_missing(
    session: AsyncSession,
):
    await weapon_abilities.seed(session)

    result = await session.execute(select(WeaponAbility))
    assert result.scalars().all() == []


async def test_seed_wargear_abilities_creates_all_entries(session: AsyncSession):
    await conditions.seed(session)
    await effects.seed(session)
    await wargear_abilities.seed(session)

    result = await session.execute(
        select(WargearAbility).options(
            selectinload(WargearAbility.conditions), selectinload(WargearAbility.effects)
        )
    )
    abilities_by_name = {a.name: a for a in result.scalars().all()}
    assert set(abilities_by_name) == {name for name, _, _, _ in wargear_abilities.ENTRIES}

    for name, _, condition_keywords, effect_keywords in wargear_abilities.ENTRIES:
        ability = abilities_by_name[name]
        assert {c.keyword for c in ability.conditions} == set(condition_keywords)
        assert {e.keyword for e in ability.effects} == set(effect_keywords)


async def test_seed_wargear_abilities_is_idempotent(session: AsyncSession):
    await conditions.seed(session)
    await effects.seed(session)
    await wargear_abilities.seed(session)
    await wargear_abilities.seed(session)

    result = await session.execute(select(WargearAbility.name))
    names = result.scalars().all()
    assert len(names) == len(wargear_abilities.ENTRIES)


async def test_seed_wargear_abilities_skips_if_conditions_or_effects_missing(
    session: AsyncSession,
):
    await wargear_abilities.seed(session)

    result = await session.execute(select(WargearAbility))
    assert result.scalars().all() == []


async def test_run_all_seeds_everything(session: AsyncSession):
    await run_all(session)

    disposition_names = set((await session.execute(select(Disposition.name))).scalars().all())
    faction_names = set((await session.execute(select(Faction.name))).scalars().all())
    faction_unit_names = set((await session.execute(select(FactionUnit.name))).scalars().all())
    detachment_names = set((await session.execute(select(Detachment.name))).scalars().all())
    condition_keywords = set((await session.execute(select(Condition.keyword))).scalars().all())
    effect_keywords = set((await session.execute(select(Effect.keyword))).scalars().all())
    weapon_ability_names = set((await session.execute(select(WeaponAbility.name))).scalars().all())
    wargear_ability_names = set((await session.execute(select(WargearAbility.name))).scalars().all())
    assert disposition_names == set(dispositions.NAMES)
    assert faction_names == set(factions.NAMES)
    assert faction_unit_names == set(adeptus_mechanicus.NAMES)
    assert detachment_names == {name for name, _, _ in adeptus_mechanicus_detachments.ENTRIES}
    assert condition_keywords == {keyword for keyword, _, _ in conditions.ENTRIES}
    assert effect_keywords == {keyword for keyword, _, _ in effects.ENTRIES}
    assert weapon_ability_names == {name for name, _, _, _ in weapon_abilities.ENTRIES}
    assert wargear_ability_names == {name for name, _, _, _ in wargear_abilities.ENTRIES}
