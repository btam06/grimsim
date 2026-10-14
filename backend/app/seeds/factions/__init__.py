from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.combat_rules import Rule
from app.models import Detachment, Faction, FactionAbility, FactionUnit
from app.seeds.factions import (
    adeptus_custodes,
    adeptus_mechanicus,
    adeptus_sororitas,
    aeldari,
    astra_militarum,
    chaos_daemons,
    chaos_knights,
    chaos_space_marines,
    death_guard,
    drukhari,
    emperors_children,
    genestealer_cults,
    grey_knights,
    imperial_agents,
    imperial_knights,
    leagues_of_votann,
    necrons,
    orks,
    space_marines,
    tau_empire,
    thousand_sons,
    tyranids,
    world_eaters,
)
from app.seeds.lookup import get_dispositions_by_name

# One folder per faction, each with:
#   info.py                  FACTION_NAME
#   abilities.py             ENTRIES of (ability name, description), plus an
#                            optional OPTIONS dict of rule options an ability
#                            grants (e.g. Doctrina Imperatives' Protector and
#                            Conqueror Imperatives) - see rule_options below
#   units/__init__.py        NAMES of the faction's units (datasheets)
#   detachments/__init__.py  ENTRIES of (name, disposition name, dp)
#
# To add a faction: copy an existing folder, fill it in, then register it in
# FACTIONS below. Everything else (the Faction rows themselves, and its
# abilities/units/detachments) is seeded from these files.
FACTIONS = [
    adeptus_sororitas,
    adeptus_custodes,
    adeptus_mechanicus,
    astra_militarum,
    grey_knights,
    imperial_agents,
    imperial_knights,
    space_marines,
    chaos_daemons,
    chaos_knights,
    chaos_space_marines,
    death_guard,
    emperors_children,
    thousand_sons,
    world_eaters,
    aeldari,
    drukhari,
    genestealer_cults,
    leagues_of_votann,
    necrons,
    orks,
    tau_empire,
    tyranids,
]

NAMES = [faction.info.FACTION_NAME for faction in FACTIONS]

# {(faction name, ability name): {option name: [Rule, ...]}} across every
# faction's abilities.py OPTIONS.
RULE_OPTIONS: dict[tuple[str, str], dict[str, list[Rule]]] = {
    (faction.info.FACTION_NAME, ability_name): options
    for faction in FACTIONS
    for ability_name, options in getattr(faction.abilities, "OPTIONS", {}).items()
}

# {option name: (faction name, ability name)} - which faction ability each
# option belongs to. Option names are unique across every faction.
OPTION_OWNERS: dict[str, tuple[str, str]] = {
    option_name: owner
    for owner, options in RULE_OPTIONS.items()
    for option_name in options
}


def rule_options(faction_name: str, ability_name: str) -> dict[str, list[Rule]]:
    # The selectable rule options a faction ability grants, if any.
    return RULE_OPTIONS.get((faction_name, ability_name), {})


async def _faction_ids_by_name(session: AsyncSession) -> dict[str, int]:
    return {
        faction.name: faction.id
        for faction in (await session.execute(select(Faction))).scalars().all()
    }


async def seed(session: AsyncSession) -> None:
    existing = set((await session.execute(select(Faction.name))).scalars().all())
    missing = [Faction(name=name) for name in NAMES if name not in existing]
    if missing:
        session.add_all(missing)
        await session.commit()


async def seed_abilities(session: AsyncSession) -> None:
    faction_ids = await _faction_ids_by_name(session)
    existing = {
        (faction_id, name)
        for faction_id, name in (
            await session.execute(select(FactionAbility.faction_id, FactionAbility.name))
        ).all()
    }

    missing = []
    for faction in FACTIONS:
        faction_id = faction_ids.get(faction.info.FACTION_NAME)
        if faction_id is None:
            continue  # faction hasn't been seeded yet
        for name, description in faction.abilities.ENTRIES:
            if (faction_id, name) in existing:
                continue
            missing.append(
                FactionAbility(name=name, description=description, faction_id=faction_id)
            )

    if missing:
        session.add_all(missing)
        await session.commit()


async def seed_units(session: AsyncSession) -> None:
    faction_ids = await _faction_ids_by_name(session)
    existing = {
        (faction_id, name)
        for faction_id, name in (
            await session.execute(select(FactionUnit.faction_id, FactionUnit.name))
        ).all()
    }

    missing = []
    for faction in FACTIONS:
        faction_id = faction_ids.get(faction.info.FACTION_NAME)
        if faction_id is None:
            continue  # faction hasn't been seeded yet
        for name in faction.units.NAMES:
            if (faction_id, name) not in existing:
                missing.append(FactionUnit(name=name, faction_id=faction_id))

    if missing:
        session.add_all(missing)
        await session.commit()


async def seed_detachments(session: AsyncSession) -> None:
    # Must run after dispositions.seed, since each entry looks its disposition
    # up by name.
    faction_ids = await _faction_ids_by_name(session)
    dispositions_by_name = await get_dispositions_by_name(session)
    existing = {
        (faction_id, name)
        for faction_id, name in (
            await session.execute(select(Detachment.faction_id, Detachment.name))
        ).all()
    }

    missing = []
    for faction in FACTIONS:
        faction_id = faction_ids.get(faction.info.FACTION_NAME)
        if faction_id is None:
            continue  # faction hasn't been seeded yet
        for name, disposition_name, dp in faction.detachments.ENTRIES:
            if (faction_id, name) in existing:
                continue
            disposition = dispositions_by_name.get(disposition_name)
            missing.append(
                Detachment(
                    name=name,
                    faction_id=faction_id,
                    dp=dp,
                    dispositions=[disposition] if disposition else [],
                )
            )

    if missing:
        session.add_all(missing)
        await session.commit()
