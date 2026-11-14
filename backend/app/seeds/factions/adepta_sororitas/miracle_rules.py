from __future__ import annotations

from collections import Counter

from fastapi import HTTPException

from app.models import Unit
from app.engine.state import (
    Game,
    GameDivineIntervention,
    GameMiracleOffer,
    GameMiracleUse,
    GameModelPosition,
    GamePlayer,
)
from app.services import dice
from app.services.in_game import casualties, deployment
from app.services.in_game.deployment import BOARD, TOLERANCE, gap
from app.services.list_building import enhancements as enhancement_rules

# The Adepta Sororitas rules that discard or re-roll Miracle dice (see
# acts_of_faith.py for the pool), each at the time its rules give:
#
# - Manual of Saint Griselda (enhancement): at the start of its player's
#   Command phase - before any Battle-shock test is taken or Miracle dice used
#   in it - discard up to 2 Miracle dice, then gain one showing their sum (at
#   most 6). Its bearer can't be destroyed.
# - Chaplet of Sacrifice (enhancement): at the end of its player's Command
#   phase - once every Battle-shock test in it is taken; no Miracle dice can
#   be used in the phase after - re-roll 1 Miracle dice (up to 3 if the
#   bearer's unit is below its Starting Strength), if its bearer is on the
#   battlefield.
# - Righteous Rage (enhancement): each time the bearer's unit is selected to
#   fight, discard up to 3 Miracle dice first: +1 Attacks and Strength to
#   the bearer's melee weapons for each, until the end of the phase (see
#   weapon_bonuses).
# - Psalm of Righteous Judgement (enhancement): each time a PENITENT unit of
#   its army destroys an enemy unit, while its bearer is on the battlefield,
#   its player is offered to discard 1 Miracle dice and gain one showing a 6
#   (until the end of that phase).
# - Divine Intervention (stratagem, game action "divine_intervention"): on
#   an ADEPTA SORORITAS CHARACTER model destroyed this phase, discarding 0-3
#   Miracle dice (the lowest - only how many counts); at the end of the
#   phase it's set up, unengaged and as close as possible to where it was
#   destroyed, with D3 wounds left plus 1 for each dice discarded (up to its
#   W). Its unit then counts as a unit of that one model (Starting Strength
#   1). The rest of its unit must be gone: a model can't be split off a unit
#   that's still on the battlefield here.
#
# Through Suffering, Strength's higher tier - +2 instead of +1 while its
# bearer has lost wounds - is also a melee bonus (see weapon_bonuses).

MANUAL = "Manual of Saint Griselda"
CHAPLET = "Chaplet of Sacrifice"
RIGHTEOUS_RAGE = "Righteous Rage"
PSALM = "Psalm of Righteous Judgement"
THROUGH_SUFFERING = "Through Suffering, Strength"
DIVINE_INTERVENTION = "divine_intervention"

MANUAL_DISCARDS = 2
CHAPLET_REROLLS = (1, 3)
RAGE_DISCARDS = 3
DIVINE_DISCARDS = 3
PSALM_VALUE = 6
MAX_VALUE = 6


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _player(game: Game, seat: int) -> GamePlayer:
    return next(p for p in game.players if p.seat == seat)


def _now(game: Game, record) -> bool:
    return (record.battle_round, record.turn_seat, record.phase) == (
        game.battle_round, game.turn_seat, game.phase
    )


def _when(game: Game) -> dict:
    return {"battle_round": game.battle_round, "turn_seat": game.turn_seat, "phase": game.phase}


def _army_rule(player: GamePlayer) -> bool:
    from app.seeds.factions.adepta_sororitas import acts_of_faith

    return acts_of_faith.army_rule(player)


def bearers(game: Game, player: GamePlayer, enhancement: str, on_battlefield: bool = True):
    # The player's models with the enhancement (not destroyed - and on the
    # battlefield, if `on_battlefield`): (unit, unit model).
    lost = casualties.damage(game)
    placed = deployment.positions(game)
    return [
        (unit, m)
        for unit in deployment.deployable_units(player)
        for m in unit.unit_models
        if m.enhancement is not None
        and m.enhancement.name == enhancement
        and not (m.id in lost and lost[m.id].destroyed)
        and (m.id in placed or not on_battlefield)
    ]


def _take(player: GamePlayer, values: list[int]) -> None:
    # Takes those dice out of the player's pool (each must be in it).
    pool = Counter(player.miracle_dice)
    if Counter(values) - pool:
        raise _bad_request("those Miracle dice aren't all in the pool")
    for value in values:
        player.miracle_dice.remove(value)


