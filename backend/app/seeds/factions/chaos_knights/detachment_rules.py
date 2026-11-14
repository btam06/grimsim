# In a game: what Chaos Knights detachment rules do beyond the abilities they
# grant (see app/data/factions/chaos_knights/). The factions package combines
# every faction's.

# Detachment rules that give an army rule's round-start choice one more
# option to select ({rule name: {"ability": the army rule, "exclude": options
# it can't be}}) - Paragons of Terror: at the start of the first battle round,
# after selecting Dread abilities, one more (not rolled for). See
# app/services/in_game/battle_round.py.
EXTRA_ROUND_CHOICES = {
    "Paragons of Terror": {"ability": "Harbingers of Dread", "exclude": ("Roll two D6",)},
}

# Detachment rules that improve the Objective Control characteristic of their
# army's models with all of `keywords` by `bonus` - Tyrannical Court. See
# app/services/in_game/objectives.py.
OC_BONUSES = {
    "Tyrannical Court": {"keywords": ("CHAOS KNIGHTS", "CHARACTER"), "bonus": 2},
}

# Detachment rules that let their army use a stratagem for 0CP once per battle
# round ({rule name: {"stratagem": its name, "warlord_on_battlefield": whether
# their WARLORD must be}}) - Tyrannical Court: Claimed for the Dark Gods. See
# app/services/in_game/game.py.
FREE_STRATAGEMS = {
    "Tyrannical Court": {"stratagem": "Claimed for the Dark Gods", "warlord_on_battlefield": True},
}

# Detachment rules that let their army's units with `keywords` re-roll a
# failed Battle-shock test (re-rolling Leadership rolls: a failed one's
# always worth re-rolling) - Wretched Thralls. See
# app/services/in_game/battle_shock.py.
BATTLE_SHOCK_REROLLS = {"Wretched Thralls": {"keywords": ("DAMNED",)}}
