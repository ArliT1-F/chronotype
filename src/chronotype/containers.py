"""
Temporal container types.

Mutation methods (``append``, ``remove``, ``set_item``, ...) record a new
snapshot at ``timestamp`` (default: now). The new snapshot is computed from
the snapshot *in effect at that timestamp* (``at(timestamp)``, or an empty
container if there is none), not from the latest snapshot.

**Backfilling.** When snapshots exist *after* ``timestamp``, the change is
also applied to them, so history stays consistent with the change having
happened at ``timestamp``:

* List additions (``append``, ``extend``, ``insert``) are applied to every
  later snapshot (``insert`` uses the same index).
* List removals (``remove``, ``pop``, ``clear_list``) remove the same
  element(s) from later snapshots. Propagation of an element stops at the
  first later snapshot that no longer contains it: a later entry already
  removed it, and everything after derives from that entry.
* Dict and set changes (``set_item``, ``update_dict``, ``delete_item``,
  ``pop_item``, ``clear_dict``; ``add``, ``update``, ``discard``, ``remove``,
  ``clear_set``) propagate key by key (element by element) while the later
  snapshot still has that key's previous state (same value / still absent /
  still present). The first later snapshot with a different state wins and
  stops propagation for that key: a later change takes precedence.

Validation happens against the snapshot at ``timestamp``: e.g. ``remove(x, ts)``
raises ``ValueError`` if ``x`` is not in the list at ``ts`` even if it is in a
later snapshot. ``set()`` / ``t[ts] = ...`` record a full snapshot and never
modify other entries.
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Callable, TypeVar

from chronotype.base import Temporal
from chronotype.exceptions import EmptyTemporalError
from chronotype.interpolation import StepInterpolation
from chronotype.utils import TimestampType, normalize_timestamp, now

K = TypeVar("K")
V = TypeVar("V")
T = TypeVar("T")
C = TypeVar("C")

_MISSING: Any = object()


class _TemporalContainer(Temporal[C]):
    """Shared helpers for container temporals (see module docs for backfill rules)."""

    @staticmethod
    def _mutation_time(timestamp: TimestampType | None) -> datetime:
        return normalize_timestamp(timestamp) if timestamp is not None else now()

    def _rebase_later(self, ts: datetime, transform: Callable[[C], bool]) -> None:
        """
        Apply ``transform`` to a copy of every snapshot strictly after ``ts``.

        ``transform`` mutates the copy in place and returns whether propagation
        should continue to the next snapshot.
        """
        for i in range(self._find_index(ts), len(self._timeline)):
            entry_ts, snapshot = self._timeline[i]
            updated = self._copy_value(snapshot)
            keep_going = transform(updated)
            self._timeline[i] = (entry_ts, updated)
            if not keep_going:
                break


class TemporalList(_TemporalContainer[list[T]]):
    """
    Temporal list that tracks history of list changes.

    Snapshots are stored as copies and returned as copies. Mutations with a
    past timestamp are applied to later snapshots too; see the module
    documentation of :mod:`chronotype.containers` for the exact rules.
    """

    def __init__(
        self,
        initial: list[T] | None = None,
        initial_time: TimestampType | None = None,
        *,
        serializer: Callable[[list[T]], dict[str, Any]] | None = None,
        deserializer: Callable[[dict[str, Any]], list[T]] | None = None,
    ) -> None:
        """
        Args:
            initial: Optional initial contents (copied)
            initial_time: Timestamp for the initial contents (defaults to now)
            serializer: Optional callable used by to_dict()/to_json() for
                contents that are not JSON-native
            deserializer: Inverse of ``serializer``
        """
        super().__init__(
            list(initial) if initial is not None else None,
            initial_time,
            StepInterpolation(),
            serializer,
            deserializer,
        )

    def set(self, timestamp: TimestampType, value: list[T]) -> None:
        """Set list at timestamp, storing a copy."""
        super().set(timestamp, list(value))

    def at(self, timestamp: TimestampType) -> list[T] | None:
        """Get list at timestamp, returning a copy."""
        value = super().at(timestamp)
        return list(value) if value is not None else None

    def current(self) -> list[T]:
        """Get the most recent list value, returning a copy."""
        return list(super().current())

    def _snapshot(self, ts: datetime) -> list[T]:
        snapshot = self.at(ts)
        return snapshot if snapshot is not None else []

    def append(self, value: T, timestamp: TimestampType | None = None) -> None:
        """Append value to the list in effect at ``timestamp`` (and to later snapshots)."""
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        snapshot.append(value)
        self.set(ts, snapshot)

        def later(lst: list[T]) -> bool:
            lst.append(value)
            return True

        self._rebase_later(ts, later)

    def extend(self, values: list[T], timestamp: TimestampType | None = None) -> None:
        """Extend the list in effect at ``timestamp`` (and later snapshots) with values."""
        ts = self._mutation_time(timestamp)
        added = list(values)
        snapshot = self._snapshot(ts)
        snapshot.extend(added)
        self.set(ts, snapshot)

        def later(lst: list[T]) -> bool:
            lst.extend(added)
            return True

        self._rebase_later(ts, later)

    def insert(self, index: int, value: T, timestamp: TimestampType | None = None) -> None:
        """Insert value at index in the list at ``timestamp`` (and in later snapshots)."""
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        snapshot.insert(index, value)
        self.set(ts, snapshot)

        def later(lst: list[T]) -> bool:
            lst.insert(index, value)
            return True

        self._rebase_later(ts, later)

    def remove(self, value: T, timestamp: TimestampType | None = None) -> None:
        """
        Remove the first occurrence of value from the list at ``timestamp``.

        Raises ValueError if it is not in the list at ``timestamp``. Later
        snapshots lose the same value while they still contain it.
        """
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        snapshot.remove(value)
        self.set(ts, snapshot)

        def later(lst: list[T]) -> bool:
            if value not in lst:
                return False
            lst.remove(value)
            return True

        self._rebase_later(ts, later)

    def pop(self, index: int = -1, timestamp: TimestampType | None = None) -> T:
        """
        Remove and return the item at index in the list at ``timestamp``.

        Raises IndexError if the list at ``timestamp`` is empty or the index is
        out of range. Later snapshots lose the same element (at the same position
        if it is still there, otherwise its first occurrence) while they still
        contain it.
        """
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        position = index if index >= 0 else len(snapshot) + index
        value = snapshot.pop(index)
        self.set(ts, snapshot)

        def later(lst: list[T]) -> bool:
            if position < len(lst) and lst[position] == value:
                del lst[position]
            elif value in lst:
                lst.remove(value)
            else:
                return False
            return True

        self._rebase_later(ts, later)
        return value

    def clear_list(self, timestamp: TimestampType | None = None) -> None:
        """
        Empty the list at ``timestamp`` (the history is kept).

        Later snapshots lose the elements that were in the list at ``timestamp``;
        elements added after ``timestamp`` are kept.
        """
        ts = self._mutation_time(timestamp)
        pending = self._snapshot(ts)
        self.set(ts, [])

        def later(lst: list[T]) -> bool:
            nonlocal pending
            still_present = []
            for item in pending:
                if item in lst:
                    lst.remove(item)
                    still_present.append(item)
            pending = still_present
            return bool(pending)

        if pending:
            self._rebase_later(ts, later)

    def current_len(self) -> int:
        """Get length of current list."""
        if not self._timeline:
            raise EmptyTemporalError()
        return len(self.current())

    def len_at(self, timestamp: TimestampType) -> int | None:
        """Get length of list at timestamp."""
        value = self.at(timestamp)
        return len(value) if value is not None else None

    def contains_at(self, timestamp: TimestampType, value: T) -> bool:
        """Check if value is in list at timestamp."""
        lst = self.at(timestamp)
        return value in lst if lst is not None else False

    def get_item_at(self, timestamp: TimestampType, index: int) -> T | None:
        """Get item at index from list at timestamp."""
        lst = self.at(timestamp)
        if lst is not None and -len(lst) <= index < len(lst):
            return lst[index]
        return None

    def _copy_value(self, value: list[T]) -> list[T]:
        return list(value)


class TemporalDict(_TemporalContainer[dict[K, V]]):
    """
    Temporal dictionary that tracks history of dict changes.

    Snapshots are stored as copies and returned as copies. Mutations with a
    past timestamp are applied to later snapshots key by key; see the module
    documentation of :mod:`chronotype.containers` for the exact rules.
    """

    def __init__(
        self,
        initial: dict[K, V] | None = None,
        initial_time: TimestampType | None = None,
        *,
        serializer: Callable[[dict[K, V]], dict[str, Any]] | None = None,
        deserializer: Callable[[dict[str, Any]], dict[K, V]] | None = None,
    ) -> None:
        """
        Args:
            initial: Optional initial contents (copied)
            initial_time: Timestamp for the initial contents (defaults to now)
            serializer: Optional callable used by to_dict()/to_json() for
                contents that are not JSON-native
            deserializer: Inverse of ``serializer``
        """
        super().__init__(
            dict(initial) if initial is not None else None,
            initial_time,
            StepInterpolation(),
            serializer,
            deserializer,
        )

    def set(self, timestamp: TimestampType, value: dict[K, V]) -> None:
        """Set dict at timestamp, storing a copy."""
        super().set(timestamp, dict(value))

    def at(self, timestamp: TimestampType) -> dict[K, V] | None:
        """Get dict at timestamp, returning a copy."""
        value = super().at(timestamp)
        return dict(value) if value is not None else None

    def current(self) -> dict[K, V]:
        """Get the most recent dict value, returning a copy."""
        return dict(super().current())

    def _snapshot(self, ts: datetime) -> dict[K, V]:
        snapshot = self.at(ts)
        return snapshot if snapshot is not None else {}

    def _apply_changes(
        self, ts: datetime, snapshot: dict[K, V], changes: dict[K, tuple[Any, Any]]
    ) -> None:
        """
        Record ``snapshot`` at ``ts`` and propagate per-key ``(old, new)`` changes.

        ``_MISSING`` as old/new means "key absent". A key keeps propagating while
        a later snapshot still has its ``old`` state.
        """
        self.set(ts, snapshot)
        active = dict(changes)

        def same(current: Any, expected: Any) -> bool:
            if current is _MISSING or expected is _MISSING:
                return current is expected
            return bool(current == expected)

        def later(dct: dict[K, V]) -> bool:
            for key, (old, new) in list(active.items()):
                if not same(dct.get(key, _MISSING), old):
                    del active[key]  # changed later: the later entry wins
                elif new is _MISSING:
                    dct.pop(key, None)
                else:
                    dct[key] = new
            return bool(active)

        if active:
            self._rebase_later(ts, later)

    def set_item(self, key: K, value: V, timestamp: TimestampType | None = None) -> None:
        """Set ``key`` to ``value`` in the dict at ``timestamp`` (and in later snapshots)."""
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        old = snapshot.get(key, _MISSING)
        snapshot[key] = value
        self._apply_changes(ts, snapshot, {key: (old, value)})

    def delete_item(self, key: K, timestamp: TimestampType | None = None) -> None:
        """Delete ``key`` from the dict at ``timestamp``; KeyError if it is absent there."""
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        old = snapshot.pop(key)
        self._apply_changes(ts, snapshot, {key: (old, _MISSING)})

    def update_dict(self, other: dict[K, V], timestamp: TimestampType | None = None) -> None:
        """Update the dict at ``timestamp`` with ``other`` (propagated per key)."""
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        changes = {key: (snapshot.get(key, _MISSING), value) for key, value in other.items()}
        snapshot.update(other)
        self._apply_changes(ts, snapshot, changes)

    def pop_item(
        self, key: K, timestamp: TimestampType | None = None, default: V | None = None
    ) -> V | None:
        """
        Remove ``key`` from the dict at ``timestamp`` and return its value.

        Returns ``default`` if the key is absent there (no entry is recorded when
        no dict is in effect at ``timestamp``).
        """
        ts = self._mutation_time(timestamp)
        snapshot = self.at(ts)
        if snapshot is None:
            return default
        if key not in snapshot:
            self.set(ts, snapshot)
            return default
        value = snapshot.pop(key)
        self._apply_changes(ts, snapshot, {key: (value, _MISSING)})
        return value

    def clear_dict(self, timestamp: TimestampType | None = None) -> None:
        """
        Empty the dict at ``timestamp`` (the history is kept).

        Later snapshots lose the keys present at ``timestamp`` unless a later
        entry changed them.
        """
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        changes = {key: (value, _MISSING) for key, value in snapshot.items()}
        self._apply_changes(ts, {}, changes)

    def get_item_at(self, timestamp: TimestampType, key: K) -> V | None:
        """Get value for key from dict at timestamp."""
        dct = self.at(timestamp)
        return dct.get(key) if dct is not None else None

    def contains_key_at(self, timestamp: TimestampType, key: K) -> bool:
        """Check if key exists in dict at timestamp."""
        dct = self.at(timestamp)
        return key in dct if dct is not None else False

    def keys_at(self, timestamp: TimestampType) -> list[K] | None:
        """Get keys of dict at timestamp."""
        dct = self.at(timestamp)
        return list(dct.keys()) if dct is not None else None

    def values_at(self, timestamp: TimestampType) -> list[V] | None:
        """Get values of dict at timestamp."""
        dct = self.at(timestamp)
        return list(dct.values()) if dct is not None else None

    def items_at(self, timestamp: TimestampType) -> list[tuple[K, V]] | None:
        """Get items of dict at timestamp."""
        dct = self.at(timestamp)
        return list(dct.items()) if dct is not None else None

    def len_at(self, timestamp: TimestampType) -> int | None:
        """Get length of dict at timestamp."""
        dct = self.at(timestamp)
        return len(dct) if dct is not None else None

    def key_history(self, key: K) -> list[tuple[datetime, V | None]]:
        """Get history of a specific key's values."""
        history = []
        prev_value: V | None = None
        key_existed = False

        for ts, dct in self._timeline:
            current_value = dct.get(key)
            currently_exists = key in dct

            if currently_exists != key_existed or current_value != prev_value:
                history.append((ts, current_value if currently_exists else None))
                prev_value = current_value
                key_existed = currently_exists

        return history

    def _copy_value(self, value: dict[K, V]) -> dict[K, V]:
        return dict(value)


