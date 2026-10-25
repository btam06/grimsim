import pytest
from httpx import AsyncClient

from app.services.in_game import game as game_service

PHASES = ["command", "movement", "shooting", "charge", "fight"]


async def _setup(client: AsyncClient, *, tactical_cards: int = 4, modes=("tactical", "tactical")):
    # Two users, each with a list in their own faction whose one detachment has
    # one disposition; a primary mission for that pairing (each way round);
    # some secondary missions; and a stratagem per timing case.
    ids: dict = {}
    for i, name in enumerate(["Alice", "Bob"], start=1):
        ids[f"user{i}"] = (await client.post("/users", json={"name": name})).json()["id"]
        ids[f"faction{i}"] = (await client.post("/factions", json={"name": f"Faction {i}"})).json()[
            "id"
        ]
        ids[f"disposition{i}"] = (
            await client.post("/dispositions", json={"name": f"Disposition {i}"})
        ).json()["id"]
        ids[f"detachment{i}"] = (
            await client.post(
                "/detachments",
                json={
                    "name": f"Detachment {i}",
                    "faction_id": ids[f"faction{i}"],
                    "dp": 1,
                    "disposition_ids": [ids[f"disposition{i}"]],
                },
            )
        ).json()["id"]
        ids[f"list{i}"] = (
            await client.post(
                "/lists",
                json={
                    "name": f"List {i}",
                    "points_limit": 2000,
                    "faction_id": ids[f"faction{i}"],
                    "detachment_ids": [ids[f"detachment{i}"]],
                    "user_id": ids[f"user{i}"],
                },
            )
        ).json()["id"]
    for mine, theirs in ((1, 2), (2, 1)):
        ids[f"primary{mine}"] = (
            await client.post(
                "/primary-missions",
                json={
                    "name": f"Primary {mine}",
                    "player_disposition_id": ids[f"disposition{mine}"],
                    "opponent_disposition_id": ids[f"disposition{theirs}"],
                },
            )
        ).json()["id"]

    ids["tactical"] = [
        (
            await client.post(
                "/secondary-missions",
                json={
                    "name": f"Tactical {n}",
                    "completes_on": "your_turn",
                    "fixed_points": 3,
                    "tactical_points": 5,
                },
            )
        ).json()["id"]
        for n in range(tactical_cards)
    ]
    ids["reactive"] = (
        await client.post(
            "/secondary-missions",
            json={"name": "Reactive", "completes_on": "opponent_turn", "fixed_points": 2},
        )
    ).json()["id"]

    async def stratagem(name, timings, cp=1, **extra):
        body = {"name": name, "cp": cp, "is_core": True, "timings": timings, **extra}
        if "detachment_ids" in extra:
            body["is_core"] = False
        return (await client.post("/stratagems", json=body)).json()["id"]

    ids["anytime"] = await stratagem("Anytime", [])
    ids["grenade"] = await stratagem("Grenade", [{"phase": "shooting", "turn": "your_turn"}])
    ids["overwatch"] = await stratagem(
        "Overwatch",
        [
            {"phase": "movement", "turn": "opponent_turn"},
            {"phase": "charge", "turn": "opponent_turn"},
        ],
    )
    ids["expensive"] = await stratagem("Expensive", [], cp=3)
    ids["detachment2_only"] = await stratagem(
        "Detachment 2 Trick", [], detachment_ids=[ids["detachment2"]]
    )
    ids["modes"] = modes
    return ids


def _game_payload(ids, *, modes=None, fixed=((), ()), attacker=1, first=1):
    modes = modes or ids["modes"]
    return {
        "players": [
            {
                "user_id": ids[f"user{seat}"],
                "list_id": ids[f"list{seat}"],
                "secondary_mode": modes[seat - 1],
                "fixed_secondary_ids": list(fixed[seat - 1]),
            }
            for seat in (1, 2)
        ],
        "attacker_seat": attacker,
        "first_seat": first,
    }


async def _new_game(client, ids, **kwargs):
    response = await client.post("/games", json=_game_payload(ids, **kwargs))
    assert response.status_code == 201, response.json()
    return response.json()


def _player(game, seat):
    return next(p for p in game["players"] if p["seat"] == seat)


