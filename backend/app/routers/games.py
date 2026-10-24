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
    ReachIn,
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
from app.services.in_game import battle_round as battle_round_service
from app.services.in_game import casualties as casualties_service
from app.services.in_game import charging as charging_service
from app.services.in_game import deployment as deployment_service
from app.services.in_game import fighting as fighting_service
from app.services.in_game import game as game_service
from app.services.in_game import movement as movement_service
from app.services.in_game import pathing as pathing_service
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
                    destroyed=all(m.destroyed for m in models),
                    models=models,
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


# --- shooting (see app/services/in_game/shooting.py) ---


async def _assault_weapons(session: AsyncSession, unit: Unit) -> set:
    # The unit's Assault weapons, as the calculator sees them (so loaded as it
    # loads units, with its detachment rules).
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
        assault = await _assault_weapons(session, unit) if status.advanced else None
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
    assault = await _assault_weapons(session, unit)
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
        game, unit, target, weapon_ids, await _assault_weapons(session, unit)
    )
    status = shooting_service.move_status(game, unit)
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
            # its Doctrina Imperative).
            attacker_rule_options=battle_round_service.active_options(
                game, deployment_service.owner(game, unit).seat
            ),
            defender_rule_options=battle_round_service.active_options(
                game, deployment_service.owner(game, target).seat
            ),
            defender_visible=True,
            defender_in_range=True,
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
    await session.commit()
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
    game = await _load_game(session, game_id)
    unit = deployment_service.find_unit(game, unit_id)
    if not shooting_service.is_shooting_phase(game):
        raise HTTPException(status_code=400, detail="units can only shoot in the shooting phase")
    bubble = shooting_service.sight_bubble(game, unit, await _assault_weapons(session, unit))
    return SightBubbleOut(
        range=bubble.range,
        regions=[
            [TerrainPointOut(x=round(x, 2), y=round(y, 2)) for x, y in region]
            for region in bubble.regions
        ],
    )


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
            # its Doctrina Imperative).
            attacker_rule_options=battle_round_service.active_options(
                game, deployment_service.owner(game, unit).seat
            ),
            defender_rule_options=battle_round_service.active_options(
                game, deployment_service.owner(game, target).seat
            ),
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
