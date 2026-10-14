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
        for name in faction.units.NAMES
    }


def _detachment_pairs():
    return {
        (faction.info.FACTION_NAME, name)
        for faction in factions.FACTIONS
        for name, _, _ in faction.detachments.ENTRIES
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
    detachments = [name for name, _, _ in faction.detachments.ENTRIES]
    assert len(abilities) == len(set(abilities))
    assert len(faction.units.NAMES) == len(set(faction.units.NAMES))
    assert len(detachments) == len(set(detachments))


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


async def test_seed_faction_units_inserts_all_names(session: AsyncSession):
    await factions.seed(session)
    await factions.seed_units(session)

    assert await _pairs(session, FactionUnit) == _unit_pairs()


async def test_seed_faction_units_is_idempotent(session: AsyncSession):
    await factions.seed(session)
    await factions.seed_units(session)
    await factions.seed_units(session)

    names = (await session.execute(select(FactionUnit.name))).scalars().all()
    assert len(names) == len(_unit_pairs())


async def test_seed_faction_units_skips_if_faction_missing(session: AsyncSession):
    await factions.seed_units(session)

    assert (await session.execute(select(FactionUnit))).scalars().all() == []


async def test_seed_detachments_inserts_all_entries(session: AsyncSession):
    await dispositions.seed(session)
    await factions.seed(session)
    await factions.seed_detachments(session)

    assert await _pairs(session, Detachment) == _detachment_pairs()

    detachments = (
        await session.execute(select(Detachment).options(selectinload(Detachment.dispositions)))
    ).scalars().all()
    expected = {
        name: (disposition_name, dp)
        for faction in factions.FACTIONS
        for name, disposition_name, dp in faction.detachments.ENTRIES
    }
    for detachment in detachments:
        disposition_name, dp = expected[detachment.name]
        assert detachment.dp == dp
        assert [d.name for d in detachment.dispositions] == [disposition_name]


async def test_seed_detachments_is_idempotent(session: AsyncSession):
    await dispositions.seed(session)
    await factions.seed(session)
    await factions.seed_detachments(session)
    await factions.seed_detachments(session)

    names = (await session.execute(select(Detachment.name))).scalars().all()
    assert len(names) == len(_detachment_pairs())


async def test_seed_detachments_skips_if_faction_missing(session: AsyncSession):
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


DATASHEETS = [
    (faction, datasheet)
    for faction in factions.FACTIONS
    for datasheet in getattr(faction.units, "DATASHEETS", [])
]
DATASHEET_IDS = [datasheet.NAME for _, datasheet in DATASHEETS]


@pytest.mark.parametrize("faction,datasheet", DATASHEETS, ids=DATASHEET_IDS)
async def test_datasheet_references_only_seeded_names(faction, datasheet):
    assert datasheet.NAME in faction.units.NAMES
    weapon_ability_names = {name for name, _, _, _ in weapon_abilities.ENTRIES}
    faction_ability_names = {name for name, _ in faction.abilities.ENTRIES}
    for spec in datasheet.MODELS:
        assert set(spec.keywords) <= set(keywords.NAMES)
        assert set(spec.faction_abilities) <= faction_ability_names
        for weapon in spec.weapons:
            assert set(weapon.abilities) <= weapon_ability_names
            assert (weapon.range is None) == (weapon.weapon_type == "melee")
        wargear_ability_names = {name for name, _, _, _ in wargear_abilities.ENTRIES}
        for gear in spec.wargear:
            assert set(gear.abilities) <= wargear_ability_names


async def test_run_all_seeds_skitarii_rangers(session: AsyncSession):
    await run_all(session)

    ranger = (
        await session.execute(
            select(Model)
            .options(
                selectinload(Model.keywords),
                selectinload(Model.faction_abilities),
                selectinload(Model.weapons).selectinload(Weapon.abilities),
                selectinload(Model.wargear).selectinload(Wargear.abilities),
            )
            .join(Faction)
            .where(Model.name == "Skitarii Ranger", Faction.name == "Adeptus Mechanicus")
        )
    ).scalar_one()
    assert (ranger.movement, ranger.toughness, ranger.save, ranger.wounds) == (6, 3, 4, 1)
    assert (ranger.leadership, ranger.oc, ranger.invulnerable) == (7, 2, 5)
    assert {"INFANTRY", "BATTLELINE", "SKITARII", "RANGERS"} <= {k.name for k in ranger.keywords}
    assert [a.name for a in ranger.faction_abilities] == ["Doctrina Imperatives"]

    weapons = {w.name: w for w in ranger.weapons}
    assert set(weapons) == {
        "Arc rifle",
        "Galvanic rifle",
        "Plasma caliver – standard",
        "Plasma caliver – supercharge",
        "Transuranic arquebus",
        "Close combat weapon",
    }
    arc_rifle = weapons["Arc rifle"]
    assert (arc_rifle.range, arc_rifle.attacks, arc_rifle.skill) == (30, "1", 4)
    assert (arc_rifle.strength, arc_rifle.ap, arc_rifle.damage) == (8, -1, "D3")
    assert {a.name for a in arc_rifle.abilities} == {
        "Anti-Vehicle 4+",
        "Devastating Wounds",
        "Rapid Fire 1",
    }
    alpha = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.weapons), selectinload(Model.wargear))
            .where(Model.name == "Skitarii Ranger Alpha")
        )
    ).scalar_one()
    alpha_weapons = {w.name: w for w in alpha.weapons}
    assert set(alpha_weapons) == {
        "Galvanic rifle",
        "Close combat weapon",
        "Alpha combat weapon",
        "Mechanicus pistol",
    }
    assert alpha_weapons["Alpha combat weapon"].weapon_type == "melee"
    assert alpha_weapons["Alpha combat weapon"].range is None
    assert alpha.wargear == []
    assert (alpha.toughness, alpha.save, alpha.wounds, alpha.invulnerable) == (3, 4, 1, 5)

    assert [g.name for g in ranger.wargear] == ["Omnispex"]
    assert [a.name for a in ranger.wargear[0].abilities] == ["Ignore Cover (Unit)"]