class TemporalSet(_TemporalContainer[set[T]]):
    """
    Temporal set that tracks history of set changes.

    Snapshots are stored as copies and returned as copies. Mutations with a
    past timestamp are applied to later snapshots element by element; see the
    module documentation of :mod:`chronotype.containers` for the exact rules.
    Without a serializer, snapshots are written to JSON as sorted lists (or in
    iteration order if the elements are not orderable).
    """

    def __init__(
        self,
        initial: Iterable[T] | None = None,
        initial_time: TimestampType | None = None,
        *,
        serializer: Callable[[builtins.set[T]], dict[str, Any]] | None = None,
        deserializer: Callable[[dict[str, Any]], builtins.set[T]] | None = None,
    ) -> None:
        """
        Args:
            initial: Optional initial elements (copied into a new set)
            initial_time: Timestamp for the initial contents (defaults to now)
            serializer: Optional callable used by to_dict()/to_json() for
                contents that are not JSON-native
            deserializer: Inverse of ``serializer``
        """
        super().__init__(
            set(initial) if initial is not None else None,
            initial_time,
            StepInterpolation(),
            serializer,
            deserializer,
        )

    def set(self, timestamp: TimestampType, value: Iterable[T]) -> None:
        """Set the set at timestamp, storing a copy."""
        super().set(timestamp, set(value))

    def at(self, timestamp: TimestampType) -> builtins.set[T] | None:
        """Get the set at timestamp, returning a copy."""
        value = super().at(timestamp)
        return set(value) if value is not None else None

    def current(self) -> builtins.set[T]:
        """Get the most recent set value, returning a copy."""
        return set(super().current())

    def _snapshot(self, ts: datetime) -> builtins.set[T]:
        snapshot = self.at(ts)
        return snapshot if snapshot is not None else set()

    def _apply_changes(
        self, ts: datetime, snapshot: builtins.set[T], changes: dict[T, tuple[bool, bool]]
    ) -> None:
        """Record ``snapshot`` at ``ts`` and propagate ``element: (was_in, is_in)`` changes."""
        self.set(ts, snapshot)
        active = {item: change for item, change in changes.items() if change[0] != change[1]}

        def later(current: builtins.set[T]) -> bool:
            for item, (was_in, is_in) in list(active.items()):
                if (item in current) != was_in:
                    del active[item]  # changed later: the later entry wins
                elif is_in:
                    current.add(item)
                else:
                    current.discard(item)
            return bool(active)

        if active:
            self._rebase_later(ts, later)

    def add(self, value: T, timestamp: TimestampType | None = None) -> None:
        """Add value to the set at ``timestamp`` (and to later snapshots)."""
        self.update([value], timestamp)

    def update(self, values: Iterable[T], timestamp: TimestampType | None = None) -> None:
        """Add all values to the set at ``timestamp`` (and to later snapshots)."""
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        changes = {item: (item in snapshot, True) for item in values}
        snapshot.update(changes)
        self._apply_changes(ts, snapshot, changes)

    def discard(self, value: T, timestamp: TimestampType | None = None) -> None:
        """Remove value from the set at ``timestamp`` if present (and from later snapshots)."""
        ts = self._mutation_time(timestamp)
        snapshot = self._snapshot(ts)
        was_in = value in snapshot
        snapshot.discard(value)
        self._apply_changes(ts, snapshot, {value: (was_in, False)})

    def remove(self, value: T, timestamp: TimestampType | None = None) -> None:
        """Like :meth:`discard`, but raise KeyError if value is not in the set at ``timestamp``."""
        ts = self._mutation_time(timestamp)
        if value not in self._snapshot(ts):
            raise KeyError(value)
        self.discard(value, ts)

    def clear_set(self, timestamp: TimestampType | None = None) -> None:
        """
        Empty the set at ``timestamp`` (the history is kept).

        Later snapshots lose the elements present at ``timestamp`` unless a later
        entry changed them.
        """
        ts = self._mutation_time(timestamp)
        changes = dict.fromkeys(self._snapshot(ts), (True, False))
        self._apply_changes(ts, set(), changes)

    def contains_at(self, timestamp: TimestampType, value: T) -> bool:
        """Check if value is in the set at timestamp."""
        current = self.at(timestamp)
        return value in current if current is not None else False

    def len_at(self, timestamp: TimestampType) -> int | None:
        """Get size of the set at timestamp."""
        current = self.at(timestamp)
        return len(current) if current is not None else None

    def _copy_value(self, value: builtins.set[T]) -> builtins.set[T]:
        return set(value)

    def _to_json_value(self, value: builtins.set[T]) -> Any:
        try:
            return sorted(value)
        except TypeError:
            return list(value)

    def _from_json_value(self, raw: Any) -> builtins.set[T]:
        return set(raw)
