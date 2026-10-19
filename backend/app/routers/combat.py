from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.combat_rules import Rule
from app.models import (
    ArmyList,
    DatasheetAbility,
    FactionAbility,
    Model,
    Stratagem,
    Unit,
    UnitModel,
    Wargear,
    WargearAbility,
    Weapon,
    WeaponAbility,
)
from app.schemas import CombatIn, CombatOut, StratagemOut, WeaponCombatResultOut
from app.seeds import datasheet_abilities as datasheet_ability_seeds
from app.seeds import factions as faction_seeds
from app.routers.stratagems import _to_out as stratagem_to_out
from app.services import combat as combat_service
from app.services import stratagem_availability

router = APIRouter(prefix="/combat", tags=["combat"])


async def _load_unit(session: AsyncSession, unit_id: int) -> Unit | None:
    weapons_loader = selectinload(Unit.unit_models).selectinload(UnitModel.weapons)
    wargear_loader = selectinload(Unit.unit_models).selectinload(UnitModel.wargear)
    model_loader = selectinload(Unit.unit_models).selectinload(UnitModel.model)
    list_units_loader = selectinload(Unit.army_list).selectinload(ArmyList.units)
    result = await session.execute(
        select(Unit)
        .options(
            weapons_loader,
            weapons_loader.selectinload(Weapon.abilities).selectinload(
                WeaponAbility.conditions
            ),
            weapons_loader.selectinload(Weapon.abilities).selectinload(WeaponAbility.effects),
            wargear_loader,
            wargear_loader.selectinload(Wargear.abilities).selectinload(
                WargearAbility.conditions
            ),
            wargear_loader.selectinload(Wargear.abilities).selectinload(
                WargearAbility.effects
            ),
            model_loader,
            model_loader.selectinload(Model.keywords),
            model_loader.selectinload(Model.abilities).selectinload(
                DatasheetAbility.conditions
            ),
            model_loader.selectinload(Model.abilities).selectinload(DatasheetAbility.effects),
            model_loader.selectinload(Model.faction_abilities).selectinload(
                FactionAbility.faction
            ),
            selectinload(Unit.faction_unit),
            selectinload(Unit.army_list).selectinload(ArmyList.detachments),
            # The rest of the army list, for army-wide rule options (e.g. a
            # Canticle from Belisarius Cawl elsewhere in the list).
            list_units_loader.selectinload(Unit.faction_unit),
            list_units_loader.selectinload(Unit.unit_models)
            .selectinload(UnitModel.model)
            .selectinload(Model.abilities),
        )
        .where(Unit.id == unit_id)
    )
    return result.scalar_one_or_none()


def _option_owner(option_name: str):
    # The ability an option belongs to - a faction ability's (faction name,
    # ability name), or a datasheet ability's name - or None if unknown.
    return faction_seeds.OPTION_OWNERS.get(
        option_name
    ) or datasheet_ability_seeds.OPTION_OWNERS.get(option_name)


def _validate_rule_options(option_names: list[str], field: str) -> None:
    unknown = [name for name in option_names if _option_owner(name) is None]
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown {field}: {', '.join(unknown)}"
        )
    # Only one option per ability can be active at a time (e.g. not both the
    # Protector and Conqueror Imperatives).
    owners = [_option_owner(name) for name in set(option_names)]
    if len(owners) != len(set(owners)):
        raise HTTPException(
            status_code=400,
            detail=f"{field} has more than one option for the same ability",
        )


def _datasheet_ability_names(unit: Unit) -> set[str]:
    return {
        ability.name for unit_model in unit.unit_models for ability in unit_model.model.abilities
    }


