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
    GameStratagemTarget,
    GameStratagemUse,
    GameTerrainLayout,
    PrimaryMission,
    SecondaryMission,
    Stratagem,
    Unit,
    User,
)
from app.models.game import BATTLE_ROUNDS, PHASES
from app.models.stratagem import CHOICE_TARGET_ACTIONS, UNIT_TARGET_ACTIONS
from app.schemas import GameIn
from app.services.in_game import actions as actions_service
from app.services.in_game import battle_formations as battle_formations_service
from app.services.in_game import battle_shock as battle_shock_service
from app.services.in_game import battle_round as battle_round_service
from app.services.in_game import coherency as coherency_service
from app.services.in_game import command_phase as command_phase_service
from app.services.in_game import deployment as deployment_service
from app.services.in_game import duty_in_death as duty_in_death_service
from app.services.in_game import overwatch as overwatch_service
from app.seeds.factions.necrons import reanimation as reanimation_service
from app.services.in_game import heal as heal_service
from app.services.in_game import mission_state as mission_state_service
from app.services.in_game import reinforcements as reinforcements_service
from app.services.in_game import scoring as scoring_service
from app.services.in_game import terrain as terrain_service
from app.services.in_game import emergency as emergency_service
from app.services.in_game import first_turn as first_turn_service
from app.services.in_game import scouts as scouts_service
from app.services.in_game import selected_objectives as selected_objectives_service
from app.services.in_game import objectives as objectives_service
from app.seeds.factions.space_marines import teleport_homer as teleport_homer_service
from app.services.in_game import turn_record as turn_record_service
from app.services.list_building import enhancements as enhancement_rules
from app.services.list_building import warlord as warlord_rules

# How many new tactical secondary cards a player draws in each of their
# command phases (11th edition: on top of any still held - no hand limit).
TACTICAL_DRAW = 2
FIXED_SECONDARY_COUNT = 2
# CP for discarding a tactical secondary (at the end of your turn).
DISCARD_CP = 1


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
        reason = await warlord_rules.warlord_reason(
            session, army_list.id, army_list.warlord_unit_id
        )
        if reason:
            raise _bad_request(f"player {seat}: {reason}")

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
) -> list[GameSecondary]:
    # A tactical player draws `count` new cards (TACTICAL_DRAW in their command
    # phase), keeping any they still hold - from the tactical secondaries
    # still in their deck: not drawn yet this game, or shuffled back into it.
    # The cards drawn. A card that must be replaced when drawn (Defend
    # Stronghold in the first battle round) is: a new card is drawn and it's
    # shuffled back.
    if player.secondary_mode != "tactical":
        return []
    seen = {c.secondary_mission_id for c in player.secondaries if c.status != SHUFFLED}
    deck = [
        m
        for m in (
            await session.execute(
                select(SecondaryMission).where(SecondaryMission.tactical_points.is_not(None))
            )
        ).scalars()
        if m.id not in seen
    ]
    drawn = []
    replacing = 0
    while len(drawn) < count + replacing and deck:
        mission = deck.pop(random.randrange(len(deck)))
        card = GameSecondary(
            secondary_mission_id=mission.id,
            mission=mission,
            fixed=False,
            status="active",
            drawn_round=game.battle_round,
        )
        player.secondaries.append(card)
        drawn.append(card)
        if mission.name in MUST_REPLACE_IN_FIRST_ROUND and game.battle_round == 1:
            # Shuffled back after its replacement is drawn (it's out of this
            # draw's deck already).
            card.status = SHUFFLED
            replacing += 1
    # Saved now, so the new cards have ids for the choices made about them
    # (e.g. whether to redraw one - see mission_state.cards_drawn).
    await session.flush()
    return [c for c in drawn if c.status == "active"]


# Shuffled back into its holder's deck: it can be drawn again.
SHUFFLED = "shuffled"
# Cards that must be replaced when drawn in the first battle round.
MUST_REPLACE_IN_FIRST_ROUND = {"Defend Stronghold"}


