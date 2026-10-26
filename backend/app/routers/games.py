from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import (
    ArmyList,
    FactionAbility,
    Game,
    GamePlayer,
    GameSecondary,
    GameStratagemUse,
    GameUnitShot,
    Model,
    Stratagem,
    Unit,
    UnitModel,
)
from app.schemas import (
    ChargeIn,
    ChargeOut,
    ChargeTargetOut,
    ChargeUnitOut,
    CombatIn,
    ConsolidatingOut,
    DeploymentCheckOut,
    FightLogOut,
    FightOut,
    FightResultOut,
    FightTargetOut,
    FirstTurnRollOut,
    FightUnitOut,
    FormationIn,
    FormationPlayerOut,
    FormationsOut,
    FormationUnitOut,
    ReachIn,
    ReservesOut,
    ReserveUnitOut,
    ReachModelOut,
    ReachOut,
    RoundStartOut,
    RoundStartPlayerOut,
    RoundStartRuleOut,
    RuleChoiceIn,
    DeploymentFormationIn,
    DeploymentModelOut,
    DeploymentOut,
    DeploymentUnitOut,
    DeployUnitIn,
    GameAchieveIn,
    GameIn,
    GameOut,
    GamePlayerOut,
    GameScoreIn,
    GameScoreOut,
    GameSecondaryOut,
    GameStratagemIn,
    GameStratagemUseOut,
    ModelPositionIn,
    ModelPositionOut,
    ModelPathOut,
    ModelProblemsOut,
    PileInOut,
    PileInUnitOut,
    SeatIn,
    UnitPlacementIn,
    MovementModelOut,
    MovementOut,
    OverwatchOut,
    EmbarkableUnitOut,
    EmbarkedOut,
    EmbarkedUnitOut,
    EmbarkIn,
    EmergencyOut,
    EmergencyRollOut,
    EmergencyUnitOut,
    TeleportHomerIn,
    PsychicAbilityOut,
    PsychicIn,
    PsychicOut,
    PsychicUnitOut,
    PsychicUseOut,
    TeleportHomersOut,
    TeleportHomerUnitOut,
    MarkedUnitOut,
    MissionAnswerIn,
    MissionPromptOut,
    MissionStateOut,
    OperationMarkerOut,
    PromptOptionOut,
    ActionIn,
    ActionOptionOut,
    ActionsOut,
    ActionTargetOut,
    UnitActionOut,
    ClaimOfferOut,
    ScoreReasonOut,
    ScoringOut,
    DestroyedModelOut,
    TurnRecordOut,
    TurnStartObjectiveOut,
    BattleShockOut,
    BattleShockRequireIn,
    BattleShockTakeIn,
    BattleShockTestOut,
    BattleShockUnitOut,
    ObjectiveControlOut,
    TerritoryOut,
    AuraOut,
    CommandAbilityOut,
    CommandChoiceIn,
    CommandHealOut,
    CommandOut,
    UnitIdNameOut,
    ReanimationOut,
    ReanimationUnitOut,
    MovementUnitOut,
    ShootIn,
    ShootingOut,
    ShootingTargetOut,
    ShootingUnitOut,
    ShootingWeaponOut,
    ShootOut,
    ShotOut,
    SightBubbleOut,
    ScoutsOut,
    ScoutsUnitOut,
    StartOfShootingIn,
    StartOfShootingOut,
    StartOfShootingResultOut,
    StratagemOut,
    StratagemTargetOut,
    TerrainPointOut,
    UnitIdIn,
    UnitMoveIn,
)
from app.routers.stratagems import _to_out as stratagem_to_out
from app.services.in_game import auras as auras_service
from app.services.in_game import actions as actions_service
from app.services.in_game import battle_formations as battle_formations_service
from app.services.in_game import battle_shock as battle_shock_service
from app.services.in_game import battle_round as battle_round_service
from app.services.in_game import casualties as casualties_service
from app.services.in_game import charging as charging_service
from app.services.in_game import command_phase as command_phase_service
from app.services.in_game import deployment as deployment_service
from app.services.in_game import embarked as embarked_service
from app.services.in_game import emergency as emergency_service
from app.services.in_game import psychic as psychic_service
from app.seeds.factions.adeptus_mechanicus import fire_support
from app.services.in_game import shoot_scoot as shoot_scoot_service
from app.services.in_game import shooting_start as shooting_start_service
from app.seeds.factions.space_marines import teleport_homer as teleport_homer_service
from app.services.in_game import fighting as fighting_service
from app.services.in_game import game as game_service
from app.services.in_game import movement as movement_service
from app.services.in_game import objectives as objectives_service
from app.services.in_game import scouts as scouts_service
from app.services.in_game import overwatch as overwatch_service
from app.services.in_game import pathing as pathing_service
from app.seeds import factions as faction_seeds
from app.seeds.factions.necrons import reanimation as reanimation_service
from app.services.in_game import heal as heal_service
from app.services.in_game import regions as regions_service
from app.services.in_game import mission_cards
from app.services.in_game import mission_state as mission_state_service
from app.services.in_game import reinforcements as reinforcements_service
from app.services.in_game import scoring as scoring_service
from app.services.in_game import shooting as shooting_service
from app.services.in_game import turn_record as turn_record_service
from app.routers import combat as combat_router
from app.routers.combat import calculate as calculate_combat
from app.services import weapon_profiles
from app.combat_rules.conditions import (
    ALWAYS,
    BELOW_HALF_STRENGTH,
    BELOW_STARTING_STRENGTH,
    CONTROLLING_OBJECTIVE,
    IN_RANGE_OF_OBJECTIVE,
    REMAINED_STATIONARY,
    WITHIN_9_OF_TARGET,
)
from app.combat_rules.effects import ASSAULT
from app.combat_rules.positions import NEAR_FRIENDLY
from app.services.in_game.deployment import TOLERANCE
from app.services.in_game.terrain import MM_PER_INCH

router = APIRouter(prefix="/games", tags=["games"])


