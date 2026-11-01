from __future__ import annotations

import contextvars
import random
import secrets
from collections.abc import Iterator, MutableSequence, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from app.engine.state import Game

T = TypeVar("T")

# Every roll in a game - dice, mission draws, terrain picks, the agent's
# random choices - comes from the game's own seeded stream, so a game can be
# replayed: the same seed and the same actions give the same rolls. Roll N of
# a game is drawn from a generator seeded with (its seed, N), so all a game
# stores is its seed (Game.rng_seed) and how many rolls it's made
# (Game.rng_rolls).
#
# The game whose dice are rolled is the one bound while it's played (see
# app/engine/context.py): the services rolling dice don't all have the game
# to hand (e.g. app/services/combat.py). With no game bound, rolls come from
# Python's own `random`. The calculator binds a throwaway generator instead
# (see using), so its previews don't use up a game's rolls.

_current: contextvars.ContextVar[Game | random.Random | None] = contextvars.ContextVar(
    "dice", default=None
)


def new_seed() -> int:
    return secrets.randbits(63)


def _rng() -> random.Random:
    bound = _current.get()
    if bound is None:
        return random._inst
    if isinstance(bound, random.Random):
        return bound
    n = bound.rng_rolls
    bound.rng_rolls = n + 1
    return random.Random((bound.rng_seed << 32) + n)


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


def bind(game: Game | None) -> None:
    # For the rest of the request (or engine call).
    _current.set(game)


@contextmanager
def bound(game: Game) -> Iterator[None]:
    token = _current.set(game)
    try:
        yield
    finally:
        _current.reset(token)


@contextmanager
def using(rng: random.Random) -> Iterator[None]:
    # Rolls in the block come from `rng`.
    token = _current.set(rng)
    try:
        yield
    finally:
        _current.reset(token)
