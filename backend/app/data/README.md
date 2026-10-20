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

A detachment can also have `rules`. In combat, a rule grants abilities to
the units of a list that has taken the detachment: those whose every model has
all the keywords of one of its `keyword_options` (a set of keywords - their
order doesn't matter; leave it out for every unit). It grants
`datasheet_abilities` (by name, e.g. `Stealth`) and `weapon_abilities` (by
name, optionally only on `"ranged"` or `"melee"` weapons).

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
- `"unit"`: every model in the unit - the only scope an upgrade can use.

## `factions/<faction>/datasheets.json`

Each datasheet's `name` should be one of that faction's units
(`units.json`).
Abilities and keywords are referenced by name and must already exist (seeded
weapon/wargear/datasheet abilities, keywords from any faction's
`keywords.json`, and the faction's abilities).
See `app/seeds/datasheets.py` for every field and its default.
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

Repeat a weapon to give a model several of it (e.g. three heavy stubbers).

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
