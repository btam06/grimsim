from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import (
    ArmyList,
    Game,
    GamePlayer,
    GameSecondary,
    GameStratagemUse,
    Stratagem,
)
from app.schemas import (
    GameIn,
    GameOut,
    GamePlayerOut,
    GameScoreIn,
    GameScoreOut,
    GameSecondaryOut,
    GameStratagemIn,
    GameStratagemUseOut,
    StratagemOut,
)
from app.routers.stratagems import _to_out as stratagem_to_out
from app.services import game as game_service

router = APIRouter(prefix="/games", tags=["games"])


def _player_out(player: GamePlayer) -> GamePlayerOut:
    return GamePlayerOut(
        id=player.id,
        seat=player.seat,
        user_id=player.user_id,
        user_name=player.user.name,
        list_id=player.list_id,
        list_name=player.army_list.name,
        secondary_mode=player.secondary_mode,
        disposition_id=player.disposition_id,
        disposition_name=player.disposition.name if player.disposition else None,
        primary_mission_id=player.primary_mission_id,
        primary_mission_name=player.primary_mission.name if player.primary_mission else None,
        primary_mission_description=(
            player.primary_mission.description if player.primary_mission else None
        ),
        cp=player.cp,
        vp=sum(score.points for score in player.scores),
        secondaries=[
            GameSecondaryOut(
                id=card.id,
                secondary_mission_id=card.secondary_mission_id,
                name=card.mission.name,
                description=card.mission.description,
                completes_on=card.mission.completes_on,
                points=game_service.mission_points(card),
                status=card.status,
                fixed=card.fixed,
                drawn_round=card.drawn_round,
            )
            for card in player.secondaries
        ],
        scores=[
            GameScoreOut(
                id=s.id,
                battle_round=s.battle_round,
                turn_seat=s.turn_seat,
                kind=s.kind,
                points=s.points,
                game_secondary_id=s.game_secondary_id,
            )
            for s in player.scores
        ],
        stratagem_uses=[
            GameStratagemUseOut(
                id=u.id,
                stratagem_id=u.stratagem_id,
                name=u.stratagem.name,
                battle_round=u.battle_round,
                turn_seat=u.turn_seat,
                phase=u.phase,
                cp=u.cp,
            )
            for u in player.stratagem_uses
        ],
    )


def _game_out(game: Game) -> GameOut:
    return GameOut(
        id=game.id,
        status=game.status,
        attacker_seat=game.attacker_seat,
        first_seat=game.first_seat,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        phase=game.phase,
        players=[_player_out(p) for p in game.players],
    )


def _game_options():
    players = selectinload(Game.players)
    return [
        players.selectinload(GamePlayer.user),
        players.selectinload(GamePlayer.army_list).selectinload(ArmyList.detachments),
        players.selectinload(GamePlayer.disposition),
        players.selectinload(GamePlayer.primary_mission),
        players.selectinload(GamePlayer.secondaries).selectinload(GameSecondary.mission),
        players.selectinload(GamePlayer.scores),
        players.selectinload(GamePlayer.stratagem_uses).selectinload(GameStratagemUse.stratagem),
    ]


async def _load_game(session: AsyncSession, game_id: int) -> Game:
    game = (
        await session.execute(
            select(Game)
            .options(*_game_options())
            .where(Game.id == game_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    return game


async def _commit_and_reload(session: AsyncSession, game_id: int) -> GameOut:
    await session.commit()
    return _game_out(await _load_game(session, game_id))


async def _load_stratagems(session: AsyncSession, ids: list[int] | None = None) -> list[Stratagem]:
    query = select(Stratagem).options(
        selectinload(Stratagem.detachments),
        selectinload(Stratagem.conditions),
        selectinload(Stratagem.effects),
        selectinload(Stratagem.keywords),
        selectinload(Stratagem.timings),
    )
    if ids is not None:
        query = query.where(Stratagem.id.in_(ids))
    return list((await session.execute(query.order_by(Stratagem.id))).scalars().all())


@router.get("", response_model=list[GameOut])
async def list_games(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Game).options(*_game_options()).order_by(Game.id))
    return [_game_out(game) for game in result.scalars().all()]


@router.post("", response_model=GameOut, status_code=201)
async def create_game(payload: GameIn, session: AsyncSession = Depends(get_session)):
    game = await game_service.create_game(session, payload)
    await session.flush()
    return await _commit_and_reload(session, game.id)


@router.get("/{game_id}", response_model=GameOut)
async def get_game(game_id: int, session: AsyncSession = Depends(get_session)):
    return _game_out(await _load_game(session, game_id))


@router.delete("/{game_id}", status_code=204)
async def delete_game(game_id: int, session: AsyncSession = Depends(get_session)):
    game = await _load_game(session, game_id)
    await session.delete(game)
    await session.commit()


@router.post("/{game_id}/start", response_model=GameOut)
async def start_game(game_id: int, session: AsyncSession = Depends(get_session)):
    game = await _load_game(session, game_id)
    await game_service.start_game(session, game)
    return await _commit_and_reload(session, game_id)


@router.post("/{game_id}/advance", response_model=GameOut)
async def advance(game_id: int, session: AsyncSession = Depends(get_session)):
    game = await _load_game(session, game_id)
    await game_service.advance(session, game)
    return await _commit_and_reload(session, game_id)


@router.get("/{game_id}/stratagems", response_model=list[StratagemOut])
async def usable_stratagems(
    game_id: int, seat: int, session: AsyncSession = Depends(get_session)
):
    # The stratagems a player could use right now (detachment, phase, whose
    # turn, and CP all checked).
    game = await _load_game(session, game_id)
    if seat not in (1, 2):
        raise HTTPException(status_code=400, detail="seat must be 1 or 2")
    player = game_service.player_at(game, seat)
    return [
        stratagem_to_out(s)
        for s in await _load_stratagems(session)
        if game_service.stratagem_unavailable_reason(game, player, s) is None
    ]


@router.post("/{game_id}/stratagems", response_model=GameOut)
async def use_stratagem(
    game_id: int, payload: GameStratagemIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    stratagems = await _load_stratagems(session, [payload.stratagem_id])
    if not stratagems:
        raise HTTPException(status_code=400, detail="stratagem not found")
    game_service.use_stratagem(game, game_service.player_at(game, payload.seat), stratagems[0])
    return await _commit_and_reload(session, game_id)


def _card(game: Game, card_id: int) -> GameSecondary:
    for player in game.players:
        for card in player.secondaries:
            if card.id == card_id:
                return card
    raise HTTPException(status_code=404, detail="secondary not found in this game")


@router.post("/{game_id}/secondaries/{card_id}/achieve", response_model=GameOut)
async def achieve_secondary(
    game_id: int, card_id: int, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    game_service.achieve_secondary(game, _card(game, card_id))
    return await _commit_and_reload(session, game_id)


@router.post("/{game_id}/secondaries/{card_id}/discard", response_model=GameOut)
async def discard_secondary(
    game_id: int, card_id: int, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    game_service.discard_secondary(game, _card(game, card_id))
    return await _commit_and_reload(session, game_id)


@router.post("/{game_id}/primary-score", response_model=GameOut)
async def score_primary(
    game_id: int, payload: GameScoreIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    game_service.score_primary(game, game_service.player_at(game, payload.seat), payload.points)
    return await _commit_and_reload(session, game_id)
