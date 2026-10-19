import pytest
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
    Model,
    Stratagem,
    Wargear,
    WargearAbility,
    Weapon,
    WeaponAbility,
)
from app.seeds import data_files
from app.seeds import datasheets as datasheet_data
from app.seeds import (
    conditions,
    datasheet_abilities,
    dispositions,
    effects,
    factions,
    keywords,
    run_all,
    stratagems,
    wargear_abilities,
    weapon_abilities,
)


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


FACTION_IDS = [faction.__name__.rsplit(".", 1)[-1] for faction in factions.FACTIONS]


def _ability_pairs():
    return {
        (faction.info.FACTION_NAME, name)
        for faction in factions.FACTIONS
        for name, _ in faction.abilities.ENTRIES
    }


def _unit_pairs():
    return {
        (faction.info.FACTION_NAME, name)
        for faction in factions.FACTIONS
        for name in factions.load_units(faction)
    }


def _detachment_pairs():
    return {
        (faction.info.FACTION_NAME, entry["name"])
        for faction in factions.FACTIONS
        for entry in factions.load_detachments(faction)
    }


async def _pairs(session: AsyncSession, model) -> set[tuple[str, str]]:
    # (faction name, row name) for every row of a faction-owned table.
    result = await session.execute(
        select(Faction.name, model.name).join(Faction, model.faction_id == Faction.id)
    )
    return set(result.all())


async def test_seed_faction_names_come_from_each_faction_info():
    assert factions.NAMES == [faction.info.FACTION_NAME for faction in factions.FACTIONS]
    assert len(factions.NAMES) == len(set(factions.NAMES))


@pytest.mark.parametrize("faction", factions.FACTIONS, ids=FACTION_IDS)
async def test_seed_faction_folder_has_no_duplicate_names(faction):
    abilities = [name for name, _ in faction.abilities.ENTRIES]
    assert len(abilities) == len(set(abilities))


@pytest.mark.parametrize("faction", factions.FACTIONS, ids=FACTION_IDS)
async def test_seed_faction_folder_has_at_least_one_ability(faction):
    assert faction.abilities.ENTRIES


async def test_seed_faction_abilities_inserts_all_entries(session: AsyncSession):
    await factions.seed(session)
    await factions.seed_abilities(session)

    assert await _pairs(session, FactionAbility) == _ability_pairs()


async def test_seed_faction_abilities_is_idempotent(session: AsyncSession):
    await factions.seed(session)
    await factions.seed_abilities(session)
    await factions.seed_abilities(session)

    names = (await session.execute(select(FactionAbility.name))).scalars().all()
    assert len(names) == len(_ability_pairs())


async def test_seed_faction_abilities_skips_entries_whose_faction_is_missing(
    session: AsyncSession,
):
    await factions.seed_abilities(session)

    assert (await session.execute(select(FactionAbility))).scalars().all() == []


async def test_seed_faction_units_inserts_all_names(session: AsyncSession, fixture_game_data):
    await factions.seed(session)
    await factions.seed_units(session)

    # The same unit name can be in more than one faction's roster.
    assert await _pairs(session, FactionUnit) == {
        ("Adeptus Mechanicus", "Test Squad"),
        ("Adeptus Mechanicus", "Test Walker"),
        ("Orks", "Test Boyz"),
        ("Orks", "Test Walker"),
    }


async def test_seed_faction_units_without_a_data_file_adds_nothing(session: AsyncSession):
    await factions.seed(session)
    await factions.seed_units(session)

    assert (await session.execute(select(FactionUnit))).scalars().all() == []


async def test_seed_faction_units_is_idempotent(session: AsyncSession, fixture_game_data):
    await factions.seed(session)
    await factions.seed_units(session)
    await factions.seed_units(session)

    names = (await session.execute(select(FactionUnit.name))).scalars().all()
    assert len(names) == 4


async def test_seed_faction_units_skips_if_faction_missing(
    session: AsyncSession, fixture_game_data
):
    await factions.seed_units(session)

    assert (await session.execute(select(FactionUnit))).scalars().all() == []


