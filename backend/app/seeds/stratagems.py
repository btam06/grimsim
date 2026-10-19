import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Condition,
    Detachment,
    Effect,
    Faction,
    Keyword,
    Stratagem,
    StratagemTiming,
)
from app.models.game import PHASES
from app.models.stratagem import STRATAGEM_GAME_ACTIONS, STRATAGEM_TURNS
from app.seeds import data_files

# Stratagems, from app/data/stratagems.json - a local file, not committed (see
# app/data/README.md). If it's missing, no stratagems are seeded and they can
# be entered on the Stratagems tab instead.


def load(path: Path | None = None) -> list[dict]:
    path = path or data_files.data_dir() / "stratagems.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["stratagems"]


async def seed(session: AsyncSession, path: Path | None = None) -> None:
    # Adds any stratagems not already present (by name). An existing one that
    # has no keyword requirements, timings or detachments yet (e.g. seeded
    # before those existed) gets them filled in; nothing else is changed.
    # Everything is referenced by name - an unknown keyword, condition,
    # effect, detachment, phase or turn is an error, not skipped - so this
    # must run after keywords, conditions, effects and detachments are seeded.
    entries = load(path)
    if not entries:
        return

    keywords = {k.name: k for k in (await session.execute(select(Keyword))).scalars()}
    conditions = {c.keyword: c for c in (await session.execute(select(Condition))).scalars()}
    effects = {e.keyword: e for e in (await session.execute(select(Effect))).scalars()}
    detachments = {
        (faction_name, d.name): d
        for d, faction_name in (
            await session.execute(
                select(Detachment, Faction.name).join(Faction, Detachment.faction_id == Faction.id)
            )
        ).all()
    }
    existing = {
        s.name: s
        for s in (
            await session.execute(
                select(Stratagem).options(
                    selectinload(Stratagem.keywords),
                    selectinload(Stratagem.timings),
                    selectinload(Stratagem.detachments),
                    selectinload(Stratagem.game_action_link),
                )
            )
        ).scalars()
    }

    def lookup(table: dict, key, kind: str, stratagem: str):
        if key not in table:
            raise ValueError(f"stratagem {stratagem!r} references unknown {kind} {key!r}")
        return table[key]

    for entry in entries:
        name = entry["name"]
        core = entry.get("core", False)
        entry_detachments = [
            lookup(detachments, (d["faction"], d["name"]), "detachment", name)
            for d in entry.get("detachments", [])
        ]
        if core == bool(entry_detachments):
            raise ValueError(
                f"stratagem {name!r} must be core or belong to a detachment, not both or neither"
            )
        entry_keywords = [lookup(keywords, k, "keyword", name) for k in entry.get("keywords", [])]
        for timing in entry.get("timings", []):
            lookup({p: p for p in PHASES}, timing["phase"], "phase", name)
            lookup({t: t for t in STRATAGEM_TURNS}, timing["turn"], "turn", name)
        timings = [
            StratagemTiming(phase=t["phase"], turn=t["turn"]) for t in entry.get("timings", [])
        ]
        game_action = entry.get("game_action")
        if game_action is not None:
            lookup({a: a for a in STRATAGEM_GAME_ACTIONS}, game_action, "game action", name)

        stratagem = existing.get(name)
        if stratagem is None:
            stratagem = Stratagem(
                name=name,
                description=entry.get("description"),
                cp=entry["cp"],
                is_core=core,
                detachments=entry_detachments,
                keywords=entry_keywords,
                timings=timings,
                conditions=[
                    lookup(conditions, c, "condition", name) for c in entry.get("conditions", [])
                ],
                effects=[lookup(effects, e, "effect", name) for e in entry.get("effects", [])],
            )
            stratagem.game_action = game_action
            session.add(stratagem)
            continue
        if entry_keywords and not stratagem.keywords:
            stratagem.keywords = entry_keywords
        if timings and not stratagem.timings:
            stratagem.timings = timings
        if entry_detachments and not stratagem.detachments:
            stratagem.detachments = entry_detachments
        if game_action and not stratagem.game_action:
            stratagem.game_action = game_action

    await session.commit()
