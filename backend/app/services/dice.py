from __future__ import annotations

import contextvars
import random
import secrets
from collections.abc import Iterator, MutableSequence, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import event

if TYPE_CHECKING:
    from app.models import Game

T = TypeVar("T")

# Every roll in a game - dice, mission draws, terrain picks, the agent's
# random choices - comes from the game's own seeded stream, so a game can be
# replayed: the same seed and the same actions give the same rolls. Roll N of
# a game is drawn from a generator seeded with (its seed, N), so all a game
# stores is its seed (Game.rng_seed) and how many rolls it's made
# (Game.rng_rolls).
#
# Which game's stream is used is whichever game was last loaded (or made) in
# the request: the services rolling dice don't all have the game to hand (e.g.
# app/services/combat.py), so it's bound when the Game row is loaded (see
# _bind below). With no game bound, rolls come from Python's own `random`.
# The calculator binds a throwaway generator instead (see using), so its
# previews don't use up a game's rolls.

_current: contextvars.ContextVar[_Stream | random.Random | None] = contextvars.ContextVar(
    "dice", default=None
)


def new_seed() -> int:
    # Fits a PostgreSQL BIGINT.
    return secrets.randbits(63)


class _Stream:
    # A game's dice: its seed and how many rolls it's made, kept here and
    # written to the Game as each roll's made - not read from it then, since
    # the Game may have been expired (by a rollback) and sync code can't
    # reload it.
    def __init__(self, game: Game) -> None:
        self.game = game
        self.seed: int | None = None
        self.rolls = 0

    def read(self) -> None:
        # From the Game's row, once it's been loaded (or reloaded).
        self.seed, self.rolls = self.game.rng_seed, self.game.rng_rolls or 0

    def next(self) -> random.Random:
        if self.seed is None:
            # A new game: its seed's set when it's made (if not, one now).
            self.seed = self.game.rng_seed
            if self.seed is None:
                self.seed = self.game.rng_seed = new_seed()
        n = self.rolls
        self.rolls = self.game.rng_rolls = n + 1
        return random.Random((self.seed << 32) + n)


def _rng() -> random.Random:
    bound = _current.get()
    if bound is None:
        return random._inst
    if isinstance(bound, random.Random):
        return bound
    return bound.next()


def randint(a: int, b: int) -> int:
    return _rng().randint(a, b)


def d6() -> int:
    return randint(1, 6)


def randrange(stop: int) -> int:
    return _rng().randrange(stop)


def choice(seq: Sequence[T]) -> T:
    return _rng().choice(seq)


def shuffle(seq: MutableSequence) -> None:
    _rng().shuffle(seq)


def chance() -> float:
    # A float in [0, 1), as random.random().
    return _rng().random()


def reset() -> None:
    # Unbinds whatever's bound (at the start of each request).
    _current.set(None)


@contextmanager
def using(rng: random.Random) -> Iterator[None]:
    # Rolls in the block come from `rng`, even if a game's loaded in it.
    token = _current.set(rng)
    try:
        yield
    finally:
        _current.reset(token)


def listen(game_class: type) -> None:
    # Binds each Game as it's loaded, refreshed or made (see above).
    def _stream(target) -> _Stream:
        stream = target.__dict__.get("_dice")
        if stream is None:
            stream = target._dice = _Stream(target)
        return stream

    def _bind(stream: _Stream) -> None:
        if not isinstance(_current.get(), random.Random):
            _current.set(stream)

    def _loaded(target, *_args) -> None:
        stream = _stream(target)
        if {"rng_seed", "rng_rolls"} <= target.__dict__.keys():
            stream.read()
        _bind(stream)

    def _made(target, *_args) -> None:
        _bind(_stream(target))

    event.listen(game_class, "load", _loaded)
    event.listen(game_class, "refresh", _loaded)
    event.listen(game_class, "init", _made)
