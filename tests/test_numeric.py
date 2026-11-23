"""Tests for numeric temporal types."""

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