async def redraw(session: AsyncSession, game: Game, prompt, card_ids: list[int]) -> None:
    # The player redraws those cards they've just drawn that they picked
    # (their WHEN DRAWN options - see app/services/in_game/mission_state.py):
    # each is discarded or shuffled back, and a new card drawn in its place
    # (which may be redrawable in turn).
    seat = prompt.seat
    player = player_at(game, seat)
    offered = mission_state_service.redraw_offers(game, seat)
    cards = [c for c in player.secondaries if c.id in set(card_ids)]
    if len(cards) != len(set(card_ids)) or any(c.id not in offered for c in cards):
        raise _bad_request("those cards can't be redrawn")
    mission_state_service.close_redraw(game, prompt)
    for card in cards:
        how = offered[card.id]
        if how == "discard":
            card.status = "discarded"
        drawn = await _draw_tactical(session, game, player, count=1)
        if how == "shuffle":
            card.status = SHUFFLED
        mission_state_service.cards_drawn(game, seat, drawn)
    mission_state_service.lapse_stale_prompts(game)


async def _begin_command_phase(session: AsyncSession, game: Game) -> None:
    # The start of a turn (how things stand recorded - see
    # app/services/in_game/turn_record.py), then its Command phase: both
    # players gain 1 CP; the player whose turn it is draws secondaries,
    # and their models that heal at its start do (e.g. Self-repair
    # Mechanisms); then its Battle-shock step: their units that must take a
    # Battle-shock test.
    turn_record_service.snapshot_turn_start(game)
    mission_state_service.start_of_turn(game)
    game.phase = "command"
    # Its start: the objectives the player selected for their rules last
    # turn (e.g. their Acquisition objective marker) are theirs no longer -
    # they select them again in this phase.
    selected_objectives_service.clear(game, game.turn_seat)
    for player in game.players:
        player.cp += 1
    drawn = await _draw_tactical(session, game, player_at(game, game.turn_seat))
    mission_state_service.cards_drawn(game, game.turn_seat, drawn)
    command_phase_service.heal(game)
    battle_shock_service.battle_shock_step(game)


def enter_deployment(game: Game) -> None:
    # A new game goes straight to deployment, if its battlefield has
    # deployment zones and there's anything to set up in them.
    if game.status == "setup" and deployment_service.can_deploy(game):
        game.status = "deployment"


# Before a battle round's first turn, if a rule at its start needs a decision
# (see app/services/in_game/battle_round.py) - not one of a turn's PHASES.
START_OF_ROUND = battle_round_service.START_OF_ROUND


async def _begin_battle_round(session: AsyncSession, game: Game) -> None:
    # The round's first turn: after the start of the round (when Warlords'
    # abilities gain CP - e.g. Transhuman Strategist), if a rule then needs a
    # decision; otherwise straight to its command phase.
    game.turn_seat = game.first_seat
    for seat, cp in battle_round_service.warlord_cp(game).items():
        player_at(game, seat).cp += cp
    if battle_round_service.needs_decisions(game, game.battle_round):
        game.phase = START_OF_ROUND
    else:
        await _begin_command_phase(session, game)


async def _begin_battle(session: AsyncSession, game: Game) -> None:
    # The start of the battle: missions that set up then prompt for it (e.g.
    # Locate and Deny's operation markers); then the first battle round. (A
    # game with nothing to deploy rolls off for who goes first now.)
    if game.first_seat is None:
        first_turn_service.roll(game)
    game.status = "in_progress"
    game.battle_round = 1
    mission_state_service.start_of_battle(game)
    await _begin_battle_round(session, game)


async def start_game(session: AsyncSession, game: Game) -> None:
    # Deployment first, if there's any (see enter_deployment); otherwise the
    # first battle round.
    if game.status != "setup":
        raise _bad_request("the game has already started")
    enter_deployment(game)
    if game.status == "setup":
        await _begin_battle(session, game)


async def declare_formations(session: AsyncSession, game: Game, seat: int) -> None:
    # The player has declared their battle formations; once both have, the
    # units go on the battlefield - or, if there are none to, the first battle
    # round begins.
    battle_formations_service.declare(game, seat)
    if deployment_service.formations_declared(game) and (
        deployment_service.deploying_seat(game) is None
    ):
        await _after_deploying(session, game)


async def deploy_unit(
    session: AsyncSession, game: Game, unit, placement: dict[int, tuple[float, float, float]]
) -> None:
    # Sets a unit up; once every unit is, on to the roll-off for who goes
    # first.
    deployment_service.deploy(game, unit, placement)
    if deployment_service.deploying_seat(game) is None:
        await _after_deploying(session, game)


