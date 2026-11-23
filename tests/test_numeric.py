"""Tests for numeric temporal types."""

import math
import operator
from datetime import timedelta

import pytest

from chronotype import LinearInterpolation, TemporalBool, TemporalFloat, TemporalInt


class TestTemporalInt:
    def test_basic_operations(self, base_time):
        t = TemporalInt(initial=10, initial_time=base_time)
        assert t.current() == 10

    def test_addition(self, base_time):
        t = TemporalInt()
        t[base_time] = 10
        t[base_time + timedelta(days=1)] = 20

        result = t + 5
        assert result.at(base_time) == 15
        assert result.at(base_time + timedelta(days=1)) == 25

    def test_addition_temporal(self, base_time):
        t1 = TemporalInt()
        t1[base_time] = 10

        t2 = TemporalInt()
        t2[base_time] = 5

        result = t1 + t2
        assert result.at(base_time) == 15

    def test_subtraction(self, base_time):
        t = TemporalInt()
        t[base_time] = 20
        result = t - 5
        assert result.at(base_time) == 15

    def test_multiplication(self, base_time):
        t = TemporalInt()
        t[base_time] = 10
        result = t * 3
        assert result.at(base_time) == 30

    def test_division_returns_float(self, base_time):
        t = TemporalInt()
        t[base_time] = 10
        result = t / 4
        assert isinstance(result, TemporalFloat)
        assert result.at(base_time) == 2.5

    def test_floor_division(self, base_time):
        t = TemporalInt()
        t[base_time] = 10
        result = t // 3
        assert result.at(base_time) == 3

    def test_modulo(self, base_time):
        t = TemporalInt()
        t[base_time] = 10
        result = t % 3
        assert result.at(base_time) == 1

    def test_power(self, base_time):
        t = TemporalInt()
        t[base_time] = 2
        result = t**3
        assert result.at(base_time) == 8

    def test_negation(self, base_time):
        t = TemporalInt()
        t[base_time] = 10
        result = -t
        assert result.at(base_time) == -10

    def test_abs(self, base_time):
        t = TemporalInt()
        t[base_time] = -10
        result = abs(t)
        assert result.at(base_time) == 10

    def test_comparison(self, base_time):
        t = TemporalInt()
        t[base_time] = 10

        result = t > 5
        assert isinstance(result, TemporalBool)
        assert result.at(base_time) is True

        result = t < 5
        assert result.at(base_time) is False

    def test_numeric_query_aggregations(self, time_series):
        t = TemporalInt()
        t[time_series[0]] = 10
        t[time_series[1]] = 20
        t[time_series[2]] = 30

        query = t.between(time_series[0], time_series[2])
        assert query.min() == 10
        assert query.max() == 30
        assert query.sum() == 60
        assert query.simple_average() == 20


class TestTemporalFloat:
    def test_interpolation_disabled(self, base_time):
        with pytest.warns(DeprecationWarning):
            t = TemporalFloat(interpolate=False)
        t[base_time] = 10.0
        t[base_time + timedelta(hours=2)] = 20.0

        mid = base_time + timedelta(hours=1)
        assert t.at(mid) == 10.0

    def test_interpolation_enabled(self, base_time):
        with pytest.warns(DeprecationWarning):
            t = TemporalFloat(interpolate=True)
        t[base_time] = 10.0
        t[base_time + timedelta(hours=2)] = 20.0

        mid = base_time + timedelta(hours=1)
        assert t.at(mid) == 15.0

    def test_weighted_average(self, base_time):
        t = TemporalFloat()
        t[base_time] = 10.0
        t[base_time + timedelta(days=1)] = 30.0

        query = t.between(base_time, base_time + timedelta(days=2))
        avg = query.average()
        assert avg == pytest.approx(20.0, rel=0.01)

    def test_rate_of_change(self, base_time):
        t = TemporalFloat()
        t[base_time] = 0.0
        t[base_time + timedelta(seconds=10)] = 100.0

        query = t.between(base_time, base_time + timedelta(seconds=10))
        assert query.rate_of_change() == pytest.approx(10.0)

    def test_statistics(self, time_series):
        t = TemporalFloat()
        t[time_series[0]] = 10.0
        t[time_series[1]] = 20.0
        t[time_series[2]] = 30.0

        query = t.between(time_series[0], time_series[2])
        assert query.median() == 20.0
        assert query.variance() == pytest.approx(66.666, rel=0.01)


