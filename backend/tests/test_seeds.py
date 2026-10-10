from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Condition,
    DatasheetAbility,
    Detachment,
    Disposition,
    Effect,
    Faction,
    FactionAbility,
    FactionUnit,
    Keyword,
    WargearAbility,
    WeaponAbility,
)
from app.seeds import (
    conditions,
    datasheet_abilities,
    dispositions,
    effects,
    faction_abilities,
    factions,
    keywords,
    run_all,
    wargear_abilities,
    weapon_abilities,
)
from app.seeds.detachments import adeptus_mechanicus as adeptus_mechanicus_detachments
from app.seeds.faction_units import adeptus_mechanicus, imperial_agents, imperial_knights


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


async def test_seed_keywords_has_no_duplicate_names():
    assert len(keywords.NAMES) == len(set(keywords.NAMES))


async def test_seed_keywords_inserts_all_names(session: AsyncSession):
    await keywords.seed(session)

    result = await session.execute(select(Keyword.name))
    names = set(result.scalars().all())
    assert names == set(keywords.NAMES)


async def test_seed_keywords_is_idempotent(session: AsyncSession):
    await keywords.seed(session)
    await keywords.seed(session)

    result = await session.execute(select(Keyword.name))
    names = result.scalars().all()
    assert len(names) == len(keywords.NAMES)


async def test_seed_factions_does_not_duplicate_existing(session: AsyncSession, faction_id: int):
    await factions.seed(session)

    result = await session.execute(select(Faction.name))
    names = result.scalars().all()
    assert len(names) == len(factions.NAMES) + 1


async def test_seed_faction_abilities_has_one_entry_per_faction():
    assert {faction_name for faction_name, _, _ in faction_abilities.ENTRIES} == set(
        factions.NAMES
    )


async def test_seed_faction_abilities_has_no_duplicate_names_within_a_faction():
    seen = set()
    for faction_name, ability_name, _ in faction_abilities.ENTRIES:
        assert (faction_name, ability_name) not in seen
        seen.add((faction_name, ability_name))


async def test_seed_faction_abilities_inserts_all_entries(session: AsyncSession):
    await factions.seed(session)
    await faction_abilities.seed(session)

    result = await session.execute(select(FactionAbility.name))
    names = set(result.scalars().all())
    assert names == {ability_name for _, ability_name, _ in faction_abilities.ENTRIES}


async def test_seed_faction_abilities_is_idempotent(session: AsyncSession):
    await factions.seed(session)
    await faction_abilities.seed(session)
    await faction_abilities.seed(session)

    result = await session.execute(select(FactionAbility.name))
    names = result.scalars().all()
    assert len(names) == len(faction_abilities.ENTRIES)


async def test_seed_faction_abilities_skips_entries_whose_faction_is_missing(
    session: AsyncSession,
):
    await faction_abilities.seed(session)

    result = await session.execute(select(FactionAbility))
    assert result.scalars().all() == []


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


async def test_seed_imperial_agents_units_has_no_duplicate_names():
    assert len(imperial_agents.NAMES) == len(set(imperial_agents.NAMES))


async def test_seed_imperial_agents_units_inserts_all_names(session: AsyncSession):
    await factions.seed(session)
    await imperial_agents.seed(session)

    result = await session.execute(select(FactionUnit.name))
    names = set(result.scalars().all())
    assert names == set(imperial_agents.NAMES)


async def test_seed_imperial_agents_units_is_idempotent(session: AsyncSession):
    await factions.seed(session)
    await imperial_agents.seed(session)
    await imperial_agents.seed(session)

    result = await session.execute(select(FactionUnit.name))
    names = result.scalars().all()
    assert len(names) == len(imperial_agents.NAMES)


async def test_seed_imperial_agents_units_skips_if_faction_missing(session: AsyncSession):
    await imperial_agents.seed(session)

    result = await session.execute(select(FactionUnit.name))
    assert result.scalars().all() == []


async def test_seed_imperial_knights_units_has_no_duplicate_names():
    assert len(imperial_knights.NAMES) == len(set(imperial_knights.NAMES))


async def test_seed_imperial_knights_units_inserts_all_names(session: AsyncSession):
    await factions.seed(session)
    await imperial_knights.seed(session)

    result = await session.execute(select(FactionUnit.name))
    names = set(result.scalars().all())
    assert names == set(imperial_knights.NAMES)


async def test_seed_imperial_knights_units_is_idempotent(session: AsyncSession):
    await factions.seed(session)
    await imperial_knights.seed(session)
    await imperial_knights.seed(session)

    result = await session.execute(select(FactionUnit.name))
    names = result.scalars().all()
    assert len(names) == len(imperial_knights.NAMES)


async def test_seed_imperial_knights_units_skips_if_faction_missing(session: AsyncSession):
    await imperial_knights.seed(session)

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