def _score_out(score) -> GameScoreOut:
    return GameScoreOut(
        id=score.id,
        battle_round=score.battle_round,
        turn_seat=score.turn_seat,
        kind=score.kind,
        points=score.points,
        game_secondary_id=score.game_secondary_id,
        reasons=[ScoreReasonOut(text=r.text, points=r.points) for r in score.reasons],
    )


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
        primary_automatic=bool(
            player.primary_mission and scoring_service.automatic(player.primary_mission.name)
        ),
        primary_manual=(
            mission_cards.MANUAL.get(player.primary_mission.name)
            if player.primary_mission
            else None
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
                automatic=scoring_service.automatic(card.mission.name),
                manual=mission_cards.MANUAL.get(card.mission.name),
            )
            for card in player.secondaries
        ],
        scores=[_score_out(s) for s in player.scores],
        stratagem_uses=[
            GameStratagemUseOut(
                id=u.id,
                stratagem_id=u.stratagem_id,
                name=u.stratagem.name,
                battle_round=u.battle_round,
                turn_seat=u.turn_seat,
                phase=u.phase,
                cp=u.cp,
                target_unit_id=u.target_unit_id,
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
        terrain_layout_id=game.layout.id if game.layout else None,
        terrain_layout_name=game.layout.name if game.layout else None,
        deployment_step=deployment_service.deployment_step(game),
        deploying_seat=deployment_service.deploying_seat(game),
        scouting_seat=scouts_service.scouting_seat(game),
        first_turn_rolls=[
            FirstTurnRollOut(attempt=r.attempt, seat=r.seat, roll=r.roll)
            for r in game.first_turn_rolls
        ],
        piling_in_seat=fighting_service.piling_seat(game),
    )


def _game_options():
    players = selectinload(Game.players)
    return [
        players.selectinload(GamePlayer.user),
        players.selectinload(GamePlayer.army_list).selectinload(ArmyList.detachments),
        # The armies, for deployment.
        players.selectinload(GamePlayer.army_list)
        .selectinload(ArmyList.units)
        .selectinload(Unit.faction_unit),
        players.selectinload(GamePlayer.army_list)
        .selectinload(ArmyList.units)
        .selectinload(Unit.unit_models)
        .selectinload(UnitModel.model)
        .selectinload(Model.abilities),
        # For shooting: their weapons and keywords.
        players.selectinload(GamePlayer.army_list)
        .selectinload(ArmyList.units)
        .selectinload(Unit.unit_models)
        .selectinload(UnitModel.weapons),
        players.selectinload(GamePlayer.army_list)
        .selectinload(ArmyList.units)
        .selectinload(Unit.unit_models)
        .selectinload(UnitModel.model)
        .selectinload(Model.keywords),
        # For the start of the battle round: their army rules.
        players.selectinload(GamePlayer.army_list)
        .selectinload(ArmyList.units)
        .selectinload(Unit.unit_models)
        .selectinload(UnitModel.model)
        .selectinload(Model.faction_abilities)
        .selectinload(FactionAbility.faction),
        players.selectinload(GamePlayer.disposition),
        players.selectinload(GamePlayer.primary_mission),
        players.selectinload(GamePlayer.secondaries).selectinload(GameSecondary.mission),
        players.selectinload(GamePlayer.scores),
        players.selectinload(GamePlayer.stratagem_uses)
        .selectinload(GameStratagemUse.stratagem)
        .selectinload(Stratagem.game_action_link),
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
        selectinload(Stratagem.game_action_link),
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
    await session.commit()
    game = await _load_game(session, game.id)
    game_service.enter_deployment(game)
    return await _commit_and_reload(session, game.id)


@router.get("/{game_id}", response_model=GameOut)
async def get_game(game_id: int, session: AsyncSession = Depends(get_session)):
    return _game_out(await _load_game(session, game_id))


@router.delete("/{game_id}", status_code=204)
async def delete_game(game_id: int, session: AsyncSession = Depends(get_session)):
    game = await _load_game(session, game_id)
    # Scores and claim offers first: they point at the secondaries (and
    # mission prompts, which point at actions).
    game.claim_offers.clear()
    game.mission_prompts.clear()
    game.card_choices.clear()
    for player in game.players:
        player.scores.clear()
    await session.flush()
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
    await game_service.use_stratagem(
        session,
        game,
        game_service.player_at(game, payload.seat),
        stratagems[0],
        payload.target_secondary_id,
        target_unit_id=payload.target_unit_id,
    )
    return await _commit_and_reload(session, game_id)


@router.get(
    "/{game_id}/stratagems/{stratagem_id}/targets", response_model=list[StratagemTargetOut]
)
async def stratagem_targets(
    game_id: int, stratagem_id: int, seat: int, session: AsyncSession = Depends(get_session)
):
    # The player's units a stratagem whose game action targets one (e.g.
    # Gunship Extraction) could be used on now.
    game = await _load_game(session, game_id)
    stratagems = await _load_stratagems(session, [stratagem_id])
    if not stratagems:
        raise HTTPException(status_code=404, detail="stratagem not found")
    player = game_service.player_at(game, seat)
    return [
        StratagemTargetOut(unit_id=u.id, name=u.faction_unit.name)
        for u in game_service.stratagem_targets(game, player, stratagems[0])
    ]


def _card(game: Game, card_id: int) -> GameSecondary:
    for player in game.players:
        for card in player.secondaries:
            if card.id == card_id:
                return card
    raise HTTPException(status_code=404, detail="secondary not found in this game")


@router.post("/{game_id}/secondaries/{card_id}/achieve", response_model=GameOut)
async def achieve_secondary(
    game_id: int,
    card_id: int,
    payload: GameAchieveIn | None = None,
    session: AsyncSession = Depends(get_session),
):
    game = await _load_game(session, game_id)
    points = payload.points if payload else None
    game_service.achieve_secondary(game, _card(game, card_id), points)
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


# --- deployment (see app/services/in_game/deployment.py) ---


def _check_out(result) -> DeploymentCheckOut:
    # A placement check's output (see deployment_service.Placement).
    return DeploymentCheckOut(
        valid=result.valid,
        problems=result.problems,
        models=[ModelProblemsOut(unit_model_id=i, problems=p) for i, p in result.models.items()],
        paths=[
            ModelPathOut(
                unit_model_id=i,
                points=[TerrainPointOut(x=round(x, 3), y=round(y, 3)) for x, y in points],
            )
            for i, points in result.paths.items()
        ],
    )


def _placement(positions: list[ModelPositionIn]) -> dict[int, tuple[float, float, float]]:
    return {p.unit_model_id: (p.x, p.y, p.rotation) for p in positions}


@router.get("/{game_id}/deployment", response_model=DeploymentOut)
async def get_deployment(game_id: int, session: AsyncSession = Depends(get_session)):
    # Both armies' units, whose turn it is to deploy, and where each deployed
    # model is.
    game = await _load_game(session, game_id)
    placed = deployment_service.positions(game)
    damage = casualties_service.damage(game)
    units = []
    for player in game.players:
        for unit in deployment_service.deployable_units(player):
            models = []
            for unit_model in deployment_service.unit_models(unit):
                width, height, measured = deployment_service.base_mm(unit_model)
                position = placed.get(unit_model.id)
                record = damage.get(unit_model.id)
                wounds = unit_model.wounds
                models.append(
                    DeploymentModelOut(
                        unit_model_id=unit_model.id,
                        name=unit_model.model.name,
                        base_size=(
                            unit_model.model.base_size.name if unit_model.model.base_size else None
                        ),
                        width=width / MM_PER_INCH,
                        height=height / MM_PER_INCH,
                        measured=measured,
                        wounds=wounds,
                        wounds_remaining=wounds - (record.wounds_lost if record else 0),
                        destroyed=bool(record and record.destroyed),
                        position=(
                            ModelPositionOut(
                                unit_model_id=unit_model.id,
                                x=position.x,
                                y=position.y,
                                rotation=position.rotation,
                            )
                            if position
                            else None
                        ),
                    )
                )
            units.append(
                DeploymentUnitOut(
                    unit_id=unit.id,
                    seat=player.seat,
                    name=unit.faction_unit.name,
                    infiltrators=deployment_service.is_infiltrator(unit),
                    deployed=deployment_service.is_deployed(unit, placed),
                    formation=(f := deployment_service.battle_formation(game, unit)) and f.place,
                    transport_unit_id=f.transport_unit_id if f else None,
                    destroyed=all(m.destroyed for m in models),
                    models=models,
                    battle_shocked=battle_shock_service.is_battle_shocked(game, unit),
                    auras=(
                        [
                            AuraOut(unit_model_id=m.id, name=name, range=reach)
                            for m, name, reach in auras_service.ranges(game, unit)
                        ]
                        if game.status == "in_progress"
                        else []
                    ),
                )
            )
    split = regions_service.split(game)
    return DeploymentOut(
        deploying_seat=deployment_service.deploying_seat(game),
        units=units,
        objectives=[
            ObjectiveControlOut(
                objective_id=c.objective.id,
                kind=c.objective.kind,
                area_ids=[a.id for a in c.objective.areas],
                oc=c.oc,
                controller=c.controller,
                secured_by=c.secured_by,
            )
            for c in objectives_service.control(game)
        ],
        territory=(
            TerritoryOut(
                split=split,
                line=[TerrainPointOut(x=x, y=y) for x, y in regions_service.split_line(game)],
                territories={
                    p.seat: [
                        TerrainPointOut(x=x, y=y)
                        for x, y in regions_service.territory(game, p.seat)
                    ]
                    for p in game.players
                },
            )
            if split
            else None
        ),
    )


@router.post("/{game_id}/deployment/formation", response_model=list[ModelPositionOut])
async def deployment_formation(
    game_id: int, payload: DeploymentFormationIn, session: AsyncSession = Depends(get_session)
):
    # Where a unit's models start when it's set down at (x, y), for the player
    # to arrange.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    deployment_service.check_turn(game, unit)
    return [
        ModelPositionOut(unit_model_id=i, x=x, y=y, rotation=rotation)
        for i, (x, y, rotation) in deployment_service.formation(
            game, unit, payload.x, payload.y
        ).items()
    ]


@router.post("/{game_id}/deployment/check", response_model=DeploymentCheckOut)
async def check_deployment(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    # Whether a unit could be deployed as placed, and if not, why.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    deployment_service.check_turn(game, unit)
    result = deployment_service.check_placement(game, unit, _placement(payload.positions))
    return _check_out(result)


@router.post("/{game_id}/deployment", response_model=GameOut)
async def deploy_unit(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    await game_service.deploy_unit(session, game, unit, _placement(payload.positions))
    return await _commit_and_reload(session, game_id)


# --- movement (see app/services/in_game/movement.py) ---


def _movement_out(game: Game) -> MovementOut:
    if not movement_service.is_movement_phase(game):
        return MovementOut(units=[])
    units = []
    for unit in movement_service.movable_units(game):
        move = movement_service.unit_move(game, unit)
        starts = movement_service.start_positions(game, unit)
        units.append(
            MovementUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                allowed_kinds=movement_service.allowed_kinds(game, unit),
                in_engagement_range=movement_service.in_engagement_range(game, unit),
                kind=move.kind if move and move.completed else None,
                advance_roll=move.advance_roll if move else None,
                moved=bool(move and move.completed),
                arrived=bool(move and move.kind == reinforcements_service.ARRIVED),
                models=[
                    MovementModelOut(
                        unit_model_id=m.id,
                        movement=m.model.movement,
                        start=(
                            ModelPositionOut(
                                unit_model_id=m.id,
                                x=starts[m.id][0],
                                y=starts[m.id][1],
                                rotation=starts[m.id][2],
                            )
                            if m.id in starts
                            else None
                        ),
                    )
                    for m in deployment_service.unit_models(unit)
                ],
            )
        )
    return MovementOut(units=units)


@router.get("/{game_id}/movement", response_model=MovementOut)
async def get_movement(game_id: int, session: AsyncSession = Depends(get_session)):
    # In the movement phase, the units the player whose turn it is can move,
    # and how.
    return _movement_out(await _load_game(session, game_id))


@router.post("/{game_id}/movement/advance", response_model=MovementOut)
async def roll_advance(
    game_id: int, payload: UnitIdIn, session: AsyncSession = Depends(get_session)
):
    # Rolls the unit's Advance D6, before it moves (once a phase: asking again
    # gives the same roll).
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    movement_service.roll_advance(game, unit)
    await session.commit()
    return _movement_out(await _load_game(session, game_id))


@router.post("/{game_id}/movement/check", response_model=DeploymentCheckOut)
async def check_move(
    game_id: int, payload: UnitMoveIn, session: AsyncSession = Depends(get_session)
):
    # Whether a unit could move as placed, and if not, why.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    result = movement_service.check_move(game, unit, payload.kind, _placement(payload.positions))
    return _check_out(result)


@router.post("/{game_id}/movement/reset", response_model=GameOut)
async def reset_move(
    game_id: int, payload: UnitIdIn, session: AsyncSession = Depends(get_session)
):
    # Puts the unit back where it started the movement phase.
    game = await _load_game(session, game_id)
    movement_service.reset_move(game, deployment_service.find_unit(game, payload.unit_id))
    return await _commit_and_reload(session, game_id)


@router.post("/{game_id}/movement", response_model=GameOut)
async def move_unit(
    game_id: int, payload: UnitMoveIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    movement_service.move_unit(game, unit, payload.kind, _placement(payload.positions))
    return await _commit_and_reload(session, game_id)


def _defender_positions(game: Game, target: Unit) -> list[str]:
    # What the battlefield says about the target that the calculator asks
    # about (see app/combat_rules/positions.py): whether it's below its
    # Starting Strength, Below Half-strength, or within range of an
    # objective.
    found = []
    if battle_shock_service.below_starting_strength(game, target):
        found.append(BELOW_STARTING_STRENGTH)
    if battle_shock_service.below_half_strength_strict(game, target):
        found.append(BELOW_HALF_STRENGTH)
    if mission_state_service.unit_objectives(game, target):
        found.append(IN_RANGE_OF_OBJECTIVE)
    if any(
        objectives_service.unit_controls(game, target, current)
        for current in objectives_service.control(game)
    ):
        found.append(CONTROLLING_OBJECTIVE)
    return found + _near_friendly(game, target)


# How close a target has to be for rules that ask (see
# app/combat_rules/positions.py): {position: inches}.
TARGET_WITHIN = {WITHIN_9_OF_TARGET: 9.0}


def _attacker_positions(
    game: Game, unit: Unit, target: Unit, stationary: bool = False
) -> list[str]:
    # What the battlefield says about the attacking unit that the calculator
    # asks about: whether it Remained Stationary, and how close its target is
    # (e.g. within 9", for Purgatus Tactics).
    found = [REMAINED_STATIONARY] if stationary else []
    distance = charging_service.distance(game, unit, target)
    found += [p for p, reach in TARGET_WITHIN.items() if distance <= reach + TOLERANCE]
    return found + _near_friendly(game, unit)


def _near_friendly(game: Game, unit: Unit) -> list[str]:
    # Positions about being near friendly units (e.g. within 6" of a friendly
    # ADEPTUS MECHANICUS BATTLELINE unit), measured on the battlefield.
    return [
        position
        for position, (keywords, reach) in NEAR_FRIENDLY.items()
        if regions_service.near_friendly(game, unit, keywords, reach)
    ]


def _rule_options(game: Game, unit: Unit, attacking: Unit | None = None) -> list[str]:
    # The rule options active for the unit in combat: its owner's army rule
    # options this round (e.g. Doctrina Imperatives), those of abilities
    # selected in their Command phase that can apply to it (see
    # app/services/in_game/command_phase.py), and the auras it's within range
    # of (see app/services/in_game/auras.py). `attacking`: the unit it's
    # attacking, if it is (for options against one enemy unit).
    seat = deployment_service.owner(game, unit).seat
    return (
        battle_round_service.active_options(game, seat)
        + command_phase_service.options_for(game, seat, unit, attacking)
        + auras_service.aura_options(game, unit)
        + psychic_service.active_options(game, unit)
    )


# --- shooting (see app/services/in_game/shooting.py) ---


async def _assault_weapons(session: AsyncSession, unit: Unit, game: Game | None = None) -> set:
    # The unit's Assault weapons, as the calculator sees them (so loaded as it
    # loads units, with its detachment rules) - every ranged weapon, in a game
    # where an active option lets it shoot after Advancing (e.g. Fanatical
    # Devotion) or gives its ranged weapons [ASSAULT] (e.g. the Devastator
    # Doctrine, the Conqueror Imperative).
    every = {w.id for m in unit.unit_models for w in shooting_service.ranged_weapons(m)}
    if game is not None and command_phase_service.eligible_after(
        game, unit, "advanced", "shoot"
    ):
        return every
    loaded = await combat_router._load_unit(session, unit.id)
    rules = await combat_router._detachment_rules(session, loaded)
    if game is not None:
        _, option_rules, _ = combat_router._active_options(
            loaded, _rule_options(game, unit), rules
        )
        if any(
            r.side == "attacker" and ASSAULT in r.effects and ALWAYS in r.conditions
            for r in option_rules
        ):
            return every
    ids = await shooting_service.assault_ability_ids(session)
    return shooting_service.assault_weapons(loaded, rules, ids)


def _unit_name(game: Game, unit_id: int) -> str:
    for player in game.players:
        for unit in player.army_list.units:
            if unit.id == unit_id:
                return unit.faction_unit.name
    return "a unit"


@router.get("/{game_id}/shooting", response_model=ShootingOut)
async def get_shooting(game_id: int, session: AsyncSession = Depends(get_session)):
    # In the shooting phase, the units the player whose turn it is has on the
    # battlefield: whether each can shoot, how it moved, and what it shot.
    game = await _load_game(session, game_id)
    if not shooting_service.is_shooting_phase(game):
        return ShootingOut(units=[])
    units = []
    for unit in shooting_service.shooting_units(game):
        status = shooting_service.move_status(game, unit)
        shot = shooting_service.unit_shot(game, unit)
        assault = await _assault_weapons(session, unit, game) if status.advanced else None
        reason = shooting_service.cant_shoot_reason(game, unit, assault)
        units.append(
            ShootingUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                can_shoot=reason is None,
                reason=reason,
                shoot_scoot=(
                    found[0]
                    if (found := shoot_scoot_service.move_of(unit))
                    and shoot_scoot_service.reason(game, unit) is None
                    else None
                ),
                shoot_scoot_reach=shoot_scoot_service.reach(unit),
                advanced=status.advanced,
                remained_stationary=status.remained_stationary,
                moved_less_than_3=status.moved_less_than_3,
                distance=status.distance,
                shot=(
                    ShotOut(
                        target_unit_id=shot.target_unit_id,
                        target_name=_unit_name(game, shot.target_unit_id),
                        total_damage=shot.total_damage,
                        models_destroyed=shot.models_destroyed,
                    )
                    if shot
                    else None
                ),
            )
        )
    return ShootingOut(units=units)


def _weapon_out(weapon: shooting_service.WeaponReach) -> ShootingWeaponOut:
    kind = weapon.id[0] if isinstance(weapon.id, tuple) else None
    return ShootingWeaponOut(
        id=weapon.id[1] if kind else weapon.id,
        enhancement=kind == "enhancement",
        firing_deck=kind == "deck",
        name=weapon.name,
        range=weapon.range,
        carried_by=weapon.carried_by,
        in_range=weapon.in_range,
        half_range=weapon.half_range,
        assault=weapon.assault,
        unusable=weapon.unusable,
        default=weapon.default,
    )


@router.get("/{game_id}/shooting/targets", response_model=list[ShootingTargetOut])
async def shooting_targets(
    game_id: int, unit_id: int, session: AsyncSession = Depends(get_session)
):
    # Each enemy unit the unit could shoot at: whether it can see it, whether
    # it's in cover, and what each of its weapons can reach.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, unit_id)
    assault = await _assault_weapons(session, unit, game)
    if (reason := shooting_service.cant_shoot_reason(game, unit, assault)) is not None:
        raise HTTPException(status_code=400, detail=f"it can't shoot: {reason}")
    targets = []
    for target in shooting_service.enemy_units(game, unit):
        result = shooting_service.reach(game, unit, target, assault)
        targets.append(
            ShootingTargetOut(
                unit_id=target.id,
                name=target.faction_unit.name,
                visible=result.visible,
                in_cover=result.in_cover,
                weapons=[_weapon_out(w) for w in result.weapons],
            )
        )
    return targets


@router.post("/{game_id}/shooting", response_model=ShootOut)
async def shoot(game_id: int, payload: ShootIn, session: AsyncSession = Depends(get_session)):
    # The unit shoots the target with the chosen weapons: the combat
    # calculator resolves it, with each model firing only the weapons it can
    # (a visible target model in range), and how the unit moved and whether
    # the target's in cover taken from the battlefield.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    target = deployment_service.find_unit(game, payload.target_unit_id)
    weapon_ids = (
        set(payload.weapon_ids)
        | {("enhancement", i) for i in payload.enhancement_weapon_ids}
        | {("deck", i) for i in payload.firing_deck_weapon_ids}
    )
    reach = shooting_service.check_shot(
        game, unit, target, weapon_ids, await _assault_weapons(session, unit, game)
    )
    firing_deck = _firing_deck(game, unit, payload, reach)
    status = shooting_service.move_status(game, unit)
    out = await _fire(
        session, game, unit, target, payload, reach, status, firing_deck=firing_deck
    )
    if firing_deck:
        shooting_service.record_deck(game, unit)
    await session.commit()
    return out


def _firing_deck(
    game: Game, unit: Unit, payload: ShootIn, reach: shooting_service.TargetReach
) -> list[tuple[int, int, int]]:
    # The Firing Deck weapons the transport fires, for the calculator: the
    # chosen weapons of its first embarked models carrying them (up to its
    # limit), those that can reach the target - as (its model's id, the
    # embarked model's id, weapon id). Only one profile of a weapon per model.
    if not payload.firing_deck_weapon_ids:
        return []
    pairs = shooting_service.deck_weapons(game, unit, set(payload.firing_deck_weapon_ids))
    for embarked_model in {m.id: m for m, _ in pairs}.values():
        group = weapon_profiles.conflicting_profiles(w for m, w in pairs if m is embarked_model)
        if group is not None:
            raise HTTPException(
                status_code=400, detail=f"choose only one profile of {group} to attack with"
            )
    found = []
    for carrier_id, can_fire in reach.firing.items():
        for embarked_model, weapon in pairs:
            if shooting_service.deck_id(embarked_model, weapon) in can_fire:
                found.append((carrier_id, embarked_model.id, weapon.id))
    return found


async def _fire(
    session: AsyncSession,
    game: Game,
    unit: Unit,
    target: Unit,
    payload: ShootIn,
    reach: shooting_service.TargetReach,
    status: shooting_service.MoveStatus,
    snap_shots: bool = False,
    firing_deck: list[tuple[int, int, int]] | None = None,
) -> ShootOut:
    # Resolves a shot the unit can make (checked): the calculator, with each
    # model firing only the weapons it can, how the unit moved, and whether
    # the target's in cover; then its casualties, and the shot recorded.
    # Each model's wounds left in this game: only those still on the
    # battlefield are attacked (and can fire).
    defender_wounds = casualties_service.wounds_remaining(game, target)
    attacker_wounds = casualties_service.wounds_remaining(game, unit)

    combat = await calculate_combat(
        session,
        CombatIn(
            game_id=game.id,
            attacking_unit_id=unit.id,
            defending_unit_id=target.id,
            selected_weapon_ids=payload.weapon_ids,
            selected_enhancement_weapon_ids=payload.enhancement_weapon_ids,
            attacker_positions=_attacker_positions(
                game, unit, target, status.remained_stationary
            ),
            defender_positions=_defender_positions(game, target),
            defender_battle_shocked=battle_shock_service.is_battle_shocked(game, target),
            in_cover=reach.in_cover,
            moved_less_than_3=status.moved_less_than_3,
            advanced=status.advanced,
            # The options each side chose for its army rules this round (e.g.
            # its Doctrina Imperative) and its abilities in its Command phase.
            attacker_rule_options=_rule_options(game, unit, target),
            defender_rule_options=_rule_options(game, target),
            defender_visible=True,
            defender_in_range=True,
            snap_shots=snap_shots,
        ),
        firing=reach.firing,
        defender_wounds=defender_wounds,
        attacker_wounds=attacker_wounds,
        firing_deck=firing_deck,
        attacker_extra_rules=fire_support.rules(game, unit, target),
    )
    fire_support.after_shooting(game, unit, target, combat.hits)
    destroyed = casualties_service.apply_attack(
        game,
        unit,
        target,
        defender_wounds,
        combat.defender_wounds_remaining,
        combat.attacker_damage,
    )
    game.unit_shots.append(
        GameUnitShot(
            unit_id=unit.id,
            target_unit_id=target.id,
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            total_damage=combat.total_damage,
            models_destroyed=combat.models_destroyed,
        )
    )
    return ShootOut(
        in_cover=reach.in_cover,
        advanced=status.advanced,
        remained_stationary=status.remained_stationary,
        moved_less_than_3=status.moved_less_than_3,
        combat=combat,
        destroyed_unit_model_ids=destroyed,
    )


@router.get("/{game_id}/shooting/bubble", response_model=SightBubbleOut)
async def shooting_bubble(
    game_id: int, unit_id: int, session: AsyncSession = Depends(get_session)
):
    # Where the unit's guns reach, to show it: within its longest range, and
    # not hidden by terrain.
    # At the end of the movement phase, for Fire Overwatch: within 24".
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, unit_id)
    if overwatch_service.overwatch_seat(game) is not None:
        bubble = shooting_service.sight_bubble(
            game, unit, max_range=overwatch_service.OVERWATCH_RANGE
        )
    elif shooting_service.is_shooting_phase(game):
        assault = await _assault_weapons(session, unit, game)
        bubble = shooting_service.sight_bubble(game, unit, assault)
    else:
        raise HTTPException(status_code=400, detail="units can only shoot in the shooting phase")
    return SightBubbleOut(
        range=bubble.range,
        regions=[
            [TerrainPointOut(x=round(x, 2), y=round(y, 2)) for x, y in region]
            for region in bubble.regions
        ],
    )


# --- Fire Overwatch (see app/services/in_game/overwatch.py) ---


def _shot_out(game: Game, shot) -> ShotOut | None:
    if shot is None:
        return None
    return ShotOut(
        target_unit_id=shot.target_unit_id,
        target_name=_unit_name(game, shot.target_unit_id),
        total_damage=shot.total_damage,
        models_destroyed=shot.models_destroyed,
    )


@router.get("/{game_id}/overwatch", response_model=OverwatchOut)
async def get_overwatch(game_id: int, session: AsyncSession = Depends(get_session)):
    # At the end of the movement phase: whether the opponent of the player
    # whose turn it is can Fire Overwatch (and if not, why), and their units
    # on the battlefield - whether each can, and what it shot, once it has.
    game = await _load_game(session, game_id)
    seat = overwatch_service.overwatch_seat(game)
    stratagem = await game_service.overwatch_stratagem(session)
    if seat is None or stratagem is None:
        return OverwatchOut(seat=None, available=False, cp=0, units=[])
    player = game_service.player_at(game, seat)
    reason = game_service.stratagem_unavailable_reason(game, player, stratagem)
    units = []
    for unit in overwatch_service.overwatch_units(game, seat):
        shot = shooting_service.unit_shot(game, unit)
        cant = reason or overwatch_service.cant_overwatch_reason(game, unit)
        units.append(
            ShootingUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                can_shoot=cant is None,
                reason=cant,
                advanced=False,
                remained_stationary=False,
                moved_less_than_3=False,
                shot=_shot_out(game, shot),
            )
        )
    return OverwatchOut(
        seat=seat, available=reason is None, reason=reason, cp=stratagem.cp, units=units
    )


@router.get("/{game_id}/overwatch/targets", response_model=list[ShootingTargetOut])
async def overwatch_targets(
    game_id: int, unit_id: int, session: AsyncSession = Depends(get_session)
):
    # Each enemy unit the unit could Fire Overwatch at: whether it's visible
    # within 24", whether it's in cover, and what each of its weapons can
    # reach.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, unit_id)
    if (reason := overwatch_service.cant_overwatch_reason(game, unit)) is not None:
        raise HTTPException(status_code=400, detail=f"it can't Fire Overwatch: {reason}")
    return [
        ShootingTargetOut(
            unit_id=result.unit.id,
            name=result.unit.faction_unit.name,
            visible=overwatch_service.within_range(result),
            in_cover=result.in_cover,
            weapons=[_weapon_out(w) for w in result.weapons],
        )
        for result in overwatch_service.targets(game, unit)
    ]


@router.post("/{game_id}/overwatch", response_model=ShootOut)
async def fire_overwatch(
    game_id: int, payload: ShootIn, session: AsyncSession = Depends(get_session)
):
    # The unit Fires Overwatch at the target with the chosen weapons (the
    # stratagem's CP spent): snap shooting, resolved by the calculator.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    target = deployment_service.find_unit(game, payload.target_unit_id)
    weapon_ids = set(payload.weapon_ids) | {
        ("enhancement", i) for i in payload.enhancement_weapon_ids
    }
    reach = overwatch_service.check_overwatch(game, unit, target, weapon_ids)
    stratagem = await game_service.overwatch_stratagem(session)
    if stratagem is None:
        raise HTTPException(status_code=400, detail="there's no Fire Overwatch stratagem")
    await game_service.use_stratagem(session, game, deployment_service.owner(game, unit), stratagem)
    # It isn't its turn: it didn't move this turn, but nothing it did counts.
    out = await _fire(
        session, game, unit, target, payload, reach, shooting_service.MoveStatus(), snap_shots=True
    )
    await session.commit()
    return out


# --- charging (see app/services/in_game/charging.py) ---


def _charge_out(game: Game) -> ChargeOut:
    if not charging_service.is_charge_phase(game):
        return ChargeOut(units=[])
    units = []
    for unit in charging_service.charging_units(game):
        charge = charging_service.unit_charge(game, unit)
        units.append(
            ChargeUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                dice=[charge.first_die, charge.second_die] if charge else [],
                bonus=charging_service.charge_bonus(game, unit),
                roll=charging_service.charge_roll(game, unit),
                can_reroll=charging_service.can_reroll(game, unit),
                failed=charging_service.failed(game, unit),
                charged=bool(charge and charge.completed),
                reason=charging_service.cant_charge_reason(game, unit),
                target_unit_id=charge.target_unit_id if charge else None,
                target_name=(
                    _unit_name(game, charge.target_unit_id)
                    if charge and charge.target_unit_id
                    else None
                ),
            )
        )
    return ChargeOut(units=units)