async def test_seed_detachments_inserts_all_entries(session: AsyncSession, fixture_game_data):
    await dispositions.seed(session)
    await factions.seed(session)
    await factions.seed_detachments(session)

    assert await _pairs(session, Detachment) == {("Orks", "Test Horde"), ("Orks", "Test Mob")}
    detachments = {
        d.name: d
        for d in (
            await session.execute(
                select(Detachment).options(selectinload(Detachment.dispositions))
            )
        )
        .scalars()
        .all()
    }
    horde = detachments["Test Horde"]
    assert horde.dp == 3
    # A detachment can have more than one disposition.
    assert {d.name for d in horde.dispositions} == {"Take and Hold", "Purge the Foe"}
    assert [d.name for d in detachments["Test Mob"].dispositions] == ["Disruption"]


async def test_seed_detachments_without_a_data_file_adds_nothing(session: AsyncSession):
    await dispositions.seed(session)
    await factions.seed(session)
    await factions.seed_detachments(session)

    assert (await session.execute(select(Detachment))).scalars().all() == []


async def test_seed_detachments_is_idempotent(session: AsyncSession, fixture_game_data):
    await dispositions.seed(session)
    await factions.seed(session)
    await factions.seed_detachments(session)
    await factions.seed_detachments(session)

    names = (await session.execute(select(Detachment.name))).scalars().all()
    assert sorted(names) == ["Test Horde", "Test Mob"]


async def test_seed_detachments_skips_if_faction_missing(session: AsyncSession, fixture_game_data):
    await dispositions.seed(session)
    await factions.seed_detachments(session)

    assert (await session.execute(select(Detachment))).scalars().all() == []


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
    # Only entries with no condition/effect dependencies at all can be created
    # before conditions.seed/effects.seed have run.
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

    # Only entries with no condition/effect dependencies (e.g. those whose
    # rules are code-defined in RULES) can be created before conditions/effects.
    names = set((await session.execute(select(DatasheetAbility.name))).scalars().all())
    assert names == {
        name
        for name, _, condition_keywords, effect_keywords in datasheet_abilities.ENTRIES
        if not condition_keywords and not effect_keywords
    }


async def test_run_all_seeds_everything(session: AsyncSession):
    await run_all(session)

    disposition_names = set((await session.execute(select(Disposition.name))).scalars().all())
    faction_names = set((await session.execute(select(Faction.name))).scalars().all())
    # Pairs rather than bare names: a unit name (e.g. "Skitarii Rangers") can
    # legitimately appear under more than one faction's roster.
    faction_unit_pairs = await _pairs(session, FactionUnit)
    faction_ability_pairs = await _pairs(session, FactionAbility)
    detachment_pairs = await _pairs(session, Detachment)
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
    assert faction_ability_pairs == _ability_pairs()
    assert faction_unit_pairs == _unit_pairs()
    assert detachment_pairs == _detachment_pairs()
    assert keyword_names == set(keywords.NAMES)
    assert condition_keywords == {keyword for keyword, _, _ in conditions.ENTRIES}
    assert effect_keywords == {keyword for keyword, _, _ in effects.ENTRIES}
    assert weapon_ability_names == {name for name, _, _, _ in weapon_abilities.ENTRIES}
    assert wargear_ability_names == {name for name, _, _, _ in wargear_abilities.ENTRIES}
    assert datasheet_ability_names == {name for name, _, _, _ in datasheet_abilities.ENTRIES}


async def test_seed_core_stratagems_inserts_all_entries(session: AsyncSession):
    await stratagems.seed(session)

    rows = (await session.execute(select(Stratagem))).scalars().all()
    assert {s.name for s in rows} == {name for name, _, _ in stratagems.CORE_ENTRIES}
    assert all(s.is_core for s in rows)


async def test_seed_core_stratagems_is_idempotent(session: AsyncSession):
    await stratagems.seed(session)
    await stratagems.seed(session)

    rows = (await session.execute(select(Stratagem.name))).scalars().all()
    assert len(rows) == len(stratagems.CORE_ENTRIES)


async def test_seed_weapon_abilities_backfills_effects_on_previously_empty_entry(
    session: AsyncSession,
):
    # "Precision" used to be seeded with no conditions/effects - an existing
    # empty row gets them filled in rather than being skipped.
    session.add(WeaponAbility(name="Precision", description="No mechanical effect."))
    await session.commit()

    await conditions.seed(session)
    await effects.seed(session)
    await weapon_abilities.seed(session)

    session.expire_all()
    precision = (
        await session.execute(
            select(WeaponAbility)
            .options(selectinload(WeaponAbility.conditions), selectinload(WeaponAbility.effects))
            .where(WeaponAbility.name == "Precision")
        )
    ).scalar_one()
    assert [c.keyword for c in precision.conditions] == ["always"]
    assert [e.keyword for e in precision.effects] == ["precision"]


