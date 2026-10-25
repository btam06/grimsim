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
    StratagemOut,
    TerrainPointOut,
    UnitIdIn,
    UnitMoveIn,
)
from app.routers.stratagems import _to_out as stratagem_to_out
from app.services.in_game import auras as auras_service
from app.services.in_game import battle_formations as battle_formations_service
from app.services.in_game import battle_round as battle_round_service
from app.services.in_game import casualties as casualties_service
from app.services.in_game import charging as charging_service
from app.services.in_game import command_phase as command_phase_service
from app.services.in_game import deployment as deployment_service
from app.services.in_game import fighting as fighting_service
from app.services.in_game import game as game_service
from app.services.in_game import movement as movement_service
from app.services.in_game import overwatch as overwatch_service
from app.services.in_game import pathing as pathing_service
from app.services.in_game import reanimation as reanimation_service
from app.services.in_game import reinforcements as reinforcements_service
from app.services.in_game import shooting as shooting_service
from app.routers import combat as combat_router
from app.routers.combat import calculate as calculate_combat
from app.services.in_game.terrain import MM_PER_INCH

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
        terrain_layout_id=game.layout.id if game.layout else None,
        terrain_layout_name=game.layout.name if game.layout else None,
        deployment_step=deployment_service.deployment_step(game),
        deploying_seat=deployment_service.deploying_seat(game),
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
    )
    return await _commit_and_reload(session, game_id)


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
                wounds = unit_model.model.wounds
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
    return DeploymentOut(deploying_seat=deployment_service.deploying_seat(game), units=units)


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


def _rule_options(game: Game, unit: Unit) -> list[str]:
    # The rule options active for the unit in combat: its owner's army rule
    # options this round (e.g. Doctrina Imperatives), those of abilities
    # selected in their Command phase that can apply to it (see
    # app/services/in_game/command_phase.py), and the auras it's within range
    # of (see app/services/in_game/auras.py).
    seat = deployment_service.owner(game, unit).seat
    return (
        battle_round_service.active_options(game, seat)
        + command_phase_service.options_for(game, seat, unit)
        + auras_service.aura_options(game, unit)
    )


# --- shooting (see app/services/in_game/shooting.py) ---


async def _assault_weapons(session: AsyncSession, unit: Unit, game: Game | None = None) -> set:
    # The unit's Assault weapons, as the calculator sees them (so loaded as it
    # loads units, with its detachment rules) - every ranged weapon, in a game
    # where an active option lets it shoot after Advancing (e.g. Fanatical
    # Devotion).
    if game is not None and command_phase_service.eligible_after(game, unit, "advanced"):
        return {w.id for m in unit.unit_models for w in shooting_service.ranged_weapons(m)}
    loaded = await combat_router._load_unit(session, unit.id)
    rules = await combat_router._detachment_rules(session, loaded)
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
    enhancement = isinstance(weapon.id, tuple)
    return ShootingWeaponOut(
        id=weapon.id[1] if enhancement else weapon.id,
        enhancement=enhancement,
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
    weapon_ids = set(payload.weapon_ids) | {
        ("enhancement", i) for i in payload.enhancement_weapon_ids
    }
    reach = shooting_service.check_shot(
        game, unit, target, weapon_ids, await _assault_weapons(session, unit, game)
    )
    status = shooting_service.move_status(game, unit)
    out = await _fire(session, game, unit, target, payload, reach, status)
    await session.commit()
    return out


async def _fire(
    session: AsyncSession,
    game: Game,
    unit: Unit,
    target: Unit,
    payload: ShootIn,
    reach: shooting_service.TargetReach,
    status: shooting_service.MoveStatus,
    snap_shots: bool = False,
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
            attacker_positions=["remained_stationary"] if status.remained_stationary else [],
            in_cover=reach.in_cover,
            moved_less_than_3=status.moved_less_than_3,
            advanced=status.advanced,
            # The options each side chose for its army rules this round (e.g.
            # its Doctrina Imperative) and its abilities in its Command phase.
            attacker_rule_options=_rule_options(game, unit),
            defender_rule_options=_rule_options(game, target),
            defender_visible=True,
            defender_in_range=True,
            snap_shots=snap_shots,
        ),
        firing=reach.firing,
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
                roll=charge.roll if charge else None,
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
                and charging_service.in_reach(game, unit, target, charge.roll),
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
            # The options each side chose for its army rules this round (e.g.
            # its Doctrina Imperative) and its abilities in its Command phase.
            attacker_rule_options=_rule_options(game, unit),
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
        if not reinforcements_service.arrival_round(game):
            seat = None
    units = reinforcements_service.reserve_units(game, seat) if seat is not None else []
    return ReservesOut(
        step=step,
        seat=seat,
        battle_round=game.battle_round,
        units=[
            ReserveUnitOut(
                unit_id=u.id,
                name=u.faction_unit.name,
                deep_strike=reinforcements_service.has_deep_strike(u),
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
        reinforcements_service.check_arrival(game, unit, _placement(payload.positions))
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
    result = reinforcements_service.check_arrival(game, unit, placement)
    if not result.valid:
        raise HTTPException(
            status_code=400, detail="can't bring it in there: " + "; ".join(result.problems)
        )
    if rapid:
        stratagem = await game_service.rapid_ingress_stratagem(session)
        if stratagem is None:
            raise HTTPException(status_code=400, detail="there's no Rapid Ingress stratagem")
        player = deployment_service.owner(game, unit)
        await game_service.use_stratagem(session, game, player, stratagem)
    reinforcements_service.bring_in(game, unit, placement, rapid)
    return await _commit_and_reload(session, game_id)


# --- Reanimation Protocols (see app/services/in_game/reanimation.py) ---


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
            reanimation_service.suggested(game, unit)
            if reanimation_service.to_place(game, unit)
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
        placing=reanimation_service.placing(game), seat=game.turn_seat, units=units
    )


@router.post("/{game_id}/reanimation/check", response_model=DeploymentCheckOut)
async def check_reanimation(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    # Whether a unit's reanimated models could be set up as placed, and if
    # not, why.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    reanimation_service.check_turn(game, unit)
    return _check_out(
        reanimation_service.check_return(game, unit, _placement(payload.positions))
    )


@router.post("/{game_id}/reanimation", response_model=GameOut)
async def place_reanimated(
    game_id: int, payload: DeployUnitIn, session: AsyncSession = Depends(get_session)
):
    # Sets up a unit's reanimated models.
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, payload.unit_id)
    reanimation_service.place(game, unit, _placement(payload.positions))
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
    command_phase_service.choose(
        game, payload.seat, payload.unit_id, payload.ability, payload.option,
        payload.target_unit_id,
    )
    await session.commit()
    return _command_out(await _load_game(session, game_id))
