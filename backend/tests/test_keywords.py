from httpx import AsyncClient


async def test_create_and_list_keyword(client: AsyncClient):
    response = await client.post("/keywords", json={"name": "INFANTRY"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "INFANTRY"

    response = await client.get("/keywords")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_create_keyword_with_duplicate_name_returns_400(client: AsyncClient):
    await client.post("/keywords", json={"name": "INFANTRY"})
    response = await client.post("/keywords", json={"name": "INFANTRY"})
    assert response.status_code == 400


async def test_delete_keyword(client: AsyncClient):
    keyword_id = (await client.post("/keywords", json={"name": "INFANTRY"})).json()["id"]

    response = await client.delete(f"/keywords/{keyword_id}")
    assert response.status_code == 204

    response = await client.get("/keywords")
    assert response.json() == []


async def test_delete_nonexistent_keyword_returns_404(client: AsyncClient):
    response = await client.delete("/keywords/9999")
    assert response.status_code == 404


async def test_delete_keyword_in_use_unlinks_rather_than_blocking(
    client: AsyncClient, faction_id: int
):
    keyword_id = (await client.post("/keywords", json={"name": "INFANTRY"})).json()["id"]
    model_id = (
        await client.post(
            "/models",
            json={
                "name": "Intercessor",
                "faction_id": faction_id,
                "save": 3,
                "toughness": 4,
                "oc": 2,
                "movement": 6,
                "wounds": 2,
                "leadership": 7,
                "keyword_ids": [keyword_id],
            },
        )
    ).json()["id"]

    response = await client.delete(f"/keywords/{keyword_id}")
    assert response.status_code == 204

    models = (await client.get("/models")).json()
    model = next(m for m in models if m["id"] == model_id)
    assert model["keyword_ids"] == []
