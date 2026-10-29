from __future__ import annotations

import random

from fastapi import HTTPException

from app.models import Game, GamePlayer, GameStratagemOutcome, GameStratagemUse, Stratagem, Unit
from app.services.in_game import casualties, charging, deployment, fighting, movement, shooting
from app.services.in_game.deployment import TOLERANCE, gap
from app.services.list_building import enhancements as enhancement_rules

# The core stratagems' game actions (15.02-15.12) - those beyond what the
# combat calculator does, or than Rapid Ingress, Fire Overwatch and Insane
# Bravery (see reinforcements.py, overwatch.py and battle_shock.py). Each is
# used on one of the player's units, some with something else picked from
# the unit's choices (see app/services/in_game/stratagem_actions.py):
#
# - Explosives (your Shooting phase): an unengaged EXPLOSIVES/GRENADES unit
#   that hasn't shot or Advanced this turn picks an unengaged enemy unit
#   within 8" of and visible to one of its EXPLOSIVES/GRENADES models - six
#   D6, a mortal wound for each 4+.
# - Crushing Impact (your Charge phase): a MONSTER/VEHICLE unit that's made
#   its charge move picks an enemy unit it's engaged with - a D6 for each
#   point of T of its toughest model engaged with that unit: each 1, a mortal
#   wound on itself; each 5+, one on the enemy unit (at most 6 each).
# - Smokescreen (the start of your opponent's Shooting phase - before any of
#   their units has shot): until the end of the phase, attacks against the
#   SMOKE unit give it the benefit of cover. (A unit not fully visible because
#   of the SMOKE unit's models: models don't block line of sight here.)
# - Epic Challenge (the Fight phase, a CHARACTER unit that can fight now):
#   one of its CHARACTER models' melee weapons have [PRECISION] until the end
#   of the phase.
# - Counteroffensive (your opponent's Fight step, just after an enemy unit
#   fought): a unit of yours eligible to fight has Fights First until the end
#   of the phase, and it's the next unit you pick to fight (see
#   app/services/in_game/fighting.py).
# - Heroic Intervention (the end of your opponent's Charge phase - see
#   charge_ended): an unengaged unit within 12" of an enemy unit (a VEHICLE
#   only if it's a CHARACTER or WALKER) charges (see
#   app/services/in_game/charging.py), Leaping to Defend (only enemy units
#   that charged this phase) or - for 1CP more - Into the Fray (a charge roll
#   of at most 6; any enemy units within 6").
# - Command Re-roll: re-rolls a unit's Advance roll (before it's moved with
#   it) or its charge roll in full (before it's charged). Rolls in attacks
#   (Hit, Wound, Save, Damage...) are re-rolled in the combat calculator.

EXPLOSIVES = "explosives"
CRUSHING_IMPACT = "crushing_impact"
SMOKESCREEN = "smokescreen"
EPIC_CHALLENGE = "epic_challenge"
COUNTEROFFENSIVE = "counteroffensive"
HEROIC_INTERVENTION = "heroic_intervention"
COMMAND_REROLL = "command_reroll"
ACTIONS = (
    EXPLOSIVES,
    CRUSHING_IMPACT,
    SMOKESCREEN,
    EPIC_CHALLENGE,
    COUNTEROFFENSIVE,
    HEROIC_INTERVENTION,
    COMMAND_REROLL,
)

EXPLOSIVES_KEYWORDS = {"EXPLOSIVES", "GRENADES"}
EXPLOSIVES_RANGE = 8.0
EXPLOSIVES_DICE = 6
CRUSHING_MAX = 6
HEROIC_RANGE = 12.0
FRAY_RANGE = 6.0
FRAY_MAX_ROLL = 6
# Heroic Intervention's modes, and Command Re-roll's rolls (choice ids).
LEAP_TO_DEFEND, INTO_THE_FRAY = 1, 2
ADVANCE_ROLL, CHARGE_ROLL = 1, 2


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _this_phase(game: Game, record) -> bool:
    return (
        record.battle_round == game.battle_round
        and record.turn_seat == game.turn_seat
        and record.phase == game.phase
    )


