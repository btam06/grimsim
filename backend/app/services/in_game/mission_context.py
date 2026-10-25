from __future__ import annotations

from functools import cached_property

from app.models import Game, Unit
from app.models.terrain import TerrainObjective
from app.services.in_game import battle_shock, deployment, objectives, regions, turn_record

# What a mission card's scoring lines look at, at one scoring moment (see
# app/services/in_game/scoring.py) for the player who holds it: when it is,
# who controls what, what's been destroyed this turn, and where units are.

AIRCRAFT = "AIRCRAFT"


class Context:
    def __init__(
        self,
        game: Game,
        seat: int,
        timing: str,
        battle_round: int,
        turn_seat: int,
        mode: str | None = None,
    ):
        # `timing`: "command_end", "turn_end" or "battle_end"; `mode`: for a
        # secondary, "fixed" or "tactical".
        self.game = game
        self.seat = seat
        self.opponent = next(p.seat for p in game.players if p.seat != seat)
        self.timing = timing
        self.battle_round = battle_round
        self.turn_seat = turn_seat
        self.mode = mode

    # --- when it is ---

    @property
    def holder_turn(self) -> bool:
        return self.turn_seat == self.seat

    def _rounds(self, rounds) -> bool:
        return rounds is None or self.battle_round in rounds

    def your_turn_end(self, rounds=None) -> bool:
        return self.timing == "turn_end" and self.holder_turn and self._rounds(rounds)

    def opponent_turn_end(self, rounds=None) -> bool:
        return self.timing == "turn_end" and not self.holder_turn and self._rounds(rounds)

    def any_turn_end(self, rounds=None) -> bool:
        return self.timing == "turn_end" and self._rounds(rounds)

    def command(self, rounds=range(2, 6)) -> bool:
        # "End of your Command phase (or the end of your turn in the fifth
        # battle round)".
        if not self.holder_turn or not self._rounds(rounds):
            return False
        if self.battle_round == 5:
            return self.timing == "turn_end"
        return self.timing == "command_end"

    def command_only(self, rounds) -> bool:
        # "End of your Command phase", with no fifth-round exception.
        return self.timing == "command_end" and self.holder_turn and self._rounds(rounds)

    def opponent_turn_or_fifth_round_end(self, rounds=None) -> bool:
        # "End of your opponent's turn or the end of the fifth battle round
        # (whichever comes first)".
        if not self.any_turn_end(rounds):
            return False
        if not self.holder_turn:
            return True
        # Their own turn ends the fifth battle round if they go second.
        return self.battle_round == 5 and self.game.first_seat != self.seat

    @property
    def battle_end(self) -> bool:
        return self.timing == "battle_end"

    # --- objectives ---

    @cached_property
    def control(self) -> list[objectives.ObjectiveControl]:
        return objectives.control(self.game)

    def objectives(self) -> list[TerrainObjective]:
        return [c.objective for c in self.control]

    def is_home(self, objective: TerrainObjective, seat: int | None = None) -> bool:
        return objectives.is_home(self.game, objective, seat or self.seat)

    def is_opponents_home(self, objective: TerrainObjective) -> bool:
        return self.is_home(objective, self.opponent)

    @staticmethod
    def is_central(objective: TerrainObjective) -> bool:
        return objectives.is_central(objective)

    @staticmethod
    def is_expansion(objective: TerrainObjective) -> bool:
        return objectives.is_expansion(objective)

    def controlled(
        self, seat: int | None = None, exclude_home: bool = False, exclude_homes: bool = False
    ) -> list[TerrainObjective]:
        # The objectives the player (the holder, by default) controls -
        # without their own home objective, or without either home.
        seat = seat or self.seat
        found = []
        for control in self.control:
            o = control.objective
            if control.controller != seat:
                continue
            if exclude_home and self.is_home(o, seat):
                continue
            if exclude_homes and o.kind in objectives.HOME_KINDS.values():
                continue
            found.append(o)
        return found

    def in_opponents_territory(self, objective: TerrainObjective) -> bool:
        return regions.point_in(
            (objective.x, objective.y), regions.territory(self.game, self.opponent)
        )

    def in_no_mans_land(self, objective: TerrainObjective) -> bool:
        return regions.point_in_no_mans_land(self.game, (objective.x, objective.y))

    def controlled_at_start(self) -> set[int]:
        # The objectives the holder controlled at the start of this turn.
        return {
            objective_id
            for objective_id, controller in turn_record.controlled_at_start(
                self.game, self.battle_round, self.turn_seat
            ).items()
            if controller == self.seat
        }

    # --- destroyed ---

    def _owner(self, unit_id: int) -> int:
        return turn_record.owner_seat(self.game, unit_id)

    def destroyed_units(self, enemy: bool = True) -> list:
        # The enemy (or friendly) units destroyed this turn.
        seat = self.opponent if enemy else self.seat
        return [
            d
            for d in turn_record.units_destroyed(self.game, self.battle_round, self.turn_seat)
            if self._owner(d.unit_id) == seat
        ]

    def destroyed_models(self, enemy: bool = True) -> list:
        seat = self.opponent if enemy else self.seat
        return [
            d
            for d in turn_record.models_destroyed(self.game, self.battle_round, self.turn_seat)
            if self._owner(d.unit_id) == seat
        ]

    def friendly_units_destroyed_previous_turn(self) -> int:
        previous = turn_record.previous_turn(self.game, self.battle_round, self.turn_seat)
        if previous is None:
            return 0
        return sum(
            1
            for d in turn_record.units_destroyed(self.game, *previous)
            if self._owner(d.unit_id) == self.seat
        )

    def started_on_objectives(self) -> dict[int, set[int]]:
        return turn_record.started_on_objectives(self.game, self.battle_round, self.turn_seat)

    def started_in_areas(self) -> dict[int, set[int]]:
        return turn_record.started_in_areas(self.game, self.battle_round, self.turn_seat)

    # --- missions' operation markers, actions and marked units ---

    def markers(self, seat: int | None = None, source: str | None = None) -> list:
        # The player's (the holder's, by default) operation markers on the
        # battlefield - from one source, if given.
        from app.services.in_game import mission_state

        return [
            m
            for m in mission_state.markers(self.game, seat or self.seat)
            if source is None or m.source == source
        ]

    def placed_this_turn(self, marker) -> bool:
        return (
            marker.placed_round == self.battle_round
            and marker.placed_turn_seat == self.turn_seat
        )

    def marker_objectives(self, marker) -> set[int]:
        from app.services.in_game import mission_state

        return mission_state.marker_objectives(self.game, marker)

    def marker_area(self, marker) -> int | None:
        from app.services.in_game import mission_state

        return mission_state.marker_area(self.game, marker)

    def completed_actions(self, name: str) -> list:
        # The holder's actions of that name completed this turn.
        from app.services.in_game import actions

        return actions.completed(self.game, self.seat, name, self.battle_round, self.turn_seat)

    def marked(self, kind: str) -> list:
        from app.services.in_game import mission_state

        return mission_state.marked(self.game, kind, self.seat)

    def objective(self, objective_id: int):
        return next(o for o in self.objectives() if o.id == objective_id)

    def units_within_area(self, seat: int, area_id: int) -> list[Unit]:
        # The player's units (any) within a terrain area.
        from app.services.in_game.terrain import area_polygon

        area = next(a for a in self.game.layout.areas if a.id == area_id)
        return [
            u
            for u in self.units(seat, scoring=False)
            if regions.unit_within(self.game, u, area_polygon(area))
        ]

    # --- units ---

    def unit(self, unit_id: int) -> Unit:
        return deployment.find_unit(self.game, unit_id)

    def unit_model(self, unit_model_id: int):
        return next(
            m
            for p in self.game.players
            for u in p.army_list.units
            for m in u.unit_models
            if m.id == unit_model_id
        )

    @staticmethod
    def keywords(unit: Unit) -> set[str]:
        return {k.name for m in unit.unit_models for k in m.model.keywords}

    def army(self, seat: int) -> list[Unit]:
        # Every unit in the player's army (on the battlefield or not).
        player = next(p for p in self.game.players if p.seat == seat)
        return deployment.deployable_units(player)

    def units(self, seat: int | None = None, scoring: bool = True) -> list[Unit]:
        # The player's units on the battlefield - for most missions, not
        # counting AIRCRAFT or Battle-shocked units (`scoring`).
        seat = seat or self.seat
        player = next(p for p in self.game.players if p.seat == seat)
        placed = deployment.positions(self.game)
        shocked = battle_shock.battle_shocked_ids(self.game)
        return [
            u
            for u in deployment.deployable_units(player)
            if deployment.is_deployed(u, placed)
            and not (scoring and (u.id in shocked or AIRCRAFT in self.keywords(u)))
        ]