@router.get("/{game_id}/charge", response_model=ChargeOut)
async def get_charge(game_id: int, session: AsyncSession = Depends(get_session)):
    # In the charge phase, the units the player whose turn it is can charge
    # with, and how their charges stand.
    return _charge_out(await _load_game(session, game_id))


@router.post("/{game_id}/charge/roll", response_model=ChargeOut)
async def roll_charge(
    game_id: int, payload: UnitIdIn, session: AsyncSession = Depends(get_session)
):
    # Rolls the unit's charge (once a phase: asking again gives the same roll).
    game = await _load_game(session, game_id)
    charging_service.roll_charge(game, deployment_service.find_unit(game, payload.unit_id))
    await session.commit()
    return _charge_out(await _load_game(session, game_id))


@router.post("/{game_id}/charge/reroll", response_model=ChargeOut)
async def reroll_charge(
    game_id: int, payload: UnitIdIn, session: AsyncSession = Depends(get_session)
):
    # Re-rolls the unit's charge roll, if an ability lets it (once).
    game = await _load_game(session, game_id)
    charging_service.reroll_charge(game, deployment_service.find_unit(game, payload.unit_id))
    await session.commit()
    return _charge_out(await _load_game(session, game_id))


@router.get("/{game_id}/charge/targets", response_model=list[ChargeTargetOut])
async def charge_targets(
    game_id: int, unit_id: int, session: AsyncSession = Depends(get_session)
):
    # Each enemy unit, how close the unit is to it, and whether its charge
    # roll reaches (once it's rolled).
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, unit_id)
    charge = charging_service.unit_charge(game, unit)
    targets = []
    for target in charging_service.enemy_units(game, unit):
        distance = charging_service.distance(game, unit, target)
        targets.append(
            ChargeTargetOut(
                unit_id=target.id,
                name=target.faction_unit.name,
                distance=round(distance, 2),
                in_reach=charge is not None
                and charging_service.in_reach(
                    game, unit, target, charging_service.charge_roll(game, unit)
                ),
            )
        )
    return sorted(targets, key=lambda t: t.distance)


