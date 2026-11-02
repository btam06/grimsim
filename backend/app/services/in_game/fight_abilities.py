from __future__ import annotations

from fastapi import HTTPException

from app.combat_rules import Rule
from app.engine.state import Game, GameFightAbilityUse
from app.models import Unit
from app.services.in_game import deployment

# Abilities a unit can use when it's selected to fight, in a game - e.g.
# Banner of Macragge: once a battle (for the army), its melee attacks have +1
# A and S that fight (see datasheet_abilities FIGHT_ABILITIES). Its player
# says so with the fight (see app/routers/games.py fight).


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _config() -> dict:
    from app.seeds import datasheet_abilities

    return datasheet_abilities.FIGHT_ABILITIES


def available(game: Game, unit: Unit) -> list[str]:
    # The unit's abilities it could use fighting now - not used up (by it, or
    # its army, for one that's once a battle per army).
    config = _config()
    seat = deployment.owner(game, unit).seat
    names = {
        a.name for m in deployment.models_on_battlefield(game, unit) for a in m.model.abilities
    }
    found = []
    for name in sorted(names & set(config)):
        ability = config[name]
        used = [
            u
            for u in game.fight_ability_uses
            if u.ability == name and (u.seat == seat if ability.per_army else u.unit_id == unit.id)
        ]
        if ability.uses_wargear is not None:
            # (Once for each model with the wargear.)
            uses = sum(
                1
                for m in deployment.models_on_battlefield(game, unit)
                for g in m.wargear
                if g.name == ability.uses_wargear
            )
            if len(used) >= uses:
                continue
        elif ability.once_per_battle and used:
            continue
        found.append(name)
    return found


def use(game: Game, unit: Unit, names: list[str]) -> list[Rule]:
    # The unit uses these abilities as it fights: their rules for its attacks.
    rules: list[Rule] = []
    usable = available(game, unit)
    for name in dict.fromkeys(names):
        if name not in usable:
            raise _bad_request(f"it can't use {name} now")
        game.fight_ability_uses.append(
            GameFightAbilityUse(
                seat=deployment.owner(game, unit).seat,
                unit_id=unit.id,
                ability=name,
                battle_round=game.battle_round,
                turn_seat=game.turn_seat,
            )
        )
        rules += _config()[name].rules
    return rules
