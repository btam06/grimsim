# Local game data

Game data - units, detachments, datasheets, stratagems and mission cards -
lives here as JSON. This is the standard format for seed data: new game data
should be added as JSON files here, not as Python seed code. It's Games
Workshop's, so it's kept local rather than committed (everything in this
folder except this README is git-ignored). The backend seeds from it on startup, adding anything missing;
if a file isn't here, that data simply isn't seeded. The Docker build copies
this folder in, so a local build includes whatever is here.

Each faction's data is in `factions/<faction>/`, named after the faction's
folder in `app/seeds/factions/` (e.g. `factions/adeptus_mechanicus/`):

```
factions/
  adeptus_mechanicus/
    keywords.json
    units.json
    detachments.json
    enhancements.json
    datasheets.json
  orks/
    ...
stratagems.json
missions.json
terrain_layouts.json
```

Any of a faction's files can be left out.

## `factions/<faction>/keywords.json`

The keywords the faction's models and stratagems use. Keywords aren't owned
by a faction: each one is added if no keyword with that name exists yet, so a
keyword several factions list (e.g. `INFANTRY`) is seeded once. Every keyword
a datasheet or stratagem names must be in some faction's `keywords.json`.

```json
{"faction": "Orks", "keywords": ["BIG MEK", "CHARACTER", "INFANTRY", "VEHICLE"]}
```

## `factions/<faction>/units.json`

The faction's units (by datasheet name). Units without a full datasheet are
seeded by name only.

```json
{"faction": "Orks", "units": ["Big Mek Dakkarig", "Tankbustas"]}
```

## `factions/<faction>/detachments.json`

A detachment can have more than one disposition (it can be either). Each
disposition must be a seeded disposition name.

```json
{
  "faction": "Orks",
  "detachments": [
    {"name": "War Horde", "dp": 3, "dispositions": ["Take and Hold", "Purge the Foe"]},
    {"name": "Madcap Meks", "dp": 1, "dispositions": ["Disruption"]}
  ]
}
```

A detachment can have a `unique_tag` (e.g. `"DYNASTY"`): a list can't take two
detachments with the same tag.