class TestTemporalBool:
    def test_logical_and(self, base_time):
        t = TemporalBool()
        t[base_time] = True

        result = t & True
        assert result.at(base_time) is True

        result = t & False
        assert result.at(base_time) is False

    def test_logical_or(self, base_time):
        t = TemporalBool()
        t[base_time] = False

        result = t | True
        assert result.at(base_time) is True

        result = t | False
        assert result.at(base_time) is False

    def test_logical_xor(self, base_time):
        t = TemporalBool()
        t[base_time] = True

        result = t ^ True
        assert result.at(base_time) is False

        result = t ^ False
        assert result.at(base_time) is True

    def test_invert(self, base_time):
        t = TemporalBool()
        t[base_time] = True
        result = ~t
        assert result.at(base_time) is False

    def test_when_true(self, base_time):
        t = TemporalBool()
        t[base_time] = True
        t[base_time + timedelta(hours=2)] = False
        t[base_time + timedelta(hours=4)] = True

        ranges = t.when_true()
        assert len(ranges) >= 1

    def test_duration_true(self, base_time):
        t = TemporalBool()
        t[base_time] = True
        t[base_time + timedelta(hours=2)] = False

        duration = t.duration_true()
        assert duration >= 7200


class TestDerivedNumericTemporals:
    """Regression (#9): slice/merge/copy keep TemporalInt/TemporalFloat behaviour."""

    def test_int_slice_is_temporal_int(self, time_series):
        t = TemporalInt()
        for i, ts in enumerate(time_series):
            t[ts] = i * 10
        sliced = t.slice(time_series[2], time_series[5])
        assert isinstance(sliced, TemporalInt)
        assert sliced.between(time_series[2], time_series[5]).average() == pytest.approx(30.0)
        assert isinstance(sliced + 1, TemporalInt)

    def test_int_merge_is_temporal_int(self, time_series):
        a = TemporalInt()
        a[time_series[0]] = 1
        b = TemporalInt()
        b[time_series[1]] = 3
        merged = a.merge(b)
        assert isinstance(merged, TemporalInt)
        assert merged.between(time_series[0], time_series[2]).max() == 3

    def test_float_slice_merge_copy_keep_interpolation(self, base_time):
        t = TemporalFloat(interpolation=LinearInterpolation())
        t[base_time] = 0.0
        t[base_time + timedelta(hours=2)] = 20.0
        t[base_time + timedelta(hours=4)] = 40.0
        mid = base_time + timedelta(hours=1)

        for derived in (
            t.copy(),
            t.deepcopy(),
            t.slice(base_time, base_time + timedelta(hours=2)),
            t.merge(TemporalFloat()),
        ):
            assert isinstance(derived, TemporalFloat)
            assert derived.at(mid) == pytest.approx(10.0)

    def test_bool_and_string_copy_keep_type(self, base_time):
        from chronotype.numeric import TemporalString

        b = TemporalBool(initial=True, initial_time=base_time)
        s = TemporalString(initial="x", initial_time=base_time)
        assert isinstance(b.slice(base_time, base_time), TemporalBool)
        assert isinstance(s.merge(TemporalString()), TemporalString)
        assert isinstance(s.deepcopy(), TemporalString)


