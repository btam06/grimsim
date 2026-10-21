from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DatasheetAbility,
    DetachmentRule,
    DetachmentRuleDatasheetAbility,
    DetachmentRuleKeywordOption,
    DetachmentRulePerModel,
    DetachmentRuleWeaponAbility,
    Unit,
    UnitModel,
    WeaponAbility,
)
from app.services import enhancements as enhancement_rules

# Which units a detachment rule reaches, and what it grants them in combat.


def _options(rule: DetachmentRule) -> list[set[str]]:
    return [{k.name for k in option} for option in rule.keyword_options]


def model_matches(rule: DetachmentRule, keywords: set[str]) -> bool:
    # Whether a model with these keywords has all the keywords of one of the
    # rule's options (or the rule has none).
    options = _options(rule)
    return not options or any(option <= keywords for option in options)


def applies_to(rule: DetachmentRule, unit: Unit) -> bool:
    # Whether a unit-wide rule reaches a unit (from a list that has its
    # detachment): every model in it must match one of its options - e.g. a
    # Tech-priest leading Skitarii isn't SKITARII, so the unit isn't a
    # "SKITARII INFANTRY unit". Per-model rules (see DetachmentRule.per_model)
    # reach models, not units, so never a whole unit here.
    if rule.per_model:
        return False
    return bool(unit.unit_models) and all(
        model_matches(rule, enhancement_rules.model_keywords(unit, unit_model))
        for unit_model in unit.unit_models
    )


def granted_weapon_abilities(
    rules: list[DetachmentRule], unit: Unit, unit_model: UnitModel
) -> list[tuple[WeaponAbility, str | None]]:
    # The weapon abilities a model's weapons gain from these rules - unit-wide
    # ones reaching its unit, and per-model ones it matches - each with the
    # weapon type it's limited to (None: any).
    return [
        (grant.weapon_ability, grant.weapon_type)
        for rule in rules
        if applies_to(rule, unit)
        or (
            rule.per_model
            and model_matches(rule, enhancement_rules.model_keywords(unit, unit_model))
        )
        for grant in rule.weapon_ability_grants
    ]


def granted_datasheet_abilities(rules: list[DetachmentRule], unit: Unit) -> list[DatasheetAbility]:
    # The datasheet abilities a whole unit gains from these (unit-wide) rules.
    return [
        grant.datasheet_ability
        for rule in rules
        if applies_to(rule, unit)
        for grant in rule.datasheet_ability_grants
    ]


def model_datasheet_abilities(
    rules: list[DetachmentRule], keywords: set[str]
) -> list[DatasheetAbility]:
    # The datasheet abilities a model with these keywords gains from these
    # per-model rules.
    return [
        grant.datasheet_ability
        for rule in rules
        if rule.per_model and model_matches(rule, keywords)
        for grant in rule.datasheet_ability_grants
    ]


async def delete_rules(session: AsyncSession, ids: list[int]) -> None:
    # Deletes detachment rules and what they grant. Doesn't commit.
    if not ids:
        return
    for table in (
        DetachmentRuleKeywordOption,
        DetachmentRuleWeaponAbility,
        DetachmentRuleDatasheetAbility,
        DetachmentRulePerModel,
    ):
        await session.execute(delete(table).where(table.rule_id.in_(ids)))
    await session.execute(delete(DetachmentRule).where(DetachmentRule.id.in_(ids)))
