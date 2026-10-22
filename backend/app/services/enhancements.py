from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import delete, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DatasheetAbility,
    Enhancement,
    EnhancementDatasheetAbility,
    EnhancementKeyword,
    EnhancementWeapon,
    EnhancementWeaponAbility,
    Model,
    Unit,
    UnitModel,
    WeaponAbility,
    enhancement_excluded_keywords,
    enhancement_keywords,
    enhancement_weapon_ability_links,
    unit_model_enhancements,
    unit_upgrades,
)

# Which models and units can take an enhancement or upgrade. Shared by the
# endpoints that offer them and the unit endpoints that validate them, so the
# two can't disagree.


def _keyword_names(model: Model) -> set[str]:
    return {k.name for k in model.keywords}


def _keyword_reason(enhancement: Enhancement, keyword_names: set[str], what: str) -> str | None:
    missing = {k.name for k in enhancement.keywords} - keyword_names
    if missing:
        return f"needs {what} with {', '.join(sorted(missing))}"
    excluded = {k.name for k in enhancement.excluded_keywords} & keyword_names
    if excluded:
        return f"can't go on {what} with {', '.join(sorted(excluded))}"
    return None


def _detachment_reason(enhancement: Enhancement, detachment_ids: set[int]) -> str | None:
    if enhancement.detachment_id not in detachment_ids:
        return "is from a detachment the unit's list hasn't taken"
    return None


def model_unavailable_reason(
    enhancement: Enhancement,
    model: Model,
    detachment_ids: set[int],
    granted: set[str] = frozenset(),
) -> str | None:
    # Why a model can't carry this enhancement, or None if it can: it must be
    # an enhancement (not an upgrade) from one of the list's detachments, and
    # the model a CHARACTER (but not an EPIC HERO) meeting its keywords -
    # counting any `granted` it (e.g. by a detachment rule). Needs the model's
    # keywords loaded.
    if enhancement.kind != "enhancement":
        return "is an upgrade, which is taken by a unit, not a model"
    names = _keyword_names(model) | set(granted)
    if "CHARACTER" not in names:
        return "can only be carried by a CHARACTER"
    if "EPIC HERO" in names:
        return "can't be carried by an EPIC HERO"
    return _detachment_reason(enhancement, detachment_ids) or _keyword_reason(
        enhancement, names, "a model"
    )


def unit_unavailable_reason(
    upgrade: Enhancement,
    models: Iterable[Model],
    detachment_ids: set[int],
    granted: list[set[str]] | None = None,
) -> str | None:
    # Why a unit made of these models can't take this upgrade, or None if it
    # can: it must be an upgrade from one of the list's detachments, and every
    # model in the unit must meet its keywords. Needs the models' keywords
    # loaded.
    if upgrade.kind != "upgrade":
        return "is an enhancement, which is carried by a model, not a unit"
    models = list(models)
    if not models:
        return "needs a unit with at least one model"
    reason = _detachment_reason(upgrade, detachment_ids)
    if reason:
        return reason
    granted = granted or [set() for _ in models]
    for model, extra in zip(models, granted):
        reason = _keyword_reason(upgrade, _keyword_names(model) | extra, "a unit")
        if reason:
            return reason
    return None


# --- what they grant in combat ---


def is_leading(unit: Unit, unit_model: UnitModel) -> bool:
    # Whether a model is leading its unit: it's a CHARACTER in a unit that has
    # at least one non-CHARACTER model (the same approximation of leader
    # attachment the combat conditions use).
    return "CHARACTER" in _keyword_names(unit_model.model) and any(
        "CHARACTER" not in _keyword_names(other.model) for other in unit.unit_models
    )


def _grants_reaching(unit: Unit, unit_model: UnitModel | None, grants_of) -> list:
    # The grants from the unit's enhancements and upgrade that apply to
    # `unit_model` (or, if None, to the unit as a whole - bearer grants count
    # for the unit the bearer is in).
    reaching = []
    for carrier in unit.unit_models:
        enhancement = carrier.enhancement
        if enhancement is None:
            continue
        for grant in grants_of(enhancement):
            if grant.scope == "bearer" and (unit_model is None or carrier is unit_model):
                reaching.append(grant)
            elif grant.scope == "led_unit" and is_leading(unit, carrier):
                reaching.append(grant)
            elif grant.scope == "bearers_unit":
                reaching.append(grant)
    if unit.upgrade is not None:
        reaching += [g for g in grants_of(unit.upgrade) if g.scope == "unit"]
    return reaching


def granted_weapon_abilities(
    unit: Unit, unit_model: UnitModel
) -> list[tuple[WeaponAbility, str | None]]:
    # The weapon abilities a model's weapons gain from enhancements and
    # upgrades, each with the weapon type it's limited to (None: any).
    return [
        (grant.weapon_ability, grant.weapon_type)
        for grant in _grants_reaching(unit, unit_model, lambda e: e.weapon_ability_grants)
    ]


def granted_keywords(unit: Unit, unit_model: UnitModel) -> set[str]:
    # The keywords a model gains from its unit's enhancements and upgrade.
    return {
        grant.keyword.name
        for grant in _grants_reaching(unit, unit_model, lambda e: e.keyword_grants)
    }