async def test_seed_datasheets_is_idempotent(session: AsyncSession):
    await run_all(session)
    models_before = (await session.execute(select(Model.name))).scalars().all()
    weapons_before = (await session.execute(select(Weapon.model_id, Weapon.name))).all()

    await factions.seed_datasheets(session)

    models_after = (await session.execute(select(Model.name))).scalars().all()
    weapons_after = (await session.execute(select(Weapon.model_id, Weapon.name))).all()
    assert sorted(models_after) == sorted(models_before)
    assert models_after.count("Skitarii Ranger") == 1
    assert sorted(weapons_after) == sorted(weapons_before)


async def test_seed_datasheets_rejects_unknown_references(session: AsyncSession):
    # Without keywords/weapon abilities seeded, the datasheet's references
    # can't be resolved - that's an error rather than a silently bare model.
    await factions.seed(session)
    await factions.seed_abilities(session)

    with pytest.raises(ValueError, match="references unknown"):
        await factions.seed_datasheets(session)


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


async def test_seed_datasheets_adds_missing_weapons_and_wargear_to_existing_model(
    session: AsyncSession,
):
    # A Ranger seeded before the datasheet gained (say) its Omnispex, and
    # whose user-edited weapon must be left alone.
    await run_all(session)
    ranger = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.weapons), selectinload(Model.wargear))
            .where(Model.name == "Skitarii Ranger")
        )
    ).scalar_one()
    omnispex = ranger.wargear[0]
    arc_rifle = next(w for w in ranger.weapons if w.name == "Arc rifle")
    galvanic = next(w for w in ranger.weapons if w.name == "Galvanic rifle")
    ranger.wargear.remove(omnispex)
    ranger.weapons.remove(arc_rifle)
    await session.delete(omnispex)
    await session.delete(arc_rifle)
    galvanic.attacks = "3"  # a user edit
    await session.commit()

    await factions.seed_datasheets(session)

    session.expire_all()
    ranger = (
        await session.execute(
            select(Model)
            .options(selectinload(Model.weapons), selectinload(Model.wargear))
            .where(Model.name == "Skitarii Ranger")
        )
    ).scalar_one()
    weapons = {w.name: w for w in ranger.weapons}
    assert "Arc rifle" in weapons
    assert len(ranger.weapons) == 6
    assert weapons["Galvanic rifle"].attacks == "3"
    assert [g.name for g in ranger.wargear] == ["Omnispex"]