async def _advance(client, game_id, times=1):
    for _ in range(times):
        response = await client.post(f"/games/{game_id}/advance")
        assert response.status_code == 200, response.json()
    return response.json()


# --- users, list owners, missions ---


async def test_users_crud(client: AsyncClient):
    response = await client.post("/users", json={"name": "Alice"})
    assert response.status_code == 201
    assert (await client.post("/users", json={"name": "Alice"})).status_code == 400
    assert [u["name"] for u in (await client.get("/users")).json()] == ["Alice"]
    assert (await client.delete(f"/users/{response.json()['id']}")).status_code == 204
    assert (await client.get("/users")).json() == []


async def test_list_owner(client: AsyncClient, faction_id: int):
    user_id = (await client.post("/users", json={"name": "Alice"})).json()["id"]
    body = {"name": "L", "points_limit": 1000, "faction_id": faction_id, "user_id": user_id}
    response = await client.post("/lists", json=body)
    assert response.json()["user_id"] == user_id
    list_id = response.json()["id"]

    response = await client.put(f"/lists/{list_id}", json={**body, "user_id": None})
    assert response.json()["user_id"] is None
    assert (await client.post("/lists", json={**body, "user_id": 9999})).status_code == 400
    # Deleting a user who owns a list leaves the list, unowned.
    await client.put(f"/lists/{list_id}", json=body)
    assert (await client.delete(f"/users/{user_id}")).status_code == 204
    [army_list] = (await client.get("/lists")).json()
    assert army_list["user_id"] is None


async def test_secondary_mission_needs_points_for_a_mode(client: AsyncClient):
    response = await client.post(
        "/secondary-missions", json={"name": "Nothing", "completes_on": "your_turn"}
    )
    assert response.status_code == 422


async def test_primary_mission_is_unique_per_disposition_pair(client: AsyncClient):
    a = (await client.post("/dispositions", json={"name": "A"})).json()["id"]
    b = (await client.post("/dispositions", json={"name": "B"})).json()["id"]
    body = {"name": "P", "player_disposition_id": a, "opponent_disposition_id": b}
    assert (await client.post("/primary-missions", json=body)).status_code == 201
    assert (await client.post("/primary-missions", json=body)).status_code == 400
    bad = {**body, "player_disposition_id": 9999}
    assert (await client.post("/primary-missions", json=bad)).status_code == 400


async def test_stratagem_timings_round_trip(client: AsyncClient):
    timings = [{"phase": "charge", "turn": "opponent_turn"}]
    response = await client.post(
        "/stratagems", json={"name": "S", "cp": 1, "is_core": True, "timings": timings}
    )
    assert response.json()["timings"] == timings
    assert (await client.get("/stratagems")).json()[0]["timings"] == timings


# --- setting up a game ---


async def test_create_game(client: AsyncClient):
    ids = await _setup(client)
    game = await _new_game(client, ids, attacker=2, first=1)

    assert game["status"] == "setup"
    assert (game["attacker_seat"], game["first_seat"], game["battle_round"]) == (2, 1, 0)
    for seat in (1, 2):
        player = _player(game, seat)
        assert player["user_id"] == ids[f"user{seat}"]
        assert player["list_id"] == ids[f"list{seat}"]
        # The only disposition on their detachments, picked automatically.
        assert player["disposition_id"] == ids[f"disposition{seat}"]
        # The primary mission for (their disposition, opponent's disposition).
        assert player["primary_mission_id"] == ids[f"primary{seat}"]
        assert (player["cp"], player["vp"], player["secondaries"]) == (0, 0, [])


async def test_create_game_validation(client: AsyncClient):
    ids = await _setup(client)

    async def status(payload):
        return (await client.post("/games", json=payload)).status_code

    # Someone else's list.
    payload = _game_payload(ids)
    payload["players"][0]["list_id"] = ids["list2"]
    assert await status(payload) == 400
    # The same user twice.
    payload = _game_payload(ids)
    payload["players"][1]["user_id"] = ids["user1"]
    assert await status(payload) == 400
    # Fixed mode needs exactly 2 fixed-usable secondaries.
    assert await status(_game_payload(ids, modes=("fixed", "tactical"))) == 400
    one = ([ids["tactical"][0]], ())
    assert await status(_game_payload(ids, modes=("fixed", "tactical"), fixed=one)) == 400
    # Tactical mode doesn't pick secondaries up front.
    two = (ids["tactical"][:2], ())
    assert await status(_game_payload(ids, fixed=two)) == 400