async def _after_deploying(session: AsyncSession, game: Game) -> None:
    # Everything's set up: the roll-off for who goes first (unless it's been
    # decided) - it waits for the players - then (redeploys, when a rule asks
    # for one, and) pre-battle abilities (Scouts - it waits for those too),
    # and the first battle round.
    if first_turn_service.waiting(game) or scouts_service.waiting(game):
        return
    await _begin_battle(session, game)


async def roll_first_turn(session: AsyncSession, game: Game) -> None:
    # The players roll off for who goes first.
    if not first_turn_service.waiting(game):
        raise _bad_request("it isn't time to roll off for who goes first")
    first_turn_service.roll(game)
    await _after_deploying(session, game)


async def finish_scouts(session: AsyncSession, game: Game, seat: int) -> None:
    # The player is done making Scouts moves - once both are, the battle
    # begins.
    scouts_service.finish(game, seat)
    await _after_deploying(session, game)


async def advance(session: AsyncSession, game: Game) -> None:
    # On to the next phase; after the fight phase, the next turn - the second
    # player's, or the next battle round's first (after the start of that
    # round, if any rules happen then). The game ends after the last battle
    # round's second turn.
    _require_in_progress(game)
    if battle_shock_service.pending(game):
        raise _bad_request("take the Battle-shock tests first")
    if scoring_service.pending_offers(game):
        raise _bad_request("claim or hold the completed secondaries first")
    if mission_state_service.pending(game):
        raise _bad_request("make the missions' choices first")
    if teleport_homer_service.waiting(game):
        raise _bad_request("set up the Teleport Homer tokens first")
    if scouts_service.waiting(game):
        raise _bad_request("make the Scouts moves first")
    if emergency_service.waiting(game):
        raise _bad_request(
            "set up the units emergency disembarking from a destroyed transport first"
        )
    if game.phase == START_OF_ROUND:
        if missing := battle_round_service.missing_choices(game):
            raise _bad_request("choose an option first for " + ", ".join(missing))
        await _begin_command_phase(session, game)
        return
    if game.phase == "command":
        # Abilities that must have an option selected in it first (e.g.
        # Canticles of the Omnissiah).
        if missing := command_phase_service.missing_choices(game):
            raise _bad_request("select an option first for " + ", ".join(missing))
        # Objectives their rules have them select (e.g. Acquisition At Any Cost).
        if missing := selected_objectives_service.missing(game):
            raise _bad_request("select " + ", ".join(missing) + " first")
        # Its scoring moment (and a pause for any tactical secondary to claim)
        # - objective control determined first, as at the end of every phase.
        objectives_service.determine(game)
        scoring_service.score(game, scoring_service.COMMAND_END)
        if scoring_service.pending_offers(game):
            return
        # The end of the command phase: Reanimation Protocols activate - and
        # if that returns destroyed models, it waits for them to be set up.
        if heal_service.placing(game):
            raise _bad_request("set up the returned models first")
        if not reanimation_service.reanimations(game):
            reanimation_service.reanimate(game)
            if heal_service.placing(game):
                return
        # Enhancements that gain CP then (e.g. Magos).
        selected_objectives_service.end_of_command(game)
    if game.phase == "charge" and await heroic_intervention_open(session, game):
        # The end of the charge phase: the opponent can use Heroic
        # Intervention - it pauses here for them to.
        return
    if game.phase == "movement" and not reinforcements_service.movement_ended(game):
        # The end of the movement phase: if the opponent could use Rapid
        # Ingress or Fire Overwatch, it pauses here for them to.
        if await rapid_ingress_open(session, game) or await overwatch_open(session, game):
            reinforcements_service.end_movement(game)
            return
    # The end of the phase: destroyed models left on the battlefield till then
    # (Duty in Death) go; secured objectives lost since, then rules that
    # secure objectives then (e.g. Raise the Banner).
    duty_in_death_service.remove(game)
    objectives_service.refresh_secured(game)
    objectives_service.secure_at_end_of(game, game.phase)
    objectives_service.determine(game)
    index = PHASES.index(game.phase)
    if index + 1 < len(PHASES):
        game.phase = PHASES[index + 1]
        if game.phase == "fight":
            # Its start: rules that make units take Battle-shock tests then
            # (e.g. Voices in the Code).
            battle_shock_service.start_of_fight(game)
            # If nobody can pile in, the Fight step starts straight away.
            from app.services.in_game import fighting

            fighting.start_fight_step(game)
        return
    # The end of the turn: actions that complete then do (or fail), then its
    # scoring moment - and after the last turn, the battle's - with a pause
    # for any tactical secondary to claim.
    if not scoring_service.evaluated(game, scoring_service.TURN_END):
        # Units out of coherency regain it (03.03).
        coherency_service.regain(game)
        # The opponent's AIRCRAFT go back into Strategic Reserves (23.02).
        reinforcements_service.aircraft_to_reserves(game)
        # Objective control, determined at the end of the turn too.
        objectives_service.determine(game)
        actions_service.end_of_turn(game)
        mission_state_service.end_of_turn(game)
        if mission_state_service.pending(game):
            return
    scoring_service.score(game, scoring_service.TURN_END)
    if game.battle_round >= BATTLE_ROUNDS and game.turn_seat != game.first_seat:
        scoring_service.score(game, scoring_service.BATTLE_END)
    if scoring_service.pending_offers(game):
        return
    if game.turn_seat == game.first_seat:
        game.turn_seat = other_seat(game.first_seat)
    elif game.battle_round >= BATTLE_ROUNDS:
        game.status = "finished"
        game.phase = None
        game.turn_seat = None
        return
    else:
        if game.battle_round == reinforcements_service.LAST_ROUND:
            # Strategic Reserves that haven't arrived are destroyed.
            reinforcements_service.destroy_unarrived(game)
        game.battle_round += 1
        await _begin_battle_round(session, game)
        return
    await _begin_command_phase(session, game)