async def test_faction_rule_options_use_known_conditions_and_effects():
    from app.combat_rules import CONDITIONS, EFFECTS

    for options in factions.RULE_OPTIONS.values():
        for rules in options.values():
            for rule in rules:
                assert set(rule.conditions) <= set(CONDITIONS)
                assert set(rule.effects) <= set(EFFECTS)


async def test_faction_rule_options_belong_to_a_seeded_ability_and_have_unique_names():
    option_names = [
        option_name for options in factions.RULE_OPTIONS.values() for option_name in options
    ]
    assert len(option_names) == len(set(option_names))
    assert set(factions.RULE_OPTIONS) <= _ability_pairs()


async def test_doctrina_imperatives_has_protector_and_conqueror_options():
    options = factions.rule_options("Adeptus Mechanicus", "Doctrina Imperatives")
    assert set(options) == {"Protector Imperative", "Conqueror Imperative"}


async def test_seed_weapon_abilities_renames_old_names_in_place(session: AsyncSession):
    # A database seeded before the rename keeps its row (and the weapons
    # linked to it) under the new name, instead of gaining a duplicate.
    old = WeaponAbility(name="RAPID FIRE 1", description="old")
    session.add(old)
    await session.commit()
    old_id = old.id

    await conditions.seed(session)
    await effects.seed(session)
    await weapon_abilities.seed(session)

    rows = (
        await session.execute(
            select(WeaponAbility.id, WeaponAbility.name).where(
                WeaponAbility.name.in_(["RAPID FIRE 1", "Rapid Fire 1"])
            )
        )
    ).all()
    assert rows == [(old_id, "Rapid Fire 1")]


async def test_datasheet_ability_rules_belong_to_seeded_abilities():
    from app.combat_rules import CONDITIONS, EFFECTS

    seeded = {name for name, _, _, _ in datasheet_abilities.ENTRIES}
    assert set(datasheet_abilities.RULES) <= seeded
    for rules in datasheet_abilities.RULES.values():
        for rule in rules:
            assert set(rule.conditions) <= set(CONDITIONS)
            assert set(rule.effects) <= set(EFFECTS)


async def test_seed_weapon_abilities_resyncs_heavy_to_the_heavy_effect(session: AsyncSession):
    # A database seeded when Heavy was a generic +1 to hit gets the HEAVY flag
    # instead - in place, so weapons that have Heavy keep it.
    await conditions.seed(session)
    await effects.seed(session)
    old_effect = (
        await session.execute(select(Effect).where(Effect.keyword == "plus_one_to_hit"))
    ).scalar_one()
    moved = (
        await session.execute(select(Condition).where(Condition.keyword == "moved_less_than_3"))
    ).scalar_one()
    heavy = WeaponAbility(
        name="Heavy", description="old", conditions=[moved], effects=[old_effect]
    )
    session.add(heavy)
    await session.commit()
    heavy_id = heavy.id

    await weapon_abilities.seed(session)

    session.expire_all()
    heavy = (
        await session.execute(
            select(WeaponAbility)
            .options(selectinload(WeaponAbility.conditions), selectinload(WeaponAbility.effects))
            .where(WeaponAbility.name == "Heavy")
        )
    ).scalar_one()
    assert heavy.id == heavy_id
    assert [c.keyword for c in heavy.conditions] == ["moved_less_than_3"]
    assert [e.keyword for e in heavy.effects] == ["heavy"]


async def test_datasheet_ability_options_are_well_formed():
    from app.combat_rules import CONDITIONS, EFFECTS

    seeded = {name for name, _, _, _ in datasheet_abilities.ENTRIES}
    assert set(datasheet_abilities.OPTIONS) <= seeded
    for options in datasheet_abilities.OPTIONS.values():
        for option in options.values():
            for rule in option.rules:
                assert set(rule.conditions) <= set(CONDITIONS)
                assert set(rule.effects) <= set(EFFECTS)
            assert set(option.keywords) <= set(keywords.NAMES)
    # Option names are unique across datasheet and faction ability options,
    # since a combat request names them without saying which ability they're from.
    names = [n for options in datasheet_abilities.OPTIONS.values() for n in options] + [
        n for options in factions.RULE_OPTIONS.values() for n in options
    ]
    assert len(names) == len(set(names))