async def test_create_game_with_fixed_secondaries(client: AsyncClient):
    ids = await _setup(client)
    picks = ([ids["tactical"][0], ids["reactive"]], ())
    game = await _new_game(client, ids, modes=("fixed", "tactical"), fixed=picks)
    cards = _player(game, 1)["secondaries"]
    assert {c["secondary_mission_id"] for c in cards} == set(picks[0])
    assert all(c["fixed"] and c["status"] == "active" for c in cards)
    # Points for the fixed mode.
    assert {c["name"]: c["points"] for c in cards} == {"Tactical 0": 3, "Reactive": 2}


async def test_create_game_chooses_between_several_dispositions(client: AsyncClient):
    ids = await _setup(client)
    extra = (await client.post("/dispositions", json={"name": "Extra"})).json()["id"]
    detachment = (
        await client.post(
            "/detachments",
            json={
                "name": "Second",
                "faction_id": ids["faction1"],
                "dp": 1,
                "disposition_ids": [extra],
            },
        )
    ).json()["id"]
    await client.put(
        f"/lists/{ids['list1']}",
        json={
            "name": "List 1",
            "points_limit": 2000,
            "faction_id": ids["faction1"],
            "detachment_ids": [ids["detachment1"], detachment],
            "user_id": ids["user1"],
        },
    )
    payload = _game_payload(ids)
    assert (await client.post("/games", json=payload)).status_code == 400
    payload["players"][0]["disposition_id"] = extra
    game = (await client.post("/games", json=payload)).json()
    assert _player(game, 1)["disposition_id"] == extra
    # No primary mission defined for that pairing.
    assert _player(game, 1)["primary_mission_id"] is None


# --- playing ---


async def test_start_game(client: AsyncClient):
    ids = await _setup(client)
    game = await _new_game(client, ids, first=2)
    game = (await client.post(f"/games/{game['id']}/start")).json()

    assert (game["status"], game["battle_round"], game["turn_seat"], game["phase"]) == (
        "in_progress",
        1,
        2,
        "command",
    )
    # Both players gain 1 CP; only the turn player (seat 2) draws.
    assert [_player(game, s)["cp"] for s in (1, 2)] == [1, 1]
    assert len(_player(game, 2)["secondaries"]) == 2
    assert _player(game, 1)["secondaries"] == []
    assert (await client.post(f"/games/{game['id']}/start")).status_code == 400


async def test_turns_and_battle_rounds(client: AsyncClient):
    ids = await _setup(client, tactical_cards=20)
    game = await _new_game(client, ids, first=1)
    game_id = game["id"]
    await client.post(f"/games/{game_id}/start")

    seen = []
    for _ in range(4):
        game = await _advance(client, game_id)
        seen.append(game["phase"])
    assert seen == PHASES[1:]

    # After the first player's fight phase: the second player's turn.
    game = await _advance(client, game_id)
    assert (game["battle_round"], game["turn_seat"], game["phase"]) == (1, 2, "command")
    assert [_player(game, s)["cp"] for s in (1, 2)] == [2, 2]
    assert len(_player(game, 2)["secondaries"]) == 2

    # After the second player's fight phase: battle round 2, first player again.
    game = await _advance(client, game_id, times=5)
    assert (game["battle_round"], game["turn_seat"], game["phase"]) == (2, 1, "command")
    assert [_player(game, s)["cp"] for s in (1, 2)] == [3, 3]

    # Five battle rounds of two five-phase turns, then the game is over.
    game = await _advance(client, game_id, times=5 * 2 * 5 - 10)
    assert (game["status"], game["battle_round"], game["turn_seat"], game["phase"]) == (
        "finished",
        5,
        None,
        None,
    )
    assert (await client.post(f"/games/{game_id}/advance")).status_code == 400