def _record(game: Game, seat: int, rule: str, unit_id, removed, added) -> GameMiracleUse:
    use = GameMiracleUse(
        seat=seat, rule=rule, unit_id=unit_id, removed=list(removed), added=list(added),
        **_when(game),
    )
    game.miracle_uses.append(use)
    return use


def used(game: Game, seat: int, rule: str, unit_id: int | None = None) -> list[GameMiracleUse]:
    # The player's uses of the rule this phase (for the unit, if given).
    return [
        u
        for u in game.miracle_uses
        if u.seat == seat
        and u.rule == rule
        and _now(game, u)
        and (unit_id is None or u.unit_id == unit_id)
    ]


def _own_command_phase(game: Game, seat: int) -> bool:
    return game.status == "in_progress" and game.phase == "command" and game.turn_seat == seat


# --- Manual of Saint Griselda: the start of the Command phase ---


def manual_reason(game: Game, seat: int) -> str | None:
    # Why the player can't use the Manual of Saint Griselda now, or None.
    from app.seeds.factions.adepta_sororitas import acts_of_faith

    player = _player(game, seat)
    if not _army_rule(player) or not bearers(game, player, MANUAL, on_battlefield=False):
        return f"they have no {MANUAL}"
    if not _own_command_phase(game, seat):
        return "it's used at the start of their Command phase"
    if used(game, seat, MANUAL):
        return "it's been used this phase"
    if used(game, seat, CHAPLET) or any(
        _now(game, t) and t.passed is not None for t in game.battle_shock_tests
    ) or any(a.seat == seat and acts_of_faith._this_phase(game, a) for a in game.acts_of_faith):
        return "the start of the Command phase has passed"
    if not player.miracle_dice:
        return "there are no Miracle dice in the pool"
    return None


def use_manual(game: Game, seat: int, values: list[int]) -> GameMiracleUse:
    # Discards the dice (up to 2), then gains one showing their sum (at most 6).
    if (reason := manual_reason(game, seat)) is not None:
        raise _bad_request(f"can't use the {MANUAL}: {reason}")
    if not 1 <= len(values) <= MANUAL_DISCARDS:
        raise _bad_request(f"discard 1 or {MANUAL_DISCARDS} Miracle dice")
    player = _player(game, seat)
    _take(player, values)
    value = min(MAX_VALUE, sum(values))
    player.miracle_dice.append(value)
    unit, _ = bearers(game, player, MANUAL, on_battlefield=False)[0]
    return _record(game, seat, MANUAL, unit.id, values, [value])


# --- Chaplet of Sacrifice: the end of the Command phase ---


def chaplet_limit(game: Game, seat: int) -> tuple[int, str | None]:
    # How many Miracle dice the player can re-roll with the Chaplet of
    # Sacrifice now - and if none, why not.
    from app.services.in_game import battle_shock

    player = _player(game, seat)
    found = bearers(game, player, CHAPLET) if _army_rule(player) else []
    if not found:
        return 0, f"they have no {CHAPLET} on the battlefield"
    if not _own_command_phase(game, seat):
        return 0, "it's used at the end of their Command phase"
    if used(game, seat, CHAPLET):
        return 0, "it's been used this phase"
    if battle_shock.pending(game):
        return 0, "the end of the Command phase comes once every Battle-shock test is taken"
    if not player.miracle_dice:
        return 0, "there are no Miracle dice in the pool"
    unit, _ = found[0]
    below = battle_shock.below_starting_strength(game, unit)
    return CHAPLET_REROLLS[1] if below else CHAPLET_REROLLS[0], None


def chaplet_used(game: Game, seat: int) -> bool:
    # Whether the player's used it this phase: the end of their Command phase
    # - no more Miracle dice can be used in it.
    return game.phase == "command" and bool(used(game, seat, CHAPLET))


def use_chaplet(game: Game, seat: int, values: list[int]) -> GameMiracleUse:
    # Re-rolls those Miracle dice, returning each to the pool with its new
    # value.
    limit, reason = chaplet_limit(game, seat)
    if reason is not None:
        raise _bad_request(f"can't use the {CHAPLET}: {reason}")
    if not 1 <= len(values) <= limit:
        raise _bad_request(f"re-roll 1 to {limit} Miracle dice")
    player = _player(game, seat)
    _take(player, values)
    rolled = [dice.randint(1, 6) for _ in values]
    player.miracle_dice.extend(rolled)
    unit, _ = bearers(game, player, CHAPLET)[0]
    return _record(game, seat, CHAPLET, unit.id, values, rolled)


# --- Psalm of Righteous Judgement: an enemy unit destroyed ---


