from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DatasheetAbility,
    Enhancement,
    EnhancementDatasheetAbility,
    EnhancementWeaponAbility,
    Model,
    Unit,
    UnitModel,
    WeaponAbility,
    enhancement_excluded_keywords,
    enhancement_keywords,
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
    enhancement: Enhancement, model: Model, detachment_ids: set[int]
) -> str | None:
    # Why a model can't carry this enhancement, or None if it can: it must be
    # an enhancement (not an upgrade) from one of the list's detachments, and
    # the model a CHARACTER (but not an EPIC HERO) meeting its keywords.
    # Needs the model's keywords loaded.
    if enhancement.kind != "enhancement":
        return "is an upgrade, which is taken by a unit, not a model"
    names = _keyword_names(model)
    if "CHARACTER" not in names:
        return "can only be carried by a CHARACTER"
    if "EPIC HERO" in names:
        return "can't be carried by an EPIC HERO"
    return _detachment_reason(enhancement, detachment_ids) or _keyword_reason(
        enhancement, names, "a model"
    )


def unit_unavailable_reason(
    upgrade: Enhancement, models: Iterable[Model], detachment_ids: set[int]
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
    for model in models:
        reason = _keyword_reason(upgrade, _keyword_names(model), "a unit")
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
    for grant in (EnhancementWeaponAbility, EnhancementDatasheetAbility):
        await session.execute(delete(grant).where(grant.enhancement_id.in_(ids)))
    for table in (
        unit_model_enhancements,
        unit_upgrades,
        enhancement_keywords,
        enhancement_excluded_keywords,
    ):
        await session.execute(delete(table).where(table.c.enhancement_id.in_(ids)))
    await session.execute(delete(Enhancement).where(Enhancement.id.in_(ids)))
