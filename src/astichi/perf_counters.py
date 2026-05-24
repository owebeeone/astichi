"""Opt-in counters for Astichi performance validation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class AstichiPerfCounters:
    """Collect call counts and timings for selected Astichi hot paths."""

    counts: Counter[str] = field(default_factory=Counter)
    seconds: Counter[str] = field(default_factory=Counter)
    max_seconds: dict[str, float] = field(default_factory=dict)

    def increment(self, key: str, amount: int = 1) -> None:
        """Increment one named counter."""
        self.counts[key] += amount

    @contextmanager
    def measure(self, key: str) -> Iterator[None]:
        """Measure a named call."""
        self.increment(key)
        start = perf_counter()
        try:
            yield
        finally:
            elapsed = perf_counter() - start
            self.seconds[key] += elapsed
            self.max_seconds[key] = max(self.max_seconds.get(key, 0.0), elapsed)

    def snapshot(self) -> dict[str, dict[str, int | float]]:
        """Return a deterministic JSON-friendly snapshot."""
        return {
            "counts": dict(sorted(self.counts.items())),
            "seconds": dict(sorted(self.seconds.items())),
            "max_seconds": dict(sorted(self.max_seconds.items())),
        }


_ACTIVE_COUNTERS: ContextVar[AstichiPerfCounters | None] = ContextVar(
    "astichi_perf_counters",
    default=None,
)


def active_perf_counters() -> AstichiPerfCounters | None:
    """Return the active counter set for this context, if any."""
    return _ACTIVE_COUNTERS.get()


@contextmanager
def collect_perf_counters() -> Iterator[AstichiPerfCounters]:
    """Collect Astichi counters inside the current context."""
    counters = AstichiPerfCounters()
    token = _ACTIVE_COUNTERS.set(counters)
    try:
        yield counters
    finally:
        _ACTIVE_COUNTERS.reset(token)


def counted_perf_call(
    key: str,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorate a hot-path function with an opt-in counter."""

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            counters = active_perf_counters()
            if counters is None:
                return func(*args, **kwargs)
            with counters.measure(key):
                return func(*args, **kwargs)

        return wrapper

    return decorator
