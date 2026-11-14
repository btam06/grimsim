from __future__ import annotations

import math

from fastapi import HTTPException

from app.engine.state import Game, GamePlayer, GameUnitSplit
from app.models import Unit
from app.services.in_game import deployment
from app.services.list_building import enhancements as enhancement_rules

# Splitting a unit in two, at the start of the Declare Battle Formations step
# - e.g. an Immolator: its player can select one of their BATTLE SISTERS
# SQUAD, DOMINION SQUAD or SISTERS NOVITIATE SQUAD units; it's split into two
# units of as equal a number of models as possible, one of which must start
# the battle embarked in that Immolator (the other can start embarked in
# another transport, or be deployed as a separate unit). If the unit has the
# Cherub ability, only one of the two can use it.
#
# The player picks which models form the new unit (by default, the second
# half of them) - as many as can make the two as equal as possible - and it
# can start embarked in the transport straight away.
#
# A game's units are its catalog's (see app/engine/catalog.py), copied from
# its army lists: the new unit's made there, from the original - its models
# moved into it - with an id of its own (SPLIT_ID_OFFSET + the original's).
# Only its CHARACTER models (leaders, as this game has them part of the unit)
# aren't counted or moved: they stay with the original. Its points are
# shared by models; the unit's upgrade stays with the original. The game's
# state records each split (Game.unit_splits) and the catalog's made to match
# it whenever it could have drifted (see sync): the catalog's read again, or
# the game's put back as it was (e.g. a refused action).
#
# Which transports can split which units: the factions' SPLITTING_TRANSPORTS
# ({transport keyword: (unit keyword, ...)}).

SPLIT_ID_OFFSET = 1_000_000
CHERUB_ABILITIES = ("Cherub", "Cherubs")


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _config() -> dict[str, tuple[str, ...]]:
    from app.seeds.factions.adepta_sororitas.unit_abilities import SPLITTING_TRANSPORTS

    return SPLITTING_TRANSPORTS


def _keywords(unit: Unit) -> set[str]:
    return {k for m in unit.unit_models for k in enhancement_rules.model_keywords(unit, m)}


def _player(game: Game, seat: int) -> GamePlayer:
    return next(p for p in game.players if p.seat == seat)


def of_unit(game: Game, unit_id: int) -> GameUnitSplit | None:
    # The split the unit is half of (either half), if it is.
    return next(
        (s for s in game.unit_splits if unit_id in (s.unit_id, s.new_unit_id)), None
    )


def transports(game: Game, player: GamePlayer) -> list[tuple[Unit, tuple[str, ...]]]:
    # The player's transports that can split a unit, and the keywords of the
    # units they can: (transport, keywords).
    from app.services.in_game.battle_formations import is_transport

    config = _config()
    found = []
    for unit in deployment.deployable_units(player):
        if not is_transport(unit):
            continue
        keywords = _keywords(unit)
        for transport_keyword, unit_keywords in config.items():
            if transport_keyword in keywords:
                found.append((unit, unit_keywords))
                break
    return found


def _troops(unit: Unit) -> list:
    # Its models that are split between the two: all but its CHARACTER models.
    return [
        m
        for m in deployment.unit_models(unit)
        if "CHARACTER" not in enhancement_rules.model_keywords(unit, m)
    ]


def troops(unit: Unit) -> list:
    return _troops(unit)


