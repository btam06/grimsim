from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.combat_rules.effects import ASSAULT
from app.engine.catalog import Catalog
from app.models import (
    ArmyList,
    DatasheetAbility,
    Detachment,
    DetachmentRule,
    DetachmentRuleDatasheetAbility,
    DetachmentRuleWeaponAbility,
    Disposition,
    Effect,
    Enhancement,
    EnhancementDatasheetAbility,
    EnhancementWeapon,
    EnhancementWeaponAbility,
    FactionAbility,
    Model,
    PrimaryMission,
    SecondaryMission,
    Stratagem,
    TerrainLayout,
    Unit,
    UnitModel,
    User,
    Wargear,
    WargearAbility,
    Weapon,
    WeaponAbility,
)
from app.models.base import is_loaded

# A new game's catalog (see app/engine/catalog.py), read from the database:
# everything its game code reads while it's played - the two armies as the
# game and the calculator see them, every stratagem, the tactical secondary
# deck, the players' missions and the terrain - so it needn't go back.


def _army_options():
    units = selectinload(ArmyList.units)
    unit_models = units.selectinload(Unit.unit_models)
    model = unit_models.selectinload(UnitModel.model)
    weapons = unit_models.selectinload(UnitModel.weapons).selectinload(Weapon.abilities)
    wargear = unit_models.selectinload(UnitModel.wargear).selectinload(Wargear.abilities)
    options = [
        selectinload(ArmyList.faction),
        selectinload(ArmyList.owner),
        selectinload(ArmyList.detachments).selectinload(Detachment.dispositions),
        selectinload(ArmyList.detachments).selectinload(Detachment.faction),
        units.selectinload(Unit.faction_unit),
        model.selectinload(Model.keywords),
        model.selectinload(Model.faction),
        model.selectinload(Model.abilities).selectinload(DatasheetAbility.conditions),
        model.selectinload(Model.abilities).selectinload(DatasheetAbility.effects),
        model.selectinload(Model.faction_abilities).selectinload(FactionAbility.faction),
        weapons.selectinload(WeaponAbility.conditions),
        weapons.selectinload(WeaponAbility.effects),
        wargear.selectinload(WargearAbility.conditions),
        wargear.selectinload(WargearAbility.effects),
    ]
    # Enhancements (on models) and upgrades (on units), with the abilities and
    # weapons they grant.
    for enhancements in (
        unit_models.selectinload(UnitModel.enhancement),
        units.selectinload(Unit.upgrade),
    ):
        weapon_grants = enhancements.selectinload(
            Enhancement.weapon_ability_grants
        ).selectinload(EnhancementWeaponAbility.weapon_ability)
        datasheet_grants = enhancements.selectinload(
            Enhancement.datasheet_ability_grants
        ).selectinload(EnhancementDatasheetAbility.datasheet_ability)
        enhancement_weapons = enhancements.selectinload(Enhancement.weapons).selectinload(
            EnhancementWeapon.abilities
        )
        options += [
            enhancements.selectinload(Enhancement.detachment),
            weapon_grants.selectinload(WeaponAbility.conditions),
            weapon_grants.selectinload(WeaponAbility.effects),
            datasheet_grants.selectinload(DatasheetAbility.conditions),
            datasheet_grants.selectinload(DatasheetAbility.effects),
            enhancement_weapons.selectinload(WeaponAbility.conditions),
            enhancement_weapons.selectinload(WeaponAbility.effects),
        ]
    return options


def _detachment_rule_options():
    weapon = selectinload(DetachmentRule.weapon_ability_grants).selectinload(
        DetachmentRuleWeaponAbility.weapon_ability
    )
    datasheet = selectinload(DetachmentRule.datasheet_ability_grants).selectinload(
        DetachmentRuleDatasheetAbility.datasheet_ability
    )
    return [
        weapon.selectinload(WeaponAbility.conditions),
        weapon.selectinload(WeaponAbility.effects),
        datasheet.selectinload(DatasheetAbility.conditions),
        datasheet.selectinload(DatasheetAbility.effects),
    ]


def _stratagem_options():
    return [
        selectinload(Stratagem.detachments),
        selectinload(Stratagem.conditions),
        selectinload(Stratagem.effects),
        selectinload(Stratagem.keywords),
        selectinload(Stratagem.excluded_keywords),
        selectinload(Stratagem.keyword_option_links),
        selectinload(Stratagem.timings),
        selectinload(Stratagem.game_action_link),
    ]