def used_on(game: Game, action: str, unit: Unit) -> GameStratagemUse | None:
    # The use of a stratagem with that game action on the unit this phase.
    return next(
        (
            use
            for player in game.players
            for use in player.stratagem_uses
            if use.stratagem.game_action == action
            and use.target_unit_id == unit.id
            and _this_phase(game, use)
        ),
        None,
    )


def _keywords(unit: Unit, unit_model) -> set[str]:
    return enhancement_rules.model_keywords(unit, unit_model)


def _unit_keywords(unit: Unit) -> set[str]:
    return {k for m in unit.unit_models for k in _keywords(unit, m)}


def _bases(game: Game, unit: Unit) -> dict:
    placed = deployment.positions(game)
    return {
        m.id: deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
        for m in unit.unit_models
        if m.id in placed
    }


# --- the end of the Charge phase (Heroic Intervention) ---


def charge_ended(game: Game) -> bool:
    # Whether the player whose turn it is has finished charging this phase.
    return game.phase == "charge" and any(
        c.battle_round == game.battle_round and c.turn_seat == game.turn_seat
        for c in game.charges_ended
    )


def end_charges(game: Game) -> None:
    from app.models import GameChargeEnded

    game.charges_ended.append(
        GameChargeEnded(battle_round=game.battle_round, turn_seat=game.turn_seat)
    )


def heroic_mode(game: Game, unit: Unit) -> int | None:
    # The unit's Heroic Intervention mode this phase, if it's intervening.
    use = used_on(game, HEROIC_INTERVENTION, unit)
    return use.choice_id if use is not None else None


# --- what each can be used on ---


def _explosive_models(game: Game, unit: Unit) -> list:
    return [
        m
        for m in deployment.models_on_battlefield(game, unit)
        if _keywords(unit, m) & EXPLOSIVES_KEYWORDS
    ]


def _explosives_targets(game: Game, unit: Unit) -> list[Unit]:
    # Unengaged enemy units within 8" of and visible to one of its
    # EXPLOSIVES/GRENADES models.
    sight = shooting.Sight(game)
    mine = _bases(game, unit)
    throwers = [mine[m.id] for m in _explosive_models(game, unit) if m.id in mine]
    return [
        enemy
        for enemy in charging.enemy_units(game, unit)
        if not movement.in_engagement_range(game, enemy)
        and any(
            gap(t, e) <= EXPLOSIVES_RANGE + TOLERANCE and sight.sees(t, e)
            for t in throwers
            for e in _bases(game, enemy).values()
        )
    ]


def choices(game: Game, player: GamePlayer, stratagem: Stratagem, unit: Unit) -> list:
    from app.services.in_game.stratagem_actions import Choice

    action = stratagem.game_action
    if action == EXPLOSIVES:
        return [Choice(e.id, e.label) for e in _explosives_targets(game, unit)]
    if action == CRUSHING_IMPACT:
        return [Choice(e.id, e.label) for e in fighting.fight_targets(game, unit)]
    if action == EPIC_CHALLENGE:
        return [
            Choice(m.id, m.model.name)
            for m in deployment.models_on_battlefield(game, unit)
            if "CHARACTER" in _keywords(unit, m)
        ]
    if action == HEROIC_INTERVENTION:
        found = [Choice(LEAP_TO_DEFEND, "Leap to Defend")]
        if player.cp >= stratagem.cp + 1:
            found.append(Choice(INTO_THE_FRAY, "Into the Fray (+1CP)"))
        return found
    if action == COMMAND_REROLL:
        found = []
        move = movement.unit_move(game, unit)
        if move is not None and move.advance_roll is not None and not move.completed:
            found.append(Choice(ADVANCE_ROLL, f"Advance roll ({move.advance_roll})"))
        charge = charging.unit_charge(game, unit)
        if charge is not None and not charge.completed:
            found.append(Choice(CHARGE_ROLL, f"Charge roll ({charge.roll})"))
        return found
    return []


