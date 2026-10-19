# Local game data

Datasheets and mission cards are Games Workshop's, so they're kept here as
local JSON files rather than committed (everything in this folder except this
README is git-ignored). The backend seeds from them on startup, adding anything
missing; if a file isn't here, that data simply isn't seeded. The Docker build
copies this folder in, so a local build includes whatever is here.

## `datasheets/<faction>.json`

One file per faction, named after the faction's folder in
`app/seeds/factions/` (e.g. `adeptus_mechanicus.json`). Each datasheet's
`name` should be one of that faction's unit names (`units/__init__.py`).
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
