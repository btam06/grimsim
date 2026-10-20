from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.list_rules import AllyRule
from app.models import ArmyList, Faction, FactionUnit, Model, Unit
from app.seeds.factions import ALLY_RULES

# Which factions' units and models an army list can include, beyond its own
# faction's, under the ally rules (see app/list_rules.py). Shared by the
# endpoint that offers them and the unit endpoints that validate them.


def _keywords(model: Model) -> set[str]:
    return {k.name for k in model.keywords}


def active_rules(list_faction: str) -> list[AllyRule]:
    # The ally rules for a list of this faction.
    return [rule for rule in ALLY_RULES if rule.host_faction == list_faction]


def model_rule(model: Model, model_faction: str, rules: list[AllyRule]) -> AllyRule | None:
    # The rule letting a model from another faction into the list, if any.
    return next(
        (
            rule
            for rule in rules
            if rule.ally_faction == model_faction and set(rule.model_keywords) & _keywords(model)
        ),
        None,
    )


def model_unavailable_reason(
    model: Model, model_faction: str, list_faction: str, rules: list[AllyRule]
) -> str | None:
    # Why a list can't include a model, or None if it can.
    if model_faction == list_faction:
        return None
    if model_rule(model, model_faction, rules) is None:
        return f"{model.name} ({model_faction}) can't be included in a {list_faction} list"
    return None


def faction_allowed(faction: str, list_faction: str, rules: list[AllyRule]) -> bool:
    # Whether a list can include a faction unit from `faction` at all.
    return faction == list_faction or any(rule.ally_faction == faction for rule in rules)


@dataclass
class ListContext:
    # An army list as the ally rules see it: its faction, every faction's
    # name by id, and its units other than the one being added or edited.
    army_list: ArmyList
    faction: str
    faction_names: dict[int, str]
    other_units: list[Unit]

    def points_by_faction(self) -> dict[str, int]:
        # The other units' points, totalled by their faction unit's faction.
        totals: dict[str, int] = {}
        for unit in self.other_units:
            faction = self.faction_names[unit.faction_unit.faction_id]
            totals[faction] = totals.get(faction, 0) + unit.points
        return totals


async def load_list_context(
    session: AsyncSession, list_id: int, except_unit_id: int | None
) -> ListContext | None:
    # None if there's no such list.
    army_list = (
        await session.execute(
            select(ArmyList)
            .options(selectinload(ArmyList.detachments))
            .where(ArmyList.id == list_id)
        )
    ).scalar_one_or_none()
    if army_list is None:
        return None
    faction_names = {
        f.id: f.name for f in (await session.execute(select(Faction))).scalars().all()
    }
    query = (
        select(Unit)
        .options(selectinload(Unit.faction_unit))
        .where(Unit.list_id == list_id)
    )
    if except_unit_id is not None:
        query = query.where(Unit.id != except_unit_id)
    other_units = list((await session.execute(query)).scalars().all())
    return ListContext(army_list, faction_names[army_list.faction_id], faction_names, other_units)


def unit_unavailable_reason(
    context: ListContext,
    faction_unit: FactionUnit,
    points: int,
    models: list[Model],
) -> str | None:
    # Why a unit (this faction unit, these points and models, which need
    # their keywords loaded) can't go in the list, or None if it can.
    rules = active_rules(context.faction)
    unit_faction = context.faction_names[faction_unit.faction_id]
    if not faction_allowed(unit_faction, context.faction, rules):
        return f"{faction_unit.name} ({unit_faction}) can't be included in a {context.faction} list"
    for model in models:
        reason = model_unavailable_reason(
            model, context.faction_names[model.faction_id], context.faction, rules
        )
        if reason:
            return reason
    totals = context.points_by_faction()
    totals[unit_faction] = totals.get(unit_faction, 0) + points
    for rule in rules:
        limit = rule.points_limits.get(context.army_list.points_limit)
        if limit is not None and totals.get(rule.ally_faction, 0) > limit:
            return (
                f"a {context.faction} list of {context.army_list.points_limit} pts can include "
                f"at most {limit} pts of {' / '.join(rule.model_keywords)} units"
            )
    return None


def can_take_enhancements(context: ListContext, model: Model) -> bool:
    # Whether a model can be given Enhancements - not if it's only in the list
    # under an ally rule that forbids them.
    model_faction = context.faction_names[model.faction_id]
    if model_faction == context.faction:
        return True
    rule = model_rule(model, model_faction, active_rules(context.faction))
    return rule is None or rule.enhancements