def target_reason(
    game: Game, player: GamePlayer, stratagem: Stratagem, unit: Unit
) -> str | None:
    # Why the stratagem can't be used on the unit now (its owner and
    # keywords already checked), or None if it can.
    action = stratagem.game_action
    if not deployment.models_on_battlefield(game, unit):
        return "it isn't on the battlefield"
    if action == EXPLOSIVES:
        if movement.in_engagement_range(game, unit):
            return "it's engaged"
        if shooting.unit_shot(game, unit) is not None:
            return "it has already shot this turn"
        if shooting.move_status(game, unit).advanced:
            return "it Advanced this turn"
        if not choices(game, player, stratagem, unit):
            return 'no unengaged enemy unit is within 8" of and visible to it'
        return None
    if action == CRUSHING_IMPACT:
        charge = charging.unit_charge(game, unit)
        if charge is None or not charge.completed:
            return "it hasn't made a charge move this phase"
        if not choices(game, player, stratagem, unit):
            return "it isn't engaged with an enemy unit"
        return None
    if action == SMOKESCREEN:
        if any(
            deployment.owner(game, deployment.find_unit(game, s.unit_id)).seat == game.turn_seat
            and shooting._this_turn(game, s)
            for s in game.unit_shots
        ):
            return "it's used at the start of the opponent's Shooting phase"
        return None
    if action == EPIC_CHALLENGE:
        if fighting.cant_fight_reason(game, unit) is not None:
            return "it isn't the unit selected to fight now"
        if not choices(game, player, stratagem, unit):
            return "it has no CHARACTER model on the battlefield"
        return None
    if action == COUNTEROFFENSIVE:
        if fighting.fight_step(game) not in ("fights_first", "remaining"):
            return "it's used in the Fight step"
        fights = fighting._fights(game)
        if not fights or fights[-1].seat == player.seat:
            return "it's used just after an enemy unit has fought"
        if not fighting.eligible_to_fight(game, unit):
            return "it isn't eligible to fight"
        return None
    if action == HEROIC_INTERVENTION:
        if not charge_ended(game):
            return "it's used at the end of the opponent's Charge phase"
        if movement.in_engagement_range(game, unit):
            return "it's engaged"
        if not any(
            charging.distance(game, unit, e) <= HEROIC_RANGE + TOLERANCE
            for e in charging.enemy_units(game, unit)
        ):
            return 'no enemy unit is within 12"'
        keywords = _unit_keywords(unit)
        if "VEHICLE" in keywords and not keywords & {"CHARACTER", "WALKER"}:
            return "a VEHICLE unit has to be a CHARACTER or WALKER"
        return None
    if action == COMMAND_REROLL:
        if not choices(game, player, stratagem, unit):
            return (
                "it has no Advance or charge roll to re-roll now (re-roll attack rolls in "
                "the combat calculator)"
            )
        return None
    return None


# --- what each does ---


def _outcome(use: GameStratagemUse, text: str, choice_id: int | None) -> None:
    use.outcome_link = GameStratagemOutcome(text=text, choice_id=choice_id)


