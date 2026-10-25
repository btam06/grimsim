from __future__ import annotations

from fastapi import HTTPException

from app.models import Game, GameClaimOffer, GameScore, GameScoreReason, GameScoringStep
from app.services.in_game import mission_cards
from app.services.in_game.mission_context import Context

# Automatic scoring. At each scoring moment - the end of a Command phase,
# the end of a turn, the end of the battle - every card in play is checked
# for its holder (see app/services/in_game/mission_cards.py):
#
# - primary missions and fixed secondaries score what they've met, there
#   and then;
# - a tactical secondary that's been met is offered to its holder: claim it
#   (scored, and the card is done) or hold it (it stays in their hand, and
#   is checked again at its next scoring moments - so it can be claimed when
#   it's worth more). The game waits for each offer to be answered.
#
# Each moment is checked once. Cards (and lines) the code doesn't score
# are scored by hand, as before.
#
# A player scores at most 15VP from primary missions, and 15VP from
# secondaries, in each battle round (see `room`): anything over is lost.

MAX_PER_ROUND = {"primary": 15, "secondary": 15}
COMMAND_END = "command_end"
TURN_END = "turn_end"
BATTLE_END = "battle_end"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _now(game: Game) -> dict:
    return {"battle_round": game.battle_round, "turn_seat": game.turn_seat}


def evaluated(game: Game, timing: str) -> bool:
    return any(
        s.battle_round == game.battle_round
        and s.turn_seat == game.turn_seat
        and s.timing == timing
        for s in game.scoring_steps
    )


def pending_offers(game: Game) -> list[GameClaimOffer]:
    return [o for o in game.claim_offers if o.status == "pending"]


def _reasons(lines: list[tuple[str, int]]) -> list[GameScoreReason]:
    return [GameScoreReason(text=text, points=points) for text, points in lines]


def room(player, battle_round: int, kind: str) -> int:
    # How much more of `kind` ("primary" or "secondary") VP the player can
    # score in that battle round.
    scored = sum(
        s.points for s in player.scores if s.battle_round == battle_round and s.kind == kind
    )
    return max(0, MAX_PER_ROUND[kind] - scored)


def capped(player, battle_round: int, kind: str, lines: list[tuple[str, int]]):
    # The VP the lines score, within the player's room this battle round -
    # and the lines, with a note if some was lost.
    total = sum(p for _, p in lines)
    allowed = min(total, room(player, battle_round, kind))
    if allowed < total:
        lines = lines + [
            (f"Capped at {MAX_PER_ROUND[kind]}VP {kind} per battle round", allowed - total)
        ]
    return allowed, lines


def score(game: Game, timing: str) -> None:
    # Checks every card in play at this scoring moment (once).
    if evaluated(game, timing):
        return
    game.scoring_steps.append(GameScoringStep(**_now(game), timing=timing))
    for player in game.players:
        mission = player.primary_mission
        card = mission_cards.PRIMARIES.get(mission.name) if mission else None
        if card is not None:
            lines = list(card(Context(game, player.seat, timing, **_now(game))))
            if lines:
                points, lines = capped(player, game.battle_round, "primary", lines)
                player.scores.append(
                    GameScore(
                        **_now(game), kind="primary", points=points, reasons=_reasons(lines)
                    )
                )
        for secondary in player.secondaries:
            card = mission_cards.SECONDARIES.get(secondary.mission.name)
            if secondary.status != "active" or card is None:
                continue
            mode = "fixed" if secondary.fixed else "tactical"
            lines = list(card(Context(game, player.seat, timing, **_now(game), mode=mode)))
            if not lines:
                continue
            if secondary.fixed:
                points, lines = capped(player, game.battle_round, "secondary", lines)
                player.scores.append(
                    GameScore(
                        **_now(game),
                        kind="secondary",
                        points=points,
                        game_secondary_id=secondary.id,
                        reasons=_reasons(lines),
                    )
                )
            else:
                game.claim_offers.append(
                    GameClaimOffer(
                        **_now(game),
                        game_secondary_id=secondary.id,
                        timing=timing,
                        points=sum(p for _, p in lines),
                        reasons="\n".join(f"{p}\t{text}" for text, p in lines),
                        status="pending",
                    )
                )


def offer_lines(offer: GameClaimOffer) -> list[tuple[str, int]]:
    # An offer's lines: (text, VP).
    found = []
    for row in offer.reasons.splitlines():
        points, text = row.split("\t", 1)
        found.append((text, int(points)))
    return found


def _offer(game: Game, offer_id: int) -> GameClaimOffer:
    offer = next((o for o in pending_offers(game) if o.id == offer_id), None)
    if offer is None:
        raise _bad_request("no such secondary waiting to be claimed or held")
    return offer


def _card(game: Game, offer: GameClaimOffer):
    return next(
        (s, p) for p in game.players for s in p.secondaries if s.id == offer.game_secondary_id
    )


def claim(game: Game, offer_id: int) -> None:
    # The tactical secondary is claimed: its VP scored, and the card done.
    offer = _offer(game, offer_id)
    secondary, player = _card(game, offer)
    if secondary.status != "active":
        raise _bad_request("that secondary isn't active")
    offer.status = "claimed"
    secondary.status = "achieved"
    points, lines = capped(player, offer.battle_round, "secondary", offer_lines(offer))
    player.scores.append(
        GameScore(
            battle_round=offer.battle_round,
            turn_seat=offer.turn_seat,
            kind="secondary",
            points=points,
            game_secondary_id=secondary.id,
            reasons=_reasons(lines),
        )
    )


def hold(game: Game, offer_id: int) -> None:
    # Not claimed: the card stays in its holder's hand.
    _offer(game, offer_id).status = "held"


def automatic(card_name: str) -> bool:
    # Whether a card is scored automatically (at least partly).
    return card_name in mission_cards.PRIMARIES or card_name in mission_cards.SECONDARIES