def unit_destroyed(game: Game, unit: Unit, destroyed_by: Unit | None) -> None:
    # The unit was destroyed by `destroyed_by`'s attacks: if that's a
    # PENITENT unit of a player with the Psalm on the battlefield, they're
    # offered it.
    if destroyed_by is None:
        return
    player = deployment.owner(game, destroyed_by)
    if player.seat == deployment.owner(game, unit).seat or not _army_rule(player):
        return
    if not any(
        "PENITENT" in enhancement_rules.model_keywords(destroyed_by, m)
        for m in destroyed_by.unit_models
    ):
        return
    if not bearers(game, player, PSALM):
        return
    game.miracle_offers.append(
        GameMiracleOffer(seat=player.seat, rule=PSALM, unit_id=unit.id, **_when(game))
    )


def offers(game: Game, seat: int) -> list[GameMiracleOffer]:
    # The player's offers open now (this phase, not yet taken or declined).
    return [
        o for o in game.miracle_offers if o.seat == seat and not o.resolved and _now(game, o)
    ]


def resolve_psalm(game: Game, seat: int, offer_id: int, value: int | None) -> None:
    # Takes the offer - discarding the Miracle dice of `value`, then gaining
    # one showing a 6 - or declines it (`value` None).
    offer = next((o for o in offers(game, seat) if o.id == offer_id), None)
    if offer is None:
        raise _bad_request(f"there's no such {PSALM} offer open")
    offer.resolved = True
    if value is None:
        return
    player = _player(game, seat)
    _take(player, [value])
    player.miracle_dice.append(PSALM_VALUE)
    _record(game, seat, PSALM, offer.unit_id, [value], [PSALM_VALUE])


# --- Righteous Rage, Through Suffering, Strength: melee bonuses ---


def rage_bearer(unit: Unit):
    return next(
        (
            m
            for m in unit.unit_models
            if m.enhancement is not None and m.enhancement.name == RIGHTEOUS_RAGE
        ),
        None,
    )


def rage_max(game: Game, unit: Unit) -> int:
    # How many Miracle dice the unit's player can discard for Righteous Rage
    # as it's selected to fight (0: it can't).
    player = deployment.owner(game, unit)
    bearer = rage_bearer(unit)
    if bearer is None or not _army_rule(player) or game.phase != "fight":
        return 0
    if bearer.id not in deployment.positions(game):
        return 0
    return min(RAGE_DISCARDS, len(player.miracle_dice))


def use_rage(game: Game, unit: Unit, values: list[int]) -> None:
    # The unit's selected to fight: discards those dice for Righteous Rage.
    if not values:
        return
    limit = rage_max(game, unit)
    if limit == 0:
        raise _bad_request(f"{unit.label} can't use {RIGHTEOUS_RAGE} now")
    if len(values) > limit:
        raise _bad_request(f"discard at most {limit} Miracle dice for {RIGHTEOUS_RAGE}")
    player = deployment.owner(game, unit)
    _take(player, values)
    _record(game, player.seat, RIGHTEOUS_RAGE, unit.id, values, [])


def weapon_bonuses(game: Game, unit: Unit, wounds: dict[int, int]) -> dict[int, list]:
    # What's added to the unit's models' melee weapons, by unit model id
    # (see app/services/combat.py WeaponBonus): Righteous Rage's dice
    # discarded this phase (+1 A and S each), and Through Suffering,
    # Strength's extra +1 A, S and D (+2 in all) while its bearer has lost
    # wounds. `wounds`: each model's wounds left.
    from app.services.combat import WeaponBonus

    found: dict[int, list] = {}
    player = deployment.owner(game, unit)
    if not _army_rule(player):
        return found
    bearer = rage_bearer(unit)
    if bearer is not None:
        rage = sum(len(u.removed) for u in used(game, player.seat, RIGHTEOUS_RAGE, unit.id))
        if rage:
            found.setdefault(bearer.id, []).append(WeaponBonus(attacks=rage, strength=rage))
    for m in unit.unit_models:
        if (
            m.enhancement is not None
            and m.enhancement.name == THROUGH_SUFFERING
            and m.id in wounds
            and wounds[m.id] < m.wounds
        ):
            found.setdefault(m.id, []).append(WeaponBonus(attacks=1, strength=1, damage=1))
    return found


# --- Divine Intervention ---


