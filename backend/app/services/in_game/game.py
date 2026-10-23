from __future__ import annotations

import random

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ArmyList,
    Detachment,
    Game,
    GamePlayer,
    GameScore,
    GameSecondary,
    GameStratagemUse,
    GameTerrainLayout,
    PrimaryMission,
    SecondaryMission,
    Stratagem,
    User,
)
from app.models.game import BATTLE_ROUNDS, PHASES
from app.schemas import GameIn
from app.services.in_game import deployment as deployment_service
from app.services.in_game import terrain as terrain_service

# How many new tactical secondary cards a player draws in each of their
# command phases (11th edition: on top of any still held - no hand limit).
TACTICAL_DRAW = 2
FIXED_SECONDARY_COUNT = 2


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def player_at(game: Game, seat: int) -> GamePlayer:
    return next(p for p in game.players if p.seat == seat)


def other_seat(seat: int) -> int:
    return 2 if seat == 1 else 1


def mission_points(card: GameSecondary) -> int:
    # A secondary's VP for the mode its holder is using.
    mission = card.mission
    if card.player.secondary_mode == "fixed":
        return mission.fixed_points or 0
    return mission.tactical_points or 0


async def create_game(session: AsyncSession, payload: GameIn) -> Game:
    users = {
        u.id: u
        for u in (
            await session.execute(
                select(User).where(User.id.in_([p.user_id for p in payload.players]))
            )
        ).scalars()
    }
    if len(users) != 2:
        raise _bad_request("a game needs two different, existing users")

    players: list[GamePlayer] = []
    for seat, spec in enumerate(payload.players, start=1):
        army_list = (
            await session.execute(
                select(ArmyList)
                .options(
                    selectinload(ArmyList.owner),
                    selectinload(ArmyList.detachments).selectinload(Detachment.dispositions),
                )
                .where(ArmyList.id == spec.list_id)
            )
        ).scalar_one_or_none()
        if army_list is None:
            raise _bad_request(f"player {seat}: list not found")
        if army_list.owner is None or army_list.owner.id != spec.user_id:
            raise _bad_request(f"player {seat}: that list doesn't belong to that user")

        # The player's disposition comes from their list's detachments.
        candidates = {
            d.id: d for detachment in army_list.detachments for d in detachment.dispositions
        }
        if spec.disposition_id is not None:
            if spec.disposition_id not in candidates:
                raise _bad_request(f"player {seat}: that disposition isn't on their detachments")
            disposition_id = spec.disposition_id
        elif len(candidates) == 1:
            disposition_id = next(iter(candidates))
        elif len(candidates) > 1:
            raise _bad_request(f"player {seat}: choose one of their list's dispositions")
        else:
            disposition_id = None

        secondaries: list[GameSecondary] = []
        if spec.secondary_mode == "fixed":
            ids = set(spec.fixed_secondary_ids)
            if len(ids) != FIXED_SECONDARY_COUNT:
                raise _bad_request(
                    f"player {seat}: choose {FIXED_SECONDARY_COUNT} different fixed secondaries"
                )
            missions = (
                await session.execute(select(SecondaryMission).where(SecondaryMission.id.in_(ids)))
            ).scalars().all()
            if len(missions) != len(ids) or any(m.fixed_points is None for m in missions):
                raise _bad_request(f"player {seat}: those secondaries can't be used as fixed")
            secondaries = [
                GameSecondary(mission=m, fixed=True, status="active", drawn_round=0)
                for m in missions
            ]
        elif spec.fixed_secondary_ids:
            raise _bad_request(f"player {seat}: only fixed mode picks secondaries up front")

        players.append(
            GamePlayer(
                seat=seat,
                user_id=spec.user_id,
                list_id=spec.list_id,
                secondary_mode=spec.secondary_mode,
                disposition_id=disposition_id,
                cp=0,
                secondaries=secondaries,
            )
        )

    # Each player's primary mission, from their disposition and their opponent's.
    for player in players:
        opponent = players[1] if player is players[0] else players[0]
        if player.disposition_id is not None and opponent.disposition_id is not None:
            player.primary_mission_id = (
                await session.execute(
                    select(PrimaryMission.id).where(
                        PrimaryMission.player_disposition_id == player.disposition_id,
                        PrimaryMission.opponent_disposition_id == opponent.disposition_id,
                    )
                )
            ).scalar_one_or_none()

    game = Game(
        status="setup",
        attacker_seat=payload.attacker_seat,
        first_seat=payload.first_seat,
        battle_round=0,
        players=players,
    )
    # Its terrain: a layout for the attacker's and defender's dispositions.
    attacker = next(p for p in players if p.seat == payload.attacker_seat)
    defender = next(p for p in players if p.seat != payload.attacker_seat)
    layout = await terrain_service.pick_layout(
        session, attacker.disposition_id, defender.disposition_id
    )
    if layout is not None:
        game.layout_link = GameTerrainLayout(layout=layout)
    session.add(game)
    return game


