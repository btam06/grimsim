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
from app.schemas import CombatIn, CombatOut, WeaponCombatResultOut
from app.seeds import factions as faction_seeds
from app.services import combat as combat_service

router = APIRouter(prefix="/combat", tags=["combat"])


async def _load_unit(session: AsyncSession, unit_id: int) -> Unit | None:
    weapons_loader = selectinload(Unit.unit_models).selectinload(UnitModel.weapons)
    wargear_loader = selectinload(Unit.unit_models).selectinload(UnitModel.wargear)
    model_loader = selectinload(Unit.unit_models).selectinload(UnitModel.model)
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
            selectinload(Unit.army_list).selectinload(ArmyList.detachments),
        )
        .where(Unit.id == unit_id)
    )
    return result.scalar_one_or_none()


def _validate_rule_options(option_names: list[str], field: str) -> None:
    unknown = [name for name in option_names if name not in faction_seeds.OPTION_OWNERS]
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown {field}: {', '.join(unknown)}"
        )
    # Only one option per faction ability can be active at a time (e.g. not
    # both the Protector and Conqueror Imperatives).
    owners = [faction_seeds.OPTION_OWNERS[name] for name in set(option_names)]
    if len(owners) != len(set(owners)):
        raise HTTPException(
            status_code=400,
            detail=f"{field} has more than one option for the same faction ability",
        )


def _active_rules(unit: Unit, option_names: list[str]) -> list[Rule]:
    # A faction ability's options apply to the whole unit if any of its models
    # has that faction ability; options for abilities it lacks are ignored.
    held = {
        (faction_ability.faction.name, faction_ability.name)
        for unit_model in unit.unit_models
        for faction_ability in unit_model.model.faction_abilities
    }
    return [
        rule
        for faction_name, ability_name in held
        for option_name, rules in faction_seeds.rule_options(faction_name, ability_name).items()
        if option_name in option_names
        for rule in rules
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

    stratagems: list[Stratagem] = []
    if payload.stratagem_ids:
        result = await session.execute(
            select(Stratagem)
            .options(
                selectinload(Stratagem.detachments),
                selectinload(Stratagem.conditions),
                selectinload(Stratagem.effects),
            )
            .where(Stratagem.id.in_(payload.stratagem_ids))
        )
        stratagems = list(result.scalars().all())
        if len(stratagems) != len(set(payload.stratagem_ids)):
            raise HTTPException(status_code=400, detail="one or more stratagem_ids not found")

        # A stratagem is usable if it's core, or if it belongs to one of the
        # detachments the attacking unit's army list has taken.
        attacker_detachment_ids = (
            {d.id for d in attacker.army_list.detachments} if attacker.army_list else set()
        )
        for stratagem in stratagems:
            if stratagem.is_core:
                continue
            if not {d.id for d in stratagem.detachments} & attacker_detachment_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"stratagem '{stratagem.name}' is not available to the attacking "
                    "unit's detachments",
                )

    _validate_rule_options(payload.attacker_rule_options, "attacker_rule_options")
    _validate_rule_options(payload.defender_rule_options, "defender_rule_options")

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
        apply_precision=payload.apply_precision,
        attacker_rules=_active_rules(attacker, payload.attacker_rule_options),
        defender_rules=_active_rules(defender, payload.defender_rule_options),
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
        save_rolls=result.save_rolls,
        total_damage=result.total_damage,
        models_destroyed=result.models_destroyed,
        defending_models_remaining=result.defending_models_remaining,
        hazardous_rolls=result.hazardous_rolls,
        hazardous_wounds=result.hazardous_wounds,
        hazardous_models_destroyed=result.hazardous_models_destroyed,
        weapon_results=[
            WeaponCombatResultOut(
                name=wr.name,
                attack_rolls=wr.attack_rolls,
                attack_rerolls=wr.attack_rerolls,
                wound_rolls=wr.wound_rolls,
                save_rolls=wr.save_rolls,
                total_damage=wr.total_damage,
                models_destroyed=wr.models_destroyed,
                hazardous_rolls=wr.hazardous_rolls,
                hazardous_wounds=wr.hazardous_wounds,
            )
            for wr in result.weapon_results
        ],
    )
