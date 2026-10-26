from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.list_rules import AllyRule
from app.models import ArmyList, Faction, FactionUnit, Model, Unit, UnitModel
from app.seeds.factions import ALLY_RULES, SUBFACTIONS

# Which factions' units and models an army list can include, beyond its own
# faction's, under the ally rules (see app/list_rules.py). Shared by the
# endpoint that offers them and the unit endpoints that validate them.


def _keywords(model: Model) -> set[str]:
    return {k.name for k in model.keywords}


def active_rules(list_faction: str, detachments: set[str] = frozenset()) -> list[AllyRule]:
    # The ally rules for a list of this faction that has taken these
    # detachments (by name).
    return [
        rule
        for rule in ALLY_RULES
        if rule.host_faction == list_faction
        and (rule.detachment is None or rule.detachment in detachments)
    ]


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


def subfaction_allies(
    list_faction: str, subfaction: str | None, detachments: set[str] = frozenset()
) -> list[dict]:
    # The selection's ally allowances (e.g. Deathwatch Allies) a list with
    # these detachments (by name) has, for options other than its own.
    config = SUBFACTIONS.get(list_faction)
    if config is None:
        return []
    own = config["options"].get(subfaction)
    return [
        ally
        for ally in config.get("allies", [])
        if ally["detachment"] in detachments and ally["keyword"] != own
    ]


def subfaction_ally(
    model: Model, list_faction: str, subfaction: str | None, detachments: set[str] = frozenset()
) -> dict | None:
    # The allowance letting a model with another option's keyword into the
    # list, if any - e.g. a DEATHWATCH model in an Ultramarines list with
    # Deathwatch Support.
    keywords = _keywords(model)
    return next(
        (
            ally
            for ally in subfaction_allies(list_faction, subfaction, detachments)
            if ally["keyword"] in keywords
        ),
        None,
    )


def subfaction_reason(
    model: Model, list_faction: str, subfaction: str | None, detachments: set[str] = frozenset()
) -> str | None:
    # Why a list can't include a model because of its faction's selection
    # (e.g. a Chapter): a model with another option's keyword of its own
    # (e.g. Roboute Guilliman, ULTRAMARINES) can only be in a list of that
    # option - unless one of the list's detachments (by name) lets it in
    # (subfaction_ally). None if it can.
    config = SUBFACTIONS.get(list_faction)
    if config is None:
        return None
    allowed = {a["keyword"] for a in subfaction_allies(list_faction, subfaction, detachments)}
    for option, keyword in config["options"].items():
        if option != subfaction and keyword in _keywords(model) and keyword not in allowed:
            article = "an" if option[0] in "AEIOU" else "a"
            return f"{model.name} can only be included in {article} {option} list"
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

    @property
    def detachments(self) -> set[str]:
        return {d.name for d in self.army_list.detachments}

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
        .options(
            selectinload(Unit.faction_unit),
            # Their models' keywords, for ally rules that cap models.
            selectinload(Unit.unit_models)
            .selectinload(UnitModel.model)
            .selectinload(Model.keywords),
        )
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
    rules = active_rules(context.faction, context.detachments)
    unit_faction = context.faction_names[faction_unit.faction_id]
    if not faction_allowed(unit_faction, context.faction, rules):
        return f"{faction_unit.name} ({unit_faction}) can't be included in a {context.faction} list"
    for model in models:
        reason = model_unavailable_reason(
            model, context.faction_names[model.faction_id], context.faction, rules
        ) or subfaction_reason(
            model, context.faction, context.army_list.subfaction, context.detachments
        )
        if reason:
            return reason
    reason = _model_limit_reason(context, models, rules) or _subfaction_points_reason(
        context, points, models
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


def _subfaction_points_reason(context: ListContext, points: int, models: list[Model]) -> str | None:
    # Why adding this unit would take the list past an ally allowance's points
    # (e.g. Deathwatch Allies: 500 pts of DEATHWATCH units), or None.
    for ally in subfaction_allies(
        context.faction, context.army_list.subfaction, context.detachments
    ):
        keyword = ally["keyword"]
        if not any(keyword in _keywords(m) for m in models):
            continue
        total = points + sum(
            unit.points
            for unit in context.other_units
            if any(keyword in _keywords(um.model) for um in unit.unit_models)
        )
        if total > ally["points"]:
            return (
                f"{ally['detachment']}: a list can include at most {ally['points']} pts of "
                f"{keyword} units"
            )
    return None


def _model_limit_reason(
    context: ListContext, models: list[Model], rules: list[AllyRule]
) -> str | None:
    # Why adding these models would break an ally rule's model cap, or its
    # choice group (only one rule of a group can be used), or None.
    # By id(rule), since a rule (holding a dict) isn't hashable.
    counts: dict[int, int] = {}
    every_model = [
        unit_model.model for unit in context.other_units for unit_model in unit.unit_models
    ] + models
    for model in every_model:
        model_faction = context.faction_names[model.faction_id]
        if model_faction == context.faction:
            continue
        rule = model_rule(model, model_faction, rules)
        if rule is not None:
            counts[id(rule)] = counts.get(id(rule), 0) + 1
    used_rules = [rule for rule in rules if id(rule) in counts]
    for rule in used_rules:
        count = counts[id(rule)]
        if rule.model_limit is not None and count > rule.model_limit:
            return (
                f"a {context.faction} list can include at most {rule.model_limit} "
                f"{' / '.join(rule.model_keywords)} {rule.ally_faction} model"
                f"{'s' if rule.model_limit != 1 else ''}"
            )
    groups: dict[str, list[AllyRule]] = {}
    for rule in used_rules:
        if rule.choice_group:
            groups.setdefault(rule.choice_group, []).append(rule)
    for group, used in groups.items():
        if len(used) > 1:
            return (
                f"{group}: a {context.faction} list can include models under only one of "
                + ", ".join(
                    f"{r.model_limit} {' / '.join(r.model_keywords)}" for r in used
                )
            )
    return None


def can_take_enhancements(context: ListContext, model: Model) -> bool:
    # Whether a model can be given Enhancements - not if it's only in the list
    # under an ally rule that forbids them.
    model_faction = context.faction_names[model.faction_id]
    if model_faction == context.faction:
        return True
    rule = model_rule(model, model_faction, active_rules(context.faction, context.detachments))
    return rule is None or rule.enhancements
