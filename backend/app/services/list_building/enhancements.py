from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import delete, select
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
from app.models.base import is_loaded
from app.seeds import factions as faction_seeds

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


def exclusive_detachments(detachments: Iterable) -> dict[int, set[str]]:
    # Those of a list's detachments whose units with certain keywords can only
    # take that detachment's enhancements (faction_seeds.EXCLUSIVE_ENHANCEMENTS
    # - e.g. Deathwatch Support's KILL TEAM units): {detachment id: keywords}.
    return {
        d.id: set(faction_seeds.EXCLUSIVE_ENHANCEMENTS[d.name])
        for d in detachments
        if d.name in faction_seeds.EXCLUSIVE_ENHANCEMENTS
    }


def _exclusive_reason(
    enhancement: Enhancement, keyword_names: set[str], exclusive: dict[int, set[str]]
) -> str | None:
    for detachment_id, keywords in exclusive.items():
        held = keywords & keyword_names
        if held and enhancement.detachment_id != detachment_id:
            return f"isn't from the detachment {', '.join(sorted(held))} units take theirs from"
    return None


def model_unavailable_reason(
    enhancement: Enhancement,
    model: Model,
    detachment_ids: set[int],
    granted: set[str] = frozenset(),
    exclusive: dict[int, set[str]] | None = None,
) -> str | None:
    # Why a model can't carry this enhancement, or None if it can: it must be
    # an enhancement (not an upgrade) from one of the list's detachments, and
    # the model a CHARACTER (but not an EPIC HERO) meeting its keywords -
    # counting any `granted` it (e.g. by a detachment rule) - and from the
    # right detachment for a model `exclusive` (exclusive_detachments) limits.
    # Needs the model's keywords loaded.
    if enhancement.kind != "enhancement":
        return "is an upgrade, which is taken by a unit, not a model"
    names = _keyword_names(model) | set(granted)
    if "CHARACTER" not in names:
        return "can only be carried by a CHARACTER"
    if "EPIC HERO" in names:
        return "can't be carried by an EPIC HERO"
    return (
        _detachment_reason(enhancement, detachment_ids)
        or _keyword_reason(enhancement, names, "a model")
        or _exclusive_reason(enhancement, names, exclusive or {})
    )


