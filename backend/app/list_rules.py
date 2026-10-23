from __future__ import annotations

from dataclasses import dataclass, field

# Army-building rules that let a list include units from a faction other than
# its own. Each is defined in the info.py of the faction whose lists it applies
# to (ALLY_RULES) - e.g. Drukhari's Corsairs and Travelling Players, or an
# Imperium faction's Imperial Agents and Imperial Knights - and applied by
# app/services/list_building/allies.py.


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
    # Most models a list can include this way (None: no cap) - e.g.
    # Dreadblades: 1 TITANIC CHAOS KNIGHTS model.
    model_limit: int | None = None
    # Rules sharing a group are alternatives: a list can include models under
    # only one of them (e.g. Dreadblades: either 1 TITANIC model or up to 3
    # WAR DOG models).
    choice_group: str | None = None
    # Only for a list that has taken this detachment (None: any list) - e.g.
    # Iconoclast Fiefdom's DAMNED units.
    detachment: str | None = None


def imperial_allies(host_faction: str) -> list[AllyRule]:
    # The ally rules of an Imperium faction (Adepta Sororitas, Adeptus
    # Custodes, Adeptus Mechanicus, Adeptus Titanicus, Astra Militarum, Grey
    # Knights, Imperial Agents, Imperial Knights, Space Marines): its lists can
    # include Imperial Agents' RETINUE, CHARACTER and REQUISITIONED units, and
    # Imperial Knights' Freeblades - either 1 TITANIC model or up to 3 ARMIGER
    # models (as Chaos Knights' Dreadblades, below) - other than its own
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
            model_keywords=("TITANIC",),
            enhancements=False,
            model_limit=1,
            choice_group="Freeblades",
        ),
        AllyRule(
            host_faction=host_faction,
            ally_faction="Imperial Knights",
            model_keywords=("ARMIGER",),
            enhancements=False,
            model_limit=3,
            choice_group="Freeblades",
        ),
    ]
    return [rule for rule in rules if rule.ally_faction != host_faction]


def chaos_allies(host_faction: str) -> list[AllyRule]:
    # The Chaos Knights' Dreadblades rule, for a Chaos faction's lists (Chaos
    # Daemons, Chaos Space Marines, Death Guard, Emperor's Children, Thousand
    # Sons, World Eaters): either 1 TITANIC CHAOS KNIGHTS model or up to 3 WAR
    # DOG models, which can't be given Enhancements. (It also needs every model
    # in the army to be CHAOS, which every model of these factions is.)
    return [
        AllyRule(
            host_faction=host_faction,
            ally_faction="Chaos Knights",
            model_keywords=("TITANIC",),
            enhancements=False,
            model_limit=1,
            choice_group="Dreadblades",
        ),
        AllyRule(
            host_faction=host_faction,
            ally_faction="Chaos Knights",
            model_keywords=("WAR DOG",),
            enhancements=False,
            model_limit=3,
            choice_group="Dreadblades",
        ),
    ]