def _active_options(
    unit: Unit, option_names: list[str]
) -> tuple[set[str], list[Rule], set[str]]:
    # The selected options this unit actually gains, as (option names, their
    # rules, keywords they grant). Options for abilities it doesn't have
    # access to are ignored:
    # - a faction ability's options, if any of the unit's models has it;
    # - a datasheet ability's options, if any of the unit's models has it;
    # - a datasheet ability's army-wide options, if a model with it is in
    #   another unit of the same faction in this unit's army list.
    active: set[str] = set()
    rules: list[Rule] = []
    keywords: set[str] = set()

    held_faction_abilities = {
        (faction_ability.faction.name, faction_ability.name)
        for unit_model in unit.unit_models
        for faction_ability in unit_model.model.faction_abilities
    }
    for faction_name, ability_name in held_faction_abilities:
        for option_name, option_rules in faction_seeds.rule_options(
            faction_name, ability_name
        ).items():
            if option_name in option_names:
                active.add(option_name)
                rules.extend(option_rules)

    def take(ability_names: set[str], army_wide_only: bool) -> None:
        for ability_name in ability_names:
            for option_name, option in datasheet_ability_seeds.OPTIONS.get(
                ability_name, {}
            ).items():
                if option_name not in option_names or option_name in active:
                    continue
                if army_wide_only and not option.army_wide:
                    continue
                active.add(option_name)
                rules.extend(option.rules)
                if not army_wide_only:
                    keywords.update(option.keywords)

    take(_datasheet_ability_names(unit), army_wide_only=False)
    if unit.army_list is not None:
        for other in unit.army_list.units:
            if other.id == unit.id:
                continue
            if other.faction_unit.faction_id != unit.faction_unit.faction_id:
                continue
            take(_datasheet_ability_names(other), army_wide_only=True)

    return active, rules, keywords


def _datasheet_rules(unit: Unit) -> list[Rule]:
    # Code-defined rules for the datasheet abilities any of the unit's models
    # has (see app/seeds/datasheet_abilities.py RULES), once per ability.
    return [
        rule
        for name in _datasheet_ability_names(unit)
        for rule in datasheet_ability_seeds.RULES.get(name, [])
    ]


async def _load_stratagems(session: AsyncSession, ids: list[int] | None = None) -> list[Stratagem]:
    query = select(Stratagem).options(
        selectinload(Stratagem.detachments),
        selectinload(Stratagem.conditions),
        selectinload(Stratagem.effects),
        selectinload(Stratagem.keywords),
        selectinload(Stratagem.timings),
        selectinload(Stratagem.game_action_link),
    )
    if ids is not None:
        query = query.where(Stratagem.id.in_(ids))
    return list((await session.execute(query.order_by(Stratagem.id))).scalars().all())


async def _usable_stratagems(
    session: AsyncSession,
    ids: list[int],
    unit: Unit,
    side: stratagem_availability.Side,
    phase: str,
) -> list[Stratagem]:
    # The requested stratagems for one side, each checked as usable on that
    # side's unit in this phase.
    if not ids:
        return []
    stratagems = await _load_stratagems(session, ids)
    if len(stratagems) != len(set(ids)):
        raise HTTPException(status_code=400, detail=f"one or more {side} stratagems not found")
    for stratagem in stratagems:
        reason = stratagem_availability.unavailable_reason(stratagem, unit, side, phase)
        if reason is not None:
            raise HTTPException(status_code=400, detail=f"stratagem '{stratagem.name}' {reason}")
    return stratagems


@router.get("/stratagems", response_model=list[StratagemOut])
async def available_stratagems(
    unit_id: int,
    side: stratagem_availability.Side,
    in_engagement_range: bool = False,
    session: AsyncSession = Depends(get_session),
):
    # The stratagems usable on a unit as the attacker or the defender, in the
    # shooting phase (ranged) or the fight phase (in engagement range).
    unit = await _load_unit(session, unit_id)
    if unit is None:
        raise HTTPException(status_code=400, detail="invalid unit_id")
    phase = stratagem_availability.calculator_phase(in_engagement_range)
    return [
        stratagem_to_out(stratagem)
        for stratagem in await _load_stratagems(session)
        if stratagem_availability.unavailable_reason(stratagem, unit, side, phase) is None
    ]