async def test_run_all_seeds_tankbustas(session: AsyncSession):
    await run_all(session)

    models = {
        m.name: m
        for m in (
            await session.execute(
                select(Model)
                .options(
                    selectinload(Model.keywords),
                    selectinload(Model.faction_abilities),
                    selectinload(Model.weapons).selectinload(Weapon.abilities),
                )
                .join(Faction)
                .where(Faction.name == "Orks", Model.name.in_(["Tankbusta", "Tankbusta Nob"]))
            )
        )
        .scalars()
        .all()
    }
    assert set(models) == {"Tankbusta", "Tankbusta Nob"}
    assert models["Tankbusta"].wounds == 2
    assert models["Tankbusta Nob"].wounds == 3
    for model in models.values():
        assert (model.toughness, model.save, model.leadership, model.oc) == (5, 4, 7, 1)
        assert [a.name for a in model.faction_abilities] == ["Waaagh!"]
        assert {k.name for k in model.keywords} == {"INFANTRY", "EXPLOSIVES"}

    tankbusta = {w.name: w for w in models["Tankbusta"].weapons}
    assert set(tankbusta) == {
        "Busta Rokkit Launcha - Standard",
        "Busta Rokkit Launcha - Hunter",
        "Gitstikka",
    }
    assert [a.name for a in tankbusta["Busta Rokkit Launcha - Hunter"].abilities] == [
        "Hunter: Monster/Vehicle"
    ]
    assert tankbusta["Busta Rokkit Launcha - Standard"].abilities == []

    nob = {w.name: w for w in models["Tankbusta Nob"].weapons}
    assert set(nob) == {
        "Choppa",
        "Rokkit Pistol",
        "Smash Hammer - Standard",
        "Smash Hammer - Hunter",
    }
    assert [a.name for a in nob["Rokkit Pistol"].abilities] == ["Close-Quarters"]
    assert nob["Smash Hammer - Hunter"].strength == 12


async def test_run_all_seeds_big_mek_dakkarig(session: AsyncSession):
    await run_all(session)

    dakkarig = (
        await session.execute(
            select(Model)
            .options(
                selectinload(Model.keywords),
                selectinload(Model.faction_abilities),
                selectinload(Model.weapons).selectinload(Weapon.abilities),
                selectinload(Model.abilities),
            )
            .where(Model.name == "Big Mek Dakkarig")
        )
    ).scalar_one()
    assert [a.name for a in dakkarig.abilities] == ["Even More Dakka"]
    assert (dakkarig.movement, dakkarig.toughness, dakkarig.save, dakkarig.wounds) == (8, 8, 3, 11)
    assert (dakkarig.leadership, dakkarig.oc, dakkarig.invulnerable) == (7, 3, 5)
    assert {k.name for k in dakkarig.keywords} == {"VEHICLE", "BIG MEK", "CHARACTER", "WALKER"}
    assert [a.name for a in dakkarig.faction_abilities] == ["Waaagh!"]

    weapons = {w.name: w for w in dakkarig.weapons}
    assert set(weapons) == {"Blitzkannon", "Multi-busta Launcha", "Stompy Feet"}
    assert {a.name for a in weapons["Blitzkannon"].abilities} == {
        "Ignores Cover",
        "Lethal Hits: non-Monster/Vehicle",
        "Blitz Dem Gitz!",
    }
    assert {a.name for a in weapons["Multi-busta Launcha"].abilities} == {
        "Ignores Cover",
        "Lethal Hits",
    }
    assert weapons["Multi-busta Launcha"].skill == 5


async def test_seed_datasheets_adds_missing_abilities_to_existing_model_and_weapons(
    session: AsyncSession,
):
    # A Dakkarig seeded before it had Even More Dakka / Blitz Dem Gitz!.
    await run_all(session)
    dakkarig = (
        await session.execute(
            select(Model)
            .options(
                selectinload(Model.abilities),
                selectinload(Model.weapons).selectinload(Weapon.abilities),
            )
            .where(Model.name == "Big Mek Dakkarig")
        )
    ).scalar_one()
    blitzkannon = next(w for w in dakkarig.weapons if w.name == "Blitzkannon")
    dakkarig.abilities = []
    blitzkannon.abilities = [a for a in blitzkannon.abilities if a.name != "Blitz Dem Gitz!"]
    await session.commit()

    await factions.seed_datasheets(session)

    session.expire_all()
    dakkarig = (
        await session.execute(
            select(Model)
            .options(
                selectinload(Model.abilities),
                selectinload(Model.weapons).selectinload(Weapon.abilities),
            )
            .where(Model.name == "Big Mek Dakkarig")
        )
    ).scalar_one()
    blitzkannon = next(w for w in dakkarig.weapons if w.name == "Blitzkannon")
    assert [a.name for a in dakkarig.abilities] == ["Even More Dakka"]
    assert "Blitz Dem Gitz!" in {a.name for a in blitzkannon.abilities}
    assert len(dakkarig.weapons) == 3