async def test_tactical_draws_two_new_cards_each_command_phase(client: AsyncClient):
    # 11th edition: no hand limit - two new cards every command phase, on top
    # of any still held, never one already drawn.
    ids = await _setup(client, tactical_cards=20)
    game = await _new_game(client, ids, first=1)
    game_id = game["id"]
    game = (await client.post(f"/games/{game_id}/start")).json()
    first, second = _player(game, 1)["secondaries"]

    # Achieve one, keep the other; their next command phase adds two more.
    await client.post(f"/games/{game_id}/secondaries/{first['id']}/achieve")
    game = await _advance(client, game_id, times=10)
    cards = _player(game, 1)["secondaries"]
    active = [c for c in cards if c["status"] == "active"]
    assert len(cards) == 4
    assert len(active) == 3
    assert second["id"] in {c["id"] for c in active}
    assert len({c["secondary_mission_id"] for c in cards}) == len(cards)

    # And again, even holding three: five active now.
    game = await _advance(client, game_id, times=10)
    active = [c for c in _player(game, 1)["secondaries"] if c["status"] == "active"]
    assert len(active) == 5


async def test_draws_stop_when_the_deck_runs_out(client: AsyncClient):
    ids = await _setup(client, tactical_cards=1)
    game = await _new_game(client, ids, first=1)
    game = (await client.post(f"/games/{game['id']}/start")).json()
    # Only one tactical-usable card exists ("Reactive" is fixed-only).
    assert len(_player(game, 1)["secondaries"]) == 1


# --- stratagems in a game ---


async def _usable(client, game_id, seat):
    response = await client.get(f"/games/{game_id}/stratagems", params={"seat": seat})
    return {s["name"] for s in response.json()}


async def test_stratagems_are_validated_by_phase_and_turn(client: AsyncClient):
    ids = await _setup(client)
    game = await _new_game(client, ids, first=1)
    game_id = game["id"]
    await client.post(f"/games/{game_id}/start")

    # Command phase, player 1's turn: anytime stratagems only (CP is 1).
    assert await _usable(client, game_id, 1) == {"Anytime"}
    # Movement: player 2 (not their turn) can Overwatch.
    await _advance(client, game_id)
    assert await _usable(client, game_id, 2) == {"Anytime", "Overwatch", "Detachment 2 Trick"}
    assert "Overwatch" not in await _usable(client, game_id, 1)
    # Shooting: player 1 (their turn) can Grenade; player 2 can't.
    await _advance(client, game_id)
    assert "Grenade" in await _usable(client, game_id, 1)
    assert "Grenade" not in await _usable(client, game_id, 2)

    response = await client.post(
        f"/games/{game_id}/stratagems", json={"seat": 2, "stratagem_id": ids["grenade"]}
    )
    assert response.status_code == 400
    response = await client.post(
        f"/games/{game_id}/stratagems", json={"seat": 1, "stratagem_id": ids["grenade"]}
    )
    assert response.status_code == 200
    game = response.json()
    assert _player(game, 1)["cp"] == 0
    [use] = _player(game, 1)["stratagem_uses"]
    assert (use["name"], use["phase"], use["battle_round"], use["turn_seat"], use["cp"]) == (
        "Grenade",
        "shooting",
        1,
        1,
        1,
    )


async def test_stratagems_need_cp_and_the_right_detachment(client: AsyncClient):
    ids = await _setup(client)
    game = await _new_game(client, ids, first=1)
    game_id = game["id"]
    await client.post(f"/games/{game_id}/start")

    async def use(seat, stratagem):
        return await client.post(
            f"/games/{game_id}/stratagems", json={"seat": seat, "stratagem_id": stratagem}
        )

    assert (await use(1, ids["expensive"])).status_code == 400  # 3 CP, has 1
    assert (await use(1, ids["detachment2_only"])).status_code == 400  # not their detachment
    assert (await use(2, ids["detachment2_only"])).status_code == 200
    assert (await use(2, ids["anytime"])).status_code == 400  # now out of CP


async def test_stratagems_cant_be_used_before_the_game_starts(client: AsyncClient):
    ids = await _setup(client)
    game = await _new_game(client, ids)
    response = await client.post(
        f"/games/{game['id']}/stratagems", json={"seat": 1, "stratagem_id": ids["anytime"]}
    )
    assert response.status_code == 400


