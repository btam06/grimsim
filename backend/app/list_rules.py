from __future__ import annotations

from dataclasses import dataclass, field

# Army-building rules that let a list include units from a faction other than
# its own. Each is defined in the info.py of the faction whose lists it applies
# to (ALLY_RULES) - e.g. Drukhari's Corsairs and Travelling Players, or an
# Imperium faction's Imperial Agents and Imperial Knights - and applied by
# app/services/list_building.py.


@dataclass(frozen=True)
class AllyRule:
    # The faction whose lists can include them.
    host_faction: str
    # The faction whose units can be included.
    ally_faction: str
    # A model from it needs one of these keywords.
    model_keywords: tuple[str, ...]
    # Most points of these units a list can include, by its points limit (no
    # entry: no cap) - e.g. Drukhari: up to 500 pts of HARLEQUINS/ANHRATHE
    # units at 2000 points.
    points_limits: dict[int, int] = field(default_factory=dict)
    # Whether models included this way can be given Enhancements.
    enhancements: bool = True


def imperial_allies(host_faction: str) -> list[AllyRule]:
    # The ally rules of an Imperium faction (Adepta Sororitas, Adeptus
    # Custodes, Adeptus Mechanicus, Adeptus Titanicus, Astra Militarum, Grey
    # Knights, Imperial Agents, Imperial Knights, Space Marines): its lists can
    # include Imperial Agents' RETINUE, CHARACTER and REQUISITIONED units, and
    # Imperial Knights' TITANIC and ARMIGER units - other than its own
    # faction's. Models included this way can't be given Enhancements.
    rules = [
        AllyRule(
            host_faction=host_faction,
            ally_faction="Imperial Agents",
            model_keywords=("RETINUE", "CHARACTER", "REQUISITIONED"),
            enhancements=False,
        ),
        AllyRule(
            host_faction=host_faction,
            ally_faction="Imperial Knights",
            model_keywords=("TITANIC", "ARMIGER"),
            enhancements=False,
        ),
    ]
    return [rule for rule in rules if rule.ally_faction != host_faction]