class TestInterpolationParameter:
    """Regression (#12): numeric types take ``interpolation=``; ``interpolate=`` is deprecated."""

    def _check_linear(self, t, base_time, expected_mid):
        t[base_time] = 0
        t[base_time + timedelta(hours=2)] = 20
        assert t.at(base_time + timedelta(hours=1)) == expected_mid

    def test_float_accepts_interpolation(self, base_time, recwarn):
        self._check_linear(TemporalFloat(interpolation=LinearInterpolation()), base_time, 10.0)
        assert not [w for w in recwarn if issubclass(w.category, DeprecationWarning)]

    def test_int_accepts_interpolation(self, base_time):
        self._check_linear(TemporalInt(interpolation=LinearInterpolation()), base_time, 10)

    def test_int_accepts_nearest_interpolation(self, base_time):
        from chronotype.interpolation import NearestInterpolation

        t = TemporalInt(interpolation=NearestInterpolation())
        t[base_time] = 1
        t[base_time + timedelta(hours=2)] = 2
        assert t.at(base_time + timedelta(minutes=30)) == 1
        assert t.at(base_time + timedelta(minutes=90)) == 2

    def test_default_is_step_without_warning(self, base_time, recwarn):
        self._check_linear(TemporalFloat(), base_time, 0)
        self._check_linear(TemporalInt(), base_time, 0)
        assert not [w for w in recwarn if issubclass(w.category, DeprecationWarning)]

    def test_interpolate_keyword_is_deprecated_alias(self, base_time):
        with pytest.warns(DeprecationWarning, match="interpolation=LinearInterpolation"):
            t = TemporalFloat(interpolate=True)
        self._check_linear(t, base_time, 10.0)
        with pytest.warns(DeprecationWarning):
            t = TemporalFloat(interpolate=False)
        self._check_linear(t, base_time, 0)

    def test_positional_bool_is_deprecated_alias(self, base_time):
        with pytest.warns(DeprecationWarning):
            t = TemporalFloat(None, None, True)
        self._check_linear(t, base_time, 10.0)

    def test_both_arguments_rejected(self):
        with pytest.raises(TypeError):
            TemporalFloat(interpolation=LinearInterpolation(), interpolate=True)

    def test_operations_do_not_warn_and_keep_interpolation(self, base_time, recwarn):
        t = TemporalFloat(interpolation=LinearInterpolation())
        t[base_time] = 0.0
        t[base_time + timedelta(hours=2)] = 20.0
        result = (t + 1.0) * 2.0
        assert result.at(base_time + timedelta(hours=1)) == pytest.approx(22.0)
        assert not [w for w in recwarn if issubclass(w.category, DeprecationWarning)]


