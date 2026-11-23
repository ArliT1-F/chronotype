"""Numeric temporal types with arithmetic operations."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from chronotype.base import Temporal
from chronotype.exceptions import InvalidTimestampError
from chronotype.interpolation import InterpolationStrategy, LinearInterpolation, StepInterpolation
from chronotype.query import NumericTemporalQuery
from chronotype.utils import TimestampType, normalize_timestamp, now


class TemporalFloat(Temporal[float]):
    """
    Temporal float with arithmetic operations and optional interpolation.
    """

    def __init__(
        self,
        initial: float | None = None,
        initial_time: TimestampType | None = None,
        interpolate: bool = False,
    ) -> None:
        """
        Initialize a temporal float.

        Args:
            initial: Optional initial value
            initial_time: Timestamp for initial value
            interpolate: If True, use linear interpolation
        """
        interp: InterpolationStrategy[float] = (
            LinearInterpolation() if interpolate else StepInterpolation()
        )
        super().__init__(initial, initial_time, interp)
        self._interpolate = interpolate

    def between(
        self,
        start: TimestampType,
        end: TimestampType,
        include_start: bool = True,
        include_end: bool = True,
    ) -> NumericTemporalQuery[float]:
        """Query values between timestamps with numeric aggregations."""
        start_dt = normalize_timestamp(start)
        end_dt = normalize_timestamp(end)

        if start_dt > end_dt:
            raise InvalidTimestampError("Start must be before or equal to end")

        lo, hi = self._range_bounds(start_dt, end_dt, include_start, include_end)
        entries = self._timeline[lo:hi]
        before_idx = self._find_index_left(start_dt) - 1
        value_before: float | None = (
            self._timeline[before_idx][1] if before_idx >= 0 else None
        )

        return NumericTemporalQuery(
            entries, start_dt, end_dt, include_start, include_end, value_before
        )

    def __add__(self, other: TemporalFloat | float | int) -> TemporalFloat:
        if isinstance(other, (int, float)):
            result = TemporalFloat(interpolate=self._interpolate)
            for ts, v in self._timeline:
                result[ts] = v + other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalFloat(interpolate=self._interpolate)
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 + v2
        return result

    def __radd__(self, other: float | int) -> TemporalFloat:
        return self.__add__(other)

    def __sub__(self, other: TemporalFloat | float | int) -> TemporalFloat:
        if isinstance(other, (int, float)):
            result = TemporalFloat(interpolate=self._interpolate)
            for ts, v in self._timeline:
                result[ts] = v - other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalFloat(interpolate=self._interpolate)
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 - v2
        return result

    def __rsub__(self, other: float | int) -> TemporalFloat:
        result = TemporalFloat(interpolate=self._interpolate)
        for ts, v in self._timeline:
            result[ts] = other - v
        return result

    def __mul__(self, other: TemporalFloat | float | int) -> TemporalFloat:
        if isinstance(other, (int, float)):
            result = TemporalFloat(interpolate=self._interpolate)
            for ts, v in self._timeline:
                result[ts] = v * other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalFloat(interpolate=self._interpolate)
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 * v2
        return result

    def __rmul__(self, other: float | int) -> TemporalFloat:
        return self.__mul__(other)

    def __truediv__(self, other: TemporalFloat | float | int) -> TemporalFloat:
        if isinstance(other, (int, float)):
            result = TemporalFloat(interpolate=self._interpolate)
            for ts, v in self._timeline:
                result[ts] = v / other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalFloat(interpolate=self._interpolate)
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None and v2 != 0:
                result[ts] = v1 / v2
        return result

    def __rtruediv__(self, other: float | int) -> TemporalFloat:
        result = TemporalFloat(interpolate=self._interpolate)
        for ts, v in self._timeline:
            if v != 0:
                result[ts] = other / v
        return result

    def __pow__(self, other: TemporalFloat | float | int) -> TemporalFloat:
        if isinstance(other, (int, float)):
            result = TemporalFloat(interpolate=self._interpolate)
            for ts, v in self._timeline:
                result[ts] = v**other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalFloat(interpolate=self._interpolate)
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1**v2
        return result

    def __neg__(self) -> TemporalFloat:
        result = TemporalFloat(interpolate=self._interpolate)
        for ts, v in self._timeline:
            result[ts] = -v
        return result

    def __abs__(self) -> TemporalFloat:
        result = TemporalFloat(interpolate=self._interpolate)
        for ts, v in self._timeline:
            result[ts] = abs(v)
        return result

    def __lt__(self, other: TemporalFloat | float | int) -> TemporalBool:
        return self._compare(other, lambda a, b: a < b)

    def __le__(self, other: TemporalFloat | float | int) -> TemporalBool:
        return self._compare(other, lambda a, b: a <= b)

    def __gt__(self, other: TemporalFloat | float | int) -> TemporalBool:
        return self._compare(other, lambda a, b: a > b)

    def __ge__(self, other: TemporalFloat | float | int) -> TemporalBool:
        return self._compare(other, lambda a, b: a >= b)

    def _compare(
        self, other: TemporalFloat | float | int, op: Callable[[float, float], bool]
    ) -> TemporalBool:
        from chronotype.numeric import TemporalBool

        if isinstance(other, (int, float)):
            result = TemporalBool()
            for ts, v in self._timeline:
                result[ts] = op(v, other)
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalBool()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = op(v1, v2)
        return result

    def copy(self) -> TemporalFloat:
        """Create a copy."""
        new = TemporalFloat(interpolate=self._interpolate)
        new._set_timeline(list(self._timeline))
        return new


class TemporalInt(Temporal[int]):
    """
    Temporal integer with arithmetic operations.
    """

    def __init__(
        self,
        initial: int | None = None,
        initial_time: TimestampType | None = None,
    ) -> None:
        super().__init__(initial, initial_time, StepInterpolation())

    def between(
        self,
        start: TimestampType,
        end: TimestampType,
        include_start: bool = True,
        include_end: bool = True,
    ) -> NumericTemporalQuery[int]:
        """Query values between timestamps with numeric aggregations."""
        start_dt = normalize_timestamp(start)
        end_dt = normalize_timestamp(end)

        if start_dt > end_dt:
            raise InvalidTimestampError("Start must be before or equal to end")

        lo, hi = self._range_bounds(start_dt, end_dt, include_start, include_end)
        entries = self._timeline[lo:hi]
        before_idx = self._find_index_left(start_dt) - 1
        value_before: int | None = (
            self._timeline[before_idx][1] if before_idx >= 0 else None
        )

        return NumericTemporalQuery(
            entries, start_dt, end_dt, include_start, include_end, value_before
        )

    def __add__(self, other: TemporalInt | int) -> TemporalInt:
        if isinstance(other, int):
            result = TemporalInt()
            for ts, v in self._timeline:
                result[ts] = v + other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalInt()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 + v2
        return result

    def __radd__(self, other: int) -> TemporalInt:
        return self.__add__(other)

    def __sub__(self, other: TemporalInt | int) -> TemporalInt:
        if isinstance(other, int):
            result = TemporalInt()
            for ts, v in self._timeline:
                result[ts] = v - other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalInt()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 - v2
        return result

    def __rsub__(self, other: int) -> TemporalInt:
        result = TemporalInt()
        for ts, v in self._timeline:
            result[ts] = other - v
        return result

    def __mul__(self, other: TemporalInt | int) -> TemporalInt:
        if isinstance(other, int):
            result = TemporalInt()
            for ts, v in self._timeline:
                result[ts] = v * other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalInt()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 * v2
        return result

    def __rmul__(self, other: int) -> TemporalInt:
        return self.__mul__(other)

    def __truediv__(self, other: TemporalInt | TemporalFloat | int | float) -> TemporalFloat:
        if isinstance(other, (int, float)):
            result = TemporalFloat()
            for ts, v in self._timeline:
                result[ts] = v / other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalFloat()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None and v2 != 0:
                result[ts] = v1 / v2
        return result

    def __floordiv__(self, other: TemporalInt | int) -> TemporalInt:
        if isinstance(other, int):
            result = TemporalInt()
            for ts, v in self._timeline:
                result[ts] = v // other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalInt()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None and v2 != 0:
                result[ts] = v1 // v2
        return result

    def __mod__(self, other: TemporalInt | int) -> TemporalInt:
        if isinstance(other, int):
            result = TemporalInt()
            for ts, v in self._timeline:
                result[ts] = v % other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalInt()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None and v2 != 0:
                result[ts] = v1 % v2
        return result

    def __pow__(self, other: TemporalInt | int) -> TemporalInt:
        if isinstance(other, int):
            result = TemporalInt()
            for ts, v in self._timeline:
                result[ts] = v**other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalInt()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1**v2
        return result

    def __neg__(self) -> TemporalInt:
        result = TemporalInt()
        for ts, v in self._timeline:
            result[ts] = -v
        return result

    def __abs__(self) -> TemporalInt:
        result = TemporalInt()
        for ts, v in self._timeline:
            result[ts] = abs(v)
        return result

    def __lt__(self, other: TemporalInt | int) -> TemporalBool:
        return self._compare(other, lambda a, b: a < b)

    def __le__(self, other: TemporalInt | int) -> TemporalBool:
        return self._compare(other, lambda a, b: a <= b)

    def __gt__(self, other: TemporalInt | int) -> TemporalBool:
        return self._compare(other, lambda a, b: a > b)

    def __ge__(self, other: TemporalInt | int) -> TemporalBool:
        return self._compare(other, lambda a, b: a >= b)

    def _compare(self, other: TemporalInt | int, op: Callable[[int, int], bool]) -> TemporalBool:
        if isinstance(other, int):
            result = TemporalBool()
            for ts, v in self._timeline:
                result[ts] = op(v, other)
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalBool()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = op(v1, v2)
        return result

    def to_float(self) -> TemporalFloat:
        """Convert to TemporalFloat."""
        result = TemporalFloat()
        for ts, v in self._timeline:
            result[ts] = float(v)
        return result

    def copy(self) -> TemporalInt:
        """Create a copy."""
        new = TemporalInt()
        new._set_timeline(list(self._timeline))
        return new


class TemporalBool(Temporal[bool]):
    """
    Temporal boolean with logical operations.
    """

    def __init__(
        self,
        initial: bool | None = None,
        initial_time: TimestampType | None = None,
    ) -> None:
        super().__init__(initial, initial_time, StepInterpolation())

    def __and__(self, other: TemporalBool | bool) -> TemporalBool:
        if isinstance(other, bool):
            result = TemporalBool()
            for ts, v in self._timeline:
                result[ts] = v and other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalBool()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 and v2
        return result

    def __rand__(self, other: bool) -> TemporalBool:
        return self.__and__(other)

    def __or__(self, other: TemporalBool | bool) -> TemporalBool:
        if isinstance(other, bool):
            result = TemporalBool()
            for ts, v in self._timeline:
                result[ts] = v or other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalBool()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 or v2
        return result

    def __ror__(self, other: bool) -> TemporalBool:
        return self.__or__(other)

    def __xor__(self, other: TemporalBool | bool) -> TemporalBool:
        if isinstance(other, bool):
            result = TemporalBool()
            for ts, v in self._timeline:
                result[ts] = v ^ other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalBool()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 ^ v2
        return result

    def __rxor__(self, other: bool) -> TemporalBool:
        return self.__xor__(other)

    def __invert__(self) -> TemporalBool:
        result = TemporalBool()
        for ts, v in self._timeline:
            result[ts] = not v
        return result

    def when_true(self) -> list[tuple[datetime, datetime]]:
        """Get list of time ranges when value was True."""
        if not self._timeline:
            return []

        ranges = []
        start = None

        for ts, value in self._timeline:
            if value and start is None:
                start = ts
            elif not value and start is not None:
                ranges.append((start, ts))
                start = None

        if start is not None:
            ranges.append((start, now()))

        return ranges

    def when_false(self) -> list[tuple[datetime, datetime]]:
        """Get list of time ranges when value was False."""
        if not self._timeline:
            return []

        ranges = []
        start = None

        for ts, value in self._timeline:
            if not value and start is None:
                start = ts
            elif value and start is not None:
                ranges.append((start, ts))
                start = None

        if start is not None:
            ranges.append((start, now()))

        return ranges

    def duration_true(self) -> float:
        """Total seconds when value was True."""
        return sum((end - start).total_seconds() for start, end in self.when_true())

    def duration_false(self) -> float:
        """Total seconds when value was False."""
        return sum((end - start).total_seconds() for start, end in self.when_false())

    def copy(self) -> TemporalBool:
        """Create a copy."""
        new = TemporalBool()
        new._set_timeline(list(self._timeline))
        return new


class TemporalString(Temporal[str]):
    """
    Temporal string type.
    """

    def __init__(
        self,
        initial: str | None = None,
        initial_time: TimestampType | None = None,
    ) -> None:
        super().__init__(initial, initial_time, StepInterpolation())

    def __add__(self, other: TemporalString | str) -> TemporalString:
        if isinstance(other, str):
            result = TemporalString()
            for ts, v in self._timeline:
                result[ts] = v + other
            return result

        all_times = sorted(set(self.timestamps() + other.timestamps()))
        result = TemporalString()
        for ts in all_times:
            v1 = self.at(ts)
            v2 = other.at(ts)
            if v1 is not None and v2 is not None:
                result[ts] = v1 + v2
        return result

    def __radd__(self, other: str) -> TemporalString:
        result = TemporalString()
        for ts, v in self._timeline:
            result[ts] = other + v
        return result

    def upper(self) -> TemporalString:
        """Return new temporal with uppercase values."""
        result = TemporalString()
        for ts, v in self._timeline:
            result[ts] = v.upper()
        return result

    def lower(self) -> TemporalString:
        """Return new temporal with lowercase values."""
        result = TemporalString()
        for ts, v in self._timeline:
            result[ts] = v.lower()
        return result

    def contains(self, substring: str) -> TemporalBool:
        """Check if substring is in value at each point."""
        result = TemporalBool()
        for ts, v in self._timeline:
            result[ts] = substring in v
        return result

    def length(self) -> TemporalInt:
        """Get length at each point."""
        result = TemporalInt()
        for ts, v in self._timeline:
            result[ts] = len(v)
        return result

    def copy(self) -> TemporalString:
        """Create a copy."""
        new = TemporalString()
        new._set_timeline(list(self._timeline))
        return new