A detachment can also have `rules`. In combat, a rule grants abilities to
the units of a list that has taken the detachment: those whose every model has
all the keywords of one of its `keyword_options` (a set of keywords - their
order doesn't matter; leave it out for every unit). It grants
`datasheet_abilities` (by name, e.g. `Stealth`), `weapon_abilities` (by
name, optionally only on `"ranged"` or `"melee"` weapons) and
`granted_keywords` (by name, e.g. `BATTLELINE` - these count everywhere
keywords do: other rules, stratagems, enhancements). Give a rule a
`"selection_limit"` (e.g. `3`) when it only reaches units picked for it while
building the list, up to that many per list - e.g. Houndpack Lance's three
WAR DOG units with CHARACTER. Set `"per_model": true` for a rule
that reaches models rather than units (e.g. "friendly TECH-PRIEST models
have..."): it then reaches each matching model in any unit, and on the defending
side its abilities take effect when an attack is allocated to that model - so
saves, invulnerable saves and Feel No Pain, but not hit-roll effects like
cover, which come before allocation.

```json
{
  "name": "Skitarii Hunter Cohort", "dp": 2, "dispositions": ["Reconnaissance"],
  "rules": [
    {"name": "Stealth Optimisation", "description": "...",
     "keyword_options": [["SKITARII", "INFANTRY"], ["SKITARII", "MOUNTED"],
                         ["IRONSTRIDER BALLISTARII"]],
     "datasheet_abilities": ["Stealth"]}
  ]
}
```

## `factions/<faction>/enhancements.json`

The faction's enhancements and upgrades, each naming its `detachment` (one of
the faction's detachments). An `enhancement` is carried by one CHARACTER model
(not an EPIC HERO); an `upgrade` is taken by a whole unit. `keywords` are
needed (all of them) on the model carrying an enhancement, or on every model in
a unit taking an upgrade; any one of the `excluded_keywords` rules it out. Both
are optional. Each can be taken once per army list, and only by a list that
has the detachment.

```json
{
  "faction": "Adeptus Mechanicus",
  "enhancements": [
    {"name": "Peerless Eradicator", "detachment": "Rad-Zone Corps", "kind": "enhancement",
     "points": 20, "keywords": ["ADEPTUS MECHANICUS"], "description": "...",
     "weapon_abilities": [{"name": "Sustained 1", "weapon_type": "ranged", "scope": "led_unit"}]},
    {"name": "Example Upgrade", "detachment": "Rad-Zone Corps", "kind": "upgrade",
     "points": 10, "keywords": ["SKITARII"], "excluded_keywords": ["VEHICLE"]}
  ]
}
```

What they do in combat is given as abilities they grant, by name:
`weapon_abilities` (seeded weapon abilities, optionally only on `"ranged"` or
`"melee"` weapons) and `datasheet_abilities` (seeded datasheet abilities, e.g.
`Stealth`). Each has a `scope` - who it reaches:

- `"bearer"`: the model carrying an enhancement;
- `"led_unit"`: every model in the bearer's unit, while it's leading one (it's
  a CHARACTER in a unit with non-CHARACTER models);
- `"bearers_unit"`: every model in the bearer's unit, whether or not it's
  leading one;
- `"unit"`: every model in the unit - the only scope an upgrade can use.

They can also give `granted_keywords` (`{"name": "SKITARII", "scope": ...}`),
which count wherever the calculator checks keywords (stratagem targets,
detachment rules, conditions like Anti-X), and an enhancement can give its
bearer `weapons` - full profiles, with weapon abilities by name:

```json
"weapons": [{"name": "TL-4Ø9", "weapon_type": "ranged", "range": 24, "attacks": "3",
             "skill": 2, "strength": 11, "ap": -2, "damage": "D3+2",
             "abilities": ["Devastating Wounds", "Hazardous"]}]
```

## `factions/<faction>/datasheets.json`

Each datasheet's `name` should be one of that faction's units
(`units.json`).
Abilities and keywords are referenced by name and must already exist (seeded
weapon/wargear/datasheet abilities, keywords from any faction's
`keywords.json`, and the faction's abilities).
See `app/seeds/datasheets.py` for every field and its default. `feel_no_pain_mortal` is a
Feel No Pain against mortal wounds only (e.g. `5`) - in the calculator, that's
the wounds a model takes from its own Hazardous weapons, and from attacks that
allow no save (e.g. Devastating Wounds); the better of it and the model's Feel
No Pain is used.
`base_size` must be one of the seeded base sizes (`app/seeds/base_sizes.py`,
e.g. `"32mm"`, `"105 x 70mm"`, `"Use model"`); it's filled in on an existing
model that doesn't have one yet.

```json
{
  "faction": "Adeptus Mechanicus",
  "datasheets": [
    {
      "name": "Skitarii Rangers",
      "models": [
        {
          "name": "Skitarii Ranger",
          "movement": 6, "toughness": 3, "save": 4, "wounds": 1,
          "leadership": 7, "oc": 2, "invulnerable": 5, "base_size": "28.5mm",
          "keywords": ["INFANTRY", "BATTLELINE"],
          "faction_abilities": ["Doctrina Imperatives"],
          "abilities": [],
          "weapons": [
            {
              "name": "Galvanic rifle", "weapon_type": "ranged", "range": 30,
              "attacks": "2", "skill": 4, "strength": 4, "ap": 0, "damage": "1",
              "abilities": []
            }
          ],
          "wargear": [{"name": "Omnispex", "description": "...", "abilities": ["Ignore Cover (Unit)"]}]
        }
      ]
    }
  ]
}
```

A TRANSPORT model can have a `transport`: how many models it can carry
(`capacity`), the keywords each needs (`keywords`, all of them) or can't have
(`excluded_keywords`, any of them), and the space a model with a keyword takes
up (`space` - otherwise 1). A transport without one can carry anything. It's
filled in on an existing model that doesn't have one yet.

```json
"transport": {"capacity": 7, "keywords": ["ADEPTUS ASTARTES", "INFANTRY"],
              "excluded_keywords": ["TERMINATOR", "JUMP PACK"], "space": {"GRAVIS": 2}}
```

Repeat a weapon to give a model several of it (e.g. three heavy stubbers).
Mark the weapons a model is equipped with by default (its datasheet's "This
model is equipped with: ...") with `"default": true`; they're pre-selected when
the model is added to a unit, and the flag is filled in on an existing weapon
that doesn't have it yet.

## `stratagems.json`

Core stratagems (`"core": true`, usable by any army) and detachment
stratagems (listed against one or more detachments, by faction and name).
`keywords` are required keywords (a model needs all of them; none means any
model). `timings` are when it can be used in a game (none means any time):
`phase` is `command`, `movement`, `shooting`, `charge` or `fight`, and `turn`
is `your_turn`, `opponent_turn` or `either`. `conditions`/`effects` are
condition/effect keywords that apply it in the combat calculator.

```json
{
  "stratagems": [
    {"name": "Grenade", "description": "...", "cp": 1, "core": true,
     "keywords": ["GRENADES"], "timings": [{"phase": "shooting", "turn": "your_turn"}]},
    {"name": "...", "cp": 1, "detachments": [{"faction": "Orks", "name": "War Horde"}],
     "conditions": ["always"], "effects": ["plus_one_to_hit"]}
  ]
}
```

## `missions.json`

Primary and secondary mission cards. A primary mission is matched to a pair of
dispositions by name.

```json
{
  "primaries": [
    {"name": "...", "player_disposition": "Take and Hold",
     "opponent_disposition": "Purge the Foe", "description": "..."}
  ],
  "secondaries": [
    {"name": "...", "completes_on": "your_turn | opponent_turn | either",
     "fixed_points": 4, "tactical_points": 5, "description": "..."}
  ]
}
```

`fixed_points`/`tactical_points` is `null` if the card can't be used in that
mode.

## `terrain_layouts.json`

The terrain kit, and the battlefield layouts that place it. Every layout uses
the same kit - the same baseplates (terrain areas) and ruin walls and
obstacles (terrain features) - each piece placed, turned and sometimes flipped
differently, and not always all of them. A game is given a layout for its
attacker's and defender's dispositions (picked at random if there are several).

`area_shapes` and `feature_shapes` are the kit, each with how many of it the
kit has (`count`). An area shape is a `width` x `height` rectangle centred on
where it's placed, or a convex polygon of `points` relative to it (in order
around it). A feature shape's `kind` is `ruin_wall` or `obstacle`, and it's
made of rectangular `parts` whose `x`/`y` is their top-left corner relative to
where it's placed (e.g. an L-shaped wall is two parts).

Each layout places shapes by name: at `x`, `y`, turned `rotation` degrees
clockwise about that point, and flipped first if `mirrored` (the shape's x
negated). A layout can't use more of a shape than the kit has. Everything is
in inches on the 60" x 44" board seen from above: `x` runs 0-60 left to right,
`y` 0-44 top to bottom. A portrait layout map (44" across, 60" down) is turned
a quarter anticlockwise onto it: the map's top edge becomes the board's left
edge.

Each layout lists its `objectives`. Objectives are terrain areas: each one
has a `kind` (`attacker_home`, `defender_home`, `expansion` or `centre`),
the `x`/`y` where its marker is drawn (board inches), and `areas`, the terrain
areas it is, as indexes into the layout's `areas` (usually one; a Take and Hold
layout's centre is both of its halves). An already-seeded layout without
objectives gains them on the next seed.

`deployments` are the deployment zones (e.g. Dawn of War): an `attacker_zone`
and a `defender_zone`, each a polygon of at least 3 corners in order around it
(in board inches; it can be concave). A layout names its `deployment`; an
already-seeded layout without one gains it on the next seed.

```json
{
  "area_shapes": [
    {"name": "Large ruin", "count": 4, "width": 7, "height": 11.5},
    {"name": "Centre half ruin", "count": 2,
     "points": [[-5.7, -4], [5.7, -4], [5.7, -2], [-5.7, 4]]}
  ],
  "feature_shapes": [
    {"name": "Ruin wall L (2.75 x 6.25)", "kind": "ruin_wall", "count": 2,
     "parts": [{"x": 0, "y": 0, "width": 6.25, "height": 0.5},
               {"x": 0, "y": 0, "width": 0.5, "height": 2.75}]}
  ],
  "deployments": [
    {"name": "Dawn of War",
     "attacker_zone": [[0, 44], [0, 32], [60, 32], [60, 44]],
     "defender_zone": [[60, 0], [60, 12], [0, 12], [0, 0]]}
  ],
  "layouts": [
    {
      "name": "Take & Hold Mirror 01",
      "attacker_disposition": "Take and Hold",
      "defender_disposition": "Take and Hold",
      "deployment": "Dawn of War",
      "areas": [
        {"shape": "Large ruin", "x": 11.75, "y": 26.5, "rotation": 90},
        {"shape": "Centre half ruin", "x": 28.5, "y": 22, "rotation": -90, "mirrored": true}
      ],
      "features": [
        {"shape": "Ruin wall L (2.75 x 6.25)", "x": 6.25, "y": 29.75, "rotation": -90}
      ],
      "objectives": [
        {"kind": "attacker_home", "x": 11.7, "y": 26.5, "areas": [0]},
        {"kind": "centre", "x": 30, "y": 22, "areas": [1]}
      ]
    }
  ]
}
```
