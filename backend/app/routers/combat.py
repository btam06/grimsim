from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.combat_rules import Rule, RuleOption
from app.combat_rules.positions import ALWAYS_ASKED, POSITION_CONDITIONS, POSITIONS
from app.models import (
    ArmyList,
    DatasheetAbility,
    DetachmentRule,
    DetachmentRuleDatasheetAbility,
    DetachmentRuleWeaponAbility,
    Enhancement,
    EnhancementDatasheetAbility,
    EnhancementWeapon,
    EnhancementWeaponAbility,
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
from app.schemas import CombatIn, CombatOut, PositionOut, StratagemOut, WeaponCombatResultOut
from app.seeds import datasheet_abilities as datasheet_ability_seeds
from app.seeds import factions as faction_seeds
from app.seeds import stratagems as stratagem_seeds
from app.routers.stratagems import _to_out as stratagem_to_out
from app.services import combat as combat_service
from app.services import weapon_profiles
from app.services import stratagem_availability
from app.services.list_building import detachment_rules as detachment_rule_service
from app.services.list_building import enhancements as enhancement_rules

router = APIRouter(prefix="/combat", tags=["combat"])


async def _load_unit(session: AsyncSession, unit_id: int) -> Unit | None:
    weapons_loader = selectinload(Unit.unit_models).selectinload(UnitModel.weapons)
    wargear_loader = selectinload(Unit.unit_models).selectinload(UnitModel.wargear)
    model_loader = selectinload(Unit.unit_models).selectinload(UnitModel.model)
    list_units_loader = selectinload(Unit.army_list).selectinload(ArmyList.units)
    # Enhancements (on models) and upgrades (on the unit), with the abilities
    # they grant and those abilities' conditions/effects.
    enhancement_loaders = [
        loader
        for enhancements in (
            selectinload(Unit.unit_models).selectinload(UnitModel.enhancement),
            selectinload(Unit.upgrade),
        )
        for loader in (
            enhancements.selectinload(Enhancement.weapon_ability_grants)
            .selectinload(EnhancementWeaponAbility.weapon_ability)
            .selectinload(WeaponAbility.conditions),
            enhancements.selectinload(Enhancement.weapon_ability_grants)
            .selectinload(EnhancementWeaponAbility.weapon_ability)
            .selectinload(WeaponAbility.effects),
            enhancements.selectinload(Enhancement.datasheet_ability_grants)
            .selectinload(EnhancementDatasheetAbility.datasheet_ability)
            .selectinload(DatasheetAbility.conditions),
            enhancements.selectinload(Enhancement.datasheet_ability_grants)
            .selectinload(EnhancementDatasheetAbility.datasheet_ability)
            .selectinload(DatasheetAbility.effects),
            enhancements.selectinload(Enhancement.weapons)
            .selectinload(EnhancementWeapon.abilities)
            .selectinload(WeaponAbility.conditions),
            enhancements.selectinload(Enhancement.weapons)
            .selectinload(EnhancementWeapon.abilities)
            .selectinload(WeaponAbility.effects),
        )
    ]
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
            # ...and their models' keywords, to tell whether a model carrying
            # an enhancement there is leading its unit.
            list_units_loader.selectinload(Unit.unit_models)
            .selectinload(UnitModel.model)
            .selectinload(Model.keywords),
            *enhancement_loaders,
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
    # The unit's models' datasheet abilities, and any its enhancements or
    # upgrade grant it.
    return {
        ability.name for unit_model in unit.unit_models for ability in unit_model.model.abilities
    } | {ability.name for ability in enhancement_rules.granted_datasheet_abilities(unit)}


def _active_options(
    unit: Unit, option_names: list[str], detachment_rules: list[DetachmentRule] = ()
) -> tuple[set[str], list[Rule], set[str]]:
    # The selected options this unit actually gains, as (option names, their
    # rules, keywords they grant). Options for abilities it doesn't have
    # access to are ignored:
    # - a faction ability's options, if any of the unit's models has it;
    # - a datasheet ability's options, if any of the unit's models has it, or
    #   its enhancements or detachment rules grant it (e.g. Malefic Surge);
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

    take(
        _datasheet_ability_names(unit)
        | {
            ability.name
            for ability in detachment_rule_service.granted_datasheet_abilities(
                list(detachment_rules), unit
            )
        },
        army_wide_only=False,
    )
    if unit.army_list is not None:
        for other in unit.army_list.units:
            if other.id == unit.id:
                continue
            if other.faction_unit.faction_id != unit.faction_unit.faction_id:
                continue
            take(_datasheet_ability_names(other), army_wide_only=True)

    # Options that active ones make active too (e.g. The Fires of Mars: both
    # Doctrina Imperatives), applied as if they'd been picked.
    granted = [
        name
        for option_name in active
        for name in _datasheet_option(option_name).grants_options
        if name not in option_names
    ]
    if granted:
        return _active_options(unit, option_names + granted, detachment_rules)
    return active, rules, keywords


def _datasheet_option(option_name: str) -> RuleOption:
    # A datasheet ability's option by name (an empty one for a faction
    # ability's option, which grants no other options).
    ability = datasheet_ability_seeds.OPTION_OWNERS.get(option_name)
    if ability is None:
        return RuleOption()
    return datasheet_ability_seeds.OPTIONS[ability][option_name]


def _datasheet_rules(unit: Unit, detachment_rules: list[DetachmentRule]) -> list[Rule]:
    # Code-defined rules for the datasheet abilities any of the unit's models
    # has, or its detachment rules grant it (see app/seeds/datasheet_abilities.py
    # RULES), once per ability.
    names = _datasheet_ability_names(unit) | {
        ability.name
        for ability in detachment_rule_service.granted_datasheet_abilities(detachment_rules, unit)
    }
    return [
        rule for name in names for rule in datasheet_ability_seeds.RULES.get(name, [])
    ] + _army_rules(unit)


def _army_rules(unit: Unit) -> list[Rule]:
    # Rules the other units of the same faction in the unit's army list give it
    # through their datasheet abilities (see ARMY_RULES in
    # app/seeds/datasheet_abilities.py - e.g. Prophet of Destruction), once per
    # ability.
    if unit.army_list is None:
        return []
    names = {
        ability.name
        for other in unit.army_list.units
        if other.id != unit.id
        and other.faction_unit.faction_id == unit.faction_unit.faction_id
        for unit_model in other.unit_models
        for ability in unit_model.model.abilities
    }
    return [rule for name in names for rule in datasheet_ability_seeds.ARMY_RULES.get(name, [])]


async def _detachment_rules(session: AsyncSession, unit: Unit) -> list[DetachmentRule]:
    # The rules of the detachments the unit's army list has taken, with the
    # abilities they grant and those abilities' conditions/effects.
    if unit.army_list is None:
        return []
    detachment_ids = [d.id for d in unit.army_list.detachments]
    weapon = selectinload(DetachmentRule.weapon_ability_grants).selectinload(
        DetachmentRuleWeaponAbility.weapon_ability
    )
    datasheet = selectinload(DetachmentRule.datasheet_ability_grants).selectinload(
        DetachmentRuleDatasheetAbility.datasheet_ability
    )
    result = await session.execute(
        select(DetachmentRule)
        .options(
            weapon.selectinload(WeaponAbility.conditions),
            weapon.selectinload(WeaponAbility.effects),
            datasheet.selectinload(DatasheetAbility.conditions),
            datasheet.selectinload(DatasheetAbility.effects),
        )
        .where(DetachmentRule.detachment_id.in_(detachment_ids))
        .order_by(DetachmentRule.id)
    )
    return list(result.scalars().all())


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


def _stratagem_rules(stratagems: list[Stratagem], side: str) -> list[Rule]:
    # The code-defined rules of the stratagems used on one side's unit (e.g. a
    # Necrons stratagem's "if a CHARACTER is leading your unit" tier) that
    # apply to that side.
    return [
        rule
        for stratagem in stratagems
        for rule in stratagem_seeds.rules(stratagem.name)
        if rule.side == side
    ]


def _granted_options(stratagems: list[Stratagem]) -> list[str]:
    # The rule options the stratagems used on one side's unit make active.
    return [option for s in stratagems for option in stratagem_seeds.granted_options(s.name)]


def _possible_rules(unit: Unit, detachment_rules: list[DetachmentRule]) -> list[Rule]:
    # Every code-defined rule the unit could have in play: its datasheet
    # abilities' rules (including those its enhancements and detachment rules
    # grant), and all the options of its faction and datasheet abilities
    # (whichever is picked) - plus those datasheet abilities' own conditions,
    # as attacker rules.
    all_options = list(faction_seeds.OPTION_OWNERS) + [
        name for options in datasheet_ability_seeds.OPTIONS.values() for name in options
    ]
    _, option_rules, _ = _active_options(unit, all_options, detachment_rules)
    abilities = (
        [ability for unit_model in unit.unit_models for ability in unit_model.model.abilities]
        + enhancement_rules.granted_datasheet_abilities(unit)
        + detachment_rule_service.granted_datasheet_abilities(detachment_rules, unit)
    )
    ability_rules = [
        Rule(conditions=tuple(c.keyword for c in ability.conditions), effects=())
        for ability in abilities
    ]
    return option_rules + _datasheet_rules(unit, detachment_rules) + ability_rules


@router.get("/granted-abilities", response_model=list[int])
async def granted_abilities(unit_id: int, session: AsyncSession = Depends(get_session)):
    # The ids of the datasheet abilities a unit gains from its enhancements and
    # the detachment rules of its army list (beyond its models' own) - so the
    # calculator can offer their options (e.g. Malefic Surge's).
    unit = await _load_unit(session, unit_id)
    if unit is None:
        raise HTTPException(status_code=400, detail="invalid unit_id")
    abilities = enhancement_rules.granted_datasheet_abilities(
        unit
    ) + detachment_rule_service.granted_datasheet_abilities(
        await _detachment_rules(session, unit), unit
    )
    return sorted({ability.id for ability in abilities})


@router.get("/positions", response_model=list[PositionOut])
async def relevant_positions(
    unit_id: int,
    side: stratagem_availability.Side,
    session: AsyncSession = Depends(get_session),
):
    # The positions worth asking about for a unit as the attacker or the
    # defender: those read by a rule it could have in play on that side (e.g.
    # Doctrina Imperatives or Breaching Command: within 6" of a friendly
    # ADEPTUS MECHANICUS BATTLELINE unit).
    unit = await _load_unit(session, unit_id)
    if unit is None:
        raise HTTPException(status_code=400, detail="invalid unit_id")
    conditions = {
        condition
        for rule in _possible_rules(unit, await _detachment_rules(session, unit))
        if rule.side == side
        for condition in rule.conditions
    }
    return [
        PositionOut(id=position, label=label)
        for position, label in POSITIONS.items()
        if side in ALWAYS_ASKED.get(position, set())
        or POSITION_CONDITIONS[position][side] & conditions
    ]


@router.post("", response_model=CombatOut)
async def run_combat(payload: CombatIn, session: AsyncSession = Depends(get_session)):
    return await calculate(session, payload)


async def calculate(
    session: AsyncSession,
    payload: CombatIn,
    firing: dict[int, dict] | None = None,
    defender_wounds: dict[int, int] | None = None,
    attacker_wounds: dict[int, int] | None = None,
) -> CombatOut:
    # Resolves an attack (see app/services/combat.py). `firing` is which
    # weapons each attacking model can fire and at half range or not, when
    # that's known from the battlefield (see app/services/in_game/shooting.py); the
    # wounds are each model's left in a game (see app/services/in_game/casualties.py).
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
    # Only one profile of a weapon with several (e.g. standard or supercharge).
    conflict = weapon_profiles.unit_conflict(attacker, set(payload.selected_weapon_ids))
    if conflict is not None:
        raise HTTPException(status_code=400, detail=conflict)
    attacker_enhancement_weapon_ids = {
        weapon.id
        for unit_model in attacker.unit_models
        if unit_model.enhancement is not None
        for weapon in unit_model.enhancement.weapons
    }
    if not set(payload.selected_enhancement_weapon_ids) <= attacker_enhancement_weapon_ids:
        raise HTTPException(
            status_code=400,
            detail="one or more selected_enhancement_weapon_ids aren't the attacking unit's",
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
    for field in ("attacker_positions", "defender_positions"):
        unknown = sorted(set(getattr(payload, field)) - set(POSITIONS))
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown {field}: {', '.join(unknown)}")

    attacker_detachment_rules = await _detachment_rules(session, attacker)
    defender_detachment_rules = await _detachment_rules(session, defender)

    # Options picked under Faction Rules, plus any a stratagem used on that
    # side makes active (e.g. Transcendent Cogitation: both Imperatives).
    attacker_options, attacker_option_rules, attacker_extra_keywords = _active_options(
        attacker,
        payload.attacker_rule_options + _granted_options(stratagems),
        attacker_detachment_rules,
    )
    defender_options, defender_option_rules, defender_extra_keywords = _active_options(
        defender,
        payload.defender_rule_options + _granted_options(defender_stratagems),
        defender_detachment_rules,
    )

    visible = True if payload.game_id is None else payload.defender_visible
    in_range = True if payload.game_id is None else payload.defender_in_range

    result = combat_service.resolve_combat(
        attacker=attacker,
        defender=defender,
        selected_weapon_ids=set(payload.selected_weapon_ids)
        | {("enhancement", i) for i in payload.selected_enhancement_weapon_ids},
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
        attacker_rules=attacker_option_rules
        + _datasheet_rules(attacker, attacker_detachment_rules)
        + _stratagem_rules(stratagems, "attacker"),
        defender_rules=defender_option_rules
        + _datasheet_rules(defender, defender_detachment_rules)
        + _stratagem_rules(defender_stratagems, "defender"),
        attacker_options=attacker_options,
        attacker_extra_keywords=attacker_extra_keywords,
        defender_extra_keywords=defender_extra_keywords,
        attacker_detachment_rules=attacker_detachment_rules,
        defender_detachment_rules=defender_detachment_rules,
        ability_rules=datasheet_ability_seeds.RULES,
        attacker_positions=set(payload.attacker_positions),
        defender_positions=set(payload.defender_positions),
        charged=payload.charged,
        defender_battle_shocked=payload.defender_battle_shocked,
        attacker_damaged=payload.attacker_damaged,
        firing=firing,
        defender_wounds=defender_wounds,
        attacker_wounds=attacker_wounds,
        snap_shots=payload.snap_shots,
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
                damage=wr.damage,
                attack_rolls=wr.attack_rolls,
                attack_rerolls=wr.attack_rerolls,
                wound_rolls=wr.wound_rolls,
                wound_rerolls=wr.wound_rerolls,
                save_rolls=wr.save_rolls,
                fnp_rolls=wr.fnp_rolls,
                damage_rolls=wr.damage_rolls,
                total_damage=wr.total_damage,
                models_destroyed=wr.models_destroyed,
                hazardous_rolls=wr.hazardous_rolls,
                hazardous_wounds=wr.hazardous_wounds,
            )
            for wr in result.weapon_results
        ],
        defender_wounds_remaining=result.defender_wounds_remaining,
        attacker_damage=result.attacker_damage,
    )
