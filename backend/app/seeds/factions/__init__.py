from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.combat_rules import Rule
from app.models import (
    DatasheetAbility,
    Detachment,
    Faction,
    FactionAbility,
    FactionUnit,
    Keyword,
    Model,
    Wargear,
    WargearAbility,
    Weapon,
    WeaponAbility,
)
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
import json

from app.seeds import data_files
from app.seeds import datasheets as datasheet_data
from app.seeds.lookup import get_dispositions_by_name

# One folder per faction, each with:
#   info.py                  FACTION_NAME
#   abilities.py             ENTRIES of (ability name, description), plus an
#                            optional OPTIONS dict of rule options an ability
#                            grants (e.g. Doctrina Imperatives' Protector and
#                            Conqueror Imperatives) - see rule_options below
#
# Game data - units, detachments and full datasheets - isn't in here: it's
# loaded from app/data/factions/<faction folder name>/ (units.json,
# detachments.json, datasheets.json) - see app/data/README.md.
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


def faction_slug(faction) -> str:
    # A faction's folder name (e.g. "adeptus_mechanicus"), which names its
    # data files.
    return faction.__name__.rsplit(".", 1)[-1]


def load_units(faction) -> list[str]:
    # A faction's unit (datasheet) names, from its units.json. None if there's
    # no file.
    path = data_files.faction_data_dir(faction_slug(faction)) / "units.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["units"]


def load_keywords(faction) -> list[str]:
    # A faction's keyword names, from its keywords.json. None if there's no
    # file.
    path = data_files.faction_data_dir(faction_slug(faction)) / "keywords.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["keywords"]


def load_detachments(faction) -> list[dict]:
    # A faction's detachments, from its detachments.json, as {"name", "dp",
    # "dispositions": [disposition names]} - a detachment can have more than
    # one disposition. None if there's no file.
    path = data_files.faction_data_dir(faction_slug(faction)) / "detachments.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["detachments"]

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


async def seed_keywords(session: AsyncSession) -> None:
    # Keywords aren't owned by a faction - each faction's keywords.json lists
    # the ones it uses, and any not already seeded (by name) are added, so a
    # keyword several factions share (e.g. INFANTRY) is added once.
    existing = set((await session.execute(select(Keyword.name))).scalars().all())
    missing = []
    for faction in FACTIONS:
        for name in load_keywords(faction):
            if name not in existing:
                existing.add(name)
                missing.append(Keyword(name=name))

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
        for name in load_units(faction):
            if (faction_id, name) not in existing:
                missing.append(FactionUnit(name=name, faction_id=faction_id))

    if missing:
        session.add_all(missing)
        await session.commit()


async def seed_detachments(session: AsyncSession) -> None:
    # Creates each faction's detachments (see load_detachments), and gives
    # existing ones any of their dispositions they're missing (additive only).
    # Must run after dispositions.seed, since dispositions are looked up by
    # name - an unknown name is an error, not skipped.
    faction_ids = await _faction_ids_by_name(session)
    dispositions_by_name = await get_dispositions_by_name(session)
    existing = {
        (detachment.faction_id, detachment.name): detachment
        for detachment in (
            await session.execute(
                select(Detachment).options(selectinload(Detachment.dispositions))
            )
        )
        .scalars()
        .all()
    }

    changed = False
    for faction in FACTIONS:
        faction_id = faction_ids.get(faction.info.FACTION_NAME)
        if faction_id is None:
            continue  # faction hasn't been seeded yet
        for entry in load_detachments(faction):
            name, dp, disposition_names = entry["name"], entry["dp"], entry["dispositions"]
            unknown = [d for d in disposition_names if d not in dispositions_by_name]
            if unknown:
                raise ValueError(f"detachment {name!r} references unknown disposition(s) {unknown}")
            dispositions = [dispositions_by_name[d] for d in disposition_names]

            detachment = existing.get((faction_id, name))
            if detachment is None:
                session.add(
                    Detachment(
                        name=name, faction_id=faction_id, dp=dp, dispositions=dispositions
                    )
                )
                changed = True
                continue
            for disposition in dispositions:
                if disposition not in detachment.dispositions:
                    detachment.dispositions.append(disposition)
                    changed = True

    if changed:
        await session.commit()


