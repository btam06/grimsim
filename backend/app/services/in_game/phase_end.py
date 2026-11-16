from __future__ import annotations

from app.engine.state import PHASES, Game, GamePhaseEnd
from app.services.in_game import deployment, reinforcements

# The end step of a phase: when the player whose turn it is ends the phase,
# if either player has something to use or declare "at the end of the
# phase", the step opens and the phase waits - theirs first, then their
# opponent's, each until they say they're done; then the phase ends. Nothing
# else in the phase can happen meanwhile. What's used or declared then:
#
# - activated abilities for the end of the phase (activations.py "when":
#   "end" - e.g. Lord of the Storm, Invasion Beams);
# - a Resurrection Orb (any phase);
# - a unit going into Strategic Reserves at the end of the turn (Tunnelling
#   Horrors, the Fight phase - the last).
#
# (Those last two can be declared during the phase too.)


def _now(game: Game, record: GamePhaseEnd) -> bool:
    return (record.battle_round, record.turn_seat, record.phase) == (
        game.battle_round, game.turn_seat, game.phase
    )


def has_options(game: Game, seat: int) -> bool:
    # Whether the player has anything to declare for the end of this phase.
    from app.seeds.factions.necrons import reanimation

    # (A unit declared already: none of its player's can be, this turn. And
    # only one that's lost wounds or models - it'd do nothing otherwise.)
    from app.services.in_game import casualties

    hurt = {
        d.unit_model_id for d in casualties.damage(game).values() if d.wounds_lost or d.destroyed
    }
    if any(
        deployment.owner(game, u).seat == seat and any(m.id in hurt for m in u.unit_models)
        for u in reanimation.resurrectable(game)
    ):
        return True
    from app.services.in_game import activations

    if activations.step_options(game, seat, "end"):
        return True
    return game.phase == PHASES[-1] and any(
        not declared and deployment.owner(game, u).seat == seat
        for u, declared in reinforcements.turn_end_units(game)
    )


def opened(game: Game) -> bool:
    return any(_now(game, r) and r.seat is None for r in game.phase_end_windows)


def done(game: Game, seat: int) -> bool:
    return any(_now(game, r) and r.seat == seat for r in game.phase_end_windows)


def to_open(game: Game) -> bool:
    # Whether ending the phase opens the window: someone has something to
    # declare, and it hasn't been opened yet.
    if game.status != "in_progress" or game.phase not in PHASES or opened(game):
        return False
    return any(has_options(game, p.seat) for p in game.players)


def window_seat(game: Game) -> int | None:
    # Whose declarations for the end of the phase are to be made (or not)
    # now, once it's opened - None when they're all done.
    if game.status != "in_progress" or game.phase not in PHASES or not opened(game):
        return None
    turn = game.turn_seat
    other = next((p.seat for p in game.players if p.seat != turn), None)
    for seat in (turn, other):
        if seat is not None and not done(game, seat) and has_options(game, seat):
            return seat
    return None


def step_open(game: Game, seat: int) -> bool:
    # Whether the player can still use things at the end of this phase.
    return (
        game.status == "in_progress"
        and game.phase in PHASES
        and opened(game)
        and not done(game, seat)
    )


def blocks(game: Game) -> str | None:
    # Why nothing else can happen in the phase now: it's ending.
    if (seat := window_seat(game)) is None:
        return None
    return f"the phase is ending - waiting for player {seat} to finish with the end of the phase"


def open(game: Game) -> None:
    game.phase_end_windows.append(
        GamePhaseEnd(battle_round=game.battle_round, turn_seat=game.turn_seat, phase=game.phase)
    )


def finish(game: Game, seat: int) -> None:
    # The player's done declaring them for the end of this phase.
    game.phase_end_windows.append(
        GamePhaseEnd(
            battle_round=game.battle_round, turn_seat=game.turn_seat, phase=game.phase, seat=seat
        )
    )


