import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Disposition, PrimaryMission, SecondaryMission
from app.seeds import data_files

# Mission card data (names, disposition matchups, timings, base VP and card
# text), from app/data/missions.json - a local file, not committed (see
# app/data/README.md). If it's missing, no missions are seeded and they can be
# entered on the Data tabs instead.


def load(path: Path | None = None) -> dict:
    path = path or data_files.data_dir() / "missions.json"
    if not path.exists():
        return {"primaries": [], "secondaries": []}
    return json.loads(path.read_text(encoding="utf-8"))


async def seed(session: AsyncSession, path: Path | None = None) -> None:
    # Adds any missions not already present (secondaries by name, primaries by
    # disposition matchup); existing ones are left alone. Must run after
    # dispositions.seed, since primaries are matched to dispositions by name.
    data = load(path)

    existing_secondaries = set(
        (await session.execute(select(SecondaryMission.name))).scalars().all()
    )
    for entry in data["secondaries"]:
        if entry["name"] not in existing_secondaries:
            session.add(
                SecondaryMission(
                    name=entry["name"],
                    description=entry.get("description"),
                    completes_on=entry["completes_on"],
                    fixed_points=entry.get("fixed_points"),
                    tactical_points=entry.get("tactical_points"),
                )
            )

    dispositions = {
        d.name: d.id for d in (await session.execute(select(Disposition))).scalars().all()
    }
    existing_pairs = set(
        (
            await session.execute(
                select(PrimaryMission.player_disposition_id, PrimaryMission.opponent_disposition_id)
            )
        ).all()
    )
    for entry in data["primaries"]:
        player = dispositions.get(entry["player_disposition"])
        opponent = dispositions.get(entry["opponent_disposition"])
        if player is None or opponent is None:
            raise ValueError(
                f"primary mission {entry['name']!r} references an unknown disposition"
            )
        if (player, opponent) in existing_pairs:
            continue
        session.add(
            PrimaryMission(
                name=entry["name"],
                description=entry.get("description"),
                player_disposition_id=player,
                opponent_disposition_id=opponent,
            )
        )
        existing_pairs.add((player, opponent))

    await session.commit()