async def core_stratagem(session: AsyncSession, name: str) -> Stratagem | None:
    return (
        await session.execute(
            select(Stratagem)
            .options(
                selectinload(Stratagem.detachments),
                selectinload(Stratagem.timings),
                selectinload(Stratagem.game_action_link),
            )
            .where(Stratagem.name == name, Stratagem.is_core)
        )
    ).scalar_one_or_none()


async def rapid_ingress_stratagem(session: AsyncSession) -> Stratagem | None:
    return await core_stratagem(session, reinforcements_service.RAPID_INGRESS)


async def overwatch_stratagem(session: AsyncSession) -> Stratagem | None:
    return await core_stratagem(session, overwatch_service.OVERWATCH)


async def heroic_intervention_open(session: AsyncSession, game: Game) -> bool:
    # Whether to pause at the end of this charge phase for the opponent of
    # the player whose turn it is to use Heroic Intervention: once (the
    # first time it's advanced), if they could on one of their units.
    from app.services.in_game import core_stratagems

    if core_stratagems.charge_ended(game):
        return False
    stratagem = next(
        (
            s
            for s in (
                await session.execute(
                    select(Stratagem)
                    .options(
                        selectinload(Stratagem.detachments),
                        selectinload(Stratagem.timings),
                        selectinload(Stratagem.game_action_link),
                        selectinload(Stratagem.keywords),
                        selectinload(Stratagem.excluded_keywords),
                        selectinload(Stratagem.keyword_option_links),
                    )
                    .where(Stratagem.is_core)
                )
            ).scalars()
            if s.game_action == core_stratagems.HEROIC_INTERVENTION
        ),
        None,
    )
    if stratagem is None:
        return False
    core_stratagems.end_charges(game)
    opponent = player_at(game, other_seat(game.turn_seat))
    if stratagem_unavailable_reason(game, opponent, stratagem) is None:
        return True
    # Nothing to intervene with: the phase just ends.
    game.charges_ended.pop()
    return False


async def rapid_ingress_open(session: AsyncSession, game: Game) -> bool:
    # Whether, at the end of this movement phase, the opponent of the player
    # whose turn it is could use Rapid Ingress: units can arrive this round,
    # they have a unit in Strategic Reserves, and they can use the stratagem
    # (CP, and not already this phase).
    if not reinforcements_service.arrival_round(game):
        return False
    opponent = player_at(game, other_seat(game.turn_seat))
    units = reinforcements_service.reserve_units(game, opponent.seat)
    if not units:
        return False
    stratagem = await rapid_ingress_stratagem(session)
    # The cheapest it could be for one of those units (e.g. with a Teleport
    # Homer token, or Beacon Angelis).
    discount = max(
        reinforcements_service.rapid_ingress_discount(u)
        + (
            teleport_homer_service.CP_DISCOUNT
            if teleport_homer_service.token(game, u) is not None
            else 0
        )
        for u in units
    )
    return (
        stratagem is not None
        and stratagem_unavailable_reason(game, opponent, stratagem, discount) is None
    )


