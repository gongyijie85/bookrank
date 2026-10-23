import time
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any


@dataclass
class _Flight:
    done: Event = field(default_factory=Event)
    value: Any = None
    error: BaseException | None = None


class DetailCache:
    """Bounded memory cache with per-key load sharing; zero TTL disables storage."""

    def __init__(self, ttl: float = 300, max_size: int = 512):
        self._ttl = ttl
        self._max_size = max_size
        self._values: OrderedDict[tuple[Any, ...], tuple[float, Any]] = OrderedDict()
        self._flights: dict[tuple[Any, ...], _Flight] = {}
        self._lock = Lock()

    def get_or_load(self, key: tuple[Any, ...], loader: Callable[[], Any]) -> Any:
        with self._lock:
            entry = self._values.get(key)
            if entry is not None:
                if entry[0] > time.monotonic():
                    self._values.move_to_end(key)
                    return deepcopy(entry[1])
                del self._values[key]

            flight = self._flights.get(key)
            owner = flight is None
            if flight is None:
                flight = _Flight()
                self._flights[key] = flight

        if not owner:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            return deepcopy(flight.value)

        try:
            flight.value = deepcopy(loader())
            with self._lock:
                if self._ttl > 0 and flight.value is not None and self._flights.get(key) is flight:
                    self._values[key] = (time.monotonic() + self._ttl, flight.value)
                    self._values.move_to_end(key)
                    while len(self._values) > self._max_size:
                        self._values.popitem(last=False)
        except BaseException as error:
            flight.error = error
            raise
        finally:
            with self._lock:
                if self._flights.get(key) is flight:
                    del self._flights[key]
                flight.done.set()

        return deepcopy(flight.value)

    def invalidate(self, predicate: Callable[[tuple[Any, ...]], bool]) -> None:
        """Detach matching loads so they cannot overwrite freshly loaded data."""
        with self._lock:
            for key in self._values.keys() | self._flights.keys():
                if predicate(key):
                    self._values.pop(key, None)
                    self._flights.pop(key, None)

    def invalidate_value(
        self,
        key: tuple[Any, ...],
        expected_value: Any,
        should_invalidate: Callable[[], bool] | None = None,
    ) -> bool:
        """Expire an observed value without detaching a newer recovery load.

        The optional condition runs under the cache lock and must not call cache methods.
        """
        with self._lock:
            entry = self._values.get(key)
            if entry is None or entry[1] != expected_value:
                return False
            if should_invalidate is not None and not should_invalidate():
                return False
            self._values.pop(key, None)
            self._flights.pop(key, None)
            return True

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
            self._flights.clear()
