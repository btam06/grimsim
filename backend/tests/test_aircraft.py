from httpx import AsyncClient

from app.models import Keyword

from app.routers.games import _load_game
from app.services.in_game import charging, deployment, movement, reinforcements
from tests.test_deployment import _unit_named
from tests.test_movement import _battle

# AIRCRAFT (23): seat 2's J is made one on the battlefield (as if it had
# made an ingress move - deploying it there isn't allowed).


async def test_aircraft(client: AsyncClient, session, tmp_path):
    units = {1: [("A", 1, {})], 2: [("J", 1, {})]}
    spots = {"A": (20, 38), "J": (20, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    game_ = await _load_game(session, game["id"])
    j = deployment.find_unit(game_, _unit_named(deployment_, "J")["unit_id"])
    j.unit_models[0].model.keywords.append(Keyword(name="AIRCRAFT"))
    # Only ingress moves; no charges.
    assert movement.allowed_kinds(game_, j) == []
    assert charging.cant_charge_reason(game_, j) == "AIRCRAFT units can't declare a charge"
    # At the end of its opponent's turn, it goes into Strategic Reserves.
    game_.turn_seat = 1
    reinforcements.aircraft_to_reserves(game_)
    assert reinforcements.in_reserves(game_, j)
