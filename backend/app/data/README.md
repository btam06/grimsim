# Local game data

Game data - detachments, datasheets and mission cards - lives here as JSON.
This is the standard format for seed data: new game data should be added as
JSON files here, not as Python seed code. It's Games Workshop's, so it's kept
local rather than committed (everything in this folder except this README is
git-ignored). The backend seeds from it on startup, adding anything missing;
if a file isn't here, that data simply isn't seeded. The Docker build copies
this folder in, so a local build includes whatever is here.

Each faction's data is in `factions/<faction>/`, named after the faction's
folder in `app/seeds/factions/` (e.g. `factions/adeptus_mechanicus/`):

```
factions/
  adeptus_mechanicus/
    units.json
    detachments.json
    datasheets.json
  orks/
    ...
missions.json
```

Any of a faction's files can be left out.

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

## `factions/<faction>/datasheets.json`

Each datasheet's `name` should be one of that faction's units
(`units.json`).
Abilities and keywords are referenced by name and must already exist (seeded
weapon/wargear/datasheet abilities, keywords, and the faction's abilities).
See `app/seeds/datasheets.py` for every field and its default.

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
          "leadership": 7, "oc": 2, "invulnerable": 5,
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
