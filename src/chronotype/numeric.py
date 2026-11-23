"""
Numeric temporal types with arithmetic operations.

Arithmetic rules shared by :class:`TemporalInt` and :class:`TemporalFloat`:

* **Operands** may be a TemporalInt, a TemporalFloat, an ``int`` or a ``float``.
  ``bool`` is *not* accepted as a numeric scalar (``True`` would silently act
  as ``1``). Any other operand makes the operator return ``NotImplemented``,
  so Python raises ``TypeError``.
* **Alignment**: two temporals are combined at the union of their timestamps,
  each side evaluated with ``at()`` (its own interpolation). Timestamps where
  either side has no value yet are skipped.
* **Result type** follows Python's numeric promotion: ``/`` always gives a
  TemporalFloat; any float operand gives a TemporalFloat; int-only operations
  give a TemporalInt, unless a result is not an int (e.g. ``t ** -1``), in
  which case the whole result is promoted to TemporalFloat.
* **Interpolation**: the result reuses the strategy of the temporal the
  operator was called on (the left operand, or the temporal of a reflected
  operation such as ``1 + t``). Comparisons return a step TemporalBool.
* **Division by zero**: float results store ``math.nan`` at that timestamp
  (``/`` always; ``//`` and ``%`` when the result is a TemporalFloat;
  ``0 ** -n``). Integer results (``//`` or ``%`` between ints) cannot hold
  NaN, so they raise ``ZeroDivisionError``; convert with ``to_float()`` first
  to get NaN instead.
"""

from __future__ import annotations

import math
import operator
import warnings
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, TypeVar, Union, overload

from chronotype.base import Temporal
from chronotype.exceptions import InvalidTimestampError
from chronotype.interpolation import InterpolationStrategy, LinearInterpolation, StepInterpolation
from chronotype.query import NumericTemporalQuery
from chronotype.utils import TimestampType, normalize_timestamp, now

_N = TypeVar("_N", int, float)
_NumericT = TypeVar("_NumericT", bound="_TemporalNumeric[Any]")
_BoolT = TypeVar("_BoolT", bound="TemporalBool")

Number = Union[int, float]
NumericOperand = Union["TemporalInt", "TemporalFloat", int, float]