def carry_out(
    game: Game,
    player: GamePlayer,
    stratagem: Stratagem,
    unit: Unit,
    choice_id: int | None,
    use: GameStratagemUse,
) -> None:
    action = stratagem.game_action
    if action == SMOKESCREEN:
        _outcome(use, f"{unit.label} has the benefit of cover this phase", None)
        return
    if action == COUNTEROFFENSIVE:
        _outcome(use, f"{unit.label} has Fights First and fights next", None)
        return
    # (Heroic Intervention's mode was checked before its CP were spent.)
    if action == HEROIC_INTERVENTION:
        if choice_id not in (LEAP_TO_DEFEND, INTO_THE_FRAY):
            raise _bad_request("pick Leap to Defend or Into the Fray")
    elif choice_id not in {c.id for c in choices(game, player, stratagem, unit)}:
        raise _bad_request(f"{stratagem.name} needs one of its choices for that unit")
    if action == EXPLOSIVES:
        enemy = deployment.find_unit(game, choice_id)
        rolls = [random.randint(1, 6) for _ in range(EXPLOSIVES_DICE)]
        wounds = sum(1 for r in rolls if r >= 4)
        casualties.mortal_wounds(game, enemy, wounds, destroyed_by=unit)
        _outcome(
            use,
            f"Rolled {', '.join(map(str, rolls))}: {wounds} mortal wounds on {enemy.label}",
            choice_id,
        )
    elif action == CRUSHING_IMPACT:
        enemy = deployment.find_unit(game, choice_id)
        theirs = list(_bases(game, enemy).values())
        mine = _bases(game, unit)
        engaged = [
            m
            for m in deployment.models_on_battlefield(game, unit)
            if m.id in mine
            and any(gap(mine[m.id], t) <= movement.ENGAGEMENT_RANGE + TOLERANCE for t in theirs)
        ]
        model = max(engaged, key=lambda m: m.model.toughness)
        rolls = [random.randint(1, 6) for _ in range(model.model.toughness)]
        to_enemy = min(sum(1 for r in rolls if r >= 5), CRUSHING_MAX)
        to_self = min(sum(1 for r in rolls if r == 1), CRUSHING_MAX)
        casualties.mortal_wounds(game, enemy, to_enemy, destroyed_by=unit)
        casualties.mortal_wounds(game, unit, to_self)
        _outcome(
            use,
            f"Rolled {len(rolls)} D6 ({', '.join(map(str, rolls))}): {to_enemy} mortal wounds "
            f"on {enemy.label}, {to_self} on {unit.label}",
            choice_id,
        )
    elif action == EPIC_CHALLENGE:
        model = next(m for m in unit.unit_models if m.id == choice_id)
        _outcome(use, f"{model.model.name}'s melee weapons have [PRECISION]", choice_id)
    elif action == HEROIC_INTERVENTION:
        if choice_id == INTO_THE_FRAY:
            if player.cp < 1:
                raise _bad_request("Into the Fray costs 1CP more")
            player.cp -= 1
            use.cp += 1
        mode = "Into the Fray" if choice_id == INTO_THE_FRAY else "Leap to Defend"
        _outcome(use, f"{unit.label} charges: {mode}", choice_id)
    elif action == COMMAND_REROLL:
        if choice_id == ADVANCE_ROLL:
            move = movement.unit_move(game, unit)
            before = move.advance_roll
            move.advance_roll = random.randint(1, 6)
            _outcome(use, f"Advance roll {before} re-rolled: {move.advance_roll}", choice_id)
        else:
            charge = charging.unit_charge(game, unit)
            before = charge.roll
            charge.first_die, charge.second_die = (
                random.randint(1, 6) for _ in range(charging.CHARGE_DICE)
            )
            _outcome(use, f"Charge roll {before} re-rolled: {charge.roll}", choice_id)


# --- their effects elsewhere ---


def smokescreened(game: Game, unit: Unit) -> bool:
    return game.phase == "shooting" and used_on(game, SMOKESCREEN, unit) is not None


def precision_models(game: Game, unit: Unit) -> set[int]:
    # The unit's models whose melee weapons have [PRECISION] this phase.
    use = used_on(game, EPIC_CHALLENGE, unit)
    return {use.choice_id} if use is not None and use.choice_id is not None else set()


def counteroffensive_unit(game: Game, seat: int) -> int | None:
    # The player's unit that used Counteroffensive this phase and hasn't
    # fought yet, if any.
    player = next(p for p in game.players if p.seat == seat)
    for use in player.stratagem_uses:
        if (
            use.stratagem.game_action == COUNTEROFFENSIVE
            and _this_phase(game, use)
            and use.target_unit_id is not None
            and not fighting.fought(game, deployment.find_unit(game, use.target_unit_id))
        ):
            return use.target_unit_id
    return None
