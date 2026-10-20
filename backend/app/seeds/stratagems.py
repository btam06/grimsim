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
from app.models.stratagem import (
    STRATAGEM_COMBAT_SIDES,
    STRATAGEM_GAME_ACTIONS,
    STRATAGEM_TURNS,
)
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
    # has no keyword requirements, options or exclusions, timings, detachments,
    # game action or combat side yet (e.g. seeded before those existed) gets them filled in; nothing
    # else is changed.
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
        entry_excluded = [
            lookup(keywords, k, "keyword", name) for k in entry.get("excluded_keywords", [])
        ]
        entry_options = [
            [lookup(keywords, k, "keyword", name) for k in option]
            for option in entry.get("keyword_options", [])
        ]
        if any(not option for option in entry_options):
            raise ValueError(f"stratagem {name!r} has an empty keyword option")
        for timing in entry.get("timings", []):
            lookup({p: p for p in PHASES}, timing["phase"], "phase", name)
            lookup({t: t for t in STRATAGEM_TURNS}, timing["turn"], "turn", name)
        timings = [
            StratagemTiming(phase=t["phase"], turn=t["turn"]) for t in entry.get("timings", [])
        ]
        game_action = entry.get("game_action")
        if game_action is not None:
            lookup({a: a for a in STRATAGEM_GAME_ACTIONS}, game_action, "game action", name)
        combat_side = entry.get("combat_side")
        if combat_side is not None:
            lookup({s: s for s in STRATAGEM_COMBAT_SIDES}, combat_side, "combat side", name)

        stratagem = existing.get(name)
        if stratagem is None:
            stratagem = Stratagem(
                name=name,
                description=entry.get("description"),
                cp=entry["cp"],
                is_core=core,
                detachments=entry_detachments,
                keywords=entry_keywords,
                excluded_keywords=entry_excluded,
                keyword_options=entry_options,
                timings=timings,
                conditions=[
                    lookup(conditions, c, "condition", name) for c in entry.get("conditions", [])
                ],
                effects=[lookup(effects, e, "effect", name) for e in entry.get("effects", [])],
            )
            stratagem.game_action = game_action
            stratagem.combat_side = combat_side
            session.add(stratagem)
            continue
        if entry_keywords and not stratagem.keywords:
            stratagem.keywords = entry_keywords
        if entry_excluded and not stratagem.excluded_keywords:
            stratagem.excluded_keywords = entry_excluded
        if entry_options and not stratagem.keyword_option_links:
            stratagem.keyword_options = entry_options
        if timings and not stratagem.timings:
            stratagem.timings = timings
        if entry_detachments and not stratagem.detachments:
            stratagem.detachments = entry_detachments
        if game_action and not stratagem.game_action:
            stratagem.game_action = game_action
        if combat_side and not stratagem.combat_side:
            stratagem.combat_side = combat_side

    await session.commit()