def _is_number(value: object) -> bool:
    """True for int/float scalars; bool is deliberately rejected."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _resolve_interpolation(
    interpolation: InterpolationStrategy[Any] | bool | None,
    interpolate: bool | None,
) -> InterpolationStrategy[Any]:
    """
    Resolve the ``interpolation=`` argument and the deprecated ``interpolate=`` flag.

    A bool passed as ``interpolation`` (e.g. the old positional
    ``TemporalFloat(value, ts, True)``) is treated like ``interpolate=``.
    """
    if isinstance(interpolation, bool):
        if interpolate is not None:
            raise TypeError("pass either 'interpolation' or 'interpolate', not both")
        interpolation, interpolate = None, interpolation
    if interpolate is not None:
        if interpolation is not None:
            raise TypeError("pass either 'interpolation' or 'interpolate', not both")
        replacement = "LinearInterpolation()" if interpolate else "StepInterpolation()"
        warnings.warn(
            f"'interpolate={interpolate}' is deprecated and will be removed in a future "
            f"release; use 'interpolation={replacement}' instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        return LinearInterpolation() if interpolate else StepInterpolation()
    return interpolation if interpolation is not None else StepInterpolation()


class _TemporalNumeric(Temporal[_N]):
    """Shared implementation of TemporalInt and TemporalFloat (see module docs)."""

    def between(
        self,
        start: TimestampType,
        end: TimestampType,
        include_start: bool = True,
        include_end: bool = True,
    ) -> NumericTemporalQuery[_N]:
        """Query values between timestamps with numeric aggregations."""
        start_dt = normalize_timestamp(start)
        end_dt = normalize_timestamp(end)

        if start_dt > end_dt:
            raise InvalidTimestampError("Start must be before or equal to end")

        lo, hi = self._range_bounds(start_dt, end_dt, include_start, include_end)
        # The value carried into the range is the latest entry *not* included:
        # before ``start`` (or exactly at ``start`` when include_start=False).
        value_before = self._timeline[lo - 1][1] if lo > 0 else None
        return NumericTemporalQuery(
            self._timeline[lo:hi], start_dt, end_dt, include_start, include_end, value_before
        )

    # -- operator machinery -------------------------------------------------

    def _binary_op(
        self, other: object, op: Callable[[Any, Any], Any], reflected: bool = False
    ) -> Any:
        """
        Combine with a scalar or another numeric temporal.

        Returns ``NotImplemented`` for unsupported operands, otherwise a new
        TemporalInt or TemporalFloat chosen by the module-level promotion rules.
        """
        if isinstance(other, _TemporalNumeric):
            other_is_float = isinstance(other, TemporalFloat)
        elif _is_number(other):
            other_is_float = isinstance(other, float)
        else:
            return NotImplemented

        float_result = op is operator.truediv or other_is_float or isinstance(self, TemporalFloat)
        nan_on_zero = float_result or op is operator.pow

        def apply(a: Any, b: Any) -> Any:
            try:
                return op(a, b)
            except ZeroDivisionError:
                if nan_on_zero:
                    return math.nan
                raise ZeroDivisionError(
                    f"integer {op.__name__} by zero: a TemporalInt result cannot hold NaN "
                    "(convert an operand with .to_float() to get NaN instead)"
                ) from None

        entries = self._pointwise(other, apply, reflected=reflected)
        if not float_result and any(isinstance(v, float) for _, v in entries):
            float_result = True

        result_cls = TemporalFloat if float_result else TemporalInt
        result: _TemporalNumeric[Any] = result_cls(interpolation=self._interpolation)
        result._set_timeline(entries)
        return result

    def _unary_op(self: _NumericT, op: Callable[[Any], Any]) -> _NumericT:
        result = self._empty_like()
        result._set_timeline([(ts, op(v)) for ts, v in self._timeline])
        return result

    def _compare(self, other: object, op: Callable[[Any, Any], bool]) -> Any:
        if not (isinstance(other, _TemporalNumeric) or _is_number(other)):
            return NotImplemented
        result = TemporalBool()
        result._set_timeline(self._pointwise(other, op))
        return result

    # -- arithmetic (precise signatures are declared on each subclass) ------

    def __add__(self, other: NumericOperand) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.add)  # type: ignore[no-any-return]

    def __radd__(self, other: Number) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.add, True)  # type: ignore[no-any-return]

    def __sub__(self, other: NumericOperand) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.sub)  # type: ignore[no-any-return]

    def __rsub__(self, other: Number) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.sub, True)  # type: ignore[no-any-return]

    def __mul__(self, other: NumericOperand) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.mul)  # type: ignore[no-any-return]

    def __rmul__(self, other: Number) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.mul, True)  # type: ignore[no-any-return]

    def __truediv__(self, other: NumericOperand) -> TemporalFloat:
        return self._binary_op(other, operator.truediv)  # type: ignore[no-any-return]

    def __rtruediv__(self, other: Number) -> TemporalFloat:
        return self._binary_op(other, operator.truediv, True)  # type: ignore[no-any-return]

    def __floordiv__(self, other: NumericOperand) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.floordiv)  # type: ignore[no-any-return]

    def __rfloordiv__(self, other: Number) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.floordiv, True)  # type: ignore[no-any-return]

    def __mod__(self, other: NumericOperand) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.mod)  # type: ignore[no-any-return]

    def __rmod__(self, other: Number) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.mod, True)  # type: ignore[no-any-return]

    def __pow__(self, other: NumericOperand) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.pow)  # type: ignore[no-any-return]

    def __rpow__(self, other: Number) -> _TemporalNumeric[Any]:
        return self._binary_op(other, operator.pow, True)  # type: ignore[no-any-return]

    def __neg__(self: _NumericT) -> _NumericT:
        return self._unary_op(operator.neg)

    def __pos__(self: _NumericT) -> _NumericT:
        return self._unary_op(operator.pos)

    def __abs__(self: _NumericT) -> _NumericT:
        return self._unary_op(abs)

    # -- comparisons (return TemporalBool; __eq__ stays structural) ---------

    def __lt__(self, other: NumericOperand) -> TemporalBool:
        return self._compare(other, operator.lt)  # type: ignore[no-any-return]

    def __le__(self, other: NumericOperand) -> TemporalBool:
        return self._compare(other, operator.le)  # type: ignore[no-any-return]

    def __gt__(self, other: NumericOperand) -> TemporalBool:
        return self._compare(other, operator.gt)  # type: ignore[no-any-return]

    def __ge__(self, other: NumericOperand) -> TemporalBool:
        return self._compare(other, operator.ge)  # type: ignore[no-any-return]


class TemporalFloat(_TemporalNumeric[float]):
    """
    Temporal float with arithmetic operations and optional interpolation.

    Every arithmetic operation returns a TemporalFloat; see the module
    documentation for alignment and division-by-zero rules.
    """

    def __init__(
        self,
        initial: float | None = None,
        initial_time: TimestampType | None = None,
        interpolation: InterpolationStrategy[Any] | None = None,
        *,
        interpolate: bool | None = None,
    ) -> None:
        """
        Initialize a temporal float.

        Args:
            initial: Optional initial value
            initial_time: Timestamp for initial value
            interpolation: Interpolation strategy (default: StepInterpolation()).
                Use ``LinearInterpolation()`` for linear interpolation.
            interpolate: Deprecated alias; ``interpolate=True`` is equivalent to
                ``interpolation=LinearInterpolation()``. Emits DeprecationWarning.
        """
        super().__init__(
            initial, initial_time, _resolve_interpolation(interpolation, interpolate)
        )

    if TYPE_CHECKING:  # narrower return types for type checkers only

        def __add__(self, other: NumericOperand) -> TemporalFloat: ...
        def __radd__(self, other: Number) -> TemporalFloat: ...
        def __sub__(self, other: NumericOperand) -> TemporalFloat: ...
        def __rsub__(self, other: Number) -> TemporalFloat: ...
        def __mul__(self, other: NumericOperand) -> TemporalFloat: ...
        def __rmul__(self, other: Number) -> TemporalFloat: ...
        def __floordiv__(self, other: NumericOperand) -> TemporalFloat: ...
        def __rfloordiv__(self, other: Number) -> TemporalFloat: ...
        def __mod__(self, other: NumericOperand) -> TemporalFloat: ...
        def __rmod__(self, other: Number) -> TemporalFloat: ...
        def __pow__(self, other: NumericOperand) -> TemporalFloat: ...
        def __rpow__(self, other: Number) -> TemporalFloat: ...


class TemporalInt(_TemporalNumeric[int]):
    """
    Temporal integer with arithmetic operations.

    Operations with ints return a TemporalInt; operations involving a float
    (or ``/``) return a TemporalFloat. See the module documentation.
    """

    def __init__(
        self,
        initial: int | None = None,
        initial_time: TimestampType | None = None,
        interpolation: InterpolationStrategy[Any] | None = None,
    ) -> None:
        """
        Initialize a temporal integer.

        Args:
            initial: Optional initial value
            initial_time: Timestamp for initial value
            interpolation: Interpolation strategy (default: StepInterpolation()).
                ``LinearInterpolation()`` rounds to the nearest int.
        """
        super().__init__(initial, initial_time, _resolve_interpolation(interpolation, None))

    def to_float(self) -> TemporalFloat:
        """Convert to TemporalFloat (keeping the interpolation strategy)."""
        result = TemporalFloat(interpolation=self._interpolation)
        result._set_timeline([(ts, float(v)) for ts, v in self._timeline])
        return result

    if TYPE_CHECKING:  # narrower return types for type checkers only

        @overload
        def __add__(self, other: TemporalInt | int) -> TemporalInt: ...
        @overload
        def __add__(self, other: TemporalFloat | float) -> TemporalFloat: ...
        @overload
        def __add__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        def __add__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        @overload
        def __radd__(self, other: int) -> TemporalInt: ...
        @overload
        def __radd__(self, other: float) -> TemporalFloat: ...
        def __radd__(self, other: Number) -> TemporalInt | TemporalFloat: ...
        @overload
        def __sub__(self, other: TemporalInt | int) -> TemporalInt: ...
        @overload
        def __sub__(self, other: TemporalFloat | float) -> TemporalFloat: ...
        @overload
        def __sub__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        def __sub__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        @overload
        def __rsub__(self, other: int) -> TemporalInt: ...
        @overload
        def __rsub__(self, other: float) -> TemporalFloat: ...
        def __rsub__(self, other: Number) -> TemporalInt | TemporalFloat: ...
        @overload
        def __mul__(self, other: TemporalInt | int) -> TemporalInt: ...
        @overload
        def __mul__(self, other: TemporalFloat | float) -> TemporalFloat: ...
        @overload
        def __mul__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        def __mul__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        @overload
        def __rmul__(self, other: int) -> TemporalInt: ...
        @overload
        def __rmul__(self, other: float) -> TemporalFloat: ...
        def __rmul__(self, other: Number) -> TemporalInt | TemporalFloat: ...
        @overload
        def __floordiv__(self, other: TemporalInt | int) -> TemporalInt: ...
        @overload
        def __floordiv__(self, other: TemporalFloat | float) -> TemporalFloat: ...
        @overload
        def __floordiv__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        def __floordiv__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        @overload
        def __rfloordiv__(self, other: int) -> TemporalInt: ...
        @overload
        def __rfloordiv__(self, other: float) -> TemporalFloat: ...
        def __rfloordiv__(self, other: Number) -> TemporalInt | TemporalFloat: ...
        @overload
        def __mod__(self, other: TemporalInt | int) -> TemporalInt: ...
        @overload
        def __mod__(self, other: TemporalFloat | float) -> TemporalFloat: ...
        @overload
        def __mod__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        def __mod__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        @overload
        def __rmod__(self, other: int) -> TemporalInt: ...
        @overload
        def __rmod__(self, other: float) -> TemporalFloat: ...
        def __rmod__(self, other: Number) -> TemporalInt | TemporalFloat: ...
        # ``**`` promotes for negative exponents, so its result is not narrowed.
        def __pow__(self, other: NumericOperand) -> TemporalInt | TemporalFloat: ...
        def __rpow__(self, other: Number) -> TemporalInt | TemporalFloat: ...

class TemporalBool(Temporal[bool]):
    """
    Temporal boolean with logical operations.

    ``&``, ``|`` and ``^`` accept a ``bool`` or another TemporalBool (aligned
    on the union of timestamps); other operands raise ``TypeError``.
    """

    def __init__(
        self,
        initial: bool | None = None,
        initial_time: TimestampType | None = None,
    ) -> None:
        super().__init__(initial, initial_time, StepInterpolation())

    def _logical_op(
        self, other: object, op: Callable[[Any, Any], Any], reflected: bool = False
    ) -> Any:
        if not isinstance(other, (bool, TemporalBool)):
            return NotImplemented
        result = TemporalBool()
        result._set_timeline(self._pointwise(other, op, reflected=reflected))
        return result

    def __and__(self, other: TemporalBool | bool) -> TemporalBool:
        return self._logical_op(other, operator.and_)  # type: ignore[no-any-return]

    def __rand__(self, other: bool) -> TemporalBool:
        return self._logical_op(other, operator.and_, True)  # type: ignore[no-any-return]

    def __or__(self, other: TemporalBool | bool) -> TemporalBool:
        return self._logical_op(other, operator.or_)  # type: ignore[no-any-return]

    def __ror__(self, other: bool) -> TemporalBool:
        return self._logical_op(other, operator.or_, True)  # type: ignore[no-any-return]

    def __xor__(self, other: TemporalBool | bool) -> TemporalBool:
        return self._logical_op(other, operator.xor)  # type: ignore[no-any-return]

    def __rxor__(self, other: bool) -> TemporalBool:
        return self._logical_op(other, operator.xor, True)  # type: ignore[no-any-return]

    def __invert__(self: _BoolT) -> _BoolT:
        result = self._empty_like()
        result._set_timeline([(ts, not v) for ts, v in self._timeline])
        return result

    def _ranges(
        self, target: bool, until: TimestampType | None
    ) -> list[tuple[datetime, datetime]]:
        ranges: list[tuple[datetime, datetime]] = []
        start: datetime | None = None

        for ts, value in self._timeline:
            if bool(value) == target and start is None:
                start = ts
            elif bool(value) != target and start is not None:
                ranges.append((start, ts))
                start = None

        if start is not None:
            end = normalize_timestamp(until) if until is not None else now()
            ranges.append((start, max(start, end)))

        return ranges

    def when_true(self, until: TimestampType | None = None) -> list[tuple[datetime, datetime]]:
        """
        Get the ``(start, end)`` time ranges during which the value was True.

        Args:
            until: End for a range that is still open at the last entry
                (default: now). It is clamped to the range's start, so a range
                is never negative (zero-length if ``until`` is before it starts).
                Closed ranges are returned unchanged.
        """
        return self._ranges(True, until)

    def when_false(self, until: TimestampType | None = None) -> list[tuple[datetime, datetime]]:
        """Get the time ranges during which the value was False (see :meth:`when_true`)."""
        return self._ranges(False, until)

    def duration_true(self, until: TimestampType | None = None) -> float:
        """Total seconds when value was True (never negative; see :meth:`when_true`)."""
        return sum((end - start).total_seconds() for start, end in self.when_true(until))

    def duration_false(self, until: TimestampType | None = None) -> float:
        """Total seconds when value was False (never negative; see :meth:`when_true`)."""
        return sum((end - start).total_seconds() for start, end in self.when_false(until))


class TemporalString(Temporal[str]):
    """
    Temporal string type.

    ``+`` concatenates with a ``str`` or another TemporalString (aligned on the
    union of timestamps); other operands raise ``TypeError``.
    """

    def __init__(
        self,
        initial: str | None = None,
        initial_time: TimestampType | None = None,
    ) -> None:
        super().__init__(initial, initial_time, StepInterpolation())

    def _concat(self, other: object, reflected: bool) -> Any:
        if not isinstance(other, (str, TemporalString)):
            return NotImplemented
        result = TemporalString()
        result._set_timeline(self._pointwise(other, operator.add, reflected=reflected))
        return result

    def __add__(self, other: TemporalString | str) -> TemporalString:
        return self._concat(other, reflected=False)  # type: ignore[no-any-return]

    def __radd__(self, other: str) -> TemporalString:
        return self._concat(other, reflected=True)  # type: ignore[no-any-return]

    def upper(self) -> TemporalString:
        """Return new temporal with uppercase values."""
        result = TemporalString()
        result._set_timeline([(ts, v.upper()) for ts, v in self._timeline])
        return result

    def lower(self) -> TemporalString:
        """Return new temporal with lowercase values."""
        result = TemporalString()
        result._set_timeline([(ts, v.lower()) for ts, v in self._timeline])
        return result

    def contains(self, substring: str) -> TemporalBool:
        """Check if substring is in value at each point."""
        result = TemporalBool()
        result._set_timeline([(ts, substring in v) for ts, v in self._timeline])
        return result

    def length(self) -> TemporalInt:
        """Get length at each point."""
        result = TemporalInt()
        result._set_timeline([(ts, len(v)) for ts, v in self._timeline])
        return result