@router.post("", response_model=CombatOut)
async def run_combat(payload: CombatIn, session: AsyncSession = Depends(get_session)):
    attacker = await _load_unit(session, payload.attacking_unit_id)
    if attacker is None:
        raise HTTPException(status_code=400, detail="invalid attacking_unit_id")

    defender = await _load_unit(session, payload.defending_unit_id)
    if defender is None:
        raise HTTPException(status_code=400, detail="invalid defending_unit_id")

    attacker_weapon_ids = {
        weapon.id for unit_model in attacker.unit_models for weapon in unit_model.weapons
    }
    if not set(payload.selected_weapon_ids) <= attacker_weapon_ids:
        raise HTTPException(
            status_code=400,
            detail="one or more selected_weapon_ids are not equipped by the attacking unit",
        )

    phase = stratagem_availability.calculator_phase(payload.in_engagement_range)
    stratagems = await _usable_stratagems(
        session, payload.stratagem_ids, attacker, "attacker", phase
    )
    defender_stratagems = await _usable_stratagems(
        session, payload.defender_stratagem_ids, defender, "defender", phase
    )

    _validate_rule_options(payload.attacker_rule_options, "attacker_rule_options")
    _validate_rule_options(payload.defender_rule_options, "defender_rule_options")

    attacker_options, attacker_option_rules, attacker_extra_keywords = _active_options(
        attacker, payload.attacker_rule_options
    )
    defender_options, defender_option_rules, defender_extra_keywords = _active_options(
        defender, payload.defender_rule_options
    )

    visible = True if payload.game_id is None else payload.defender_visible
    in_range = True if payload.game_id is None else payload.defender_in_range

    result = combat_service.resolve_combat(
        attacker=attacker,
        defender=defender,
        selected_weapon_ids=set(payload.selected_weapon_ids),
        in_engagement_range=payload.in_engagement_range,
        visible=visible,
        in_range=in_range,
        in_cover=payload.in_cover,
        half_range=payload.half_range,
        moved_less_than_3=payload.moved_less_than_3,
        advanced=payload.advanced,
        stratagems=stratagems,
        defender_stratagems=defender_stratagems,
        apply_precision=payload.apply_precision,
        attacker_rules=attacker_option_rules + _datasheet_rules(attacker),
        defender_rules=defender_option_rules + _datasheet_rules(defender),
        attacker_options=attacker_options,
        attacker_extra_keywords=attacker_extra_keywords,
        defender_extra_keywords=defender_extra_keywords,
    )

    return CombatOut(
        visible=visible,
        in_range=in_range,
        in_engagement_range=payload.in_engagement_range,
        in_cover=payload.in_cover,
        half_range=payload.half_range,
        moved_less_than_3=payload.moved_less_than_3,
        advanced=payload.advanced,
        attack_rolls=result.attack_rolls,
        attack_rerolls=result.attack_rerolls,
        wound_rolls=result.wound_rolls,
        wound_rerolls=result.wound_rerolls,
        save_rolls=result.save_rolls,
        fnp_rolls=result.fnp_rolls,
        total_damage=result.total_damage,
        models_destroyed=result.models_destroyed,
        defending_models_remaining=result.defending_models_remaining,
        hazardous_rolls=result.hazardous_rolls,
        hazardous_wounds=result.hazardous_wounds,
        hazardous_models_destroyed=result.hazardous_models_destroyed,
        deadly_demise_rolls=result.deadly_demise_rolls,
        deadly_demise_explosions=result.deadly_demise_explosions,
        weapon_results=[
            WeaponCombatResultOut(
                name=wr.name,
                attack_rolls=wr.attack_rolls,
                attack_rerolls=wr.attack_rerolls,
                wound_rolls=wr.wound_rolls,
                wound_rerolls=wr.wound_rerolls,
                save_rolls=wr.save_rolls,
                fnp_rolls=wr.fnp_rolls,
                total_damage=wr.total_damage,
                models_destroyed=wr.models_destroyed,
                hazardous_rolls=wr.hazardous_rolls,
                hazardous_wounds=wr.hazardous_wounds,
            )
            for wr in result.weapon_results
        ],
    )