async def test_core_stratagems_have_their_keyword_requirements(session: AsyncSession):
    await run_all(session)
    rows = {
        s.name: {k.name for k in s.keywords}
        for s in (
            await session.execute(select(Stratagem).options(selectinload(Stratagem.keywords)))
        )
        .scalars()
        .all()
    }
    assert rows["Epic Challenge"] == {"CHARACTER"}
    assert rows["Grenade"] == {"GRENADES"}
    assert rows["Tank Shock"] == {"VEHICLE"}
    assert rows["Go to Ground"] == {"INFANTRY"}
    assert rows["Smokescreen"] == {"SMOKE"}
    assert rows["Command Re-roll"] == set()
    assert set(stratagems.REQUIRED_KEYWORDS) <= set(rows)
    for required in stratagems.REQUIRED_KEYWORDS.values():
        assert set(required) <= set(keywords.NAMES)


async def test_seed_fills_in_keyword_requirements_on_existing_core_stratagems(
    session: AsyncSession,
):
    # Core stratagems seeded before they had keyword requirements.
    session.add(Stratagem(name="Grenade", description="old", cp=1, is_core=True))
    await session.commit()

    await keywords.seed(session)
    await stratagems.seed(session)

    session.expire_all()
    grenade = (
        await session.execute(
            select(Stratagem)
            .options(selectinload(Stratagem.keywords))
            .where(Stratagem.name == "Grenade")
        )
    ).scalar_one()
    assert [k.name for k in grenade.keywords] == ["GRENADES"]


async def test_core_stratagems_have_their_timings(session: AsyncSession):
    await run_all(session)
    rows = {
        s.name: {(t.phase, t.turn) for t in s.timings}
        for s in (
            await session.execute(select(Stratagem).options(selectinload(Stratagem.timings)))
        )
        .scalars()
        .all()
    }
    assert rows["Grenade"] == {("shooting", "your_turn")}
    assert rows["Fire Overwatch"] == {("movement", "opponent_turn"), ("charge", "opponent_turn")}
    assert rows["Command Re-roll"] == set()
    assert set(stratagems.TIMINGS) <= set(rows)


async def test_seed_missions_without_a_data_file_adds_nothing(session: AsyncSession):
    from app.models import PrimaryMission, SecondaryMission
    from app.seeds import missions

    await dispositions.seed(session)
    await missions.seed(session)
    assert (await session.execute(select(SecondaryMission))).scalars().all() == []
    assert (await session.execute(select(PrimaryMission))).scalars().all() == []


async def test_seed_missions_from_a_data_file(session: AsyncSession, tmp_path):
    import json

    from app.models import PrimaryMission, SecondaryMission
    from app.seeds import missions

    path = tmp_path / "missions.json"
    path.write_text(
        json.dumps(
            {
                "primaries": [
                    {
                        "name": "Battlefield Dominance",
                        "player_disposition": "Take and Hold",
                        "opponent_disposition": "Take and Hold",
                        "description": "Hold things.",
                    },
                    {
                        "name": "Purge and Secure",
                        "player_disposition": "Take and Hold",
                        "opponent_disposition": "Reconnaissance",
                        "description": None,
                    },
                ],
                "secondaries": [
                    {
                        "name": "Assassination",
                        "completes_on": "either",
                        "fixed_points": 3,
                        "tactical_points": 5,
                        "description": "Kill characters.",
                    }
                ],
            }
        )
    )
    await dispositions.seed(session)
    await missions.seed(session, path)
    await missions.seed(session, path)  # idempotent

    [secondary] = (await session.execute(select(SecondaryMission))).scalars().all()
    assert (secondary.name, secondary.completes_on, secondary.fixed_points) == (
        "Assassination",
        "either",
        3,
    )
    primaries = (
        await session.execute(
            select(PrimaryMission).options(
                selectinload(PrimaryMission.player_disposition),
                selectinload(PrimaryMission.opponent_disposition),
            )
        )
    ).scalars().all()
    assert {
        (p.name, p.player_disposition.name, p.opponent_disposition.name) for p in primaries
    } == {
        ("Battlefield Dominance", "Take and Hold", "Take and Hold"),
        ("Purge and Secure", "Take and Hold", "Reconnaissance"),
    }