async def seed_datasheets(session: AsyncSession) -> None:
    # Creates the models (with stats, keywords, faction/datasheet abilities,
    # weapons and wargear) in each faction's datasheets.json.
    #
    # For a model that already exists in its faction (by name), only what it's
    # missing (by name) is added: faction/datasheet abilities, weapons,
    # wargear, and abilities on same-named weapons. Nothing existing is changed
    # or removed, so additions to a datasheet reach previously seeded models
    # without overwriting edits. (Stats and keywords aren't synced.)
    #
    # Must run after keywords, weapon/wargear/datasheet abilities and faction
    # abilities are seeded, since everything is referenced by name - a name
    # that isn't found is an error, not skipped.
    faction_ids = await _faction_ids_by_name(session)
    keywords = {k.name: k for k in (await session.execute(select(Keyword))).scalars().all()}
    weapon_abilities = {
        a.name: a for a in (await session.execute(select(WeaponAbility))).scalars().all()
    }
    wargear_abilities = {
        a.name: a for a in (await session.execute(select(WargearAbility))).scalars().all()
    }
    datasheet_abilities = {
        a.name: a for a in (await session.execute(select(DatasheetAbility))).scalars().all()
    }
    faction_abilities = {
        (a.faction_id, a.name): a
        for a in (await session.execute(select(FactionAbility))).scalars().all()
    }
    existing = {
        (model.faction_id, model.name): model
        for model in (
            await session.execute(
                select(Model).options(
                    selectinload(Model.weapons).selectinload(Weapon.abilities),
                    selectinload(Model.wargear),
                    selectinload(Model.abilities),
                    selectinload(Model.faction_abilities),
                )
            )
        )
        .scalars()
        .all()
    }

    def lookup(table: dict, key, kind: str, datasheet: str):
        if key not in table:
            raise ValueError(f"datasheet {datasheet!r} references unknown {kind} {key!r}")
        return table[key]

    def build_weapon(weapon, datasheet: str) -> Weapon:
        return Weapon(
            name=weapon.name,
            weapon_type=weapon.weapon_type,
            range=weapon.range,
            attacks=weapon.attacks,
            skill=weapon.skill,
            strength=weapon.strength,
            ap=weapon.ap,
            damage=weapon.damage,
            abilities=[
                lookup(weapon_abilities, name, "weapon ability", datasheet)
                for name in weapon.abilities
            ],
        )

    def build_wargear(gear, datasheet: str) -> Wargear:
        return Wargear(
            name=gear.name,
            description=gear.description,
            abilities=[
                lookup(wargear_abilities, name, "wargear ability", datasheet)
                for name in gear.abilities
            ],
        )

    changed = False
    for faction in FACTIONS:
        faction_id = faction_ids.get(faction.info.FACTION_NAME)
        if faction_id is None:
            continue  # faction hasn't been seeded yet
        for datasheet in datasheet_data.load(faction_slug(faction)):
            for spec in datasheet.models:
                model = existing.get((faction_id, spec.name))
                if model is not None:
                    faction_ability_names = {a.name for a in model.faction_abilities}
                    for name in spec.faction_abilities:
                        if name not in faction_ability_names:
                            model.faction_abilities.append(
                                lookup(
                                    faction_abilities,
                                    (faction_id, name),
                                    "faction ability",
                                    datasheet.name,
                                )
                            )
                            changed = True
                    ability_names = {a.name for a in model.abilities}
                    for name in spec.abilities:
                        if name not in ability_names:
                            model.abilities.append(
                                lookup(
                                    datasheet_abilities, name, "datasheet ability", datasheet.name
                                )
                            )
                            changed = True
                    # Matched by name, counting copies - a datasheet can give a
                    # model several of the same weapon (e.g. 3 heavy stubbers).
                    weapons_by_name: dict[str, list[Weapon]] = {}
                    for w in model.weapons:
                        weapons_by_name.setdefault(w.name, []).append(w)
                    specs_by_name: dict[str, list] = {}
                    for weapon in spec.weapons:
                        specs_by_name.setdefault(weapon.name, []).append(weapon)
                    for name, weapon_specs in specs_by_name.items():
                        existing_weapons = weapons_by_name.get(name, [])
                        for weapon in weapon_specs[len(existing_weapons):]:
                            model.weapons.append(build_weapon(weapon, datasheet.name))
                            changed = True
                        for existing_weapon in existing_weapons:
                            ability_names = {a.name for a in existing_weapon.abilities}
                            for ability_name in weapon_specs[0].abilities:
                                if ability_name not in ability_names:
                                    existing_weapon.abilities.append(
                                        lookup(
                                            weapon_abilities,
                                            ability_name,
                                            "weapon ability",
                                            datasheet.name,
                                        )
                                    )
                                    changed = True
                    wargear_names = {g.name for g in model.wargear}
                    for gear in spec.wargear:
                        if gear.name not in wargear_names:
                            model.wargear.append(build_wargear(gear, datasheet.name))
                            changed = True
                    continue

                session.add(
                    Model(
                        name=spec.name,
                        faction_id=faction_id,
                        movement=spec.movement,
                        toughness=spec.toughness,
                        save=spec.save,
                        wounds=spec.wounds,
                        leadership=spec.leadership,
                        oc=spec.oc,
                        invulnerable=spec.invulnerable,
                        feel_no_pain=spec.feel_no_pain,
                        is_support=spec.is_support,
                        is_leader=spec.is_leader,
                        keywords=[
                            lookup(keywords, name, "keyword", datasheet.name)
                            for name in spec.keywords
                        ],
                        faction_abilities=[
                            lookup(
                                faction_abilities,
                                (faction_id, name),
                                "faction ability",
                                datasheet.name,
                            )
                            for name in spec.faction_abilities
                        ],
                        abilities=[
                            lookup(datasheet_abilities, name, "datasheet ability", datasheet.name)
                            for name in spec.abilities
                        ],
                        weapons=[build_weapon(w, datasheet.name) for w in spec.weapons],
                        wargear=[build_wargear(g, datasheet.name) for g in spec.wargear],
                    )
                )
                changed = True

    if changed:
        await session.commit()