@router.post("/{game_id}/charge/check", response_model=DeploymentCheckOut)
async def check_charge(
    game_id: int, payload: ChargeIn, session: AsyncSession = Depends(get_session)
):
    # Whether the unit could charge the target as placed, and if not, why.
    game = await _load_game(session, game_id)
    result = charging_service.check_charge(
        game,
        deployment_service.find_unit(game, payload.unit_id),
        deployment_service.find_unit(game, payload.target_unit_id),
        _placement(payload.positions),
    )
    return _check_out(result)


@router.post("/{game_id}/charge", response_model=GameOut)
async def make_charge(
    game_id: int, payload: ChargeIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    charging_service.make_charge(
        game,
        deployment_service.find_unit(game, payload.unit_id),
        deployment_service.find_unit(game, payload.target_unit_id),
        _placement(payload.positions),
    )
    return await _commit_and_reload(session, game_id)


# --- the fight phase: piling in (see app/services/in_game/fighting.py) ---


def _pile_in_out(game: Game) -> PileInOut:
    seat = fighting_service.piling_seat(game)
    if seat is None:
        return PileInOut(seat=None, units=[])
    units = []
    for unit in fighting_service.player_units(game, seat):
        reason = fighting_service.cant_pile_in_reason(game, unit)
        units.append(
            PileInUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                engaged=fighting_service.engaged(game, unit),
                can_pile_in=reason is None,
                reason=reason,
                piled_in=fighting_service.piled_in(game, unit),
                locked_unit_model_ids=sorted(fighting_service.locked_models(game, unit)),
            )
        )
    return PileInOut(seat=seat, units=units)


@router.get("/{game_id}/pile-in", response_model=PileInOut)
async def get_pile_in(game_id: int, session: AsyncSession = Depends(get_session)):
    # At the start of the fight phase: whose turn it is to pile in, and which
    # of their units can.
    return _pile_in_out(await _load_game(session, game_id))


@router.post("/{game_id}/pile-in/check", response_model=DeploymentCheckOut)
async def check_pile_in(
    game_id: int, payload: UnitPlacementIn, session: AsyncSession = Depends(get_session)
):
    # Whether the unit could pile in as placed, and if not, why.
    game = await _load_game(session, game_id)
    result = fighting_service.check_pile_in(
        game, deployment_service.find_unit(game, payload.unit_id), _placement(payload.positions)
    )
    return _check_out(result)


