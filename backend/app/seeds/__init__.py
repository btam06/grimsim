from sqlalchemy.ext.asyncio import AsyncSession

from app.seeds import (
    conditions,
    datasheet_abilities,
    dispositions,
    effects,
    factions,
    keywords,
    stratagems,
    wargear_abilities,
    weapon_abilities,
)

# To seed another table on startup: add a module here with a NAMES list and an
# async def seed(session) function (see dispositions.py / keywords.py), then
# register its `seed` function below.
#
# Everything faction-specific lives in app/seeds/factions/, one folder per
# faction (info.py, abilities.py, units/, detachments/ - see that package's
# __init__.py). factions.seed creates the Faction rows from each info.py, and
# seed_abilities/seed_units/seed_detachments fill in the rest for every
# faction, so they must run after factions.seed (and seed_detachments after
# dispositions.seed, since it looks dispositions up by name).
#
# conditions.seed/effects.seed populate the hardcoded condition/effect catalog
# (see app/combat_rules/) that WeaponAbility/WargearAbility/DatasheetAbility
# rows reference; weapon_abilities.seed/wargear_abilities.seed/
# datasheet_abilities.seed build abilities from them (each with an ENTRIES
# list of (name, description, condition keywords, effect keywords)), so all
# three must run after conditions.seed/effects.seed.
#
# stratagems.seed populates the core stratagems (usable by any detachment).
SEED_FUNCS = [
    dispositions.seed,
    factions.seed,
    factions.seed_abilities,
    keywords.seed,
    conditions.seed,
    effects.seed,
    weapon_abilities.seed,
    wargear_abilities.seed,
    datasheet_abilities.seed,
    factions.seed_units,
    factions.seed_detachments,
    stratagems.seed,
]


async def run_all(session: AsyncSession) -> None:
    for seed_func in SEED_FUNCS:
        await seed_func(session)