def sizes(unit: Unit) -> list[int]:
    # How many models the new unit can have: half (either way, for an odd
    # number).
    n = len(_troops(unit))
    return sorted({n // 2, math.ceil(n / 2)})


def candidates(game: Game, player: GamePlayer, keywords: tuple[str, ...]) -> list[Unit]:
    # The player's units a transport splitting units with `keywords` could
    # split now: not split already, not yet given a battle formation, and of
    # two or more models (not counting CHARACTERs).
    wanted = set(keywords)
    return [
        u
        for u in deployment.deployable_units(player)
        if wanted & _keywords(u)
        and of_unit(game, u.id) is None
        and deployment.battle_formation(game, u) is None
        and len(_troops(u)) >= 2
    ]


def _check_step(game: Game, seat: int) -> None:
    from app.services.in_game import battle_formations

    if deployment.deployment_step(game) != "formations":
        raise _bad_request("units are split at the start of the Declare Battle Formations step")
    if battle_formations.done(game, seat):
        raise _bad_request("that player has already declared their battle formations")


def split(
    game: Game,
    seat: int,
    transport: Unit,
    unit: Unit,
    cherub_to_new: bool = False,
    unit_model_ids: list[int] | None = None,
    embark: bool = False,
) -> GameUnitSplit:
    # The transport splits the unit in two: the new unit, with the models
    # `unit_model_ids` (by default, the second half of them). (`cherub_to_new`:
    # the new unit, not the original, can use its Cherub ability; `embark`:
    # the new unit starts embarked in the transport.)
    from app.engine import context

    _check_step(game, seat)
    player = _player(game, seat)
    found = {t.id: kws for t, kws in transports(game, player)}
    if transport.id not in found:
        raise _bad_request(f"{transport.label} can't split a unit")
    if any(s.transport_unit_id == transport.id for s in game.unit_splits):
        raise _bad_request(f"{transport.label} has already split a unit")
    if unit.id not in {u.id for u in candidates(game, player, found[transport.id])}:
        raise _bad_request(
            f"{transport.label} can split one of their "
            + ", ".join(found[transport.id])
            + " units of two or more models (not already split, or given a battle formation)"
        )
    troops = _troops(unit)
    if unit_model_ids is None:
        moved = troops[math.ceil(len(troops) / 2):]
    else:
        picked = set(unit_model_ids)
        if not picked <= {m.id for m in troops}:
            raise _bad_request(
                f"pick {unit.label}'s models (not its CHARACTER models) for the new unit"
            )
        if len(picked) not in sizes(unit):
            raise _bad_request(
                "the two units must be as equal as possible: pick "
                + " or ".join(map(str, sizes(unit)))
                + " models"
            )
        moved = [m for m in troops if m.id in picked]
    points = round(unit.points * len(moved) / len(deployment.unit_models(unit)))
    new_id = SPLIT_ID_OFFSET + unit.id
    cherub = unit.id
    if cherub_to_new:
        cherub = new_id
    record = GameUnitSplit(
        seat=seat,
        unit_id=unit.id,
        new_unit_id=new_id,
        transport_unit_id=transport.id,
        unit_model_ids=[m.id for m in moved],
        points=points,
        cherub_unit_id=cherub if _has_cherub(unit) else None,
    )
    game.unit_splits.append(record)
    _apply(context.catalog(), record)
    if embark:
        from app.services.in_game import battle_formations

        battle_formations.set_formation(
            game, seat, deployment.find_unit(game, new_id), "embarked", transport
        )
    return record


def unsplit(game: Game, seat: int, unit: Unit) -> None:
    # The split the unit's half of is undone (neither half given a battle
    # formation yet).
    from app.engine import context

    _check_step(game, seat)
    record = of_unit(game, unit.id)
    if record is None or record.seat != seat:
        raise _bad_request(f"{unit.label} wasn't split")
    for unit_id in (record.unit_id, record.new_unit_id):
        half = deployment.find_unit(game, unit_id)
        if deployment.battle_formation(game, half) is not None:
            raise _bad_request(f"{half.label} has a battle formation: take it off first")
    game.unit_splits.remove(record)
    _undo(context.catalog(), record)


def check_declared(game: Game, seat: int) -> None:
    # Before the player's battle formations are declared: one half of each
    # unit they split starts embarked in the transport that split it.
    for record in game.unit_splits:
        if record.seat != seat:
            continue
        halves = [deployment.find_unit(game, i) for i in (record.unit_id, record.new_unit_id)]
        if not any(
            (f := deployment.battle_formation(game, h)) is not None
            and f.place == "embarked"
            and f.transport_unit_id == record.transport_unit_id
            for h in halves
        ):
            transport = deployment.find_unit(game, record.transport_unit_id)
            raise _bad_request(
                f"one of {halves[0].label} and {halves[1].label} must start embarked in "
                f"{transport.label}"
            )


def _has_cherub(unit: Unit) -> bool:
    return any(a.name in CHERUB_ABILITIES for m in unit.unit_models for a in m.model.abilities)


def cherub_allowed(game: Game, unit: Unit) -> bool:
    # Whether the unit can use its Cherub ability: a half of a split unit
    # only if it's the one chosen.
    record = of_unit(game, unit.id)
    return record is None or record.cherub_unit_id in (None, unit.id)


# --- the catalog ---


def _apply(catalog, record: GameUnitSplit) -> None:
    # The new unit made in the catalog, the models moved into it (once).
    if catalog.get("Unit", record.new_unit_id) is not None:
        return
    original = catalog.get("Unit", record.unit_id)
    if original is None:
        return
    moved = set(record.unit_model_ids)
    new = type(original).__new__(type(original))
    new.__dict__.update(original.__dict__)
    new.__dict__["id"] = record.new_unit_id
    new.__dict__["points"] = record.points
    new.__dict__["unit_models"] = [m for m in original.unit_models if m.id in moved]
    for name in ("upgrade", "upgrade_id"):
        if name in new.__dict__:
            new.__dict__[name] = None
    if "rule_selection_links" in new.__dict__:
        new.__dict__["rule_selection_links"] = []
    original.__dict__["unit_models"] = [m for m in original.unit_models if m.id not in moved]
    original.__dict__["points"] = original.points - record.points
    for m in new.unit_models:
        m.__dict__["unit_id"] = new.id
        if "unit" in m.__dict__:
            m.__dict__["unit"] = new
    catalog.rows.setdefault("Unit", {})[(new.id,)] = new
    army_list = original.__dict__.get("army_list")
    if army_list is not None and "units" in army_list.__dict__:
        army_list.__dict__["units"] = list(army_list.units) + [new]


def _undo(catalog, record: GameUnitSplit) -> None:
    # The new unit's models back in the original, and it gone.
    new = catalog.get("Unit", record.new_unit_id)
    original = catalog.get("Unit", record.unit_id)
    if new is None or original is None:
        return
    for m in new.unit_models:
        m.__dict__["unit_id"] = original.id
        if "unit" in m.__dict__:
            m.__dict__["unit"] = original
    original.__dict__["unit_models"] = sorted(
        list(original.unit_models) + list(new.unit_models), key=lambda m: m.id
    )
    original.__dict__["points"] = original.points + new.points
    del catalog.rows["Unit"][(new.id,)]
    army_list = original.__dict__.get("army_list")
    if army_list is not None and "units" in army_list.__dict__:
        army_list.__dict__["units"] = [u for u in army_list.units if u.id != new.id]


def sync(game: Game, catalog) -> None:
    # The catalog's units made to match the game's splits: those it has that
    # the game doesn't (e.g. the game put back as it was) undone, those the
    # game has that it doesn't (e.g. the catalog read again) made.
    recorded = {s.new_unit_id: s for s in game.unit_splits}
    for (unit_id,), unit in list(catalog.rows.get("Unit", {}).items()):
        if unit_id >= SPLIT_ID_OFFSET and unit_id not in recorded:
            original_id = unit_id - SPLIT_ID_OFFSET
            _undo(
                catalog,
                GameUnitSplit(
                    unit_id=original_id,
                    new_unit_id=unit_id,
                    unit_model_ids=[m.id for m in unit.unit_models],
                    points=unit.points,
                ),
            )
    for record in game.unit_splits:
        _apply(catalog, record)