# --- scoring ---


async def test_achieving_a_tactical_secondary_scores_its_tactical_points(client: AsyncClient):
    ids = await _setup(client)
    game = await _new_game(client, ids, first=1)
    game = (await client.post(f"/games/{game['id']}/start")).json()
    card = _player(game, 1)["secondaries"][0]

    game = (await client.post(f"/games/{game['id']}/secondaries/{card['id']}/achieve")).json()
    player = _player(game, 1)
    assert player["vp"] == 5
    assert next(c for c in player["secondaries"] if c["id"] == card["id"])["status"] == "achieved"
    [score] = player["scores"]
    assert (score["kind"], score["points"], score["game_secondary_id"]) == (
        "secondary",
        5,
        card["id"],
    )
    again = await client.post(f"/games/{game['id']}/secondaries/{card['id']}/achieve")
    assert again.status_code == 400


async def test_secondaries_complete_only_on_their_turn(client: AsyncClient):
    ids = await _setup(client)
    picks = ([ids["tactical"][0], ids["reactive"]], ())
    game = await _new_game(client, ids, modes=("fixed", "tactical"), fixed=picks, first=1)
    game_id = game["id"]
    game = (await client.post(f"/games/{game_id}/start")).json()
    cards = {c["name"]: c["id"] for c in _player(game, 1)["secondaries"]}

    # Player 1's turn: "Reactive" completes on the opponent's turn, so not yet.
    reactive = f"/games/{game_id}/secondaries/{cards['Reactive']}/achieve"
    assert (await client.post(reactive)).status_code == 400
    tactical = f"/games/{game_id}/secondaries/{cards['Tactical 0']}/achieve"
    game = (await client.post(tactical)).json()
    # Fixed: scored with fixed points, and stays active for later turns...
    assert _player(game, 1)["vp"] == 3
    assert all(c["status"] == "active" for c in _player(game, 1)["secondaries"])
    # ...but only once per turn.
    assert (await client.post(tactical)).status_code == 400

    # Player 2's turn: now "Reactive" can be completed by player 1.
    await _advance(client, game_id, times=5)
    game = (await client.post(reactive)).json()
    assert _player(game, 1)["vp"] == 5


async def test_discarding_a_tactical_secondary(client: AsyncClient):
    # At the end of its holder's turn (the fight phase), for 1 CP.
    ids = await _setup(client)
    game = await _new_game(client, ids, first=1)
    game = (await client.post(f"/games/{game['id']}/start")).json()
    card = _player(game, 1)["secondaries"][0]
    url = f"/games/{game['id']}/secondaries/{card['id']}/discard"
    response = await client.post(url)
    assert "end of their holder's turn" in response.json()["detail"]
    game = await _advance(client, game["id"], times=4)
    assert game["phase"] == "fight"
    cp = _player(game, 1)["cp"]
    game = (await client.post(url)).json()
    assert next(c for c in _player(game, 1)["secondaries"] if c["id"] == card["id"])[
        "status"
    ] == "discarded"
    assert (_player(game, 1)["vp"], _player(game, 1)["cp"]) == (0, cp + 1)


async def test_fixed_secondaries_cant_be_discarded(client: AsyncClient):
    ids = await _setup(client)
    picks = ([ids["tactical"][0], ids["reactive"]], ())
    game = await _new_game(client, ids, modes=("fixed", "tactical"), fixed=picks)
    game = (await client.post(f"/games/{game['id']}/start")).json()
    card = _player(game, 1)["secondaries"][0]
    response = await client.post(f"/games/{game['id']}/secondaries/{card['id']}/discard")
    assert response.status_code == 400


async def test_primary_vp_is_added_by_hand(client: AsyncClient):
    ids = await _setup(client)
    game = await _new_game(client, ids)
    game_id = game["id"]
    payload = {"seat": 2, "points": 10}
    assert (await client.post(f"/games/{game_id}/primary-score", json=payload)).status_code == 400
    await client.post(f"/games/{game_id}/start")
    game = (await client.post(f"/games/{game_id}/primary-score", json=payload)).json()
    assert _player(game, 2)["vp"] == 10
    assert _player(game, 2)["scores"][0]["kind"] == "primary"


