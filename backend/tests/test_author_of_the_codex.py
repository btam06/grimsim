from httpx import AsyncClient

from app.models import DatasheetAbility
from app.routers.games import _load_game
from app.services.in_game import command_phase, deployment
from tests.test_movement import _battle
from tests.test_reinforcements import _advance_to
from tests.test_space_marine_units import _model_of

# Roboute Guilliman's Author of the Codex: in your Movement phase, one
# visible friendly ADEPTUS ASTARTES unit within 12" has a combat doctrine of
# your choice active too, until the start of your next Command phase.

AUTHOR = "Author of the Codex"
ASTARTES = ("ADEPTUS ASTARTES",)


async def _game(client, session, tmp_path):
    # Seat 2 (first) has G (with the ability), A 8" from it and B 30" away.
    units = {
        1: [("D", 1, {})],
        2: [("G", 1, {"keywords": ASTARTES}), ("A", 1, {"keywords": ASTARTES}),
            ("B", 1, {"keywords": ASTARTES})],
    }
    spots = {"D": (20, 38), "G": (10, 4), "A": (18, 4), "B": (40, 4)}
    game, deployment_ = await _battle(client, session, tmp_path, units=units, spots=spots)
    g = next(u for u in deployment_["units"] if u["name"] == "G")
    model = await _model_of(session, g)
    model.abilities.append(DatasheetAbility(name=AUTHOR, description=AUTHOR))
    await session.commit()
    return game["id"], {u["name"]: u for u in deployment_["units"]}


def _author(command):
    return next(a for a in command["abilities"] if a["ability"] == AUTHOR)


async def test_author_of_the_codex_in_the_movement_phase(client: AsyncClient, session, tmp_path):
    game_id, units = await _game(client, session, tmp_path)
    command = (await client.get(f"/games/{game_id}/command")).json()
    assert command["phase"] == "movement"
    author = _author(command)
    assert (author["target_range"], author["required"]) == (12.0, False)
    assert author["unit_model_id"] == units["G"]["models"][0]["unit_model_id"]
    assert {t["name"] for t in author["targets"]} == {"G", "A"}
    assert set(author["options"]) == {"Assault Doctrine", "Devastator Doctrine", "Tactical Doctrine"}

    # Not B (30" away).
    choice = {"seat": 2, "unit_id": units["G"]["unit_id"], "ability": AUTHOR,
              "option": "Assault Doctrine", "target_unit_id": units["B"]["unit_id"]}
    assert (await client.post(f"/games/{game_id}/command/choice", json=choice)).status_code == 400
    choice["target_unit_id"] = units["A"]["unit_id"]
    response = await client.post(f"/games/{game_id}/command/choice", json=choice)
    assert response.status_code == 200, response.text

    game = await _load_game(session, game_id)
    a, b = (deployment.find_unit(game, units[n]["unit_id"]) for n in "AB")
    assert "Assault Doctrine" in command_phase.options_for(game, 2, a)
    assert "Assault Doctrine" not in command_phase.options_for(game, 2, b)
    # Advancing doesn't stop A charging.
    assert command_phase.eligible_after(game, a, "advanced", "charge")
    assert not command_phase.eligible_after(game, b, "advanced", "charge")

    # Until the start of their next Command phase.
    await _advance_to(client, game_id, 1, 1, "command")
    session.expire_all()
    game = await _load_game(session, game_id)
    a = deployment.find_unit(game, units["A"]["unit_id"])
    assert "Assault Doctrine" in command_phase.options_for(game, 2, a)
    await _advance_to(client, game_id, 2, 2, "command")
    session.expire_all()
    game = await _load_game(session, game_id)
    a = deployment.find_unit(game, units["A"]["unit_id"])
    assert "Assault Doctrine" not in command_phase.options_for(game, 2, a)
    # Not selected in the Command phase.
    command = (await client.get(f"/games/{game_id}/command")).json()
    assert all(x["ability"] != AUTHOR for x in command["abilities"])
    assert (await client.post(f"/games/{game_id}/command/choice", json=choice)).status_code == 400