async def test_datasheet_ability_rules_belong_to_seeded_abilities():
    from app.combat_rules import CONDITIONS, EFFECTS

    seeded = {name for name, _, _, _ in datasheet_abilities.ENTRIES}
    assert set(datasheet_abilities.RULES) <= seeded
    for rules in datasheet_abilities.RULES.values():
        for rule in rules:
            assert set(rule.conditions) <= set(CONDITIONS)
            assert set(rule.effects) <= set(EFFECTS)


async def test_run_all_seeds_fulgurite_electro_priests(session: AsyncSession):
    await run_all(session)

    priest = (
        await session.execute(
            select(Model)
            .options(
                selectinload(Model.keywords),
                selectinload(Model.abilities),
                selectinload(Model.faction_abilities),
                selectinload(Model.weapons).selectinload(Weapon.abilities),
            )
            .where(Model.name == "Fulgurite Electro-priest")
        )
    ).scalar_one()
    assert (priest.movement, priest.toughness, priest.save, priest.wounds) == (6, 3, 7, 1)
    assert (priest.leadership, priest.oc) == (7, 1)
    assert (priest.invulnerable, priest.feel_no_pain) == (5, 5)
    assert {k.name for k in priest.keywords} == {
        "INFANTRY",
        "IMPERIUM",
        "CULT MECHANICUS",
        "ELECTRO-PRIESTS",
        "FULGURITE",
    }
    assert [a.name for a in priest.abilities] == ["Electro-infusion"]
    assert [a.name for a in priest.faction_abilities] == ["Doctrina Imperatives"]
    [stave] = priest.weapons
    assert (stave.name, stave.weapon_type, stave.attacks, stave.skill) == (
        "Electroleech stave",
        "melee",
        "2",
        3,
    )
    assert (stave.strength, stave.ap, stave.damage) == (6, -1, "2")
    assert [a.name for a in stave.abilities] == ["Devastating Wounds"]


async def test_seed_datasheets_adds_missing_faction_abilities_to_existing_model(
    session: AsyncSession,
):
    # Electro-priests seeded before they had Doctrina Imperatives.
    await run_all(session)
    load = (
        select(Model)
        .options(selectinload(Model.faction_abilities))
        .where(Model.name == "Fulgurite Electro-priest")
    )
    priest = (await session.execute(load)).scalar_one()
    priest.faction_abilities = []
    await session.commit()

    await factions.seed_datasheets(session)

    session.expire_all()
    priest = (await session.execute(load)).scalar_one()
    assert [a.name for a in priest.faction_abilities] == ["Doctrina Imperatives"]


async def test_run_all_seeds_tech_priest_dominus(session: AsyncSession):
    await run_all(session)

    dominus = (
        await session.execute(
            select(Model)
            .options(
                selectinload(Model.keywords),
                selectinload(Model.abilities),
                selectinload(Model.faction_abilities),
                selectinload(Model.weapons).selectinload(Weapon.abilities),
            )
            .where(Model.name == "Tech-priest Dominus")
        )
    ).scalar_one()
    assert (dominus.movement, dominus.toughness, dominus.save, dominus.wounds) == (6, 4, 2, 4)
    assert (dominus.leadership, dominus.oc, dominus.invulnerable) == (7, 1, 5)
    assert dominus.is_leader is True
    assert {k.name for k in dominus.keywords} == {
        "IMPERIUM",
        "INFANTRY",
        "CHARACTER",
        "CULT MECHANICUS",
        "TECH-PRIEST",
        "DOMINUS",
    }
    assert {a.name for a in dominus.abilities} == {"Lord of the Machine Cult", "Data-spike"}
    assert [a.name for a in dominus.faction_abilities] == ["Doctrina Imperatives"]

    weapons = {w.name: w for w in dominus.weapons}
    assert len(weapons) == 6
    assert weapons["Eradication ray – focused"].attacks == "D3"
    assert {a.name for a in weapons["Phosphor serpenta"].abilities} == {"Ignores Cover", "Pistol"}
    assert [a.name for a in weapons["Volkite blaster"].abilities] == ["Devastating Wounds"]
    assert weapons["Macrostubber pistol"].abilities == []
    assert weapons["Omnissian axe"].weapon_type == "melee"