def _require_in_progress(game: Game) -> None:
    if game.status != "in_progress":
        raise _bad_request("the game isn't in progress")


async def _draw_tactical(
    session: AsyncSession, game: Game, player: GamePlayer, count: int = TACTICAL_DRAW
) -> None:
    # A tactical player draws `count` new cards (TACTICAL_DRAW in their command
    # phase), keeping any they still hold - from the tactical secondaries they
    # haven't drawn yet this game.
    if player.secondary_mode != "tactical":
        return
    seen = {c.secondary_mission_id for c in player.secondaries}
    deck = [
        m
        for m in (
            await session.execute(
                select(SecondaryMission).where(SecondaryMission.tactical_points.is_not(None))
            )
        ).scalars()
        if m.id not in seen
    ]
    for _ in range(count):
        if not deck:
            break
        mission = deck.pop(random.randrange(len(deck)))
        player.secondaries.append(
            GameSecondary(
                secondary_mission_id=mission.id,
                mission=mission,
                fixed=False,
                status="active",
                drawn_round=game.battle_round,
            )
        )


async def _begin_command_phase(session: AsyncSession, game: Game) -> None:
    # Both players gain 1 CP; the player whose turn it is draws secondaries.
    game.phase = "command"
    for player in game.players:
        player.cp += 1
    await _draw_tactical(session, game, player_at(game, game.turn_seat))


def enter_deployment(game: Game) -> None:
    # A new game goes straight to deployment, if its battlefield has
    # deployment zones and there's anything to set up in them.
    if game.status == "setup" and deployment_service.can_deploy(game):
        game.status = "deployment"


async def _begin_battle(session: AsyncSession, game: Game) -> None:
    game.status = "in_progress"
    game.battle_round = 1
    game.turn_seat = game.first_seat
    await _begin_command_phase(session, game)


async def start_game(session: AsyncSession, game: Game) -> None:
    # Deployment first, if there's any (see enter_deployment); otherwise the
    # first battle round.
    if game.status != "setup":
        raise _bad_request("the game has already started")
    enter_deployment(game)
    if game.status == "setup":
        await _begin_battle(session, game)


async def deploy_unit(
    session: AsyncSession, game: Game, unit, placement: dict[int, tuple[float, float, float]]
) -> None:
    # Sets a unit up; once every unit is, the first battle round begins.
    deployment_service.deploy(game, unit, placement)
    if deployment_service.deploying_seat(game) is None:
        await _begin_battle(session, game)


async def advance(session: AsyncSession, game: Game) -> None:
    # On to the next phase; after the fight phase, the next turn - the second
    # player's, or the next battle round's first. The game ends after the
    # last battle round's second turn.
    _require_in_progress(game)
    index = PHASES.index(game.phase)
    if index + 1 < len(PHASES):
        game.phase = PHASES[index + 1]
        return
    if game.turn_seat == game.first_seat:
        game.turn_seat = other_seat(game.first_seat)
    elif game.battle_round >= BATTLE_ROUNDS:
        game.status = "finished"
        game.phase = None
        game.turn_seat = None
        return
    else:
        game.battle_round += 1
        game.turn_seat = game.first_seat
    await _begin_command_phase(session, game)