class TestNumericSerializationRoundTrip:
    """Regression (#1): every numeric subclass round-trips through JSON and dicts."""

    def _populate(self, cls, values, time_series, **kwargs):
        t = cls(**kwargs)
        for ts, v in zip(time_series, values):
            t[ts] = v
        return t

    @pytest.mark.parametrize(
        "cls_name, values",
        [
            ("TemporalInt", [1, -2, 3]),
            ("TemporalFloat", [1.5, -2.25, 3.0]),
            ("TemporalBool", [True, False, True]),
            ("TemporalString", ["a", "", "c"]),
        ],
    )
    def test_round_trip(self, cls_name, values, time_series):
        import chronotype

        cls = getattr(chronotype.numeric, cls_name)
        t = self._populate(cls, values, time_series)

        from_json = cls.from_json(t.to_json())
        from_dict = cls.from_dict(t.to_dict())
        for restored in (from_json, from_dict):
            assert type(restored) is cls
            assert restored == t
            assert restored.history() == t.history()

    def test_linear_float_still_interpolates(self, base_time):
        t = TemporalFloat(interpolation=LinearInterpolation())
        t[base_time] = 10.0
        t[base_time + timedelta(hours=2)] = 20.0
        mid = base_time + timedelta(hours=1)

        restored = TemporalFloat.from_json(t.to_json())
        assert restored.at(mid) == pytest.approx(15.0)
        assert TemporalFloat.from_dict(t.to_dict()).at(mid) == pytest.approx(15.0)

    def test_deprecated_interpolate_flag_survives_round_trip(self, base_time):
        with pytest.warns(DeprecationWarning):
            t = TemporalFloat(interpolate=True)
        t[base_time] = 0.0
        t[base_time + timedelta(hours=2)] = 2.0
        restored = TemporalFloat.from_json(t.to_json())
        assert restored.at(base_time + timedelta(hours=1)) == pytest.approx(1.0)

    def test_step_float_stays_step(self, base_time):
        t = TemporalFloat()
        t[base_time] = 10.0
        t[base_time + timedelta(hours=2)] = 20.0
        restored = TemporalFloat.from_json(t.to_json())
        assert restored.at(base_time + timedelta(hours=1)) == 10.0

    def test_int_interpolation_round_trip(self, base_time):
        from chronotype.interpolation import NearestInterpolation

        t = TemporalInt(interpolation=NearestInterpolation())
        t[base_time] = 1
        t[base_time + timedelta(hours=2)] = 2
        restored = TemporalInt.from_json(t.to_json())
        assert restored.at(base_time + timedelta(minutes=90)) == 2

    def test_restored_supports_arithmetic_and_queries(self, time_series):
        t = self._populate(TemporalInt, [10, 20, 30], time_series)
        restored = TemporalInt.from_json(t.to_json())
        assert (restored + 1).at(time_series[1]) == 21
        assert restored.between(time_series[0], time_series[2]).max() == 30


class TestIntLinearInterpolationRounding:
    """Regression (#11): linear interpolation of ints rounds instead of truncating."""

    def _linear_int(self, base_time, a, b):
        t = TemporalInt(interpolation=LinearInterpolation())
        t[base_time] = a
        t[base_time + timedelta(hours=4)] = b
        return t

    def test_negative_values_round_not_truncate(self, base_time):
        t = self._linear_int(base_time, 0, -4)
        # 3/4 of the way from 0 to -4 is -3.0; 3/8 of the way is -1.5
        assert t.at(base_time + timedelta(hours=3)) == -3
        assert t.at(base_time + timedelta(minutes=90)) == -2  # int() gave -1
        assert t.at(base_time + timedelta(minutes=165)) == -3  # -2.75; int() gave -2

    def test_positive_values_round_to_nearest(self, base_time):
        t = self._linear_int(base_time, 0, 4)
        assert t.at(base_time + timedelta(minutes=165)) == 3  # 2.75; int() gave 2
        assert t.at(base_time + timedelta(minutes=45)) == 1  # 0.75; int() gave 0

    def test_ties_round_half_to_even(self, base_time):
        t = self._linear_int(base_time, 0, 1)
        assert t.at(base_time + timedelta(hours=2)) == 0  # 0.5 -> 0
        t = self._linear_int(base_time, 1, 2)
        assert t.at(base_time + timedelta(hours=2)) == 2  # 1.5 -> 2

    def test_result_is_int(self, base_time):
        value = self._linear_int(base_time, 0, 3).at(base_time + timedelta(hours=1))
        assert type(value) is int


_ARITH_OPS = [
    operator.add,
    operator.sub,
    operator.mul,
    operator.truediv,
    operator.floordiv,
    operator.mod,
    operator.pow,
]
_LEFT = {"int": [3, 7, 2], "float": [3.5, 7.25, 2.0]}
_RIGHT = {"int": [2, 5, 4], "float": [1.5, 2.5, 4.0]}


def _operand(kind, values, time_series):
    """A TemporalInt/TemporalFloat over ``values`` or the first value as a scalar."""
    if kind == "TemporalInt":
        t = TemporalInt()
    elif kind == "TemporalFloat":
        t = TemporalFloat()
    else:
        return values[0]
    for ts, v in zip(time_series, values):
        t[ts] = v
    return t