async def test_seed_weapon_abilities_skips_entries_with_missing_conditions_or_effects(
    session: AsyncSession,
):
    await weapon_abilities.seed(session)

    result = await session.execute(select(WeaponAbility.name))
    names = set(result.scalars().all())
    # Only entries with no condition/effect dependencies at all (e.g. "Precision",
    # which has none) can be created before conditions.seed/effects.seed have run.
    no_dependency_names = {
        name
        for name, _, condition_keywords, effect_keywords in weapon_abilities.ENTRIES
        if not condition_keywords and not effect_keywords
    }
    assert names == no_dependency_names


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


async def test_seed_datasheet_abilities_creates_all_entries(session: AsyncSession):
    await conditions.seed(session)
    await effects.seed(session)
    await datasheet_abilities.seed(session)

    result = await session.execute(
        select(DatasheetAbility).options(
            selectinload(DatasheetAbility.conditions), selectinload(DatasheetAbility.effects)
        )
    )
    abilities_by_name = {a.name: a for a in result.scalars().all()}
    assert set(abilities_by_name) == {name for name, _, _, _ in datasheet_abilities.ENTRIES}

    for name, _, condition_keywords, effect_keywords in datasheet_abilities.ENTRIES:
        ability = abilities_by_name[name]
        assert {c.keyword for c in ability.conditions} == set(condition_keywords)
        assert {e.keyword for e in ability.effects} == set(effect_keywords)


async def test_seed_datasheet_abilities_is_idempotent(session: AsyncSession):
    await conditions.seed(session)
    await effects.seed(session)
    await datasheet_abilities.seed(session)
    await datasheet_abilities.seed(session)

    result = await session.execute(select(DatasheetAbility.name))
    names = result.scalars().all()
    assert len(names) == len(datasheet_abilities.ENTRIES)


async def test_seed_datasheet_abilities_skips_if_conditions_or_effects_missing(
    session: AsyncSession,
):
    await datasheet_abilities.seed(session)

    result = await session.execute(select(DatasheetAbility))
    assert result.scalars().all() == []


async def test_run_all_seeds_everything(session: AsyncSession):
    await run_all(session)

    disposition_names = set((await session.execute(select(Disposition.name))).scalars().all())
    faction_names = set((await session.execute(select(Faction.name))).scalars().all())
    # Pairs rather than bare names: a unit name (e.g. "Skitarii Rangers") can
    # legitimately appear under more than one faction's roster.
    faction_unit_pairs = {
        (faction_id, name)
        for faction_id, name in (
            await session.execute(select(FactionUnit.faction_id, FactionUnit.name))
        ).all()
    }
    faction_id_by_name = dict(
        (await session.execute(select(Faction.name, Faction.id))).all()
    )
    faction_ability_pairs = {
        (faction_id, name)
        for faction_id, name in (
            await session.execute(select(FactionAbility.faction_id, FactionAbility.name))
        ).all()
    }
    detachment_names = set((await session.execute(select(Detachment.name))).scalars().all())
    keyword_names = set((await session.execute(select(Keyword.name))).scalars().all())
    condition_keywords = set((await session.execute(select(Condition.keyword))).scalars().all())
    effect_keywords = set((await session.execute(select(Effect.keyword))).scalars().all())
    weapon_ability_names = set((await session.execute(select(WeaponAbility.name))).scalars().all())
    wargear_ability_names = set((await session.execute(select(WargearAbility.name))).scalars().all())
    datasheet_ability_names = set(
        (await session.execute(select(DatasheetAbility.name))).scalars().all()
    )
    assert disposition_names == set(dispositions.NAMES)
    assert faction_names == set(factions.NAMES)
    assert faction_ability_pairs == {
        (faction_id_by_name[faction_name], ability_name)
        for faction_name, ability_name, _ in faction_abilities.ENTRIES
    }
    assert faction_unit_pairs == (
        {(faction_id_by_name[adeptus_mechanicus.FACTION_NAME], name) for name in adeptus_mechanicus.NAMES}
        | {(faction_id_by_name[imperial_agents.FACTION_NAME], name) for name in imperial_agents.NAMES}
        | {(faction_id_by_name[imperial_knights.FACTION_NAME], name) for name in imperial_knights.NAMES}
    )
    assert detachment_names == {name for name, _, _ in adeptus_mechanicus_detachments.ENTRIES}
    assert keyword_names == set(keywords.NAMES)
    assert condition_keywords == {keyword for keyword, _, _ in conditions.ENTRIES}
    assert effect_keywords == {keyword for keyword, _, _ in effects.ENTRIES}
    assert weapon_ability_names == {name for name, _, _, _ in weapon_abilities.ENTRIES}
    assert wargear_ability_names == {name for name, _, _, _ in wargear_abilities.ENTRIES}
    assert datasheet_ability_names == {name for name, _, _, _ in datasheet_abilities.ENTRIES}