def stratagem_unavailable_reason(
    game: Game, player: GamePlayer, stratagem: Stratagem
) -> str | None:
    # Why a player can't use a stratagem right now, or None if they can.
    if game.status != "in_progress":
        return "the game isn't in progress"
    if not stratagem.is_core and not (
        {d.id for d in stratagem.detachments} & {d.id for d in player.army_list.detachments}
    ):
        return "it isn't from one of their list's detachments"
    if stratagem.timings:
        whose = "your_turn" if game.turn_seat == player.seat else "opponent_turn"
        if not any(
            t.phase == game.phase and t.turn in (whose, "either") for t in stratagem.timings
        ):
            return f"it can't be used in the {game.phase} phase of this turn"
    if any(
        use.stratagem_id == stratagem.id
        and use.battle_round == game.battle_round
        and use.turn_seat == game.turn_seat
        and use.phase == game.phase
        for use in player.stratagem_uses
    ):
        # Each stratagem can be used once per phase (by each player).
        return "it has already been used this phase"
    if player.cp < stratagem.cp:
        return "not enough CP"
    if stratagem.game_action == "replace_secondary" and not replaceable_secondaries(player):
        return "they have no active tactical Secondary Mission to replace"
    return None


def replaceable_secondaries(player: GamePlayer) -> list[GameSecondary]:
    # The cards New Orders-style stratagems can target: the player's active
    # tactical (not fixed) Secondary Missions.
    return [c for c in player.secondaries if c.status == "active" and not c.fixed]


async def use_stratagem(
    session: AsyncSession,
    game: Game,
    player: GamePlayer,
    stratagem: Stratagem,
    target_secondary_id: int | None = None,
) -> None:
    reason = stratagem_unavailable_reason(game, player, stratagem)
    if reason is not None:
        raise _bad_request(f"can't use {stratagem.name}: {reason}")

    target = None
    if stratagem.game_action == "replace_secondary":
        target = next(
            (c for c in replaceable_secondaries(player) if c.id == target_secondary_id), None
        )
        if target is None:
            raise _bad_request(
                f"{stratagem.name} needs one of their active tactical Secondary Missions "
                "as its target"
            )
    elif target_secondary_id is not None:
        raise _bad_request(f"{stratagem.name} doesn't take a target")

    player.cp -= stratagem.cp
    player.stratagem_uses.append(
        GameStratagemUse(
            stratagem_id=stratagem.id,
            stratagem=stratagem,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            phase=game.phase,
            cp=stratagem.cp,
        )
    )
    if target is not None:
        # Discard the target and draw one new card in its place.
        target.status = "discarded"
        await _draw_tactical(session, game, player, count=1)


def achieve_secondary(game: Game, card: GameSecondary, points: int | None = None) -> None:
    # Scores the card's VP for the player's mode, or `points` if given (many
    # cards score more or less depending on the outcome).
    _require_in_progress(game)
    player = card.player
    if card.status != "active":
        raise _bad_request("that secondary isn't active")
    completes_on = card.mission.completes_on
    if completes_on != "either":
        completes_on_your_turn = completes_on == "your_turn"
        if completes_on_your_turn != (game.turn_seat == player.seat):
            whose = "their own" if completes_on_your_turn else "their opponent's"
            raise _bad_request(f"{card.mission.name} can only be completed in {whose} turn")
    if any(
        s.game_secondary_id == card.id
        and s.battle_round == game.battle_round
        and s.turn_seat == game.turn_seat
        for s in player.scores
    ):
        raise _bad_request(f"{card.mission.name} has already been scored this turn")

    player.scores.append(
        GameScore(
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            kind="secondary",
            points=mission_points(card) if points is None else points,
            game_secondary_id=card.id,
        )
    )
    # A tactical card is done once achieved; a fixed one stays for later turns.
    if not card.fixed:
        card.status = "achieved"


def discard_secondary(game: Game, card: GameSecondary) -> None:
    _require_in_progress(game)
    if card.fixed:
        raise _bad_request("fixed secondaries can't be discarded")
    if card.status != "active":
        raise _bad_request("that secondary isn't active")
    card.status = "discarded"


def score_primary(game: Game, player: GamePlayer, points: int) -> None:
    _require_in_progress(game)
    player.scores.append(
        GameScore(
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            kind="primary",
            points=points,
        )
    )