def _destroyed_character(game: Game, unit: Unit):
    # The unit's ADEPTA SORORITAS CHARACTER model destroyed this phase (its
    # record), if one was - that hasn't been the target of Divine
    # Intervention this battle.
    models = {m.id: m for m in unit.unit_models}
    targeted = {d.unit_model_id for d in game.divine_interventions}
    for record in game.models_destroyed:
        model = models.get(record.unit_model_id)
        if (
            model is None
            or record.unit_id != unit.id
            or not _now(game, record)
            or record.x is None
            or model.id in targeted
        ):
            continue
        keywords = enhancement_rules.model_keywords(unit, model)
        if {"CHARACTER", "ADEPTA SORORITAS"} <= keywords:
            return record
    return None


def divine_reason(game: Game, player: GamePlayer, unit: Unit) -> str | None:
    if _destroyed_character(game, unit) is None:
        return (
            "no ADEPTA SORORITAS CHARACTER model of it was just destroyed (or it's already "
            "been the target of Divine Intervention this battle)"
        )
    if deployment.models_on_battlefield(game, unit):
        return (
            "the rest of its unit is still on the battlefield (a model can't be split off "
            "its unit here)"
        )
    return None


def divine_choices(game: Game, player: GamePlayer) -> list:
    # How many Miracle dice to discard: 0 to 3 (choice ids 1-4: one more).
    from app.services.in_game.stratagem_actions import Choice

    return [
        Choice(n + 1, f"Discard {n} Miracle dice" + (" (D3 wounds)" if n == 0 else f" (D3+{n} wounds)"))
        for n in range(min(DIVINE_DISCARDS, len(player.miracle_dice)) + 1)
    ]


def divine_intervention(game: Game, player: GamePlayer, unit: Unit, choice_id: int) -> str:
    # The stratagem's used on the unit: the lowest Miracle dice discarded.
    if choice_id not in {c.id for c in divine_choices(game, player)}:
        raise _bad_request("pick how many Miracle dice to discard")
    record = _destroyed_character(game, unit)
    discarded = sorted(player.miracle_dice)[: choice_id - 1]
    _take(player, discarded)
    game.divine_interventions.append(
        GameDivineIntervention(
            seat=player.seat, unit_id=unit.id, unit_model_id=record.unit_model_id,
            discarded=discarded, **_when(game),
        )
    )
    return (
        f"Discarded {len(discarded)} Miracle dice: it's set up at the end of the phase with "
        f"D3+{len(discarded)} wounds"
    )


def returned_model(game: Game, unit: Unit):
    # The unit's model set up again by Divine Intervention, if it was: the
    # unit is that one model now.
    for record in game.divine_interventions:
        if record.unit_id == unit.id and record.returned:
            return next(m for m in unit.unit_models if m.id == record.unit_model_id)
    return None


def end_of_phase(game: Game) -> None:
    # Divine Interventions this phase: each model's set up, unengaged and as
    # close as possible to where it was destroyed, with D3 (+1 a dice
    # discarded) wounds left.
    for record in game.divine_interventions:
        if record.returned or not _now(game, record):
            continue
        unit = deployment.find_unit(game, record.unit_id)
        model = next(m for m in unit.unit_models if m.id == record.unit_model_id)
        where = next(
            r for r in game.models_destroyed if r.unit_model_id == model.id and _now(game, r)
        )
        record.roll = dice.randint(1, 3)
        wounds = min(model.wounds, record.roll + len(record.discarded))
        damage = casualties.damage(game)[model.id]
        damage.destroyed = False
        damage.wounds_lost = model.wounds - wounds
        spot = _set_up_spot(game, unit, model, (where.x, where.y))
        if spot is None:
            # Nowhere to set it up: it stays destroyed.
            damage.destroyed = True
            damage.wounds_lost = model.wounds
        else:
            game.model_positions.append(
                GameModelPosition(unit_model_id=model.id, x=spot[0], y=spot[1], rotation=0.0)
            )
        record.returned = spot is not None


def _set_up_spot(game: Game, unit: Unit, model, start) -> tuple[float, float] | None:
    # The nearest spot to `start` the model can be set up: on the battlefield,
    # not overlapping models or terrain features, and unengaged.
    seat = deployment.owner(game, unit).seat
    others = deployment.placed_bases(game, unit)
    taken = [b for _, _, b in others]
    enemies = [b for p, _, b in others if p.seat != seat]
    features = deployment._features(game)
    from app.services.in_game.movement import ENGAGEMENT_RANGE

    def free(base, in_zone: bool) -> bool:
        return (
            deployment.wholly_within(base, BOARD)
            and not any(deployment.overlaps(base, other) for other in taken)
            and deployment._feature_overlapped(base, features) is None
            and not any(gap(base, e) <= ENGAGEMENT_RANGE + TOLERANCE for e in enemies)
        )

    if free(deployment.base_at(model, *start), True):
        return start
    return deployment._nearest_free(model, start, free)