async def overwatch_open(session: AsyncSession, game: Game) -> bool:
    # Whether, at the end of this movement phase, the opponent of the player
    # whose turn it is could Fire Overwatch: they can use the stratagem (CP,
    # and not already this phase), and one of their units has an enemy unit
    # visible within 24" to shoot at.
    opponent = player_at(game, other_seat(game.turn_seat))
    stratagem = await overwatch_stratagem(session)
    if stratagem is None or stratagem_unavailable_reason(game, opponent, stratagem) is not None:
        return False
    return overwatch_service.can_overwatch(game, opponent.seat)


def _ability_names(unit: Unit) -> set[str]:
    # Its models' abilities, and their wargear's.
    return {a.name for m in unit.unit_models for a in m.model.abilities} | {
        a.name for m in unit.unit_models for g in m.wargear for a in g.abilities
    }


def stratagem_cost(stratagem: Stratagem, unit: Unit | None) -> tuple[int, bool]:
    # What the stratagem costs used on the unit, and whether it can be even
    # if it's already been used this phase - an ability can change that for
    # its unit (datasheet_abilities STRATAGEM_COSTS - e.g. Shock Charge:
    # Crushing Impact for 0CP).
    from app.seeds import datasheet_abilities

    if unit is not None:
        config = datasheet_abilities.STRATAGEM_COSTS
        for name in sorted(_ability_names(unit) & set(config)):
            if stratagem.name in config[name]:
                return config[name][stratagem.name]
    return stratagem.cp, False


def stratagem_unavailable_reason(
    game: Game,
    player: GamePlayer,
    stratagem: Stratagem,
    cp_discount: int = 0,
    target: Unit | None = None,
) -> str | None:
    # Why a player can't use a stratagem right now (on `target`, if given),
    # or None if they can. Without a target, it's available if it is on
    # one of their units an ability makes it cheaper for (see stratagem_cost).
    if target is None and stratagem.game_action not in UNIT_TARGET_ACTIONS:
        reason = _unavailable(game, player, stratagem, cp_discount, None)
        if reason is not None and any(
            stratagem_cost(stratagem, u) != (stratagem.cp, False)
            and _unavailable(game, player, stratagem, cp_discount, u) is None
            for u in deployment_service.deployable_units(player)
        ):
            return None
        return reason
    return _unavailable(game, player, stratagem, cp_discount, target)


def _unavailable(
    game: Game,
    player: GamePlayer,
    stratagem: Stratagem,
    cp_discount: int,
    target: Unit | None,
) -> str | None:
    cp, repeatable = stratagem_cost(stratagem, target)
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
    if not repeatable and any(
        use.stratagem_id == stratagem.id
        and use.battle_round == game.battle_round
        and use.turn_seat == game.turn_seat
        and use.phase == game.phase
        for use in player.stratagem_uses
    ):
        # Each stratagem can be used once per phase (by each player).
        return "it has already been used this phase"
    if player.cp < max(0, cp - cp_discount):
        return "not enough CP"
    if stratagem.game_action == "replace_secondary" and not replaceable_secondaries(player):
        return "they have no active tactical Secondary Mission to replace"
    if stratagem.game_action == "strategic_reserves" and not stratagem_targets(
        game, player, stratagem
    ):
        return "they have no unit it can place in Strategic Reserves now"
    if stratagem.game_action in _stratagem_actions().ACTIONS and not stratagem_targets(
        game, player, stratagem
    ):
        return "they have no unit it can be used on now"
    return None


def _stratagem_actions():
    # (Imported here: it imports fighting, which imports this module.)
    from app.services.in_game import stratagem_actions

    return stratagem_actions