async def test_games_list_and_delete(client: AsyncClient):
    ids = await _setup(client)
    game = await _new_game(client, ids)
    assert [g["id"] for g in (await client.get("/games")).json()] == [game["id"]]
    # A list used in a game can't be deleted.
    assert (await client.delete(f"/lists/{ids['list1']}")).status_code == 400
    # Nor can a user who has played a game.
    assert (await client.delete(f"/users/{ids['user1']}")).status_code == 400
    assert (await client.delete(f"/games/{game['id']}")).status_code == 204
    assert (await client.get("/games")).json() == []
    assert (await client.get(f"/games/{game['id']}")).status_code == 404


def test_other_seat():
    assert game_service.other_seat(1) == 2
    assert game_service.other_seat(2) == 1


async def test_concurrent_games_are_independent(client: AsyncClient):
    # The same two players (and lists) in two games at once: advancing,
    # spending CP and scoring in one leaves the other untouched.
    ids = await _setup(client, tactical_cards=20)
    first = (await _new_game(client, ids, first=1))["id"]
    second = (await _new_game(client, ids, first=2))["id"]
    await client.post(f"/games/{first}/start")
    await client.post(f"/games/{second}/start")

    await _advance(client, first, times=2)
    await client.post(
        f"/games/{first}/stratagems", json={"seat": 1, "stratagem_id": ids["anytime"]}
    )
    await client.post(f"/games/{first}/primary-score", json={"seat": 1, "points": 7})

    one = (await client.get(f"/games/{first}")).json()
    two = (await client.get(f"/games/{second}")).json()
    assert (one["phase"], one["turn_seat"]) == ("shooting", 1)
    assert (two["phase"], two["turn_seat"]) == ("command", 2)
    assert (_player(one, 1)["cp"], _player(one, 1)["vp"]) == (0, 7)
    assert (_player(two, 1)["cp"], _player(two, 1)["vp"]) == (1, 0)
    assert _player(two, 1)["stratagem_uses"] == []
    # Each game's tactical draws are its own.
    assert len(_player(two, 2)["secondaries"]) == 2
    assert _player(one, 2)["secondaries"] == []


async def test_either_turn_secondaries_complete_on_any_turn(client: AsyncClient):
    ids = await _setup(client)
    either = (
        await client.post(
            "/secondary-missions",
            json={"name": "Either", "completes_on": "either", "fixed_points": 3},
        )
    ).json()["id"]
    picks = ([either, ids["reactive"]], ())
    game = await _new_game(client, ids, modes=("fixed", "tactical"), fixed=picks, first=1)
    game_id = game["id"]
    game = (await client.post(f"/games/{game_id}/start")).json()
    card = next(c for c in _player(game, 1)["secondaries"] if c["name"] == "Either")

    url = f"/games/{game_id}/secondaries/{card['id']}/achieve"
    assert (await client.post(url)).status_code == 200  # player 1's own turn
    await _advance(client, game_id, times=5)
    game = (await client.post(url)).json()  # and their opponent's
    assert _player(game, 1)["vp"] == 6


async def test_achieving_a_secondary_can_score_a_different_amount(client: AsyncClient):
    # e.g. a card that scores 2 VP for one objective or 5 for two.
    ids = await _setup(client)
    game = await _new_game(client, ids, first=1)
    game = (await client.post(f"/games/{game['id']}/start")).json()
    card = _player(game, 1)["secondaries"][0]

    url = f"/games/{game['id']}/secondaries/{card['id']}/achieve"
    assert (await client.post(url, json={"points": -1})).status_code == 422
    game = (await client.post(url, json={"points": 8})).json()
    assert _player(game, 1)["vp"] == 8
    assert _player(game, 1)["scores"][0]["points"] == 8


# --- New Orders: discard a secondary and draw a new one ---


async def _new_orders_game(client, ids=None, *, modes=("tactical", "tactical"), fixed=((), ())):
    ids = ids or await _setup(client, tactical_cards=20)
    ids["new_orders"] = (
        await client.post(
            "/stratagems",
            json={
                "name": "New Orders",
                "cp": 1,
                "is_core": True,
                "timings": [{"phase": "command", "turn": "your_turn"}],
                "game_action": "replace_secondary",
            },
        )
    ).json()["id"]
    game = await _new_game(client, ids, modes=modes, fixed=fixed, first=1)
    game = (await client.post(f"/games/{game['id']}/start")).json()
    return ids, game