def _own_keywords(unit: Unit, unit_model: UnitModel) -> set[str]:
    # A model's keywords and those its unit's enhancements and upgrade give it.
    return {k.name for k in unit_model.model.keywords} | granted_keywords(unit, unit_model)


def rule_granted_keywords(
    rules: Iterable, keyword_sets: list[set[str]], selected_rule_ids: Iterable[int] = ()
) -> list[set[str]]:
    # The keywords detachment rules give each model of a unit whose models have
    # these keywords (one set per model): a per-model rule gives them to each
    # model matching one of its keyword options; any other rule to every model,
    # if they all match one (or it has no options) - and a rule with a
    # selection limit only if the unit was selected for it.
    selected = set(selected_rule_ids)
    granted: list[set[str]] = [set() for _ in keyword_sets]
    for rule in rules:
        names = {k.name for k in rule.granted_keywords}
        if not names:
            continue
        if rule.selection_limit is not None and rule.id not in selected:
            continue
        options = [{k.name for k in option} for option in rule.keyword_options]

        def matches(keywords: set[str]) -> bool:
            return not options or any(option <= keywords for option in options)

        if rule.per_model:
            reached = [matches(keywords) for keywords in keyword_sets]
        else:
            whole = bool(keyword_sets) and all(matches(k) for k in keyword_sets)
            reached = [whole] * len(keyword_sets)
        for extra, reaches in zip(granted, reached):
            if reaches:
                extra |= names
    return granted


def list_rules(army_list) -> list:
    # The rules of the detachments an army list has taken (loaded with them).
    return [rule for detachment in army_list.detachments for rule in detachment.rules]


def _detachment_keywords(unit: Unit, unit_model: UnitModel) -> set[str]:
    # The keywords the rules of the unit's list's detachments give this model -
    # none if the unit isn't in a list, or its list wasn't loaded with it.
    if "army_list" in inspect(unit).unloaded or unit.army_list is None:
        return set()
    rules = list_rules(unit.army_list)
    if not rules:
        return set()
    index = next((i for i, um in enumerate(unit.unit_models) if um is unit_model), None)
    if index is None:
        return set()
    keyword_sets = [_own_keywords(unit, um) for um in unit.unit_models]
    return rule_granted_keywords(rules, keyword_sets, unit.selected_rule_ids)[index]


def model_keywords(unit: Unit, unit_model: UnitModel) -> set[str]:
    # A model's keywords, including any its unit's enhancements and upgrade
    # give it (e.g. SKITARII from Martial Signatum Amplificator), and any the
    # rules of its list's detachments give it (e.g. BATTLELINE for Houndpack
    # Lance's WAR DOGs). Needs the model's keywords loaded.
    return _own_keywords(unit, unit_model) | _detachment_keywords(unit, unit_model)


@dataclass(eq=False)
class GrantedWeapon:
    # An enhancement's weapon, shaped like a Weapon for the combat engine. Its
    # id is ("enhancement", EnhancementWeapon.id), apart from real weapon ids.
    id: tuple[str, int]
    name: str
    weapon_type: str
    range: int | None
    attacks: str
    skill: int
    strength: int
    ap: int
    damage: str
    abilities: list[WeaponAbility]


def granted_weapons(unit_model: UnitModel) -> list[GrantedWeapon]:
    # The weapons a model has from the enhancement it carries (e.g. TL-4Ø9).
    enhancement = unit_model.enhancement
    if enhancement is None:
        return []
    return [
        GrantedWeapon(
            id=("enhancement", weapon.id),
            name=weapon.name,
            weapon_type=weapon.weapon_type,
            range=weapon.range,
            attacks=weapon.attacks,
            skill=weapon.skill,
            strength=weapon.strength,
            ap=weapon.ap,
            damage=weapon.damage,
            abilities=list(weapon.abilities),
        )
        for weapon in enhancement.weapons
    ]


def granted_datasheet_abilities(unit: Unit) -> list[DatasheetAbility]:
    # The datasheet abilities a unit gains from its enhancements and upgrade.
    return [
        grant.datasheet_ability
        for grant in _grants_reaching(unit, None, lambda e: e.datasheet_ability_grants)
    ]


async def delete_enhancements(session: AsyncSession, ids: list[int]) -> None:
    # Deletes enhancements, first taking them off any models and units that
    # have them. Doesn't commit.
    if not ids:
        return
    weapon_ids = select(EnhancementWeapon.id).where(EnhancementWeapon.enhancement_id.in_(ids))
    await session.execute(
        delete(enhancement_weapon_ability_links).where(
            enhancement_weapon_ability_links.c.enhancement_weapon_id.in_(weapon_ids)
        )
    )
    for grant in (
        EnhancementWeaponAbility,
        EnhancementDatasheetAbility,
        EnhancementKeyword,
        EnhancementWeapon,
    ):
        await session.execute(delete(grant).where(grant.enhancement_id.in_(ids)))
    for table in (
        unit_model_enhancements,
        unit_upgrades,
        enhancement_keywords,
        enhancement_excluded_keywords,
    ):
        await session.execute(delete(table).where(table.c.enhancement_id.in_(ids)))
    await session.execute(delete(Enhancement).where(Enhancement.id.in_(ids)))