def unit_unavailable_reason(
    upgrade: Enhancement,
    models: Iterable[Model],
    detachment_ids: set[int],
    granted: list[set[str]] | None = None,
    exclusive: dict[int, set[str]] | None = None,
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
        names = _keyword_names(model) | extra
        reason = _keyword_reason(upgrade, names, "a unit") or _exclusive_reason(
            upgrade, names, exclusive or {}
        )
        if reason:
            return reason
    return None


# --- what they grant in combat ---


def _led_from(unit_model) -> int | None:
    # The leader or support unit a model in a game's attached unit came from
    # (None: the unit's own model) - see app/engine/loader.py attach_leaders.
    return unit_model.__dict__.get("led_from")


def _marked(unit: Unit) -> bool:
    # Whether its models say where they came from (a game's, loaded since
    # leaders became units of their own; an older autosave's don't).
    return all("led_from" in m.__dict__ for m in unit.unit_models)


# Models destroyed by the attacks being made, which still count until the
# attacking unit has made them all (see lasting).
_lasting: ContextVar[list[int] | None] = ContextVar(
    "lasting", default=None
)


@contextmanager
def lasting(destroyed: list[int]):
    # While a unit makes its attacks: the models in `destroyed` (the unit
    # model ids they've destroyed so far - added to as they are) still give
    # what they gave, e.g. an enhancement's bearer to its unit - "if that last
    # model was destroyed as the result of an attack, the ability it was
    # conferring upon the attached unit applies until the attacking unit has
    # resolved all of its attacks" (Core Rules 19.04).
    token = _lasting.set(destroyed)
    try:
        yield
    finally:
        _lasting.reset(token)


def _destroyed() -> set[int] | None:
    # The bound game's destroyed models' unit model ids (None: no game) -
    # those destroyed by the attacks being made aside (see lasting).
    from app.engine import context

    live = context.current()
    if live is None:
        return None
    still = set(_lasting.get() or ())
    return {d.unit_model_id for d in live.game.model_damage if d.destroyed} - still


def _any_alive(models: list) -> bool:
    destroyed = _destroyed()
    return any(destroyed is None or m.id not in destroyed for m in models)


def is_leading(unit: Unit, unit_model: UnitModel) -> bool:
    # Whether a model is leading a unit: its leader or support unit is
    # attached to a bodyguard unit - in a game, it started the battle in an
    # attached unit, and is leading even once its bodyguard unit's destroyed
    # (Core Rules 19.04: "leader/support units continue to benefit from their
    # own 'while this model is leading a unit' abilities even after their
    # bodyguard unit is destroyed"). In a game the two are one unit (see
    # app/engine/loader.py merge): it came from an attached unit. In a list,
    # its unit is attached to one.
    from app.engine.catalog import Mirror

    if unit.unit_models and _marked(unit):
        return _led_from(unit_model) is not None
    if isinstance(unit, Mirror):
        # (An older game's: leaders as models in their units - a CHARACTER
        # in a unit with others.)
        return "CHARACTER" in _keyword_names(unit_model.model) and any(
            "CHARACTER" not in _keyword_names(other.model) for other in unit.unit_models
        )
    return getattr(unit, "attached_to_id", None) is not None


def _upgrades_reaching(unit: Unit) -> list:
    # The upgrades that apply to the (attached) unit (Core Rules 19.04): its
    # own, until the last of its own models is destroyed, and each attached
    # leader or support unit's, until the last of that unit's models is.
    if not _marked(unit):
        return [unit.upgrade] if unit.upgrade is not None else []
    found = []
    if unit.upgrade is not None and _any_alive(
        [m for m in unit.unit_models if _led_from(m) is None]
    ):
        found.append(unit.upgrade)
    for upgrade, leader_id in zip(
        unit.__dict__.get("attached_upgrades", []), unit.__dict__.get("attached_upgrade_units", [])
    ):
        if _any_alive([m for m in unit.unit_models if _led_from(m) == leader_id]):
            found.append(upgrade)
    return found


def _grants_reaching(unit: Unit, unit_model: UnitModel | None, grants_of) -> list:
    # The grants from the unit's enhancements and upgrades that apply to
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
            elif grant.scope == "bearers_unit" and _any_alive([carrier]):
                # (A specific model's: until it's destroyed - Core Rules 19.04.)
                reaching.append(grant)
    for upgrade in _upgrades_reaching(unit):
        reaching += [g for g in grants_of(upgrade) if g.scope == "unit"]
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
    if not is_loaded(unit, "army_list") or unit.army_list is None:
        return set()
    rules = list_rules(unit.army_list)
    if not rules:
        return set()
    index = next((i for i, um in enumerate(unit.unit_models) if um is unit_model), None)
    if index is None:
        return set()
    keyword_sets = [_own_keywords(unit, um) for um in unit.unit_models]
    return rule_granted_keywords(rules, keyword_sets, unit.selected_rule_ids)[index]


def _subfaction_keywords(unit: Unit, unit_model: UnitModel) -> set[str]:
    # The keyword the unit's list's selection gives this model, if it has the
    # keyword that gets it (e.g. an Ultramarines list: ULTRAMARINES for its
    # ADEPTUS ASTARTES models) - none if the unit isn't in a list, or its list
    # wasn't loaded with it, or the model has another option's keyword of its
    # own (e.g. a DEATHWATCH model there under Deathwatch Allies).
    if not is_loaded(unit, "army_list") or unit.army_list is None:
        return set()
    selected = unit.army_list.subfaction
    own = {k.name for k in unit_model.model.keywords}
    for config in faction_seeds.SUBFACTIONS.values():
        keyword = config["options"].get(selected)
        if (
            keyword
            and config["keyword_holders"] in own
            and not own & (set(config["options"].values()) - {keyword})
        ):
            return {keyword}
    return set()


# While a simulation resolves the same attack over and over (see
# app/routers/combat.py simulate), each model's keywords are worked out once:
# {(id(unit), id(unit model)): keywords}. None: not caching.
_keyword_cache: ContextVar[dict | None] = ContextVar("keyword_cache", default=None)


@contextmanager
def cached_keywords():
    # Within this, model_keywords remembers each model's keywords - for when
    # nothing that changes them (lists, enhancements, rules) can change.
    token = _keyword_cache.set({})
    try:
        yield
    finally:
        _keyword_cache.reset(token)


def model_keywords(unit: Unit, unit_model: UnitModel) -> set[str]:
    # A model's keywords, including any its unit's enhancements and upgrade
    # give it (e.g. SKITARII from Martial Signatum Amplificator), any the
    # rules of its list's detachments give it (e.g. BATTLELINE for Houndpack
    # Lance's WAR DOGs), and its list's Chapter's (e.g. ULTRAMARINES). Needs
    # the model's keywords loaded.
    cache = _keyword_cache.get()
    key = (id(unit), id(unit_model))
    if cache is not None and key in cache:
        return set(cache[key])
    keywords = (
        _own_keywords(unit, unit_model)
        | _detachment_keywords(unit, unit_model)
        | _subfaction_keywords(unit, unit_model)
    )
    if cache is not None:
        cache[key] = frozenset(keywords)
    return keywords


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