async def load(
    session: AsyncSession,
    list_ids: list[int],
    user_ids: list[int],
    disposition_ids: list[int],
    primary_mission_ids: list[int],
    layout: TerrainLayout | None,
) -> Catalog:
    catalog = Catalog()

    async def rows(query):
        return list((await session.execute(query)).scalars().unique())

    lists = await rows(select(ArmyList).options(*_army_options()).where(ArmyList.id.in_(list_ids)))
    for army_list in lists:
        # Each unit's list, as loaded (so units of the same datasheet in it
        # can be numbered - see Unit.label).
        for unit in army_list.units:
            if not is_loaded(unit, "army_list") or unit.army_list is not army_list:
                set_committed_value(unit, "army_list", army_list)
        attach_leaders(catalog, catalog.add(army_list))
    detachment_ids = [d.id for army_list in lists for d in army_list.detachments]
    for rule in await rows(
        select(DetachmentRule)
        .options(*_detachment_rule_options())
        .where(DetachmentRule.detachment_id.in_(detachment_ids))
        .order_by(DetachmentRule.id)
    ):
        catalog.add(rule)
    for user in await rows(select(User).where(User.id.in_(user_ids))):
        catalog.add(user)
    for disposition in await rows(
        select(Disposition)
        .options(selectinload(Disposition.detachments))
        .where(Disposition.id.in_(disposition_ids))
    ):
        catalog.add(disposition)
    for mission in await rows(
        select(PrimaryMission)
        .options(
            selectinload(PrimaryMission.player_disposition),
            selectinload(PrimaryMission.opponent_disposition),
        )
        .where(PrimaryMission.id.in_(primary_mission_ids))
    ):
        catalog.add(mission)
    for mission in await rows(select(SecondaryMission).order_by(SecondaryMission.id)):
        catalog.add(mission)
    for stratagem in await rows(
        select(Stratagem).options(*_stratagem_options()).order_by(Stratagem.id)
    ):
        catalog.add(stratagem)
    # The weapon abilities that give a weapon Assault (see
    # app/services/in_game/shooting.py).
    for ability in await rows(
        select(WeaponAbility)
        .options(selectinload(WeaponAbility.effects), selectinload(WeaponAbility.conditions))
        .join(WeaponAbility.effects)
        .where(Effect.keyword == ASSAULT)
    ):
        catalog.add(ability)
    if layout is not None:
        catalog.add(layout)
    return catalog


def attach_leaders(catalog: Catalog, army_list) -> None:
    # Each leader or support unit attached to a bodyguard unit (Unit.
    # attached_to_id) and that unit as one, as the game plays them - an
    # attached unit "is a single unit for all rules purposes" (Core Rules
    # 19.01) - see merge. The attached units leave the list (and the
    # catalog). Only the game's copies change.
    units = {u.id: u for u in army_list.units}
    for unit in army_list.units:
        mark_own(unit)
    merged = []
    for unit in army_list.units:
        target = units.get(unit.__dict__.get("attached_to_id"))
        if target is None or target is unit:
            continue
        merge(target, unit, army_list)
        merged.append(unit)
    if merged:
        army_list.__dict__["units"] = [u for u in army_list.units if u not in merged]
        table = catalog.rows.get("Unit", {})
        for unit in merged:
            table.pop((unit.id,), None)


def mark_own(unit) -> None:
    # Its models as its own (`led_from` None - see merge).
    for unit_model in unit.unit_models:
        unit_model.__dict__.setdefault("led_from", None)


def merge(target, unit, army_list=None) -> None:
    # A leader or support unit's mirror merged into its bodyguard unit's: the
    # bodyguard unit (its id, its label) with the attached unit's models,
    # points and detachment rule selections too, and the list's Warlord there
    # if it was the attached unit. Each model is marked with the unit it came
    # from - `led_from`: the attached unit's id (the bodyguard's own: None) -
    # and the bodyguard unit given the attached unit's upgrade
    # (`attached_upgrades`, with `attached_upgrade_units` its unit's id), for
    # what applies while they last (Core Rules 19.04 - see
    # app/services/list_building/enhancements.py).
    for unit_model in unit.unit_models:
        unit_model.__dict__["unit_id"] = target.id
        unit_model.__dict__["led_from"] = unit.id
        if "unit" in unit_model.__dict__:
            unit_model.__dict__["unit"] = target
    upgrade = unit.__dict__.get("upgrade")
    if upgrade is not None:
        target.__dict__["attached_upgrades"] = [*target.__dict__.get("attached_upgrades", []), upgrade]
        target.__dict__["attached_upgrade_units"] = [
            *target.__dict__.get("attached_upgrade_units", []), unit.id
        ]
    target.__dict__["unit_models"] = [*target.unit_models, *unit.unit_models]
    target.__dict__["points"] = target.points + unit.points
    if "rule_selection_links" in unit.__dict__:
        target.__dict__["rule_selection_links"] = [
            *target.__dict__.get("rule_selection_links", []), *unit.rule_selection_links
        ]
    warlord = army_list.__dict__.get("warlord_link") if army_list is not None else None
    if warlord is not None and warlord.unit_id == unit.id:
        warlord.__dict__["unit_id"] = target.id


async def reload(session: AsyncSession, live) -> None:
    # The game's catalog read again from the database (e.g. after the rows
    # it copied have changed), what it refers to pointed at the new copies.
    game = live.game
    layout_id = game.layout_link.layout_id if game.layout_link else None
    layout = (
        (
            await session.execute(select(TerrainLayout).where(TerrainLayout.id == layout_id))
        ).scalar_one_or_none()
        if layout_id is not None
        else None
    )
    catalog = await load(
        session,
        list_ids=[p.list_id for p in game.players],
        user_ids=[p.user_id for p in game.players],
        disposition_ids=[p.disposition_id for p in game.players if p.disposition_id is not None],
        primary_mission_ids=[
            p.primary_mission_id for p in game.players if p.primary_mission_id is not None
        ],
        layout=layout,
    )
    # (Units split in the game made again - see
    # app/services/in_game/unit_splits.py.)
    from app.services.in_game import unit_splits

    unit_splits.sync(game, catalog)
    for record in game.records():
        for attr, (id_attr, class_name) in record._refs.items():
            ref_id = getattr(record, id_attr)
            if ref_id is not None:
                object.__setattr__(record, attr, catalog.get(class_name, ref_id))
    live.catalog = catalog
    live.stale = False