class TestOperatorSemantics:
    """Regression (#6/#7): one operator implementation matching Python's numeric rules."""

    @pytest.mark.parametrize("op", _ARITH_OPS, ids=lambda o: o.__name__)
    @pytest.mark.parametrize(
        "left, right",
        [
            (left, right)
            for left in ("TemporalInt", "TemporalFloat", "int", "float")
            for right in ("TemporalInt", "TemporalFloat", "int", "float")
            if "Temporal" in left or "Temporal" in right
        ],
    )
    def test_matches_python_scalar_semantics(self, op, left, right, time_series):
        lvals = _LEFT["float" if "Float" in left or left == "float" else "int"]
        rvals = _RIGHT["float" if "Float" in right or right == "float" else "int"]
        if left in ("int", "float"):
            lvals = [lvals[0]] * 3
        if right in ("int", "float"):
            rvals = [rvals[0]] * 3

        result = op(_operand(left, lvals, time_series), _operand(right, rvals, time_series))

        expected = [op(a, b) for a, b in zip(lvals, rvals)]
        expected_cls = TemporalFloat if any(isinstance(v, float) for v in expected) else TemporalInt
        assert type(result) is expected_cls
        assert result.values() == pytest.approx(expected)
        assert result.timestamps() == time_series[:3]

    def test_int_plus_float_scalar_promotes(self, base_time):
        t = TemporalInt(initial=1, initial_time=base_time)
        for result in (t + 1.5, 1.5 + t, t - 0.5, t * 2.5, t**0.5):
            assert isinstance(result, TemporalFloat)
        assert (t + 1.5).at(base_time) == 2.5
        assert (10.0 - t).at(base_time) == 9.0

    def test_int_with_temporal_float_promotes(self, base_time):
        i = TemporalInt(initial=3, initial_time=base_time)
        f = TemporalFloat(initial=0.5, initial_time=base_time)
        for result in (i + f, f + i, i - f, i * f, i / f, i // f, i % f, i**f, f**i):
            assert isinstance(result, TemporalFloat)
        assert (i + f).at(base_time) == 3.5

    def test_int_with_int_stays_int(self, base_time):
        a = TemporalInt(initial=7, initial_time=base_time)
        b = TemporalInt(initial=2, initial_time=base_time)
        for result in (a + b, a - b, a * b, a // b, a % b, a**b, -a, +a, abs(a), a + 1, 1 + a):
            assert type(result) is TemporalInt
        assert isinstance(a / b, TemporalFloat)

    def test_int_negative_power_promotes(self, base_time):
        t = TemporalInt(initial=2, initial_time=base_time)
        result = t**-1
        assert isinstance(result, TemporalFloat)
        assert result.at(base_time) == 0.5

    @pytest.mark.parametrize("op", _ARITH_OPS, ids=lambda o: o.__name__)
    def test_bool_scalar_rejected(self, op, base_time):
        for t in (TemporalInt(initial=1, initial_time=base_time),
                  TemporalFloat(initial=1.0, initial_time=base_time)):
            with pytest.raises(TypeError):
                op(t, True)
            with pytest.raises(TypeError):
                op(False, t)

    def test_bool_comparison_rejected(self, base_time):
        t = TemporalInt(initial=1, initial_time=base_time)
        with pytest.raises(TypeError):
            t < True  # noqa: B015
        with pytest.raises(TypeError):
            t >= TemporalBool(initial=True, initial_time=base_time)  # noqa: B015

    @pytest.mark.parametrize("other", ["x", None, [1], {"a": 1}])
    def test_unsupported_operands_raise_type_error(self, other, base_time):
        t = TemporalInt(initial=1, initial_time=base_time)
        assert t.__add__(other) is NotImplemented
        assert t.__rsub__(other) is NotImplemented
        assert t.__lt__(other) is NotImplemented
        with pytest.raises(TypeError):
            t + other
        with pytest.raises(TypeError):
            other * t
        with pytest.raises(TypeError):
            t < other  # noqa: B015

    def test_unsupported_temporal_operands_raise_type_error(self, base_time):
        from chronotype.numeric import TemporalString

        i = TemporalInt(initial=1, initial_time=base_time)
        s = TemporalString(initial="a", initial_time=base_time)
        b = TemporalBool(initial=True, initial_time=base_time)
        with pytest.raises(TypeError):
            i + s
        with pytest.raises(TypeError):
            s + i
        with pytest.raises(TypeError):
            i * b
        with pytest.raises(TypeError):
            b & 1
        with pytest.raises(TypeError):
            1 | b
        with pytest.raises(TypeError):
            s + 1
        with pytest.raises(TypeError):
            1 + s

    def test_timestamp_alignment(self, time_series):
        a = TemporalInt()
        a[time_series[0]] = 1
        a[time_series[2]] = 3
        b = TemporalInt()
        b[time_series[1]] = 10
        b[time_series[3]] = 30
        result = a + b
        # nothing at time_series[0]: b has no value yet
        assert result.history() == [
            (time_series[1], 11),
            (time_series[2], 13),
            (time_series[3], 33),
        ]

    def test_result_keeps_interpolation_of_temporal_operand(self, base_time):
        f = TemporalFloat(interpolation=LinearInterpolation())
        f[base_time] = 0.0
        f[base_time + timedelta(hours=2)] = 2.0
        mid = base_time + timedelta(hours=1)
        assert (f + 1).at(mid) == pytest.approx(2.0)
        assert (1 + f).at(mid) == pytest.approx(2.0)
        assert (-f).at(mid) == pytest.approx(-1.0)

        i = TemporalInt(interpolation=LinearInterpolation())
        i[base_time] = 0
        i[base_time + timedelta(hours=2)] = 20
        assert (i + 0.5).at(mid) == pytest.approx(10.5)
        assert i.to_float().at(mid) == pytest.approx(10.0)

    def test_comparisons_mixed(self, base_time):
        i = TemporalInt(initial=2, initial_time=base_time)
        f = TemporalFloat(initial=2.5, initial_time=base_time)
        assert (i < f).at(base_time) is True
        assert (f <= i).at(base_time) is False
        assert (i > 1.5).at(base_time) is True
        assert (f >= 2.5).at(base_time) is True
        assert isinstance(i < f, TemporalBool)

    def test_float_has_floordiv_and_mod(self, base_time):
        f = TemporalFloat(initial=7.5, initial_time=base_time)
        assert (f // 2).at(base_time) == 3.0
        assert (f % 2).at(base_time) == 1.5
        assert (8 // f).at(base_time) == 1.0
        assert (2**f).at(base_time) == pytest.approx(2**7.5)


class TestDivisionByZero:
    """Regression (#8): a zero divisor must not carry the previous quotient forward."""

    def _series(self, cls, values, time_series):
        t = cls()
        for ts, v in zip(time_series, values):
            t[ts] = v
        return t

    def test_float_division_by_temporal_zero_is_nan(self, time_series):
        a = self._series(TemporalFloat, [10.0, 10.0, 10.0], time_series)
        b = self._series(TemporalFloat, [2.0, 0.0, 5.0], time_series)
        result = a / b
        assert result.at(time_series[0]) == 5.0
        assert math.isnan(result.at(time_series[1]))  # used to show 5.0
        assert result.at(time_series[2]) == 2.0
        assert len(result) == 3

    def test_int_true_division_by_zero_is_nan(self, time_series):
        a = self._series(TemporalInt, [10, 10], time_series)
        b = self._series(TemporalInt, [2, 0], time_series)
        assert math.isnan((a / b).at(time_series[1]))
        assert all(math.isnan(v) for v in (a / 0).values())

    def test_reflected_division_by_zero_is_nan(self, time_series):
        t = self._series(TemporalFloat, [2.0, 0.0], time_series)
        result = 10 / t
        assert result.at(time_series[0]) == 5.0
        assert math.isnan(result.at(time_series[1]))

    @pytest.mark.parametrize("op", [operator.floordiv, operator.mod], ids=lambda o: o.__name__)
    def test_float_floordiv_and_mod_by_zero_is_nan(self, op, time_series):
        a = self._series(TemporalFloat, [10.0, 10.0], time_series)
        b = self._series(TemporalFloat, [3.0, 0.0], time_series)
        result = op(a, b)
        assert result.at(time_series[0]) == op(10.0, 3.0)
        assert math.isnan(result.at(time_series[1]))
        assert all(math.isnan(v) for v in op(a, 0).values())
        i = self._series(TemporalInt, [10, 10], time_series)
        assert math.isnan(op(i, b).at(time_series[1]))  # promoted to float -> NaN

    @pytest.mark.parametrize("op", [operator.floordiv, operator.mod], ids=lambda o: o.__name__)
    def test_int_floordiv_and_mod_by_zero_raises(self, op, time_series):
        a = self._series(TemporalInt, [10, 10], time_series)
        b = self._series(TemporalInt, [3, 0], time_series)
        with pytest.raises(ZeroDivisionError, match="to_float"):
            op(a, b)
        with pytest.raises(ZeroDivisionError):
            op(a, 0)
        with pytest.raises(ZeroDivisionError):
            op(10, self._series(TemporalInt, [0], time_series))

    def test_zero_to_negative_power_is_nan(self, time_series):
        t = self._series(TemporalInt, [0, 2], time_series)
        result = t**-1
        assert isinstance(result, TemporalFloat)
        assert math.isnan(result.at(time_series[0]))
        assert result.at(time_series[1]) == 0.5


class TestBoolRangesUntil:
    """Regression (#10): open ranges end at ``until`` and never have negative length."""

    def test_future_start_has_zero_duration(self):
        from chronotype.utils import now

        start = now() + timedelta(days=1)
        t = TemporalBool()
        t[start] = True
        assert t.when_true() == [(start, start)]
        assert t.duration_true() == 0.0
        t2 = TemporalBool()
        t2[start] = False
        assert t2.duration_false() == 0.0

    def test_until_ends_open_range(self, base_time):
        t = TemporalBool()
        t[base_time] = True
        t[base_time + timedelta(hours=2)] = False
        t[base_time + timedelta(hours=4)] = True
        until = base_time + timedelta(hours=5)

        assert t.when_true(until=until) == [
            (base_time, base_time + timedelta(hours=2)),
            (base_time + timedelta(hours=4), until),
        ]
        assert t.duration_true(until=until) == 3 * 3600
        assert t.when_false(until=until) == [
            (base_time + timedelta(hours=2), base_time + timedelta(hours=4))
        ]
        assert t.duration_false(until=until) == 2 * 3600

    def test_until_before_open_range_is_clamped(self, base_time):
        t = TemporalBool()
        t[base_time] = False
        t[base_time + timedelta(hours=4)] = True
        until = base_time + timedelta(hours=1)
        assert t.when_true(until=until) == [
            (base_time + timedelta(hours=4), base_time + timedelta(hours=4))
        ]
        assert t.duration_true(until=until) == 0.0
        # closed ranges are not truncated by ``until``
        assert t.duration_false(until=until) == 4 * 3600

    def test_until_accepts_dates_and_naive_datetimes(self, base_time):
        from datetime import date, datetime

        t = TemporalBool()
        t[base_time] = True
        assert t.duration_true(until=date(2024, 1, 2)) == 86400
        assert t.duration_true(until=datetime(2024, 1, 1, 12)) == 43200

    def test_default_until_is_now(self, base_time):
        from chronotype.utils import now

        t = TemporalBool()
        t[base_time] = True
        before = now()
        (start, end), = t.when_true()
        assert start == base_time
        assert before <= end <= now()

    def test_empty(self):
        assert TemporalBool().when_true(until=None) == []
        assert TemporalBool().duration_false() == 0.0
