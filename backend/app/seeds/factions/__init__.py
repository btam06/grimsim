from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.combat_rules import Rule
from app.models import (
    BaseSize,
    DatasheetAbility,
    Detachment,
    DetachmentRule,
    DetachmentRuleDatasheetAbility,
    DetachmentRuleWeaponAbility,
    Enhancement,
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
    adepta_sororitas,
    adeptus_custodes,
    adeptus_mechanicus,
    adeptus_titanicus,
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

from app.models.enhancement import (
    ENHANCEMENT_KINDS,
    KIND_SCOPES,
    EnhancementDatasheetAbility,
    EnhancementKeyword,
    EnhancementWeapon,
    EnhancementWeaponAbility,
)
from app.models.wargear import WARGEAR_SCOPES
from app.seeds import data_files
from app.seeds import datasheets as datasheet_data
from app.seeds.lookup import get_dispositions_by_name

# One folder per faction, each with:
#   info.py                  FACTION_NAME, and optional ALLY_RULES
#   abilities.py             ENTRIES of (ability name, description), plus an
#                            optional OPTIONS dict of rule options an ability
#                            grants (e.g. Doctrina Imperatives' Protector and
#                            Conqueror Imperatives) - see rule_options below
#   datasheet_abilities.py   optional: the faction's datasheet abilities, in the
#                            shape of the core ones in
#                            app/seeds/datasheet_abilities.py, which combines
#                            them
#
# Game data - units, detachments and full datasheets - isn't in here: it's
# loaded from app/data/factions/<faction folder name>/ (units.json,
# detachments.json, datasheets.json) - see app/data/README.md.
#
# To add a faction: copy an existing folder, fill it in, then register it in
# FACTIONS below. Everything else (the Faction rows themselves, and its
# abilities/units/detachments) is seeded from these files.
FACTIONS = [
    adepta_sororitas,
    adeptus_custodes,
    adeptus_mechanicus,
    adeptus_titanicus,
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

# Each faction's list selection, for those that have one (info.py SUBFACTION -
# e.g. the Space Marines' Chapter), by faction name.
SUBFACTIONS: dict[str, dict] = {
    faction.info.FACTION_NAME: faction.info.SUBFACTION
    for faction in FACTIONS
    if hasattr(faction.info, "SUBFACTION")
}

# Detachments whose units with certain keywords can only take that
# detachment's enhancements (info.py EXCLUSIVE_ENHANCEMENTS - e.g. Deathwatch
# Support's KILL TEAM units): {detachment name: (keyword, ...)}.
EXCLUSIVE_ENHANCEMENTS: dict[str, tuple[str, ...]] = {
    name: keywords
    for faction in FACTIONS
    for name, keywords in getattr(faction.info, "EXCLUSIVE_ENHANCEMENTS", {}).items()
}

# (Option names are unique across every faction's.)


# Every faction's army-building ally rules (see app/list_rules.py).
ALLY_RULES = [rule for faction in FACTIONS for rule in getattr(faction.info, "ALLY_RULES", [])]


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


def load_enhancements(faction) -> list[dict]:
    # A faction's enhancements and upgrades, from its enhancements.json, each
    # naming the detachment it's from. None if there's no file.
    path = data_files.faction_data_dir(faction_slug(faction)) / "enhancements.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["enhancements"]


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


# (faction name, ability name) for every faction ability whose options are
# required (abilities.py REQUIRED_OPTIONS): one is always chosen - no "none".
REQUIRED_OPTIONS: set[tuple[str, str]] = {
    (faction.info.FACTION_NAME, ability_name)
    for faction in FACTIONS
    for ability_name in getattr(faction.abilities, "REQUIRED_OPTIONS", set())
}


def required(faction_name: str, ability_name: str) -> bool:
    return (faction_name, ability_name) in REQUIRED_OPTIONS


# In a game: faction abilities whose round-start choices aren't (just) their
# calculator options (abilities.py ROUND_START_CHOICES, with
# ROUND_START_DESCRIPTIONS), and those whose choices last the rest of the
# battle (LASTING_CHOICES) - e.g. Harbingers of Dread.
ROUND_START_CHOICES: dict[tuple[str, str], list[str]] = {
    (faction.info.FACTION_NAME, ability_name): choices
    for faction in FACTIONS
    for ability_name, choices in getattr(faction.abilities, "ROUND_START_CHOICES", {}).items()
}
ROUND_START_DESCRIPTIONS: dict[tuple[str, str], dict[str, str]] = {
    (faction.info.FACTION_NAME, ability_name): descriptions
    for faction in FACTIONS
    for ability_name, descriptions in getattr(
        faction.abilities, "ROUND_START_DESCRIPTIONS", {}
    ).items()
}
LASTING_CHOICES: set[tuple[str, str]] = {
    (faction.info.FACTION_NAME, ability_name)
    for faction in FACTIONS
    for ability_name in getattr(faction.abilities, "LASTING_CHOICES", set())
}


# In a game: faction abilities whose option is selected in the player's
# Command phase (abilities.py COMMAND_PHASE_CHOICES, with
# COMMAND_PHASE_DESCRIPTIONS), those whose options can each be selected only
# once per battle (ONCE_PER_BATTLE), and what options let a unit still do
# after Advancing or Falling Back (ELIGIBLE_AFTER: {option name: {action:
# (things it can still do)}}) - e.g. Combat Doctrines.
COMMAND_PHASE_CHOICES: set[tuple[str, str]] = {
    (faction.info.FACTION_NAME, ability_name)
    for faction in FACTIONS
    for ability_name in getattr(faction.abilities, "COMMAND_PHASE_CHOICES", set())
}
COMMAND_PHASE_DESCRIPTIONS: dict[tuple[str, str], dict[str, str]] = {
    (faction.info.FACTION_NAME, ability_name): descriptions
    for faction in FACTIONS
    for ability_name, descriptions in getattr(
        faction.abilities, "COMMAND_PHASE_DESCRIPTIONS", {}
    ).items()
}
ONCE_PER_BATTLE: set[tuple[str, str]] = {
    (faction.info.FACTION_NAME, ability_name)
    for faction in FACTIONS
    for ability_name in getattr(faction.abilities, "ONCE_PER_BATTLE", set())
}
# In a game, what detachment rules do beyond the abilities they grant (each
# faction's optional detachment_rules.py): extra selections of once-per-battle
# options ({detachment name: {option name: extra}} - e.g. Assault Mastery: the
# Assault Doctrine twice), and charge roll bonuses ({rule name: bonus} - e.g.
# Death Blow).
EXTRA_SELECTIONS: dict[str, dict[str, int]] = {
    detachment: extra
    for faction in FACTIONS
    for detachment, extra in getattr(
        getattr(faction, "detachment_rules", None), "EXTRA_SELECTIONS", {}
    ).items()
}
# {enhancement name: how it changes its bearer's unit's arrival from Reserves}
# - detachment_rules.py ARRIVAL_ENHANCEMENTS (e.g. Beacon Angelis).
ARRIVAL_ENHANCEMENTS: dict[str, dict] = {
    name: arrival
    for faction in FACTIONS
    for name, arrival in getattr(
        getattr(faction, "detachment_rules", None), "ARRIVAL_ENHANCEMENTS", {}
    ).items()
}
CHARGE_BONUSES: dict[str, int] = {
    rule: bonus
    for faction in FACTIONS
    for rule, bonus in getattr(
        getattr(faction, "detachment_rules", None), "CHARGE_BONUSES", {}
    ).items()
}
# {detachment rule name: the objective it has its player select in their
# Command phase} - detachment_rules.py OBJECTIVE_SELECTIONS (e.g. Acquisition
# At Any Cost); and {enhancement name: the CP it rolls for at the end of the
# bearer's Command phase} - END_OF_COMMAND_CP (e.g. Magos). See
# app/services/in_game/selected_objectives.py.
OBJECTIVE_SELECTIONS: dict[str, dict] = {
    rule: selection
    for faction in FACTIONS
    for rule, selection in getattr(
        getattr(faction, "detachment_rules", None), "OBJECTIVE_SELECTIONS", {}
    ).items()
}
END_OF_COMMAND_CP: dict[str, dict] = {
    name: config
    for faction in FACTIONS
    for name, config in getattr(
        getattr(faction, "detachment_rules", None), "END_OF_COMMAND_CP", {}
    ).items()
}
ELIGIBLE_AFTER: dict[str, dict[str, tuple[str, ...]]] = {
    option_name: eligible
    for faction in FACTIONS
    for option_name, eligible in getattr(faction.abilities, "ELIGIBLE_AFTER", {}).items()
}


def rule_options(faction_name: str, ability_name: str) -> dict[str, list[Rule]]:
    # The selectable rule options a faction ability grants, if any.
    return RULE_OPTIONS.get((faction_name, ability_name), {})


def option_descriptions(faction_name: str, ability_name: str) -> dict[str, str]:
    # What each of a faction ability's options does in the calculator: its
    # rules' descriptions, together.
    return {
        option: " ".join(rule.description for rule in rules if rule.description)
        for option, rules in rule_options(faction_name, ability_name).items()
        if any(rule.description for rule in rules)
    }


# {(faction name, ability name): note} across every faction's abilities.py
# CALCULATOR_NOTES - how the calculator handles an ability, where that needs
# saying.
CALCULATOR_NOTES: dict[tuple[str, str], str] = {
    (faction.info.FACTION_NAME, ability_name): note
    for faction in FACTIONS
    for ability_name, note in getattr(faction.abilities, "CALCULATOR_NOTES", {}).items()
}


def calculator_notes(faction_name: str, ability_name: str) -> list[str]:
    note = CALCULATOR_NOTES.get((faction_name, ability_name))
    return [note] if note else []


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
    # existing ones any of their dispositions they're missing, and their unique
    # tag if they have none (additive only).
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
                detachment = Detachment(
                    name=name, faction_id=faction_id, dp=dp, dispositions=dispositions
                )
                detachment.unique_tag = entry.get("unique_tag")
                session.add(detachment)
                changed = True
                continue
            if entry.get("unique_tag") and not detachment.unique_tag:
                detachment.unique_tag = entry["unique_tag"]
                changed = True
            for disposition in dispositions:
                if disposition not in detachment.dispositions:
                    detachment.dispositions.append(disposition)
                    changed = True

    if changed:
        await session.commit()


async def seed_detachment_rules(session: AsyncSession) -> None:
    # Adds each detachment's rules (the "rules" of its entry in
    # detachments.json) that it doesn't have yet, by name. An existing one
    # only gains per_model if it's since been set, and granted keywords if it
    # has none; nothing else is changed.
    # Must run after seed_detachments, seed_keywords and the weapon/datasheet
    # ability seeds; an unknown keyword or ability is an error, not skipped.
    faction_ids = await _faction_ids_by_name(session)
    keywords = {k.name: k for k in (await session.execute(select(Keyword))).scalars().all()}
    weapon_abilities = {
        a.name: a for a in (await session.execute(select(WeaponAbility))).scalars().all()
    }
    datasheet_abilities = {
        a.name: a for a in (await session.execute(select(DatasheetAbility))).scalars().all()
    }
    detachments = {
        (d.faction_id, d.name): d.id
        for d in (await session.execute(select(Detachment))).scalars().all()
    }
    existing = {
        (r.detachment_id, r.name): r
        for r in (await session.execute(select(DetachmentRule))).scalars().all()
    }

    def lookup(table: dict, key: str, kind: str, rule: str):
        if key not in table:
            raise ValueError(f"detachment rule {rule!r} references unknown {kind} {key!r}")
        return table[key]

    changed = False
    for faction in FACTIONS:
        faction_id = faction_ids.get(faction.info.FACTION_NAME)
        if faction_id is None:
            continue  # faction hasn't been seeded yet
        for detachment_entry in load_detachments(faction):
            detachment_id = detachments.get((faction_id, detachment_entry["name"]))
            if detachment_id is None:
                continue  # detachment hasn't been seeded yet
            for entry in detachment_entry.get("rules", []):
                name = entry["name"]
                options = [
                    [lookup(keywords, k, "keyword", name) for k in option]
                    for option in entry.get("keyword_options", [])
                ]
                if any(not option for option in options):
                    raise ValueError(f"detachment rule {name!r} has an empty keyword option")
                if entry.get("per_model") and entry.get("selection_limit"):
                    raise ValueError(
                        f"detachment rule {name!r} can't be both per_model and selected for units"
                    )
                weapon_grants = [
                    DetachmentRuleWeaponAbility(
                        weapon_ability=lookup(weapon_abilities, g["name"], "weapon ability", name),
                        weapon_type=g.get("weapon_type"),
                    )
                    for g in entry.get("weapon_abilities", [])
                ]
                datasheet_grants = [
                    DetachmentRuleDatasheetAbility(
                        datasheet_ability=lookup(
                            datasheet_abilities, ability, "datasheet ability", name
                        )
                    )
                    for ability in entry.get("datasheet_abilities", [])
                ]
                granted_keywords = [
                    lookup(keywords, k, "keyword", name)
                    for k in entry.get("granted_keywords", [])
                ]
                rule = existing.get((detachment_id, name))
                if rule is not None:
                    # Added after it was first seeded.
                    if entry.get("per_model") and not rule.per_model:
                        rule.per_model = True
                        changed = True
                    if granted_keywords and not rule.keyword_grant_links:
                        rule.granted_keywords = granted_keywords
                        changed = True
                    if entry.get("selection_limit") and rule.selection_limit is None:
                        rule.selection_limit = entry["selection_limit"]
                        changed = True
                    continue
                rule = DetachmentRule(
                    detachment_id=detachment_id,
                    name=name,
                    description=entry.get("description"),
                    keyword_options=options,
                    weapon_ability_grants=weapon_grants,
                    datasheet_ability_grants=datasheet_grants,
                )
                rule.per_model = entry.get("per_model", False)
                rule.granted_keywords = granted_keywords
                rule.selection_limit = entry.get("selection_limit")
                existing[(detachment_id, name)] = rule
                session.add(rule)
                changed = True

    if changed:
        await session.commit()


async def seed_enhancements(session: AsyncSession) -> None:
    # Adds each faction's enhancements and upgrades (see load_enhancements)
    # that its detachments don't have yet, by name. An existing one gets any
    # kind of grant (weapon/datasheet abilities, keywords, weapons) it has none
    # of yet; nothing else is changed.
    # Must run after seed_detachments, seed_keywords and the weapon/datasheet
    # ability seeds; an unknown detachment, kind, keyword, ability or scope is
    # an error, not skipped.
    faction_ids = await _faction_ids_by_name(session)
    keywords = {k.name: k for k in (await session.execute(select(Keyword))).scalars().all()}
    detachments = {
        (d.faction_id, d.name): d.id
        for d in (await session.execute(select(Detachment))).scalars().all()
    }
    weapon_abilities = {
        a.name: a for a in (await session.execute(select(WeaponAbility))).scalars().all()
    }
    datasheet_abilities = {
        a.name: a for a in (await session.execute(select(DatasheetAbility))).scalars().all()
    }
    existing = {
        (e.detachment_id, e.name): e
        for e in (await session.execute(select(Enhancement))).scalars().all()
    }

    def lookup(table: dict, key: str, kind: str, enhancement: str):
        if key not in table:
            raise ValueError(f"enhancement {enhancement!r} references unknown {kind} {key!r}")
        return table[key]

    def lookup_keyword(name: str, enhancement: str) -> Keyword:
        return lookup(keywords, name, "keyword", enhancement)

    def grants(entry: dict) -> dict[str, list]:
        # What the entry grants, by Enhancement attribute.
        name = entry["name"]
        allowed = KIND_SCOPES[entry["kind"]]
        if entry.get("weapons") and entry["kind"] != "enhancement":
            raise ValueError(f"enhancement {name!r} is an upgrade, which can't give a weapon")
        for grant in (
            entry.get("weapon_abilities", [])
            + entry.get("datasheet_abilities", [])
            + entry.get("granted_keywords", [])
        ):
            if grant["scope"] not in allowed:
                raise ValueError(
                    f"enhancement {name!r} has scope {grant['scope']!r}; "
                    f"an {entry['kind']} can use {', '.join(allowed)}"
                )
        weapon = [
            EnhancementWeaponAbility(
                weapon_ability=lookup(weapon_abilities, g["name"], "weapon ability", name),
                weapon_type=g.get("weapon_type"),
                scope=g["scope"],
            )
            for g in entry.get("weapon_abilities", [])
        ]
        datasheet = [
            EnhancementDatasheetAbility(
                datasheet_ability=lookup(
                    datasheet_abilities, g["name"], "datasheet ability", name
                ),
                scope=g["scope"],
            )
            for g in entry.get("datasheet_abilities", [])
        ]
        granted_keywords = [
            EnhancementKeyword(
                keyword=lookup_keyword(g["name"], name),
                scope=g["scope"],
            )
            for g in entry.get("granted_keywords", [])
        ]
        weapons = [
            EnhancementWeapon(
                name=w["name"],
                weapon_type=w["weapon_type"],
                range=w.get("range"),
                attacks=w["attacks"],
                skill=w["skill"],
                strength=w["strength"],
                ap=w["ap"],
                damage=w["damage"],
                abilities=[
                    lookup(weapon_abilities, a, "weapon ability", name)
                    for a in w.get("abilities", [])
                ],
            )
            for w in entry.get("weapons", [])
        ]
        return {
            "weapon_ability_grants": weapon,
            "datasheet_ability_grants": datasheet,
            "keyword_grants": granted_keywords,
            "weapons": weapons,
        }

    changed = False
    for faction in FACTIONS:
        faction_id = faction_ids.get(faction.info.FACTION_NAME)
        if faction_id is None:
            continue  # faction hasn't been seeded yet
        for entry in load_enhancements(faction):
            name = entry["name"]
            detachment_id = detachments.get((faction_id, entry["detachment"]))
            if detachment_id is None:
                raise ValueError(
                    f"enhancement {name!r} references unknown detachment {entry['detachment']!r}"
                )
            if entry["kind"] not in ENHANCEMENT_KINDS:
                raise ValueError(f"enhancement {name!r} has unknown kind {entry['kind']!r}")
            required = [lookup_keyword(k, name) for k in entry.get("keywords", [])]
            excluded = [lookup_keyword(k, name) for k in entry.get("excluded_keywords", [])]
            entry_grants = grants(entry)
            enhancement = existing.get((detachment_id, name))
            if enhancement is not None:
                # Fill in each kind of grant it has none of yet (e.g. a weapon
                # added to the data after it was first seeded).
                for attribute, values in entry_grants.items():
                    if values and not getattr(enhancement, attribute):
                        setattr(enhancement, attribute, values)
                        changed = True
                continue
            enhancement = Enhancement(
                name=name,
                description=entry.get("description"),
                points=entry["points"],
                kind=entry["kind"],
                detachment_id=detachment_id,
                keywords=required,
                excluded_keywords=excluded,
                **entry_grants,
            )
            existing[(detachment_id, name)] = enhancement
            session.add(enhancement)
            changed = True

    if changed:
        await session.commit()


async def seed_datasheets(session: AsyncSession) -> None:
    # Creates the models (with stats, keywords, faction/datasheet abilities,
    # weapons and wargear) in each faction's datasheets.json.
    #
    # For a model that already exists in its faction (by name), only what it's
    # missing (by name) is added: faction/datasheet abilities, weapons,
    # wargear, abilities on same-named weapons, and its base size if it has
    # none. Nothing existing is changed
    # or removed, so additions to a datasheet reach previously seeded models
    # without overwriting edits. (Stats and keywords aren't synced.)
    #
    # Must run after keywords, weapon/wargear/datasheet abilities and faction
    # abilities are seeded, since everything is referenced by name - a name
    # that isn't found is an error, not skipped.
    faction_ids = await _faction_ids_by_name(session)
    keywords = {k.name: k for k in (await session.execute(select(Keyword))).scalars().all()}
    base_sizes = {b.name: b for b in (await session.execute(select(BaseSize))).scalars().all()}
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
        built = Weapon(
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
        built.is_default = weapon.default
        return built

    def build_wargear(gear, datasheet: str) -> Wargear:
        if gear.scope not in WARGEAR_SCOPES:
            raise ValueError(f"{datasheet}: wargear {gear.name!r} has unknown scope {gear.scope!r}")
        wargear = Wargear(
            name=gear.name,
            description=gear.description,
            abilities=[
                lookup(wargear_abilities, name, "wargear ability", datasheet)
                for name in gear.abilities
            ],
        )
        wargear.scope = gear.scope
        return wargear

    changed = False
    for faction in FACTIONS:
        faction_id = faction_ids.get(faction.info.FACTION_NAME)
        if faction_id is None:
            continue  # faction hasn't been seeded yet
        for datasheet in datasheet_data.load(faction_slug(faction)):
            for spec in datasheet.models:
                model = existing.get((faction_id, spec.name))
                if model is not None:
                    if spec.invulnerable_ranged_only and not model.invulnerable_ranged_only:
                        model.invulnerable_ranged_only = True
                        changed = True
                    if spec.feel_no_pain_mortal and not model.feel_no_pain_mortal:
                        model.feel_no_pain_mortal = spec.feel_no_pain_mortal
                        changed = True
                    if spec.base_size and not model.base_size:
                        model.base_size = lookup(
                            base_sizes, spec.base_size, "base size", datasheet.name
                        )
                        changed = True
                    if spec.transport and model.transport is None:
                        model.transport = spec.transport
                        changed = True
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
                        for existing_weapon, weapon_spec in zip(existing_weapons, weapon_specs):
                            # Marked as a default weapon since it was seeded.
                            if weapon_spec.default and not existing_weapon.is_default:
                                existing_weapon.is_default = True
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
                        feel_no_pain_mortal=spec.feel_no_pain_mortal,
                        invulnerable_ranged_only=spec.invulnerable_ranged_only,
                        base_size=(
                            lookup(base_sizes, spec.base_size, "base size", datasheet.name)
                            if spec.base_size
                            else None
                        ),
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
                        transport=spec.transport,
                    )
                )
                changed = True

    if changed:
        await session.commit()