async def test_seed_missions_rejects_an_unknown_disposition(session: AsyncSession, tmp_path):
    import json

    import pytest

    from app.seeds import missions

    path = tmp_path / "missions.json"
    path.write_text(
        json.dumps(
            {
                "primaries": [
                    {"name": "X", "player_disposition": "Nope", "opponent_disposition": "Nope"}
                ],
                "secondaries": [],
            }
        )
    )
    await dispositions.seed(session)
    with pytest.raises(ValueError, match="unknown disposition"):
        await missions.seed(session, path)


async def test_seed_dispositions_renames_reconnaisance_in_place(session: AsyncSession):
    old = Disposition(name="Reconnaisance")
    session.add(old)
    await session.commit()
    old_id = old.id

    await dispositions.seed(session)

    rows = (
        await session.execute(
            select(Disposition.id, Disposition.name).where(
                Disposition.name.in_(["Reconnaisance", "Reconnaissance"])
            )
        )
    ).all()
    assert rows == [(old_id, "Reconnaissance")]


# --- datasheets, from app/data/factions/<faction>/datasheets.json ---

# The real local data folder (tests otherwise point seeds at an empty one).
LOCAL_DATA_DIR = data_files.DATA_DIR


def _local_datasheets():
    return [
        (faction, datasheet)
        for faction in factions.FACTIONS
        for datasheet in _load_from(LOCAL_DATA_DIR, faction)
    ]


def _load_from(folder, faction):
    original = data_files.DATA_DIR
    data_files.DATA_DIR = folder
    try:
        return datasheet_data.load(faction.__name__.rsplit(".", 1)[-1])
    finally:
        data_files.DATA_DIR = original


LOCAL_DATASHEETS = _local_datasheets()


def _local(load, faction):
    # Calls a loader against the real local data folder.
    original = data_files.DATA_DIR
    data_files.DATA_DIR = LOCAL_DATA_DIR
    try:
        return load(faction)
    finally:
        data_files.DATA_DIR = original


LOCAL_UNITS = [
    (faction, names)
    for faction in factions.FACTIONS
    if (names := _local(factions.load_units, faction))
]


@pytest.mark.skipif(not LOCAL_UNITS, reason="no local unit data (app/data/factions/*/units.json)")
@pytest.mark.parametrize(
    "faction,names", LOCAL_UNITS, ids=[f.info.FACTION_NAME for f, _ in LOCAL_UNITS] or None
)
async def test_local_units_are_well_formed(faction, names):
    # Checks your local data files, if you have any.
    assert names and all(isinstance(name, str) and name for name in names)
    assert len(names) == len(set(names))


@pytest.mark.skipif(not LOCAL_DATASHEETS, reason="no local datasheet data (app/data/factions/*/datasheets.json)")
@pytest.mark.parametrize(
    "faction,datasheet", LOCAL_DATASHEETS, ids=[d.name for _, d in LOCAL_DATASHEETS] or None
)
async def test_local_datasheet_references_only_seeded_names(faction, datasheet):
    # Checks your local data files, if you have any: every datasheet is one of
    # its faction's units, and every keyword/ability it names gets seeded.
    assert datasheet.name in _local(factions.load_units, faction)
    weapon_ability_names = {name for name, _, _, _ in weapon_abilities.ENTRIES}
    wargear_ability_names = {name for name, _, _, _ in wargear_abilities.ENTRIES}
    datasheet_ability_names = {name for name, _, _, _ in datasheet_abilities.ENTRIES}
    faction_ability_names = {name for name, _ in faction.abilities.ENTRIES}
    for spec in datasheet.models:
        assert set(spec.keywords) <= set(keywords.NAMES)
        assert set(spec.faction_abilities) <= faction_ability_names
        assert set(spec.abilities) <= datasheet_ability_names
        for weapon in spec.weapons:
            assert set(weapon.abilities) <= weapon_ability_names
            assert (weapon.range is None) == (weapon.weapon_type == "melee")
        for gear in spec.wargear:
            assert set(gear.abilities) <= wargear_ability_names


async def test_load_datasheets_without_a_data_file_is_empty():
    assert datasheet_data.load("adeptus_mechanicus") == []


