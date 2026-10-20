from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DatasheetAbility,
    DetachmentRule,
    DetachmentRuleDatasheetAbility,
    DetachmentRuleKeywordOption,
    DetachmentRuleWeaponAbility,
    Unit,
    WeaponAbility,
)

# Which units a detachment rule reaches, and what it grants them in combat.


def applies_to(rule: DetachmentRule, unit: Unit) -> bool:
    # Whether a rule reaches a unit (from a list that has its detachment):
    # every model in it must have all the keywords of one of its options -
    # e.g. a Tech-priest leading Skitarii isn't SKITARII, so the unit isn't a
    # "SKITARII INFANTRY unit". No options means every unit. Needs the
    # unit's models' keywords loaded.
    options = [{k.name for k in option} for option in rule.keyword_options]
    if not options:
        return True
    return bool(unit.unit_models) and all(
        any(option <= {k.name for k in unit_model.model.keywords} for option in options)
        for unit_model in unit.unit_models
    )


def granted_weapon_abilities(
    rules: list[DetachmentRule], unit: Unit
) -> list[tuple[WeaponAbility, str | None]]:
    # The weapon abilities the unit's weapons gain from these rules, each
    # with the weapon type it's limited to (None: any).
    return [
        (grant.weapon_ability, grant.weapon_type)
        for rule in rules
        if applies_to(rule, unit)
        for grant in rule.weapon_ability_grants
    ]


def granted_datasheet_abilities(rules: list[DetachmentRule], unit: Unit) -> list[DatasheetAbility]:
    # The datasheet abilities the unit gains from these rules.
    return [
        grant.datasheet_ability
        for rule in rules
        if applies_to(rule, unit)
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
    ):
        await session.execute(delete(table).where(table.rule_id.in_(ids)))
    await session.execute(delete(DetachmentRule).where(DetachmentRule.id.in_(ids)))
