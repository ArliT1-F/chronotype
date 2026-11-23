"""Base temporal class for generic types."""

from __future__ import annotations

import bisect
import copy
import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Callable, Generic, TypeVar, cast

from chronotype.exceptions import EmptyTemporalError, InvalidTimestampError
from chronotype.interpolation import (
    InterpolationStrategy,
    StepInterpolation,
    strategy_from_name,
    strategy_to_name,
)
from chronotype.query import TemporalQuery
from chronotype.utils import TimestampType, normalize_timestamp, now

T = TypeVar("T")
_TemporalT = TypeVar("_TemporalT", bound="Temporal[Any]")


class Temporal(Generic[T]):
    """
    A temporal value that tracks its history over time.

    Every assignment is stored with its timestamp, allowing queries
    at any point in time and analysis over time ranges.
    """

    def __init__(
        self,
        initial: T | None = None,
        initial_time: TimestampType | None = None,
        interpolation: InterpolationStrategy[T] | None = None,
        serializer: Callable[[T], dict[str, Any]] | None = None,
        deserializer: Callable[[dict[str, Any]], T] | None = None,
    ) -> None:
        """
        Initialize a temporal value.

        Args:
            initial: Optional initial value
            initial_time: Timestamp for initial value (defaults to now)
            interpolation: Strategy for interpolating between values
        """
        # ``_timeline`` holds the (timestamp, value) entries sorted by timestamp;
        # ``_keys`` mirrors its timestamps so lookups can bisect in O(log n).
        # Both lists must always be updated together.
        self._timeline: list[tuple[datetime, T]] = []
        self._keys: list[datetime] = []
        self._interpolation: InterpolationStrategy[T] = interpolation or StepInterpolation()
        self._serializer = serializer
        self._deserializer = deserializer

        if initial is not None:
            ts = normalize_timestamp(initial_time) if initial_time else now()
            self._timeline.append((ts, initial))
            self._keys.append(ts)

    def _set_timeline(self, entries: list[tuple[datetime, T]]) -> None:
        """Replace all entries (must already be sorted by timestamp)."""
        self._timeline = entries
        self._keys = [ts for ts, _ in entries]

    def _find_index(self, ts: datetime) -> int:
        """Find insertion index for timestamp using binary search."""
        return bisect.bisect_right(self._keys, ts)

    def _find_index_left(self, ts: datetime) -> int:
        """Find leftmost insertion index for timestamp."""
        return bisect.bisect_left(self._keys, ts)

    def _range_bounds(
        self,
        start: datetime,
        end: datetime,
        include_start: bool,
        include_end: bool,
    ) -> tuple[int, int]:
        """Return ``(lo, hi)`` such that ``_timeline[lo:hi]`` is the requested range."""
        lo = bisect.bisect_left(self._keys, start) if include_start else bisect.bisect_right(
            self._keys, start
        )
        hi = bisect.bisect_right(self._keys, end) if include_end else bisect.bisect_left(
            self._keys, end
        )
        return lo, max(lo, hi)

    def set(self, timestamp: TimestampType, value: T) -> None:
        """Set value at a specific timestamp."""
        ts = normalize_timestamp(timestamp)
        idx = self._find_index_left(ts)

        if idx < len(self._keys) and self._keys[idx] == ts:
            self._timeline[idx] = (ts, value)
        else:
            self._timeline.insert(idx, (ts, value))
            self._keys.insert(idx, ts)

    def __setitem__(self, timestamp: TimestampType, value: T) -> None:
        """Set value at timestamp using bracket notation."""
        self.set(timestamp, value)

    def at(self, timestamp: TimestampType) -> T | None:
        """
        Get value at a specific timestamp.

        Returns the value that was active at the given time,
        using the interpolation strategy if needed.
        """
        if not self._timeline:
            return None

        ts = normalize_timestamp(timestamp)

        idx = self._find_index(ts)

        if idx == 0:
            after = self._timeline[0] if self._timeline else None
            return self._interpolation.interpolate(ts, None, after)

        before = self._timeline[idx - 1]

        if idx < len(self._timeline):
            after = self._timeline[idx]
        else:
            after = None

        return self._interpolation.interpolate(ts, before, after)

    def __getitem__(self, timestamp: TimestampType) -> T | None:
        """Get value at timestamp using bracket notation."""
        return self.at(timestamp)

    def current(self) -> T:
        """Get the most recent value."""
        if not self._timeline:
            raise EmptyTemporalError("No values in temporal")
        return self._timeline[-1][1]

    def current_entry(self) -> tuple[datetime, T]:
        """Get the most recent entry as (timestamp, value)."""
        if not self._timeline:
            raise EmptyTemporalError("No values in temporal")
        return self._timeline[-1]

    def first(self) -> T:
        """Get the first (oldest) value."""
        if not self._timeline:
            raise EmptyTemporalError("No values in temporal")
        return self._timeline[0][1]

    def first_entry(self) -> tuple[datetime, T]:
        """Get the first entry as (timestamp, value)."""
        if not self._timeline:
            raise EmptyTemporalError("No values in temporal")
        return self._timeline[0]

    def between(
        self,
        start: TimestampType,
        end: TimestampType,
        include_start: bool = True,
        include_end: bool = True,
    ) -> TemporalQuery[T]:
        """
        Query values between two timestamps.

        Args:
            start: Start of range
            end: End of range
            include_start: Include entries at exactly start time
            include_end: Include entries at exactly end time

        Returns:
            TemporalQuery object for further operations
        """
        start_dt = normalize_timestamp(start)
        end_dt = normalize_timestamp(end)

        if start_dt > end_dt:
            raise InvalidTimestampError("Start must be before or equal to end")

        lo, hi = self._range_bounds(start_dt, end_dt, include_start, include_end)
        entries = self._timeline[lo:hi]
        return TemporalQuery(entries, start_dt, end_dt, include_start, include_end)

    def history(self) -> list[tuple[datetime, T]]:
        """Get full history as list of (timestamp, value) tuples."""
        return list(self._timeline)

    def changes(self) -> list[tuple[datetime, T | None, T]]:
        """
        Get list of changes as (timestamp, old_value, new_value) tuples.
        First entry has None as old_value.
        """
        if not self._timeline:
            return []

        changes: list[tuple[datetime, T | None, T]] = [
            (self._timeline[0][0], None, self._timeline[0][1])
        ]

        for i in range(1, len(self._timeline)):
            ts, new_val = self._timeline[i]
            old_val = self._timeline[i - 1][1]
            changes.append((ts, old_val, new_val))

        return changes

    def rollback(self, to: TimestampType | None = None, steps: int = 1) -> None:
        """
        Rollback changes.

        Args:
            to: If provided, remove all entries after this timestamp
            steps: If 'to' not provided, remove this many recent entries
        """
        if to is not None:
            keep = self._find_index(normalize_timestamp(to))
        elif steps > 0:
            keep = max(len(self._timeline) - steps, 0)
        else:
            return
        del self._timeline[keep:]
        del self._keys[keep:]

    def clear(self) -> None:
        """Remove all entries."""
        self._timeline.clear()
        self._keys.clear()

    def __len__(self) -> int:
        """Number of entries in history."""
        return len(self._timeline)

    def __bool__(self) -> bool:
        """True if there are any entries."""
        return len(self._timeline) > 0

    def __iter__(self) -> Iterator[tuple[datetime, T]]:
        """Iterate over (timestamp, value) pairs."""
        return iter(self._timeline)

    def __contains__(self, timestamp: TimestampType) -> bool:
        """Check if there's an entry at exactly this timestamp."""
        ts = normalize_timestamp(timestamp)
        idx = self._find_index_left(ts)
        return idx < len(self._keys) and self._keys[idx] == ts

    def __repr__(self) -> str:
        if not self._timeline:
            return f"{self.__class__.__name__}(empty)"
        name = self.__class__.__name__
        return f"{name}(entries={len(self._timeline)}, current={self._timeline[-1][1]!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Temporal):
            return NotImplemented
        return self._timeline == other._timeline

    def _empty_like(self: _TemporalT) -> _TemporalT:
        """
        Create an empty temporal of the same class with the same configuration.

        Interpolation strategy, serializer/deserializer and any extra attributes a
        subclass sets are carried over; only the timeline is left empty.
        """
        cls = type(self)
        new = cls.__new__(cls)
        new.__dict__.update(self.__dict__)
        new._set_timeline([])
        return new

    def _copy_value(self, value: T) -> T:
        """
        Copy a stored value when a timeline is duplicated (copy/slice/merge).

        Values are shared by default; mutable container subclasses override this
        so derived temporals never share snapshots with the original.
        """
        return value

    def _pointwise(
        self,
        other: object,
        op: Callable[[Any, Any], Any],
        reflected: bool = False,
    ) -> list[tuple[datetime, Any]]:
        """
        Apply a binary ``op`` point by point and return the sorted entries.

        If ``other`` is a Temporal, both operands are evaluated with ``at()`` (so
        each uses its own interpolation) at the union of their timestamps;
        timestamps where either operand has no value yet are skipped. Otherwise
        ``other`` is treated as a constant and combined with every entry.
        With ``reflected=True`` the operands are swapped: ``op(other, self)``.
        """
        if isinstance(other, Temporal):
            entries: list[tuple[datetime, Any]] = []
            for ts in sorted(set(self._keys).union(other._keys)):
                a = self.at(ts)
                b = other.at(ts)
                if a is None or b is None:
                    continue
                entries.append((ts, op(b, a) if reflected else op(a, b)))
            return entries
        if reflected:
            return [(ts, op(other, v)) for ts, v in self._timeline]
        return [(ts, op(v, other)) for ts, v in self._timeline]

    def copy(self: _TemporalT) -> _TemporalT:
        """Create a shallow copy of the same type and configuration."""
        new = self._empty_like()
        new._set_timeline([(ts, self._copy_value(v)) for ts, v in self._timeline])
        return new

    def deepcopy(self: _TemporalT) -> _TemporalT:
        """Create a deep copy (values are deep-copied) of the same type and configuration."""
        new = self._empty_like()
        new._set_timeline([(ts, copy.deepcopy(v)) for ts, v in self._timeline])
        return new

    def timestamps(self) -> list[datetime]:
        """Get all timestamps."""
        return list(self._keys)

    def values(self) -> list[T]:
        """Get all values."""
        return [v for _, v in self._timeline]

    def slice(self: _TemporalT, start: TimestampType, end: TimestampType) -> _TemporalT:
        """
        Create a new temporal (same type and configuration) containing only the
        entries in the inclusive range ``[start, end]``.
        """
        start_dt = normalize_timestamp(start)
        end_dt = normalize_timestamp(end)
        if start_dt > end_dt:
            raise InvalidTimestampError("Start must be before or equal to end")
        lo, hi = self._range_bounds(start_dt, end_dt, True, True)
        new = self._empty_like()
        new._set_timeline([(ts, self._copy_value(v)) for ts, v in self._timeline[lo:hi]])
        return new

    def merge(self: _TemporalT, other: Temporal[Any], prefer_self: bool = True) -> _TemporalT:
        """
        Merge with another temporal.

        Args:
            other: Another temporal to merge with
            prefer_self: If True, prefer this temporal's values on conflict

        Returns:
            A new temporal of the same type and configuration as ``self``
        """
        first, second = (other, self) if prefer_self else (self, other)
        all_entries: dict[datetime, Any] = {}
        for ts, v in first._timeline:
            all_entries[ts] = v
        for ts, v in second._timeline:
            all_entries[ts] = v

        new = self._empty_like()
        new._set_timeline(
            [(ts, self._copy_value(v)) for ts, v in sorted(all_entries.items(), key=lambda x: x[0])]
        )
        return new

    def _to_json_value(self, value: T) -> Any:
        """Hook: JSON-native form of a value, used when no serializer is set."""
        return value

    def _from_json_value(self, raw: Any) -> T:
        """Hook: inverse of :meth:`_to_json_value`."""
        return cast(T, raw)

    def _serialize_value(self, value: T) -> dict[str, Any]:
        if self._serializer is not None:
            payload = self._serializer(value)
            if not isinstance(payload, dict) or "type" not in payload or "value" not in payload:
                raise ValueError("Serializer must return a dict with 'type' and 'value' keys.")
            return {"type": payload["type"], "value": payload["value"]}

        raw = self._to_json_value(value)
        try:
            json.dumps(raw)
        except TypeError as exc:
            raise TypeError(
                f"Temporal value of type {type(value).__name__} is not JSON serializable; "
                "provide serializer/deserializer callables."
            ) from exc
        return {"type": None, "value": raw}

    def _deserialize_value(self, payload: dict[str, Any]) -> T:
        value_type = payload.get("type")
        if value_type is None:
            return self._from_json_value(payload.get("value"))
        if self._deserializer is None:
            raise ValueError(
                "Temporal entry includes type metadata but no deserializer was provided."
            )
        return self._deserializer(payload)

    def _config(self) -> dict[str, Any]:
        """
        JSON-serializable configuration stored by :meth:`to_dict`.

        Subclasses with extra settings can extend this and :meth:`_apply_config`.
        """
        return {"interpolation": strategy_to_name(self._interpolation)}

    def _apply_config(self, config: dict[str, Any]) -> None:
        """Restore configuration produced by :meth:`_config`."""
        name = config.get("interpolation")
        if name is not None:
            self._interpolation = strategy_from_name(name)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to a JSON-compatible dictionary.

        The result holds the class name, the configuration (currently the
        interpolation strategy, e.g. ``{"interpolation": "linear"}``) and the
        entries. Values that are not JSON-native need a serializer.
        """
        return {
            "entries": [
                {"timestamp": ts.isoformat(), **self._serialize_value(v)}
                for ts, v in self._timeline
            ],
            "type": self.__class__.__name__,
            "config": self._config(),
        }

    @classmethod
    def from_dict(
        cls: type[_TemporalT],
        data: dict[str, Any],
        serializer: Callable[[Any], dict[str, Any]] | None = None,
        deserializer: Callable[[dict[str, Any]], Any] | None = None,
        interpolation: InterpolationStrategy[Any] | None = None,
    ) -> _TemporalT:
        """
        Create an instance of ``cls`` from :meth:`to_dict` output.

        Args:
            data: Dictionary produced by :meth:`to_dict` (payloads written by
                0.1.1, which have no ``config``, are accepted too)
            serializer: Serializer to attach to the new instance
            deserializer: Deserializer used for entries with type metadata
            interpolation: Overrides the stored interpolation strategy. Required
                to restore custom (non built-in) strategies.
        """
        new = cls()
        if serializer is not None:
            new._serializer = serializer
        if deserializer is not None:
            new._deserializer = deserializer
        if interpolation is not None:
            new._interpolation = interpolation
        else:
            new._apply_config(data.get("config") or {})

        for entry in data.get("entries", []):
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                ts_str, value = entry
                new.set(datetime.fromisoformat(ts_str), new._from_json_value(value))
                continue
            if not isinstance(entry, dict):
                raise ValueError("Temporal entries must be dicts with timestamp/value metadata.")
            ts_str = entry.get("timestamp")
            if ts_str is None:
                raise ValueError("Temporal entry is missing a timestamp.")
            value = new._deserialize_value({"type": entry.get("type"), "value": entry.get("value")})
            new.set(datetime.fromisoformat(ts_str), value)
        return new

    def to_json(self) -> str:
        """Serialize to JSON string (see :meth:`to_dict`)."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(
        cls: type[_TemporalT],
        json_str: str,
        serializer: Callable[[Any], dict[str, Any]] | None = None,
        deserializer: Callable[[dict[str, Any]], Any] | None = None,
        interpolation: InterpolationStrategy[Any] | None = None,
    ) -> _TemporalT:
        """Deserialize from JSON string (see :meth:`from_dict`)."""
        return cls.from_dict(
            json.loads(json_str),
            serializer=serializer,
            deserializer=deserializer,
            interpolation=interpolation,
        )

    def __getstate__(self) -> dict[str, Any]:
        """Support for pickle serialization."""
        return {
            "timeline": self._timeline,
            "interpolation": self._interpolation,
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Support for pickle deserialization."""
        self._set_timeline(list(state["timeline"]))
        self._interpolation = state["interpolation"]
        # Serializer callables are not pickled (they are often lambdas).
        self._serializer = None
        self._deserializer = None
