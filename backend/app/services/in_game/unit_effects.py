from __future__ import annotations

from app.engine.state import Game, GameUnitEffect
from app.models import Unit
from app.services.in_game import deployment

# What abilities do to units for a while, in a game - e.g. Electro-shock: the
# enemy unit it shoots is shocked until the end of its next turn, -2" Move
# and -2 to its Advance and Charge rolls; Shattered Defences: friendly
# ADEPTUS ASTARTES units' ranged attacks against the MONSTER or VEHICLE it hit
# have +1 AP (see datasheet_abilities AFTER_SHOOTING_EFFECTS). An effect lasts until the end of a turn - turns
# counted one after another through the battle (see turn_index); the same
# ability's effect again on a unit replaces it, different abilities' add up.


def turn_index(game: Game, battle_round: int | None = None, turn_seat: int | None = None) -> int:
    # The turns in order: each battle round's first player's, then the
    # other's. (Now, by default.)
    battle_round = game.battle_round if battle_round is None else battle_round
    turn_seat = game.turn_seat if turn_seat is None else turn_seat
    return battle_round * 2 + (0 if turn_seat == game.first_seat else 1)


def until_their_next_turn(game: Game) -> int:
    # The end of the next turn of the player whose turn it isn't - the next
    # turn (turns alternate).
    return turn_index(game) + 1


def apply(
    game: Game,
    unit: Unit,
    source: str,
    until_turn: int,
    move: int = 0,
    advance: int = 0,
    charge: int = 0,
    source_unit: Unit | None = None,
    ranged_ap: int = 0,
    by_keyword: str | None = None,
    melee_skill: int = 0,
) -> GameUnitEffect:
    for old in [e for e in game.unit_effects if e.unit_id == unit.id and e.source == source]:
        game.unit_effects.remove(old)
    effect = GameUnitEffect(
        unit_id=unit.id,
        source=source,
        source_unit_id=source_unit.id if source_unit is not None else None,
        move=move,
        advance=advance,
        charge=charge,
        ranged_ap=ranged_ap,
        by_keyword=by_keyword,
        melee_skill=melee_skill,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        until_turn=until_turn,
    )
    game.unit_effects.append(effect)
    return effect


def active(game: Game, unit: Unit) -> list[GameUnitEffect]:
    if game.status != "in_progress" or game.turn_seat is None:
        return []
    now = turn_index(game)
    return [e for e in game.unit_effects if e.unit_id == unit.id and now <= e.until_turn]


def move_change(game: Game, unit: Unit) -> int:
    # What its effects add to its models' Move characteristic now.
    return sum(e.move for e in active(game, unit))


def roll_change(game: Game, unit: Unit, roll: str) -> int:
    # What its effects add to its `roll` ("advance", "charge") now.
    return sum(getattr(e, roll) for e in active(game, unit))


def attack_rules(game: Game, attacker: Unit, target: Unit) -> list:
    # Rules for the attacker's attacks against the target from the target's
    # effects - e.g. +1 AP for ranged attacks by ADEPTUS ASTARTES units
    # (Shattered Defences).
    from app.combat_rules import Rule
    from app.combat_rules.conditions import RANGED_ATTACK
    from app.combat_rules.effects import IMPROVE_AP

    keywords = {k.name for m in attacker.unit_models for k in m.model.keywords}
    seat = deployment.owner(game, attacker).seat

    def friendly(effect: GameUnitEffect) -> bool:
        # (The attacker is on the side of the unit it's from.)
        if effect.source_unit_id is None:
            return True
        source = deployment.find_unit(game, effect.source_unit_id)
        return deployment.owner(game, source).seat == seat

    return [
        Rule(conditions=(RANGED_ATTACK,), effects=(IMPROVE_AP,))
        for e in active(game, target)
        if e.ranged_ap and (e.by_keyword is None or e.by_keyword in keywords) and friendly(e)
    ]


def own_attack_rules(game: Game, unit: Unit) -> list:
    # Rules for the unit's own attacks from its effects - e.g. its melee
    # weapons' Weapon Skill worsened (Data-spike).
    from app.combat_rules import Rule
    from app.combat_rules.conditions import MELEE_ATTACK
    from app.combat_rules.effects import WORSE_MELEE_SKILL

    return [
        Rule(conditions=(MELEE_ATTACK,), effects=(WORSE_MELEE_SKILL,))
        for e in active(game, unit)
        if e.melee_skill
    ][:1]


def after_shooting(game: Game, unit: Unit, target: Unit, hits: int) -> list[GameUnitEffect]:
    # The unit has shot `target` in its Shooting phase, scoring `hits`: its
    # abilities that do something to an enemy unit it hit (e.g. Electro-shock)
    # do - until the end of that unit's next turn (or this one).
    from app.seeds import datasheet_abilities

    if game.phase != "shooting" or deployment.owner(game, unit).seat != game.turn_seat:
        return []
    if hits <= 0 or not deployment.models_on_battlefield(game, target):
        return []
    config = datasheet_abilities.AFTER_SHOOTING_EFFECTS
    names = {
        a.name for m in deployment.models_on_battlefield(game, unit) for a in m.model.abilities
    }
    keywords = {k.name for m in target.unit_models for k in m.model.keywords}
    found = []
    for name in sorted(names & set(config)):
        effect = config[name]
        if keywords & set(effect.excluded_keywords):
            continue
        if effect.required_keywords and not keywords & set(effect.required_keywords):
            continue
        until = until_their_next_turn(game) if effect.lasts == "their next turn" else turn_index(game)
        found.append(
            apply(
                game, target, name, until,
                move=effect.move, advance=effect.advance, charge=effect.charge,
                source_unit=unit, ranged_ap=effect.ranged_ap, by_keyword=effect.by_keyword,
            )
        )
    return found


def describe(effect: GameUnitEffect) -> str:
    # E.g. 'Electro-shock: -2" Move, -2 to Advance and Charge rolls'.
    parts = []
    if effect.move:
        parts.append(f'{effect.move:+d}" Move')
    rolls = [r for r in ("advance", "charge") if getattr(effect, r)]
    if rolls and len({getattr(effect, r) for r in rolls}) == 1:
        parts.append(
            f"{getattr(effect, rolls[0]):+d} to "
            + " and ".join(r.capitalize() for r in rolls)
            + " rolls"
        )
    else:
        parts += [f"{getattr(effect, r):+d} to {r.capitalize()} rolls" for r in rolls]
    if effect.melee_skill:
        parts.append(f"melee Weapon Skill worsened by {effect.melee_skill}")
    if effect.ranged_ap:
        parts.append(
            f"+{effect.ranged_ap} AP for ranged attacks against it"
            + (f" by {effect.by_keyword} units" if effect.by_keyword else "")
        )
    return f"{effect.source}: " + ", ".join(parts)