@router.post("/{game_id}/pile-in", response_model=GameOut)
async def pile_in(
    game_id: int, payload: UnitPlacementIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    fighting_service.pile_in(
        game, deployment_service.find_unit(game, payload.unit_id), _placement(payload.positions)
    )
    return await _commit_and_reload(session, game_id)


@router.post("/{game_id}/pile-in/done", response_model=GameOut)
async def finish_piling_in(
    game_id: int, payload: SeatIn, session: AsyncSession = Depends(get_session)
):
    # The player has finished piling in.
    game = await _load_game(session, game_id)
    fighting_service.finish_piling_in(game, payload.seat)
    return await _commit_and_reload(session, game_id)


# --- the fight phase: fighting (see app/services/in_game/fighting.py) ---


def _fight_out(game: Game) -> FightOut:
    step = fighting_service.fight_step(game)
    if step is None:
        return FightOut(step=None, seat=None, units=[], fights=[])
    units = []
    for seat in (game.turn_seat, game_service.other_seat(game.turn_seat)):
        for unit in fighting_service.player_units(game, seat):
            reason = fighting_service.cant_fight_reason(game, unit)
            units.append(
                FightUnitOut(
                    unit_id=unit.id,
                    seat=seat,
                    name=unit.faction_unit.name,
                    fights_first=fighting_service.has_fights_first(game, unit),
                    charged=fighting_service.charged(game, unit),
                    fought=fighting_service.fought(game, unit),
                    can_fight=reason is None,
                    reason=reason,
                )
            )
    pending = fighting_service.consolidating(game)
    return FightOut(
        step=step,
        seat=pending.seat if pending else fighting_service.fighting_seat(game),
        consolidating=(
            ConsolidatingOut(
                unit_id=pending.unit_id,
                unit_name=_unit_name(game, pending.unit_id),
                target_name=_unit_name(game, pending.target_unit_id),
                target_destroyed=fighting_service._target(game, pending) is None,
            )
            if pending
            else None
        ),
        units=units,
        fights=[
            FightLogOut(
                unit_id=f.unit_id,
                unit_name=_unit_name(game, f.unit_id),
                seat=f.seat,
                target_name=_unit_name(game, f.target_unit_id),
                fights_first=f.fights_first,
                total_damage=f.total_damage,
                models_destroyed=f.models_destroyed,
            )
            for f in fighting_service._fights(game)
        ],
    )


@router.get("/{game_id}/fight", response_model=FightOut)
async def get_fight(game_id: int, session: AsyncSession = Depends(get_session)):
    # Where the fight phase is, who picks the next unit to fight, and every
    # unit's standing.
    return _fight_out(await _load_game(session, game_id))


@router.get("/{game_id}/fight/targets", response_model=list[FightTargetOut])
async def fight_targets(
    game_id: int, unit_id: int, session: AsyncSession = Depends(get_session)
):
    # The enemy units within Engagement Range of the unit, and its melee
    # weapons against each.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, unit_id)
    if (reason := fighting_service.cant_fight_reason(game, unit)) is not None:
        raise HTTPException(status_code=400, detail=f"it can't fight: {reason}")
    return [
        FightTargetOut(
            unit_id=target.id,
            name=target.faction_unit.name,
            weapons=[_weapon_out(w) for w in fighting_service.fight_reach(game, unit, target)[0]],
        )
        for target in fighting_service.fight_targets(game, unit)
    ]


@router.post("/{game_id}/fight", response_model=FightResultOut)
async def fight(game_id: int, payload: ShootIn, session: AsyncSession = Depends(get_session)):
    # The unit fights the target with the chosen melee weapons: the combat
    # calculator resolves it, each model fighting only if it's within
    # Engagement Range of the target.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    target = deployment_service.find_unit(game, payload.target_unit_id)
    weapon_ids = set(payload.weapon_ids) | {
        ("enhancement", i) for i in payload.enhancement_weapon_ids
    }
    firing = fighting_service.check_fight(game, unit, target, weapon_ids)
    charged = fighting_service.charged(game, unit)
    fights_first = fighting_service.has_fights_first(game, unit)
    defender_wounds = casualties_service.wounds_remaining(game, target)
    attacker_wounds = casualties_service.wounds_remaining(game, unit)

    combat = await calculate_combat(
        session,
        CombatIn(
            game_id=game.id,
            attacking_unit_id=unit.id,
            defending_unit_id=target.id,
            selected_weapon_ids=payload.weapon_ids,
            selected_enhancement_weapon_ids=payload.enhancement_weapon_ids,
            in_engagement_range=True,
            charged=charged,
            attacker_positions=_attacker_positions(game, unit, target),
            defender_positions=_defender_positions(game, target),
            defender_battle_shocked=battle_shock_service.is_battle_shocked(game, target),
            # The options each side chose for its army rules this round (e.g.
            # its Doctrina Imperative) and its abilities in its Command phase.
            attacker_rule_options=_rule_options(game, unit, target),
            defender_rule_options=_rule_options(game, target),
            defender_visible=True,
            defender_in_range=True,
        ),
        firing=firing,
        defender_wounds=defender_wounds,
        attacker_wounds=attacker_wounds,
    )
    destroyed = casualties_service.apply_attack(
        game,
        unit,
        target,
        defender_wounds,
        combat.defender_wounds_remaining,
        combat.attacker_damage,
    )
    fighting_service.record_fight(
        game, unit, target, fights_first, combat.total_damage, combat.models_destroyed
    )
    await session.commit()
    return FightResultOut(
        charged=charged,
        fights_first=fights_first,
        combat=combat,
        destroyed_unit_model_ids=destroyed,
    )


@router.post("/{game_id}/fight/consolidate/check", response_model=DeploymentCheckOut)
async def check_consolidation(
    game_id: int, payload: UnitPlacementIn, session: AsyncSession = Depends(get_session)
):
    # Whether the unit that just fought could consolidate as placed, and if
    # not, why.
    game = await _load_game(session, game_id)
    result = fighting_service.check_consolidation(
        game, deployment_service.find_unit(game, payload.unit_id), _placement(payload.positions)
    )
    return _check_out(result)


@router.post("/{game_id}/fight/consolidate", response_model=GameOut)
async def consolidate(
    game_id: int, payload: UnitPlacementIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    fighting_service.consolidate(
        game, deployment_service.find_unit(game, payload.unit_id), _placement(payload.positions)
    )
    return await _commit_and_reload(session, game_id)


@router.post("/{game_id}/fight/consolidate/skip", response_model=GameOut)
async def skip_consolidation(
    game_id: int, payload: UnitIdIn, session: AsyncSession = Depends(get_session)
):
    # The unit that just fought doesn't consolidate.
    game = await _load_game(session, game_id)
    fighting_service.skip_consolidation(game, deployment_service.find_unit(game, payload.unit_id))
    return await _commit_and_reload(session, game_id)


# --- the start of the battle round (see app/services/in_game/battle_round.py) ---


@router.get("/{game_id}/round-start", response_model=RoundStartOut)
async def round_start(game_id: int, session: AsyncSession = Depends(get_session)):
    # The rules each player has at the start of the current battle round.
    game = await _load_game(session, game_id)
    rules = battle_round_service.round_start_rules(game, game.battle_round)
    chosen = {p.seat: battle_round_service.choices(game, p.seat) for p in game.players}
    return RoundStartOut(
        battle_round=game.battle_round,
        players=[
            RoundStartPlayerOut(
                seat=player.seat,
                user_name=player.user.name,
                rules=[
                    RoundStartRuleOut(
                        kind=r.kind,
                        name=r.name,
                        description=r.description,
                        units=r.units,
                        faction_ability_id=r.faction_ability_id,
                        options=r.options,
                        option_descriptions=r.option_descriptions,
                        required=r.required,
                        decision=r.decision,
                        chosen=chosen[player.seat].get(r.faction_ability_id),
                    )
                    for r in rules[player.seat]
                ],
            )
            for player in game.players
        ],
    )


@router.post("/{game_id}/round-start/choice", response_model=RoundStartOut)
async def choose_rule_option(
    game_id: int, payload: RuleChoiceIn, session: AsyncSession = Depends(get_session)
):
    # A player picks an option for one of their army rules this battle round
    # (e.g. which Doctrina Imperative is active), at its start.
    game = await _load_game(session, game_id)
    battle_round_service.choose(game, payload.seat, payload.faction_ability_id, payload.option)
    await session.commit()
    return await round_start(game_id, session)


# --- where models can reach (see app/services/in_game/pathing.py) ---


@router.post("/{game_id}/reach", response_model=ReachOut)
async def reach(game_id: int, payload: ReachIn, session: AsyncSession = Depends(get_session)):
    # Where each of a unit's models can get from where it sets off within its
    # distance, going round dense terrain unless it can go through it - for
    # showing how far a unit can move or charge.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    models = {m.id: m for m in unit.unit_models}
    starts = {
        m.unit_model_id: deployment_service.base_at(models[m.unit_model_id], m.x, m.y)
        for m in payload.models
        if m.unit_model_id in models
    }
    pather = pathing_service.for_unit(
        game, unit, starts, max((m.distance for m in payload.models), default=0)
    )
    out = []
    for m in payload.models:
        if m.unit_model_id not in starts:
            continue
        start = starts[m.unit_model_id]
        out.append(
            ReachModelOut(
                unit_model_id=m.unit_model_id,
                clearance=max(start.semi_axes),
                regions=[
                    [TerrainPointOut(x=round(x, 2), y=round(y, 2)) for x, y in region]
                    for region in pather.reach(start, m.distance)
                ],
            )
        )
    return ReachOut(models=out)


# --- declaring battle formations (see app/services/in_game/battle_formations.py) ---


def _formations_out(game: Game) -> FormationsOut:
    players = []
    for player in game.players:
        units = []
        for unit in deployment_service.deployable_units(player):
            f = deployment_service.battle_formation(game, unit)
            units.append(
                FormationUnitOut(
                    unit_id=unit.id,
                    name=unit.faction_unit.name,
                    points=unit.points,
                    transport=battle_formations_service.is_transport(unit),
                    place=f.place if f else None,
                    transport_unit_id=f.transport_unit_id if f else None,
                )
            )
        players.append(
            FormationPlayerOut(
                seat=player.seat,
                user_name=player.user.name,
                done=battle_formations_service.done(game, player.seat),
                army_points=battle_formations_service.army_points(game, player),
                reserves_points=battle_formations_service.reserves_points(game, player),
                reserves_limit=battle_formations_service.reserves_limit(game, player),
                units=units,
            )
        )
    return FormationsOut(step=deployment_service.deployment_step(game), players=players)


@router.get("/{game_id}/formations", response_model=FormationsOut)
async def get_formations(game_id: int, session: AsyncSession = Depends(get_session)):
    # Each player's units and where they start (battlefield, Strategic
    # Reserves, or embarked).
    return _formations_out(await _load_game(session, game_id))


@router.post("/{game_id}/formations", response_model=FormationsOut)
async def set_formation(
    game_id: int, payload: FormationIn, session: AsyncSession = Depends(get_session)
):
    # Puts one of a player's units in Strategic Reserves, embarks it in a
    # transport, or back on the battlefield.
    game = await _load_game(session, game_id)
    transport = (
        deployment_service.find_unit(game, payload.transport_unit_id)
        if payload.transport_unit_id is not None
        else None
    )
    battle_formations_service.set_formation(
        game,
        payload.seat,
        deployment_service.find_unit(game, payload.unit_id),
        payload.place,
        transport,
    )
    await session.commit()
    return _formations_out(await _load_game(session, game_id))


@router.post("/{game_id}/formations/done", response_model=GameOut)
async def declare_formations(
    game_id: int, payload: SeatIn, session: AsyncSession = Depends(get_session)
):
    # The player has declared their battle formations.
    game = await _load_game(session, game_id)
    await game_service.declare_formations(session, game, payload.seat)
    return await _commit_and_reload(session, game_id)


# --- bringing units in from Reserves (see app/services/in_game/reinforcements.py) ---


def _reserves_out(game: Game) -> ReservesOut:
    step = seat = None
    if game.status == "in_progress" and game.phase == "movement":
        if reinforcements_service.movement_ended(game):
            step, seat = "rapid_ingress", game_service.other_seat(game.turn_seat)
        else:
            step, seat = "movement", game.turn_seat
    units = (
        [
            u
            for u in reinforcements_service.reserve_units(game, seat)
            # (In the first battle round, only those that can make an
            # ingress move.)
            if reinforcements_service.arrival_round(game, u, step == "rapid_ingress")
        ]
        if seat is not None
        else []
    )
    if not units and not reinforcements_service.arrival_round(game):
        seat = None
    return ReservesOut(
        step=step,
        seat=seat,
        battle_round=game.battle_round,
        units=[
            ReserveUnitOut(
                unit_id=u.id,
                name=u.faction_unit.name,
                deep_strike=reinforcements_service.has_deep_strike(u),
                teleport_homer=(
                    {"x": token.x, "y": token.y}
                    if (token := teleport_homer_service.token(game, u)) is not None
                    else None
                ),
            )
            for u in units
        ],
    )


@router.get("/{game_id}/reserves", response_model=ReservesOut)
async def get_reserves(game_id: int, session: AsyncSession = Depends(get_session)):
    # Who can bring units in from Strategic Reserves now, and which.
    return _reserves_out(await _load_game(session, game_id))


def _arriving(game: Game, unit_id: int):
    # The unit to bring in, and whether it's by Rapid Ingress (the movement
    # phase is over) - checked that it can arrive now.
    unit = deployment_service.find_unit(game, unit_id)
    rapid = reinforcements_service.movement_ended(game)
    reinforcements_service.check_turn(game, unit, rapid)
    return unit, rapid


@router.post("/{game_id}/reserves/formation", response_model=list[ModelPositionOut])
async def reserves_formation(
    game_id: int, payload: DeploymentFormationIn, session: AsyncSession = Depends(get_session)
):
    # Where a unit from Reserves starts when it's set down at (x, y), for the
    # player to arrange.
    game = await _load_game(session, game_id)
    unit, _ = _arriving(game, payload.unit_id)
    return [
        ModelPositionOut(unit_model_id=i, x=x, y=y, rotation=rotation)
        for i, (x, y, rotation) in deployment_service.formation(
            game, unit, payload.x, payload.y
        ).items()
    ]


@router.post("/{game_id}/reserves/check", response_model=DeploymentCheckOut)
async def check_arrival(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    # Whether a unit could arrive from Reserves as placed, and if not, why.
    game = await _load_game(session, game_id)
    unit, _ = _arriving(game, payload.unit_id)
    return _check_out(
        reinforcements_service.check_arrival(
            game, unit, _placement(payload.positions), payload.teleport_homer
        )
    )


@router.post("/{game_id}/reserves", response_model=GameOut)
async def bring_in(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    # Sets a unit up from Reserves - at the end of the opponent's movement
    # phase, by using Rapid Ingress (its CP spent).
    game = await _load_game(session, game_id)
    unit, rapid = _arriving(game, payload.unit_id)
    placement = _placement(payload.positions)
    homer = payload.teleport_homer
    if homer and not rapid:
        raise HTTPException(
            status_code=400, detail="a Teleport Homer token is used with Rapid Ingress"
        )
    result = reinforcements_service.check_arrival(game, unit, placement, homer)
    if not result.valid:
        raise HTTPException(
            status_code=400, detail="can't bring it in there: " + "; ".join(result.problems)
        )
    if rapid:
        stratagem = await game_service.rapid_ingress_stratagem(session)
        if stratagem is None:
            raise HTTPException(status_code=400, detail="there's no Rapid Ingress stratagem")
        player = deployment_service.owner(game, unit)
        # Using its Teleport Homer token: 1CP less - and any its enhancement
        # takes off (e.g. Beacon Angelis).
        discount = (
            teleport_homer_service.CP_DISCOUNT if homer else 0
        ) + reinforcements_service.rapid_ingress_discount(unit)
        await game_service.use_stratagem(
            session, game, player, stratagem, cp_discount=discount, targeted_unit=unit
        )
    reinforcements_service.bring_in(game, unit, placement, rapid, homer)
    return await _commit_and_reload(session, game_id)


# --- Reanimation Protocols (see app/seeds/factions/necrons/reanimation.py), and
# setting up the models healing returns (app/services/in_game/heal.py) ---


@router.get("/{game_id}/reanimation", response_model=ReanimationOut)
async def get_reanimation(game_id: int, session: AsyncSession = Depends(get_session)):
    # The Reanimation Protocols activated at the end of this turn's command
    # phase - each unit's roll, what it healed - and, while there are
    # returned models to set up (`placing`), where to start each.
    game = await _load_game(session, game_id)
    if game.status != "in_progress" or game.phase != "command":
        return ReanimationOut(placing=False, seat=None, units=[])
    units = []
    for record in reanimation_service.reanimations(game):
        unit = deployment_service.find_unit(game, record.unit_id)
        start = (
            heal_service.suggested(game, unit)
            if heal_service.to_place(game, unit)
            else {}
        )
        units.append(
            ReanimationUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                roll=record.roll,
                healed=record.healed,
                returned=record.returned,
                to_place=[
                    ModelPositionOut(unit_model_id=i, x=x, y=y, rotation=rotation)
                    for i, (x, y, rotation) in start.items()
                ],
            )
        )
    return ReanimationOut(
        placing=heal_service.placing(game), seat=game.turn_seat, units=units
    )


@router.post("/{game_id}/reanimation/check", response_model=DeploymentCheckOut)
async def check_reanimation(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    # Whether a unit's reanimated models could be set up as placed, and if
    # not, why.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    heal_service.check_turn(game, unit)
    return _check_out(
        heal_service.check_return(game, unit, _placement(payload.positions))
    )


@router.post("/{game_id}/reanimation", response_model=GameOut)
async def place_reanimated(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    # Sets up a unit's reanimated models.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    heal_service.place(game, unit, _placement(payload.positions))
    return await _commit_and_reload(session, game_id)


# --- the Command phase's abilities (see app/services/in_game/command_phase.py) ---


def _command_out(game: Game) -> CommandOut:
    if not command_phase_service.is_command_phase(game):
        return CommandOut(seat=None, abilities=[], heals=[])
    seat = game.turn_seat
    active = {
        (c.unit_id, c.ability): c for c in command_phase_service.active_choices(game, seat)
    }
    chosen = {(c.unit_id, c.ability) for c in command_phase_service.this_phase(game, seat)}
    abilities = []
    for ability in command_phase_service.command_abilities(game, seat):
        key = (ability.unit.id, ability.ability)
        options = command_phase_service.options(ability.ability)
        current = active.get(key)
        description = next(
            a.description for a in ability.model.model.abilities if a.name == ability.ability
        )
        abilities.append(
            CommandAbilityOut(
                unit_id=ability.unit.id,
                unit_name=ability.unit.faction_unit.name,
                ability=ability.ability,
                description=description or "",
                options=list(options),
                option_descriptions={
                    name: option.description
                    for name, option in options.items()
                    if option.description
                },
                required=ability.config.required,
                persistent=ability.config.persistent,
                active=current.option if current else None,
                chosen=key in chosen,
                needs_target=bool(ability.config.target_keywords),
                targets=[
                    UnitIdNameOut(unit_id=u.id, name=u.faction_unit.name)
                    for u in command_phase_service.targets(game, ability)
                ],
                target_unit_id=current.target_unit_id if current else None,
                option_targets={
                    name: [
                        UnitIdNameOut(unit_id=u.id, name=u.faction_unit.name)
                        for u in command_phase_service.enemy_targets(game, ability)
                    ]
                    for name, option in options.items()
                    if option.targets_enemy
                },
            )
        )
    for rule in command_phase_service.army_rules(game, seat):
        names = list(faction_seeds.rule_options(*rule.key))
        available = command_phase_service.army_rule_options(game, seat, rule)
        selected = command_phase_service.army_rule_this_phase(game, seat, rule.ability.id)
        abilities.append(
            CommandAbilityOut(
                unit_name=", ".join(rule.units),
                faction_ability_id=rule.ability.id,
                ability=rule.ability.name,
                description=rule.ability.description or "",
                options=available,
                option_descriptions=faction_seeds.COMMAND_PHASE_DESCRIPTIONS.get(rule.key, {}),
                used_options=[n for n in names if n not in available],
                required=False,
                persistent=False,
                active=selected.option if selected else None,
                chosen=selected is not None,
            )
        )
    units = {
        m.id: (u, m) for p in game.players for u in p.army_list.units for m in u.unit_models
    }
    return CommandOut(
        seat=seat,
        abilities=abilities,
        heals=[
            CommandHealOut(
                unit_name=units[h.unit_model_id][0].faction_unit.name,
                model_name=units[h.unit_model_id][1].model.name,
                ability=h.ability,
                roll=h.roll,
                healed=h.healed,
            )
            for h in command_phase_service.heals(game)
        ],
    )


@router.get("/{game_id}/command", response_model=CommandOut)
async def get_command(game_id: int, session: AsyncSession = Depends(get_session)):
    # In the Command phase: the player whose turn it is's abilities whose
    # options they select now, and the models that healed at its start.
    return _command_out(await _load_game(session, game_id))


@router.post("/{game_id}/command/choice", response_model=CommandOut)
async def choose_command_option(
    game_id: int, payload: CommandChoiceIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    if payload.faction_ability_id is not None:
        command_phase_service.choose_army_rule(
            game, payload.seat, payload.faction_ability_id, payload.option
        )
    else:
        if payload.unit_id is None:
            raise HTTPException(status_code=400, detail="choose a unit's ability or an army rule")
        command_phase_service.choose(
            game, payload.seat, payload.unit_id, payload.ability, payload.option,
            payload.target_unit_id,
        )
    await session.commit()
    return _command_out(await _load_game(session, game_id))


# --- Battle-shock (see app/services/in_game/battle_shock.py) ---


def _test_out(game: Game, test) -> BattleShockTestOut:
    unit = deployment_service.find_unit(game, test.unit_id)
    return BattleShockTestOut(
        id=test.id,
        unit_id=unit.id,
        unit_name=unit.faction_unit.name,
        seat=deployment_service.owner(game, unit).seat,
        reason=test.reason,
        modifier=test.modifier,
        leadership=battle_shock_service.needed(game, unit),
        starting_strength=battle_shock_service.starting_strength(unit),
        current_strength=battle_shock_service.current_strength(game, unit),
        dice=[d for d in (test.first_die, test.second_die) if d is not None],
        insane_bravery=test.insane_bravery,
        passed=test.passed,
        mortal_wounds=(
            f"{test.wounds.source}: {test.wounds.roll} mortal wounds" if test.wounds else None
        ),
    )


async def _battle_shock_out(session: AsyncSession, game: Game) -> BattleShockOut:
    stratagem = await game_service.core_stratagem(session, battle_shock_service.INSANE_BRAVERY)
    shocked = battle_shock_service.battle_shocked_ids(game)
    placed = deployment_service.positions(game)
    return BattleShockOut(
        pending=[_test_out(game, t) for t in battle_shock_service.pending(game)],
        taken=[
            _test_out(game, t)
            for t in game.battle_shock_tests
            if t.passed is not None
            and t.battle_round == game.battle_round
            and t.turn_seat == game.turn_seat
            and t.phase == game.phase
        ],
        battle_shocked=[
            BattleShockUnitOut(unit_id=u.id, name=u.faction_unit.name, seat=p.seat)
            for p in game.players
            for u in deployment_service.deployable_units(p)
            if u.id in shocked and deployment_service.is_deployed(u, placed)
        ],
        insane_bravery_cp=stratagem.cp if stratagem else None,
        insane_bravery={
            p.seat: battle_shock_service.insane_bravery_reason(game, p.seat, stratagem)
            for p in game.players
        },
    )


@router.get("/{game_id}/battle-shock", response_model=BattleShockOut)
async def get_battle_shock(game_id: int, session: AsyncSession = Depends(get_session)):
    return await _battle_shock_out(session, await _load_game(session, game_id))


@router.post("/{game_id}/battle-shock/test", response_model=BattleShockOut)
async def require_battle_shock_test(
    game_id: int, payload: BattleShockRequireIn, session: AsyncSession = Depends(get_session)
):
    # A rule or stratagem makes a unit take a Battle-shock test (for its
    # controller to take).
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    battle_shock_service.require(game, unit, payload.reason, payload.modifier)
    await session.commit()
    return await _battle_shock_out(session, await _load_game(session, game_id))


@router.post("/{game_id}/battle-shock/{test_id}/take", response_model=BattleShockOut)
async def take_battle_shock_test(
    game_id: int,
    test_id: int,
    payload: BattleShockTakeIn,
    session: AsyncSession = Depends(get_session),
):
    # Takes a pending test: rolled, or passed with Insane Bravery.
    game = await _load_game(session, game_id)
    test = next((t for t in battle_shock_service.pending(game) if t.id == test_id), None)
    if test is None:
        raise HTTPException(status_code=400, detail="no such Battle-shock test to take")
    stratagem = None
    if payload.insane_bravery:
        stratagem = await game_service.core_stratagem(
            session, battle_shock_service.INSANE_BRAVERY
        )
        if stratagem is None:
            raise HTTPException(status_code=400, detail="there's no Insane Bravery stratagem")
    battle_shock_service.take(game, test, stratagem)
    await session.commit()
    return await _battle_shock_out(session, await _load_game(session, game_id))


# --- the turn record (see app/services/in_game/turn_record.py) ---


@router.get("/{game_id}/turn-record", response_model=TurnRecordOut)
async def get_turn_record(
    game_id: int,
    battle_round: int | None = None,
    turn_seat: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    # What happened in a turn (this one, unless another is asked for): the
    # models destroyed, and the objectives at its start.
    game = await _load_game(session, game_id)
    battle_round = battle_round if battle_round is not None else game.battle_round
    turn_seat = turn_seat if turn_seat is not None else game.turn_seat
    if turn_seat is None:
        raise HTTPException(status_code=400, detail="the game isn't in a turn")
    models = {m.id: m for p in game.players for u in p.army_list.units for m in u.unit_models}
    on = turn_record_service.started_on_objectives(game, battle_round, turn_seat)
    kinds = {o.id: o.kind for o in (game.layout.objectives if game.layout else [])}
    return TurnRecordOut(
        battle_round=battle_round,
        turn_seat=turn_seat,
        destroyed=[
            DestroyedModelOut(
                phase=d.phase,
                seat=turn_record_service.owner_seat(game, d.unit_id),
                unit_id=d.unit_id,
                unit_name=_unit_name(game, d.unit_id),
                model_name=models[d.unit_model_id].model.name,
                destroyed_by_unit_id=d.destroyed_by_unit_id,
                destroyed_by=(
                    _unit_name(game, d.destroyed_by_unit_id) if d.destroyed_by_unit_id else None
                ),
                unit_destroyed=d.unit_destroyed,
            )
            for d in turn_record_service.models_destroyed(game, battle_round, turn_seat)
        ],
        start=[
            TurnStartObjectiveOut(
                objective_id=objective_id,
                kind=kinds.get(objective_id, ""),
                controller=controller,
                unit_ids=sorted(u for u, objs in on.items() if objective_id in objs),
            )
            for objective_id, controller in turn_record_service.controlled_at_start(
                game, battle_round, turn_seat
            ).items()
        ],
    )


# --- automatic scoring (see app/services/in_game/scoring.py) ---


def _scoring_out(game: Game) -> ScoringOut:
    cards = {s.id: (s, p) for p in game.players for s in p.secondaries}
    return ScoringOut(
        offers=[
            ClaimOfferOut(
                id=o.id,
                seat=cards[o.game_secondary_id][1].seat,
                game_secondary_id=o.game_secondary_id,
                name=cards[o.game_secondary_id][0].mission.name,
                timing=o.timing,
                points=o.points,
                reasons=[
                    ScoreReasonOut(text=t, points=p) for t, p in scoring_service.offer_lines(o)
                ],
            )
            for o in scoring_service.pending_offers(game)
        ],
        scored={
            p.seat: [
                _score_out(s)
                for s in p.scores
                if s.battle_round == game.battle_round and s.turn_seat == game.turn_seat
            ]
            for p in game.players
        },
    )


@router.get("/{game_id}/scoring", response_model=ScoringOut)
async def get_scoring(game_id: int, session: AsyncSession = Depends(get_session)):
    return _scoring_out(await _load_game(session, game_id))


@router.post("/{game_id}/scoring/offers/{offer_id}/claim", response_model=GameOut)
async def claim_offer(game_id: int, offer_id: int, session: AsyncSession = Depends(get_session)):
    game = await _load_game(session, game_id)
    scoring_service.claim(game, offer_id)
    return await _commit_and_reload(session, game_id)


@router.post("/{game_id}/scoring/offers/{offer_id}/hold", response_model=GameOut)
async def hold_offer(game_id: int, offer_id: int, session: AsyncSession = Depends(get_session)):
    game = await _load_game(session, game_id)
    scoring_service.hold(game, offer_id)
    return await _commit_and_reload(session, game_id)


# --- actions (see app/services/in_game/actions.py) ---


def _action_target(game: Game, record) -> str:
    layout = game.layout
    if record.target_unit_id is not None:
        return _unit_name(game, record.target_unit_id)
    if record.objective_id is not None:
        objective = next(o for o in layout.objectives if o.id == record.objective_id)
        return actions_service._objective_label(objective)
    area = next(a for a in layout.areas if a.id == record.area_id)
    return actions_service._area_label(game, area)


def _actions_out(game: Game) -> ActionsOut:
    options = {}
    if game.status == "in_progress" and game.phase == "shooting":
        for unit in shooting_service.shooting_units(game):
            options[unit.id] = [
                ActionOptionOut(
                    action=a.action.name,
                    card=actions_service.card_for(
                        game, deployment_service.owner(game, unit).seat, a.action
                    ),
                    completes=a.action.completes,
                    targets=[
                        ActionTargetOut(kind=t.kind, id=t.id, label=t.label) for t in a.targets
                    ],
                    reason=a.reason,
                )
                for a in actions_service.available(game, unit)
            ]
    return ActionsOut(
        options=options,
        started=[
            UnitActionOut(
                unit_id=a.unit_id,
                unit_name=_unit_name(game, a.unit_id),
                action=a.action,
                target=_action_target(game, a),
                status=a.status,
            )
            for a in game.actions
            if a.battle_round == game.battle_round and a.turn_seat == game.turn_seat
        ],
    )


@router.get("/{game_id}/actions", response_model=ActionsOut)
async def get_actions(game_id: int, session: AsyncSession = Depends(get_session)):
    # In the Shooting phase: the actions each of the player whose turn it
    # is's units could start, and those started this turn.
    return _actions_out(await _load_game(session, game_id))


@router.post("/{game_id}/actions", response_model=ActionsOut)
async def start_action(
    game_id: int, payload: ActionIn, session: AsyncSession = Depends(get_session)
):
    # The unit starts an action instead of shooting.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    actions_service.start(game, unit, payload.action, payload.target_id)
    await session.commit()
    return _actions_out(await _load_game(session, game_id))


# --- missions' markers, marked units and prompts (see
# app/services/in_game/mission_state.py) ---

PROMPT_TEXT = {
    "place_markers": "Place your operation markers: pick {n} terrain areas not within your "
    "deployment zone.",
    "consecrate": "Consecration units can each consecrate an objective they're within range of "
    "(placing an operation marker there) - or not.",
    "condemn": "Condemn 1 to {n} enemy units (within range of objectives, or that destroyed "
    "your units last turn) until the start of your next turn.",
    "condemn_any": "Condemn one enemy unit until the start of your next turn.",
    "remove_marker": "Sensor sweep: remove one operation marker from the battlefield.",
    "beacon": "Select one of your units on the battlefield (or embarked in a transport there) "
    "to be your beacon unit.",
    "guards": "For each objective, you can select one of your units to guard it until the start "
    "of your next turn (guarded while it's within range and you control the objective).",
    "tempting_target": "Select one objective within No Man's Land (not a home objective) to be "
    "your opponent's tempting target.",
    "redraw": "WHEN DRAWN: you can redraw these cards (pick any).",
}
PROMPT_MISSIONS = {
    "place_markers": "Locate and Deny",
    "consecrate": "Consecrate",
    "condemn": "Punishment",
    "beacon": "Beacon",
    "guards": "Burden of Trust",
    "tempting_target": "A Tempting Target",
}


def _marker_out(game: Game, marker, index: int) -> OperationMarkerOut:
    layout = game.layout
    if marker.objective_id is not None:
        objective = next(o for o in layout.objectives if o.id == marker.objective_id)
        x, y = objective.x, objective.y
        label = actions_service._objective_label(objective)
    else:
        area = next(a for a in layout.areas if a.id == marker.area_id)
        x, y = area.x, area.y
        label = actions_service._area_label(game, area)
    # Several on one place: spread a little.
    return OperationMarkerOut(
        id=marker.id,
        seat=marker.seat,
        source=marker.source,
        objective_id=marker.objective_id,
        area_id=marker.area_id,
        x=round(x + 1.2 * (index % 3) - 1.2, 2),
        y=round(y + 1.8 + 1.2 * (index // 3), 2),
        label=label,
    )


def _prompt_out(game: Game, prompt) -> MissionPromptOut:
    seat, kind = prompt.seat, prompt.kind
    mission = PROMPT_MISSIONS.get(kind, "")
    if kind == "place_markers":
        areas, count = mission_state_service.place_marker_options(game, seat)
        options = [
            PromptOptionOut(id=a.id, label=f"#{i + 1} {actions_service._area_label(game, a)}")
            for i, a in enumerate(areas)
        ]
        return MissionPromptOut(
            id=prompt.id, seat=seat, kind=kind, mission=mission,
            text=PROMPT_TEXT[kind].format(n=count), options=options,
            pick_min=count, pick_max=count,
        )
    if kind == "consecrate":
        options = [
            PromptOptionOut(
                id=o.id,
                label=f"{_unit_name(game, unit_id)}: {actions_service._objective_label(o)}",
                unit_id=unit_id,
            )
            for unit_id, objs in mission_state_service.consecrate_options(game, seat).items()
            for o in objs
        ]
        return MissionPromptOut(
            id=prompt.id, seat=seat, kind=kind, mission=mission, text=PROMPT_TEXT[kind],
            options=options, pick_min=0, pick_max=len(options),
        )
    if kind == "condemn":
        units, eligible = mission_state_service.condemn_options(game, seat)
        most = mission_state_service.MAX_CONDEMNED if eligible else 1
        return MissionPromptOut(
            id=prompt.id, seat=seat, kind=kind, mission=mission,
            text=PROMPT_TEXT["condemn" if eligible else "condemn_any"].format(n=most),
            options=[PromptOptionOut(id=u.id, label=u.faction_unit.name) for u in units],
            pick_min=1, pick_max=most,
        )
    if kind in ("beacon", "guards"):
        candidates = (
            mission_state_service.beacon_candidates
            if kind == "beacon"
            else mission_state_service.beacon_options
        )
        units = [
            PromptOptionOut(id=u.id, label=u.faction_unit.name)
            for u in candidates(game, seat)
        ]
        if kind == "beacon":
            return MissionPromptOut(
                id=prompt.id, seat=seat, kind=kind, mission=mission, text=PROMPT_TEXT[kind],
                options=units, pick_min=1, pick_max=1,
            )
        objectives = game.layout.objectives if game.layout else []
        return MissionPromptOut(
            id=prompt.id, seat=seat, kind=kind, mission=mission, text=PROMPT_TEXT[kind],
            options=[
                PromptOptionOut(id=o.id, label=actions_service._objective_label(o))
                for o in objectives
            ],
            pick_min=0, pick_max=len(objectives), units=units,
        )
    if kind == "redraw":
        cards = {c.id: c for c in game_service.player_at(game, seat).secondaries}
        how = {
            "discard": "discard it and draw a new card",
            "shuffle": "draw a new card and shuffle it back into your deck",
        }
        return MissionPromptOut(
            id=prompt.id, seat=seat, kind=kind, mission="Secondary missions",
            text=PROMPT_TEXT[kind],
            options=[
                PromptOptionOut(id=card_id, label=f"{cards[card_id].mission.name}: {how[way]}")
                for card_id, way in mission_state_service.redraw_offers(game, seat).items()
            ],
            pick_min=0, pick_max=len(mission_state_service.redraw_offers(game, seat)),
        )
    if kind == "tempting_target":
        holder = game_service.other_seat(seat)
        return MissionPromptOut(
            id=prompt.id, seat=seat, kind=kind, mission=mission, text=PROMPT_TEXT[kind],
            options=[
                PromptOptionOut(id=o.id, label=actions_service._objective_label(o))
                for o in mission_state_service.tempting_options(game, holder)
            ],
            pick_min=1, pick_max=1,
        )
    markers = mission_state_service.markers(game)
    player = next(p for p in game.players if p.seat == seat)
    return MissionPromptOut(
        id=prompt.id, seat=seat, kind=kind,
        mission=player.primary_mission.name if player.primary_mission else "",
        text=PROMPT_TEXT[kind],
        options=[
            PromptOptionOut(
                id=m.id,
                label=f"{game_service.player_at(game, m.seat).user.name}'s marker - "
                f"{_marker_out(game, m, 0).label}",
            )
            for m in markers
        ],
        pick_min=1, pick_max=1,
    )


def _mission_state_out(game: Game) -> MissionStateOut:
    on_battlefield = mission_state_service.markers(game)
    counts: dict[tuple, int] = {}
    markers = []
    for m in on_battlefield:
        key = (m.objective_id, m.area_id)
        markers.append(_marker_out(game, m, counts.get(key, 0)))
        counts[key] = counts.get(key, 0) + 1
    return MissionStateOut(
        prompts=[_prompt_out(game, p) for p in mission_state_service.pending(game)],
        markers=markers,
        marked=[
            MarkedUnitOut(
                unit_id=m.unit_id, unit_name=_unit_name(game, m.unit_id), seat=m.seat, kind=m.kind
            )
            for kind in ("condemned", "surveilled", "consecration")
            for m in mission_state_service.marked(game, kind)
        ],
    )


@router.get("/{game_id}/mission", response_model=MissionStateOut)
async def get_mission_state(game_id: int, session: AsyncSession = Depends(get_session)):
    # The operation markers on the battlefield, the units missions mark, and
    # the choices missions are waiting for.
    return _mission_state_out(await _load_game(session, game_id))


@router.post("/{game_id}/mission/prompts/{prompt_id}", response_model=MissionStateOut)
async def answer_mission_prompt(
    game_id: int,
    prompt_id: int,
    payload: MissionAnswerIn,
    session: AsyncSession = Depends(get_session),
):
    game = await _load_game(session, game_id)
    prompt = next((p for p in mission_state_service.pending(game) if p.id == prompt_id), None)
    if prompt is None:
        raise HTTPException(status_code=400, detail="no such choice waiting to be made")
    if prompt.kind == "redraw":
        await game_service.redraw(session, game, prompt, payload.ids)
        await session.commit()
        return _mission_state_out(await _load_game(session, game_id))
    given = mission_state_service.Answer(
        consecrations=payload.consecrations, guards=payload.guards
    )
    if prompt.kind == "place_markers":
        given.area_ids = payload.ids
    elif prompt.kind in ("condemn", "beacon"):
        given.unit_ids = payload.ids
    elif prompt.kind == "tempting_target":
        given.objective_id = payload.ids[0] if payload.ids else None
    elif prompt.kind == "remove_marker":
        given.marker_id = payload.ids[0] if payload.ids else None
    mission_state_service.answer(game, prompt_id, given)
    await session.commit()
    return _mission_state_out(await _load_game(session, game_id))


# --- disembarking from transports (see app/services/in_game/embarked.py) ---


def _embarked_out(game: Game) -> EmbarkedOut:
    from app.services.in_game import reinforcements

    if (
        game.status != "in_progress"
        or game.phase != "movement"
        or reinforcements.movement_ended(game)
    ):
        return EmbarkedOut(seat=None, units=[])
    return EmbarkedOut(
        seat=game.turn_seat,
        units=[
            EmbarkedUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                transport_unit_id=carrier.id,
                transport_name=carrier.faction_unit.name,
            )
            for unit, carrier in embarked_service.embarked_units(game, game.turn_seat)
            # Not one that embarked this phase: it can't disembark again yet.
            if not embarked_service.transited(game, unit, "embarked")
        ],
        embarkable=[
            EmbarkableUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                transports=[
                    UnitIdNameOut(unit_id=c.id, name=c.faction_unit.name) for c in carriers
                ],
            )
            for unit, carriers in embarked_service.embarkable(game)
        ],
    )


@router.get("/{game_id}/embarked", response_model=EmbarkedOut)
async def get_embarked(game_id: int, session: AsyncSession = Depends(get_session)):
    # Which units the player whose turn it is can disembark now.
    return _embarked_out(await _load_game(session, game_id))


@router.post("/{game_id}/embarked/formation", response_model=list[ModelPositionOut])
async def disembark_formation(
    game_id: int, payload: DeploymentFormationIn, session: AsyncSession = Depends(get_session)
):
    # Where a disembarking unit's models start when it's set down at (x, y),
    # for the player to arrange.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    embarked_service.check_turn(game, unit)
    return [
        ModelPositionOut(unit_model_id=i, x=x, y=y, rotation=rotation)
        for i, (x, y, rotation) in deployment_service.formation(
            game, unit, payload.x, payload.y, embarked_service.surviving_models(game, unit)
        ).items()
    ]


@router.post("/{game_id}/embarked/check", response_model=DeploymentCheckOut)
async def check_disembark(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    embarked_service.check_turn(game, unit)
    return _check_out(embarked_service.check_disembark(game, unit, _placement(payload.positions)))


# --- psychic abilities (see app/services/in_game/psychic.py) ---


def _psychic_out(game: Game) -> PsychicOut:
    units = []
    for unit in psychic_service.psykers(game):
        abilities = []
        for name, level in psychic_service.abilities(unit).items():
            reason = psychic_service.unavailable_reason(game, unit, name)
            targets = (
                psychic_service.soul_sight_targets(game, unit)
                if name == psychic_service.SOUL_SIGHT and reason is None
                else []
            )
            abilities.append(
                PsychicAbilityOut(
                    name=name,
                    level=level,
                    usable=reason is None,
                    reason=reason,
                    targets=[UnitIdNameOut(unit_id=t.id, name=t.faction_unit.name) for t in targets],
                )
            )
        units.append(
            PsychicUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                seat=deployment_service.owner(game, unit).seat,
                psyker_level=psychic_service.psyker_level(unit),
                used_this_round=sum(
                    psychic_service.abilities(unit).get(u.ability, 0)
                    for u in psychic_service.uses_this_round(game, unit)
                ),
                abilities=abilities,
            )
        )
    names = {u.id: u.faction_unit.name for p in game.players for u in p.army_list.units}
    uses = [
        PsychicUseOut(
            unit_name=names.get(u.unit_id, "?"),
            ability=u.ability,
            roll=u.roll,
            target_name=names.get(u.target_unit_id) if u.target_unit_id else None,
        )
        for u in game.psychic_uses
        if u.battle_round == game.battle_round
    ]
    return PsychicOut(units=units, uses=uses)


@router.get("/{game_id}/psychic", response_model=PsychicOut)
async def get_psychic(game_id: int, session: AsyncSession = Depends(get_session)):
    return _psychic_out(await _load_game(session, game_id))


@router.post("/{game_id}/psychic", response_model=PsychicOut)
async def use_psychic(
    game_id: int, payload: PsychicIn, session: AsyncSession = Depends(get_session)
):
    # A PSYKER unit uses a psychic ability: its psychic roll (a 1
    # Battle-shocks it), and its effect.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    target = (
        deployment_service.find_unit(game, payload.target_unit_id)
        if payload.target_unit_id is not None
        else None
    )
    psychic_service.use(game, unit, payload.ability, target)
    await session.commit()
    return _psychic_out(await _load_game(session, game_id))


# --- Teleport Homers (see app/seeds/factions/space_marines/teleport_homer.py) ---


def _teleport_homers_out(game: Game) -> TeleportHomersOut:
    units = []
    for player in game.players:
        for unit in teleport_homer_service.homer_units(game, player.seat):
            token = teleport_homer_service.token(game, unit)
            units.append(
                TeleportHomerUnitOut(
                    unit_id=unit.id,
                    name=unit.faction_unit.name,
                    seat=player.seat,
                    token={"x": token.x, "y": token.y} if token else None,
                )
            )
    tokens = []
    for homer in game.teleport_homers:
        if homer.status != "placed":
            continue
        unit = deployment_service.find_unit(game, homer.unit_id)
        tokens.append(
            {
                "unit_id": unit.id,
                "name": unit.faction_unit.name,
                "seat": deployment_service.owner(game, unit).seat,
                "x": homer.x,
                "y": homer.y,
            }
        )
    return TeleportHomersOut(
        waiting_seats=teleport_homer_service.waiting_seats(game), units=units, tokens=tokens
    )


@router.get("/{game_id}/teleport-homers", response_model=TeleportHomersOut)
async def get_teleport_homers(game_id: int, session: AsyncSession = Depends(get_session)):
    return _teleport_homers_out(await _load_game(session, game_id))


@router.post("/{game_id}/teleport-homers", response_model=TeleportHomersOut)
async def place_teleport_homer(
    game_id: int, payload: TeleportHomerIn, session: AsyncSession = Depends(get_session)
):
    # Sets up (or moves) a unit's token - or, with no position, takes it back.
    game = await _load_game(session, game_id)
    if payload.unit_id is None:
        raise HTTPException(status_code=400, detail="choose a unit")
    unit = deployment_service.find_unit(game, payload.unit_id)
    if payload.x is None or payload.y is None:
        teleport_homer_service.remove(game, payload.seat, unit)
    else:
        teleport_homer_service.place(game, payload.seat, unit, payload.x, payload.y)
    await session.commit()
    return _teleport_homers_out(await _load_game(session, game_id))


@router.post("/{game_id}/teleport-homers/done", response_model=GameOut)
async def finish_teleport_homers(
    game_id: int, payload: TeleportHomerIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    teleport_homer_service.finish(game, payload.seat)
    return await _commit_and_reload(session, game_id)


# --- the start of the Shooting phase (see app/services/in_game/shooting_start.py) ---


@router.get("/{game_id}/shooting-start", response_model=list[StartOfShootingOut])
async def get_shooting_start(game_id: int, session: AsyncSession = Depends(get_session)):
    # The abilities the player whose turn it is can use now, at the start of
    # their Shooting phase (e.g. Secutor of Olympus).
    game = await _load_game(session, game_id)
    return [
        StartOfShootingOut(
            unit_id=a.unit.id,
            unit_name=a.unit.faction_unit.name,
            ability=a.name,
            description=next(
                (x.description for x in a.model.model.abilities if x.name == a.name), None
            ),
            targets=[UnitIdNameOut(unit_id=t.id, name=t.faction_unit.name) for t in a.targets],
        )
        for a in shooting_start_service.available(game)
    ]


@router.post("/{game_id}/shooting-start", response_model=StartOfShootingResultOut)
async def use_shooting_start(
    game_id: int, payload: StartOfShootingIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    result = shooting_start_service.use(
        game,
        deployment_service.find_unit(game, payload.unit_id),
        payload.ability,
        deployment_service.find_unit(game, payload.target_unit_id),
    )
    await session.commit()
    return StartOfShootingResultOut(
        roll=result.roll, wounds=result.wounds, destroyed_unit_model_ids=result.destroyed
    )


# --- moving after shooting (see app/services/in_game/shoot_scoot.py) ---


@router.post("/{game_id}/shoot-scoot/check", response_model=DeploymentCheckOut)
async def check_shoot_scoot(
    game_id: int, payload: UnitPlacementIn, session: AsyncSession = Depends(get_session)
):
    # Whether the unit could move after shooting as placed, and if not, why.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    return _check_out(shoot_scoot_service.check(game, unit, _placement(payload.positions)))


@router.post("/{game_id}/shoot-scoot", response_model=GameOut)
async def shoot_scoot(
    game_id: int, payload: UnitPlacementIn, session: AsyncSession = Depends(get_session)
):
    # The unit moves after shooting (e.g. Ride the Thermals).
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    shoot_scoot_service.scoot(game, unit, _placement(payload.positions))
    return await _commit_and_reload(session, game_id)


# --- the roll-off for who goes first, and Scouts moves (see
# app/services/in_game/first_turn.py and scouts.py) ---


@router.post("/{game_id}/first-turn/roll", response_model=GameOut)
async def roll_first_turn(game_id: int, session: AsyncSession = Depends(get_session)):
    # The players roll off for who goes first (ties re-rolled).
    game = await _load_game(session, game_id)
    await game_service.roll_first_turn(session, game)
    return await _commit_and_reload(session, game_id)


def _scouts_out(game: Game) -> ScoutsOut:
    seat = scouts_service.scouting_seat(game)
    units = scouts_service.scout_units(game, seat) if seat is not None else []
    return ScoutsOut(
        seat=seat,
        units=[
            ScoutsUnitOut(
                unit_id=u.id,
                name=u.faction_unit.name,
                distance=scouts_service.distance(u),
                moved=scouts_service.scout_move(game, u) is not None,
            )
            for u in units
        ],
    )


@router.get("/{game_id}/scouts", response_model=ScoutsOut)
async def get_scouts(game_id: int, session: AsyncSession = Depends(get_session)):
    return _scouts_out(await _load_game(session, game_id))


@router.post("/{game_id}/scouts/check", response_model=DeploymentCheckOut)
async def check_scout_move(
    game_id: int, payload: UnitPlacementIn, session: AsyncSession = Depends(get_session)
):
    # Whether the unit could make its Scouts move as placed, and if not, why.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    seat = deployment_service.owner(game, unit).seat
    return _check_out(scouts_service.check(game, seat, unit, _placement(payload.positions)))


@router.post("/{game_id}/scouts", response_model=ScoutsOut)
async def scout_move(
    game_id: int, payload: UnitPlacementIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    seat = deployment_service.owner(game, unit).seat
    scouts_service.move(game, seat, unit, _placement(payload.positions))
    await session.commit()
    return _scouts_out(await _load_game(session, game_id))


@router.post("/{game_id}/scouts/done", response_model=GameOut)
async def finish_scouts(
    game_id: int, payload: SeatIn, session: AsyncSession = Depends(get_session)
):
    # The player is done making Scouts moves.
    game = await _load_game(session, game_id)
    await game_service.finish_scouts(session, game, payload.seat)
    return await _commit_and_reload(session, game_id)


# --- emergency disembarking (see app/services/in_game/emergency.py) ---


def _emergency_out(game: Game) -> EmergencyOut:
    names = {
        m.id: (u, m) for p in game.players for u in p.army_list.units for m in u.unit_models
    }
    units = []
    for record in emergency_service.pending(game):
        unit = deployment_service.find_unit(game, record.unit_id)
        transport = deployment_service.find_unit(game, record.transport_unit_id)
        units.append(
            EmergencyUnitOut(
                unit_id=unit.id,
                name=unit.faction_unit.name,
                seat=deployment_service.owner(game, unit).seat,
                transport_unit_id=transport.id,
                transport_name=transport.faction_unit.name,
                suggested=[
                    ModelPositionOut(unit_model_id=i, x=x, y=y, rotation=r)
                    for i, (x, y, r) in emergency_service.suggested(game, unit).items()
                ],
                wreck=[
                    {
                        "x": b.x,
                        "y": b.y,
                        "rotation": b.rotation,
                        "rx": b.semi_axes[0],
                        "ry": b.semi_axes[1],
                    }
                    for b in emergency_service.wreck_bases(game, transport.id)
                ],
                models=[
                    {"unit_model_id": m.id, "name": m.model.name}
                    for m in emergency_service.surviving_models(game, unit)
                ],
            )
        )
    rolls = []
    for r in game.emergency_rolls:
        name = None
        if r.unit_model_id in names:
            unit, model = names[r.unit_model_id]
            name = unit.faction_unit.name if r.kind == "deadly_demise_wounds" else model.model.name
        rolls.append(EmergencyRollOut(kind=r.kind, name=name, roll=r.roll, wounds=r.wounds))
    return EmergencyOut(units=units, rolls=rolls)


@router.get("/{game_id}/emergency", response_model=EmergencyOut)
async def get_emergency(game_id: int, session: AsyncSession = Depends(get_session)):
    # Units that must emergency disembark from destroyed transports, and the
    # rolls after those that have.
    return _emergency_out(await _load_game(session, game_id))


@router.post("/{game_id}/emergency/check", response_model=DeploymentCheckOut)
async def check_emergency(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    return _check_out(emergency_service.check(game, unit, _placement(payload.positions)))


@router.post("/{game_id}/emergency", response_model=GameOut)
async def emergency_disembark(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    # The unit emergency disembarks with the models placed (the rest are
    # destroyed); then its hazard rolls, and the transport's Deadly Demise.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    emergency_service.disembark(game, unit, _placement(payload.positions))
    return await _commit_and_reload(session, game_id)


@router.post("/{game_id}/embarked/embark", response_model=GameOut)
async def embark(game_id: int, payload: EmbarkIn, session: AsyncSession = Depends(get_session)):
    # A unit that's moved embarks in a transport within 3" of it.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    carrier = deployment_service.find_unit(game, payload.transport_unit_id)
    embarked_service.embark(game, unit, carrier)
    return await _commit_and_reload(session, game_id)


@router.post("/{game_id}/embarked", response_model=GameOut)
async def disembark(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    embarked_service.disembark(game, unit, _placement(payload.positions))
    return await _commit_and_reload(session, game_id)
