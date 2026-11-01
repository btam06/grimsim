from httpx import AsyncClient

from app.engine import saves, state, store
from app.engine.catalog import Catalog
from tests.test_deployment import _unit_named
from tests.test_movement import _battle

# Autosaves (see app/engine/saves.py): a game's state at the start of each
# phase - restorable.


async def test_each_phase_is_saved_at_its_start(client: AsyncClient, session, tmp_path, saves_dir):
    game, _ = await _battle(client, session, tmp_path)
    names = {p.name for p in saves.saves(game["id"])}
    # Seat 2 goes first: its command phase, then its movement phase (now).
    assert {"r1-s2-command.json", "r1-s2-movement.json"} <= names
    assert (saves_dir / str(game["id"]) / saves.CATALOG).exists()


async def test_a_save_restores_the_game(client: AsyncClient, session, tmp_path):
    game, deployment = await _battle(client, session, tmp_path)
    restored, catalog = saves.restore(saves.folder(game["id"]) / "r1-s2-movement.json")
    live = store.get(game["id"]).game
    assert restored.to_dict() == live.to_dict()
    assert (restored.battle_round, restored.turn_seat, restored.phase) == (1, 2, "movement")
    # What it refers to in the catalog comes back as objects: the armies,
    # down to each model's datasheet.
    d = _unit_named(deployment, "D")
    player = next(p for p in restored.players if p.seat == 2)
    assert player.army_list is catalog.get("ArmyList", player.list_id)
    unit = next(u for u in player.army_list.units if u.id == d["unit_id"])
    assert unit.unit_models and unit.unit_models[0].model.name
    assert unit.label  # a property, copied from the ORM class
    # Positions as they were.
    assert {p.unit_model_id for p in restored.model_positions} == {
        p.unit_model_id for p in live.model_positions
    }


async def test_restored_records_get_new_ids(client: AsyncClient, session, tmp_path):
    game, _ = await _battle(client, session, tmp_path)
    restored, _ = saves.restore(saves.folder(game["id"]) / "r1-s2-movement.json")
    highest = max(getattr(r, "id", 0) or 0 for r in restored.records() if r is not restored)
    token = state.playing(restored)
    try:
        move = state.GameUnitMove(unit_id=1, battle_round=1, turn_seat=2, kind="normal")
    finally:
        state.stop_playing(token)
    assert move.id == highest + 1


async def test_the_catalog_round_trips(client: AsyncClient, session, tmp_path):
    game, _ = await _battle(client, session, tmp_path)
    catalog = store.get(game["id"]).catalog
    again = Catalog.from_dict(catalog.to_dict())
    assert again.to_dict() == catalog.to_dict()
    assert {name for name in catalog.rows} >= {"ArmyList", "Unit", "UnitModel", "Model"}


async def test_deleting_a_game_deletes_its_saves(client: AsyncClient, session, tmp_path):
    game, _ = await _battle(client, session, tmp_path)
    assert saves.folder(game["id"]).exists()
    assert (await client.delete(f"/games/{game['id']}")).status_code == 204
    assert not saves.folder(game["id"]).exists()