# --- mortal wounds at the end of a phase (datasheet_abilities
# END_OF_PHASE_MORTALS - e.g. Bomb Rack: at the end of the opponent's Fight
# phase, six D6 against a visible enemy unit, not a Lone Operative, within
# 24"; 1 mortal wound per 4+) ---


MORTALS_ROLLED = "end_of_phase_mortals:"


def mortals(game: Game) -> None:
    # The end of the phase: each unit with such an ability, on the
    # battlefield, rolls against the closest unit it can (its player's pick,
    # in the rules - here the closest, as for Crimson Harvest).
    from app.seeds import datasheet_abilities
    from app.seeds.factions.adepta_sororitas.unit_abilities import visible_enemies
    from app.services import dice
    from app.services.in_game import casualties, charging, shooting

    from app.services.in_game import mission_state

    config = datasheet_abilities.END_OF_PHASE_MORTALS
    each = datasheet_abilities.END_OF_PHASE_EACH_ENEMY
    if not (config or each) or game.status != "in_progress":
        return
    # (Once a phase - ending it can pause, and run again.)
    kind = f"{MORTALS_ROLLED}{game.phase}"
    if any(
        m.battle_round == game.battle_round and m.turn_seat == game.turn_seat
        for m in mission_state.marked(game, kind)
    ):
        return
    mission_state.mark(game, game.turn_seat, kind, 0)
    for player in game.players:
        theirs = player.seat == game.turn_seat
        for unit in deployment.deployable_units(player):
            models = deployment.models_on_battlefield(game, unit)
            names = sorted({a.name for m in models for a in m.model.abilities} & set(config))
            for name in names:
                how = config[name]
                if how["phase"] != game.phase or theirs != (how["turn"] == "own"):
                    continue
                with_it = [m for m in models if any(a.name == name for a in m.model.abilities)]
                found = [
                    e
                    for e in visible_enemies(game, unit, how["range"], with_it)
                    if not shooting.lone_operative(game, e)
                ]
                if not found:
                    continue
                target = min(found, key=lambda e: (charging.distance(game, unit, e), e.id))
                wounds = sum(1 for _ in range(how["dice"]) if dice.randint(1, 6) >= how["on"])
                if wounds:
                    casualties.mortal_wounds(game, target, wounds, destroyed_by=unit)
    _each_enemy(game, each)


def _each_enemy(game: Game, config: dict) -> None:
    # END_OF_PHASE_EACH_ENEMY: at the end of the phase, one D6 for each enemy
    # unit within range of one or more of the player's models with the
    # ability - on `on`+, `wounds` mortal wounds (e.g. Drain Life: the Fight
    # phase, 6", 4+, D3; Warp Storms: your Movement phase, 9", 3+, D3).
    from app.services import dice
    from app.services.combat import roll_dice
    from app.services.in_game import casualties
    from app.services.in_game.deployment import TOLERANCE, gap

    placed = deployment.positions(game)

    def bases(unit, only=None):
        return [
            deployment.base_at(m, placed[m.id].x, placed[m.id].y, placed[m.id].rotation)
            for m in deployment.models_on_battlefield(game, unit)
            if m.id in placed and (only is None or any(a.name == only for a in m.model.abilities))
        ]

    for player in game.players:
        theirs = player.seat == game.turn_seat
        for name, how in sorted(config.items()):
            if how["phase"] != game.phase or (how["turn"] != "any" and theirs != (how["turn"] == "own")):
                continue
            sources = [
                (u, b) for u in deployment.deployable_units(player) for b in bases(u, name)
            ]
            if not sources:
                continue
            killer = sources[0][0]
            for other in game.players:
                if other.seat == player.seat:
                    continue
                for enemy in deployment.deployable_units(other):
                    theirs_b = bases(enemy)
                    if not theirs_b or not any(
                        gap(s, b) <= how["range"] + TOLERANCE for _, s in sources for b in theirs_b
                    ):
                        continue
                    if dice.randint(1, 6) >= how["on"]:
                        casualties.mortal_wounds(game, enemy, roll_dice(how["wounds"]), destroyed_by=killer)