def stratagem_target_reason(
    game: Game, player: GamePlayer, stratagem: Stratagem, unit: Unit
) -> str | None:
    # Why the player can't use a stratagem whose game action targets one of
    # their units (UNIT_TARGET_ACTIONS) on that unit, or None if they can: it's
    # theirs, on the battlefield, has a model with the stratagem's keywords,
    # and its action can be carried out on it.
    if deployment_service.owner(game, unit).seat != player.seat:
        return "it isn't one of their units"
    if (reason := unit_target_reason(game, player, unit)) is not None:
        return reason
    if not stratagem.is_unrestricted and not any(
        stratagem.applies_to(enhancement_rules.model_keywords(unit, unit_model))
        for unit_model in unit.unit_models
    ):
        return "it doesn't have the keywords the stratagem needs"
    if stratagem.game_action == "strategic_reserves":
        return reinforcements_service.extraction_reason(game, player.seat, unit)
    if stratagem.game_action in _stratagem_actions().ACTIONS:
        return _stratagem_actions().target_reason(game, player, stratagem, unit)
    if not deployment_service.models_on_battlefield(game, unit):
        return "it isn't on the battlefield"
    return None


def unit_target_reason(game: Game, player: GamePlayer, unit: Unit) -> str | None:
    # Why none of the player's stratagems can target their unit now (15.01,
    # 01.07), or None: it's Battle-shocked, or one already has this phase.
    if battle_shock_service.is_battle_shocked(game, unit):
        return "it's Battle-shocked"
    if any(
        use.target_unit_id == unit.id
        and use.battle_round == game.battle_round
        and use.turn_seat == game.turn_seat
        and use.phase == game.phase
        for use in player.stratagem_uses
    ):
        return "one of their stratagems has already targeted it this phase"
    return None


def stratagem_choices(game: Game, player: GamePlayer, stratagem: Stratagem, unit: Unit) -> list:
    # What else its use on the unit could target (an objective, or a
    # transport - e.g. Cached Acquisition's objective), for those that do.
    if stratagem.game_action not in CHOICE_TARGET_ACTIONS:
        return []
    return _stratagem_actions().choices(game, player, stratagem, unit)


def stratagem_targets(game: Game, player: GamePlayer, stratagem: Stratagem) -> list[Unit]:
    # The player's units the stratagem could be used on now.
    return [
        unit
        for unit in deployment_service.deployable_units(player)
        if stratagem_target_reason(game, player, stratagem, unit) is None
    ]


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
    cp_discount: int = 0,
    target_unit_id: int | None = None,
    targeted_unit: Unit | None = None,
    target_choice_id: int | None = None,
) -> None:
    # `cp_discount`: what a rule takes off its cost (e.g. Rapid Ingress using
    # a Teleport Homer token: 1CP). `target_unit_id`: the unit a stratagem
    # whose game action targets one is used on (e.g. Gunship Extraction) -
    # and `target_choice_id`, for one that also targets an objective or a
    # transport, which (e.g. Cached Acquisition's objective). Any other
    # stratagem can be given the unit it targets (`target_unit_id`): then
    # it's checked it can be (15.01), and costs what it does for that unit.
    target_unit = None
    if stratagem.game_action in UNIT_TARGET_ACTIONS:
        if target_unit_id is None:
            raise _bad_request(f"{stratagem.name} needs one of their units as its target")
        target_unit = deployment_service.find_unit(game, target_unit_id)
    elif target_unit_id is not None:
        targeted_unit = deployment_service.find_unit(game, target_unit_id)
    reason = stratagem_unavailable_reason(
        game, player, stratagem, cp_discount, target_unit or targeted_unit
    )
    if reason is not None:
        raise _bad_request(f"can't use {stratagem.name}: {reason}")
    if target_unit is not None or target_unit_id is not None:
        reason = stratagem_target_reason(
            game, player, stratagem, target_unit or targeted_unit
        )
        if reason is not None:
            raise _bad_request(f"can't use {stratagem.name} on that unit: {reason}")
    if targeted_unit is not None and target_unit_id is None:
        reason = unit_target_reason(game, player, targeted_unit)
        if reason is not None:
            raise _bad_request(f"can't use {stratagem.name} on that unit: {reason}")
    if stratagem.game_action in CHOICE_TARGET_ACTIONS:
        choices = stratagem_choices(game, player, stratagem, target_unit)
        if target_choice_id is None and len(choices) == 1:
            target_choice_id = choices[0].id
        if target_choice_id not in {c.id for c in choices}:
            raise _bad_request(
                f"{stratagem.name} needs one of "
                + ", ".join(c.name for c in choices)
                + " as its target too"
            )
    elif target_choice_id is not None:
        raise _bad_request(f"{stratagem.name} doesn't take a second target")

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

    cost = max(0, stratagem_cost(stratagem, target_unit or targeted_unit)[0] - cp_discount)
    player.cp -= cost
    use = GameStratagemUse(
        stratagem_id=stratagem.id,
        stratagem=stratagem,
        battle_round=game.battle_round,
        turn_seat=game.turn_seat,
        phase=game.phase,
        cp=cost,
    )
    if (target_unit or targeted_unit) is not None:
        use.target_link = GameStratagemTarget(unit_id=(target_unit or targeted_unit).id)
    player.stratagem_uses.append(use)
    if stratagem.game_action == "strategic_reserves":
        reinforcements_service.place_in_reserves(game, player.seat, target_unit)
    if stratagem.game_action in _stratagem_actions().ACTIONS:
        _stratagem_actions().carry_out(
            game, player, stratagem, target_unit, target_choice_id, use
        )
    # The unit it targeted (its target, or one it's used on - e.g. Rapid
    # Ingress): abilities that gain CP then (e.g. Broad Spectrum Data-tether).
    _stratagem_targeted(player, target_unit or targeted_unit)
    if target is not None:
        # Discard the target and draw one new card in its place.
        target.status = "discarded"
        drawn = await _draw_tactical(session, game, player, count=1)
        mission_state_service.cards_drawn(game, player.seat, drawn)


