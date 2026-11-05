import json

from app.config import settings
from app.routers import ml


def _side(seed, seat, side, list_id, vp, **extra):
    return {
        "seed": seed, "save": "saves/1/setup.json", "end": "terminated", "seat": seat,
        "side": side, "list_id": list_id, "vp": vp, "policy": "p.pt", "opponent": "scripted",
        "charges": 4, "charges_made": 1, "stratagem_uses": [], **extra,
    }


ROWS = [
    _side(1, 1, "policy", 7, 60, stratagem_uses=[
        {"name": "Command Re-roll", "phase": "movement", "round": 1, "cp": 1, "own_turn": True},
        {"name": "Fire Overwatch", "phase": "movement", "round": 1, "cp": 1, "own_turn": False},
    ]),
    _side(1, 2, "opponent", 8, 50),
    _side(2, 2, "policy", 8, 40),
    _side(2, 1, "opponent", 7, 40, stratagem_uses=[
        {"name": "Fire Overwatch", "phase": "movement", "round": 2, "cp": 1, "own_turn": False},
    ]),
    {"seed": 3, "save": "saves/1/setup.json", "end": "truncated"},
]


def test_summarize_wins_draws_and_lists():
    out = ml.summarize(ROWS, {7: "Red", 8: "Blue"})
    assert out["games"] == 2
    assert out["unfinished"] == 1
    rows = {(r["list"], r["side"]): r for r in out["by_list"]}
    # A win and a draw: 75%, over all lists.
    assert rows[("All lists", "policy")]["win"] == 0.75
    assert rows[("Red", "policy")]["win"] == 1
    assert rows[("Blue", "policy")]["win"] == 0.5
    assert rows[("All lists", "policy")]["margin"] == 5
    assert rows[("All lists", "policy")]["charge_rate"] == 0.25
    lo, hi = rows[("All lists", "policy")]["win_lo"], rows[("All lists", "policy")]["win_hi"]
    assert lo < 0.75 < hi


def test_summarize_stratagems_per_game():
    out = ml.summarize(ROWS, {})
    by_name = {s["name"]: s["values"] for s in out["stratagems"]}
    assert by_name["Fire Overwatch"] == [0.5, 0.5]
    assert by_name["Command Re-roll"] == [0.5, 0]
    times = {s["name"]: s["values"] for s in out["stratagem_times"]}
    assert times["Movement, own turn"] == [0.5, 0]


async def test_diagnose_endpoints(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ml_data_dir", str(tmp_path))
    (tmp_path / "diagnose-x.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    (tmp_path / "other.jsonl").write_text("")

    listed = (await client.get("/ml/diagnoses")).json()
    assert [d["name"] for d in listed] == ["diagnose-x.jsonl"]
    assert listed[0]["policy"] == "p.pt"

    response = await client.get("/ml/diagnoses/diagnose-x.jsonl")
    assert response.status_code == 200
    assert response.json()["games"] == 2

    assert (await client.get("/ml/diagnoses/other.jsonl")).status_code == 404
    assert (await client.get("/ml/diagnoses/..%2Fsecret.jsonl")).status_code == 404