async def test_load_datasheets_from_a_data_file(fixture_game_data):
    [sheet] = datasheet_data.load("adeptus_mechanicus")
    assert sheet.name == "Test Squad"
    trooper, sergeant = sheet.models
    assert (trooper.name, trooper.toughness, trooper.invulnerable) == ("Test Trooper", 3, 5)
    assert trooper.keywords == ("INFANTRY", "BATTLELINE")
    assert [w.name for w in trooper.weapons].count("Test Stubber") == 3
    assert trooper.weapons[0].abilities == ("Rapid Fire 1", "Heavy")
    assert trooper.wargear[0].abilities == ("Ignore Cover (Unit)",)
    # Fields left out of the file take their defaults.
    assert (sergeant.is_leader, sergeant.invulnerable, sergeant.wargear) == (True, None, ())


def _test_squad_query():
    return (
        select(Model)
        .options(
            selectinload(Model.keywords),
            selectinload(Model.abilities),
            selectinload(Model.faction_abilities),
            selectinload(Model.wargear).selectinload(Wargear.abilities),
            selectinload(Model.weapons).selectinload(Weapon.abilities),
        )
        .where(Model.name.in_(["Test Trooper", "Test Sergeant"]))
    )


async def _test_squad(session: AsyncSession) -> dict:
    session.expire_all()
    return {m.name: m for m in (await session.execute(_test_squad_query())).scalars().all()}


async def test_run_all_seeds_datasheets_from_data_files(session: AsyncSession, fixture_game_data):
    await run_all(session)

    models = await _test_squad(session)
    trooper, sergeant = models["Test Trooper"], models["Test Sergeant"]
    assert (trooper.movement, trooper.toughness, trooper.save, trooper.wounds) == (6, 3, 4, 1)
    assert (trooper.leadership, trooper.oc, trooper.invulnerable) == (7, 2, 5)
    assert {k.name for k in trooper.keywords} == {"INFANTRY", "BATTLELINE"}
    assert [a.name for a in trooper.faction_abilities] == ["Doctrina Imperatives"]
    assert [a.name for a in trooper.abilities] == ["Stealth"]
    weapons = sorted(w.name for w in trooper.weapons)
    assert weapons == ["Test Blade", "Test Rifle", "Test Stubber", "Test Stubber", "Test Stubber"]
    rifle = next(w for w in trooper.weapons if w.name == "Test Rifle")
    assert (rifle.range, rifle.attacks, rifle.ap, rifle.damage) == (24, "2", -1, "D3")
    assert {a.name for a in rifle.abilities} == {"Rapid Fire 1", "Heavy"}
    [scope] = trooper.wargear
    assert [a.name for a in scope.abilities] == ["Ignore Cover (Unit)"]
    assert sergeant.is_leader is True
    assert [w.name for w in sergeant.weapons] == ["Test Blade"]


async def test_seed_datasheets_is_idempotent(session: AsyncSession, fixture_game_data):
    await run_all(session)
    models_before = (await session.execute(select(Model.name))).scalars().all()
    weapons_before = (await session.execute(select(Weapon.model_id, Weapon.name))).all()

    await factions.seed_datasheets(session)

    assert sorted((await session.execute(select(Model.name))).scalars().all()) == sorted(
        models_before
    )
    assert sorted((await session.execute(select(Weapon.model_id, Weapon.name))).all()) == sorted(
        weapons_before
    )


async def test_seed_datasheets_rejects_unknown_references(session: AsyncSession, fixture_game_data):
    # Without keywords/weapon abilities seeded, the datasheet's references
    # can't be resolved - that's an error rather than a silently bare model.
    await factions.seed(session)
    await factions.seed_abilities(session)

    with pytest.raises(ValueError, match="references unknown"):
        await factions.seed_datasheets(session)