def _stratagem_targeted(player: GamePlayer, unit: Unit | None) -> None:
    # A Stratagem targeted the player's unit: its abilities that gain CP on a
    # roll then roll (datasheet_abilities STRATAGEM_TARGET_CP).
    from app.seeds import datasheet_abilities

    if unit is None:
        return
    config = datasheet_abilities.STRATAGEM_TARGET_CP
    # (Its models' abilities, and their wargear's - e.g. an enhanced
    # data-tether.)
    for name in sorted(_ability_names(unit) & set(config)):
        if random.randint(1, 6) >= config[name]:
            player.cp += 1


def achieve_secondary(game: Game, card: GameSecondary, points: int | None = None) -> None:
    # Scores the card's VP for the player's mode, or `points` if given (many
    # cards score more or less depending on the outcome).
    _require_in_progress(game)
    player = card.player
    if card.status != "active":
        raise _bad_request("that secondary isn't active")
    if scoring_service.automatic(card.mission.name):
        how = "it's scored automatically" if card.fixed else "claim it when it's completed"
        raise _bad_request(f"{card.mission.name} isn't scored by hand: {how}")
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

    wanted = mission_points(card) if points is None else points
    allowed = min(wanted, scoring_service.room(player, game.battle_round, "secondary"))
    if allowed < wanted and allowed == 0:
        raise _bad_request("they've already scored 15VP from secondaries this battle round")
    player.scores.append(
        GameScore(
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            kind="secondary",
            points=allowed,
            game_secondary_id=card.id,
        )
    )
    # A tactical card is done once achieved; a fixed one stays for later turns.
    if not card.fixed:
        card.status = "achieved"


def discard_secondary(game: Game, card: GameSecondary) -> None:
    # A tactical secondary is discarded at the end of its holder's turn (in
    # its last phase, the fight phase), for 1 CP.
    _require_in_progress(game)
    if card.fixed:
        raise _bad_request("fixed secondaries can't be discarded")
    if card.status != "active":
        raise _bad_request("that secondary isn't active")
    if game.turn_seat != card.player.seat or game.phase != PHASES[-1]:
        raise _bad_request("secondaries are discarded at the end of their holder's turn")
    card.status = "discarded"
    card.player.cp += DISCARD_CP


def score_primary(game: Game, player: GamePlayer, points: int) -> None:
    # VP from primary missions scored by hand - within the 15VP a battle
    # round.
    _require_in_progress(game)
    allowed = min(points, scoring_service.room(player, game.battle_round, "primary"))
    if allowed < points and allowed == 0:
        raise _bad_request("they've already scored 15VP from primary missions this battle round")
    player.scores.append(
        GameScore(
            battle_round=game.battle_round,
            turn_seat=game.turn_seat,
            kind="primary",
            points=allowed,
        )
    )