async def test_new_orders_replaces_the_target_secondary(client: AsyncClient):
    ids, game = await _new_orders_game(client)
    game_id = game["id"]
    target, kept = _player(game, 1)["secondaries"]
    assert "New Orders" in await _usable(client, game_id, 1)

    response = await client.post(
        f"/games/{game_id}/stratagems",
        json={"seat": 1, "stratagem_id": ids["new_orders"], "target_secondary_id": target["id"]},
    )
    assert response.status_code == 200
    player = _player(response.json(), 1)
    assert player["cp"] == 0
    cards = {c["id"]: c for c in player["secondaries"]}
    assert cards[target["id"]]["status"] == "discarded"
    assert cards[kept["id"]]["status"] == "active"
    active = [c for c in player["secondaries"] if c["status"] == "active"]
    assert len(active) == 2  # the kept card plus one newly drawn
    new = next(c for c in active if c["id"] not in (target["id"], kept["id"]))
    assert new["secondary_mission_id"] not in (
        target["secondary_mission_id"],
        kept["secondary_mission_id"],
    )
    assert [u["name"] for u in player["stratagem_uses"]] == ["New Orders"]


async def test_new_orders_needs_a_valid_target(client: AsyncClient):
    ids, game = await _new_orders_game(client)
    game_id = game["id"]
    opponent_card_ids = [c["id"] for c in _player(game, 2)["secondaries"]]

    async def use(target):
        return await client.post(
            f"/games/{game_id}/stratagems",
            json={"seat": 1, "stratagem_id": ids["new_orders"], "target_secondary_id": target},
        )

    assert (await use(None)).status_code == 400
    assert (await use(9999)).status_code == 400
    if opponent_card_ids:  # the opponent holds no cards yet on turn 1
        assert (await use(opponent_card_ids[0])).status_code == 400
    # Nothing was spent on the failed attempts.
    game = (await client.get(f"/games/{game_id}")).json()
    assert _player(game, 1)["cp"] == 1


async def test_new_orders_isnt_usable_without_a_tactical_secondary(client: AsyncClient):
    # A fixed player has no tactical cards to replace.
    ids = await _setup(client, tactical_cards=20)
    picks = ([ids["tactical"][0], ids["reactive"]], ())
    _, game = await _new_orders_game(client, ids, modes=("fixed", "tactical"), fixed=picks)
    assert "New Orders" not in await _usable(client, game["id"], 1)


async def test_other_stratagems_dont_take_a_target(client: AsyncClient):
    ids, game = await _new_orders_game(client)
    card = _player(game, 1)["secondaries"][0]
    response = await client.post(
        f"/games/{game['id']}/stratagems",
        json={"seat": 1, "stratagem_id": ids["anytime"], "target_secondary_id": card["id"]},
    )
    assert response.status_code == 400


# --- once per phase ---


async def test_a_stratagem_can_be_used_once_per_phase(client: AsyncClient):
    ids = await _setup(client)
    game = await _new_game(client, ids, first=1)
    game_id = game["id"]
    await client.post(f"/games/{game_id}/start")
    # On to player 2's command phase, where each player has 2 CP.
    game = await _advance(client, game_id, times=5)
    assert (game["turn_seat"], game["phase"]) == (2, "command")
    assert [_player(game, s)["cp"] for s in (1, 2)] == [2, 2]

    async def use(seat):
        return await client.post(
            f"/games/{game_id}/stratagems", json={"seat": seat, "stratagem_id": ids["anytime"]}
        )

    assert (await use(1)).status_code == 200
    second = await use(1)
    assert second.status_code == 400
    assert "already been used this phase" in second.json()["detail"]
    assert "Anytime" not in await _usable(client, game_id, 1)
    # The other player can still use it this phase.
    assert (await use(2)).status_code == 200

    # In the next phase it's available again.
    await _advance(client, game_id)
    assert "Anytime" in await _usable(client, game_id, 1)
    assert (await use(1)).status_code == 200