async def test_seed_datasheets_fills_in_what_an_existing_model_is_missing(
    session: AsyncSession, fixture_game_data
):
    # A model seeded before its datasheet gained things (or that's had some
    # removed) gets them back - weapons (counting copies), wargear, abilities,
    # faction abilities, and abilities on existing weapons - while a user's
    # edit to an existing weapon is left alone.
    await run_all(session)
    trooper = (await _test_squad(session))["Test Trooper"]
    stubbers = [w for w in trooper.weapons if w.name == "Test Stubber"]
    blade = next(w for w in trooper.weapons if w.name == "Test Blade")
    rifle = next(w for w in trooper.weapons if w.name == "Test Rifle")
    for extra in stubbers[1:] + [blade]:
        trooper.weapons.remove(extra)
        await session.delete(extra)
    scope = trooper.wargear[0]
    trooper.wargear.remove(scope)
    await session.delete(scope)
    trooper.abilities = []
    trooper.faction_abilities = []
    rifle.abilities = [a for a in rifle.abilities if a.name != "Heavy"]
    rifle.attacks = "9"  # a user edit
    await session.commit()

    await factions.seed_datasheets(session)

    trooper = (await _test_squad(session))["Test Trooper"]
    names = sorted(w.name for w in trooper.weapons)
    assert names == ["Test Blade", "Test Rifle", "Test Stubber", "Test Stubber", "Test Stubber"]
    rifle = next(w for w in trooper.weapons if w.name == "Test Rifle")
    assert {a.name for a in rifle.abilities} == {"Rapid Fire 1", "Heavy"}
    assert rifle.attacks == "9"
    assert [g.name for g in trooper.wargear] == ["Test Scope"]
    assert [a.name for a in trooper.abilities] == ["Stealth"]
    assert [a.name for a in trooper.faction_abilities] == ["Doctrina Imperatives"]


async def test_canticles_of_the_omnissiah_options():
    assert set(datasheet_abilities.OPTIONS["Canticles of the Omnissiah"]) == {
        "Invocation of Machine Vengeance",
        "Mantra of Discipline",
        "Shroudpsalm",
    }



async def test_seed_detachments_fills_in_missing_dispositions(
    session: AsyncSession, fixture_game_data
):
    # A detachment seeded with fewer dispositions than its data now lists
    # gets the rest; nothing is removed.
    await dispositions.seed(session)
    await factions.seed(session)
    await factions.seed_detachments(session)
    load = (
        select(Detachment)
        .options(selectinload(Detachment.dispositions))
        .where(Detachment.name == "Test Horde")
    )
    horde = (await session.execute(load)).scalar_one()
    horde.dispositions = [d for d in horde.dispositions if d.name == "Take and Hold"]
    await session.commit()

    await factions.seed_detachments(session)

    session.expire_all()
    horde = (await session.execute(load)).scalar_one()
    assert {d.name for d in horde.dispositions} == {"Take and Hold", "Purge the Foe"}


async def test_seed_detachments_rejects_an_unknown_disposition(
    session: AsyncSession, monkeypatch, tmp_path
):
    import json

    (tmp_path / "factions" / "orks").mkdir(parents=True)
    (tmp_path / "factions" / "orks" / "detachments.json").write_text(
        json.dumps(
            {
                "faction": "Orks",
                "detachments": [{"name": "Typo Mob", "dp": 1, "dispositions": ["Reconnaisance"]}],
            }
        )
    )
    monkeypatch.setattr(data_files, "DATA_DIR", tmp_path)
    await dispositions.seed(session)
    await factions.seed(session)
    with pytest.raises(ValueError, match="Typo Mob"):
        await factions.seed_detachments(session)


def _local_detachments():
    original = data_files.DATA_DIR
    data_files.DATA_DIR = LOCAL_DATA_DIR
    try:
        return [(f, factions.load_detachments(f)) for f in factions.FACTIONS]
    finally:
        data_files.DATA_DIR = original


LOCAL_DETACHMENTS = [(f, entries) for f, entries in _local_detachments() if entries]


@pytest.mark.skipif(not LOCAL_DETACHMENTS, reason="no local detachment data (app/data/factions/*/detachments.json)")
@pytest.mark.parametrize(
    "faction,entries",
    LOCAL_DETACHMENTS,
    ids=[f.info.FACTION_NAME for f, _ in LOCAL_DETACHMENTS] or None,
)
async def test_local_detachments_are_well_formed(faction, entries):
    # Checks your local data files, if you have any.
    names = [entry["name"] for entry in entries]
    assert len(names) == len(set(names))
    for entry in entries:
        assert isinstance(entry["dp"], int)
        assert entry["dispositions"], entry["name"]
        assert set(entry["dispositions"]) <= set(dispositions.NAMES), entry["name"]
