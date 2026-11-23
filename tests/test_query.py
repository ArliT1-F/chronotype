"""Tests for query functionality."""

from datetime import date, datetime, timedelta, timezone

import pytest

from chronotype import TemporalFloat, TemporalInt
from chronotype.exceptions import EmptyTemporalError, InvalidTimestampError


class TestNumericQuery:
    def test_min_max(self, time_series):
        t = TemporalInt()
        t[time_series[0]] = 5
        t[time_series[1]] = 10
        t[time_series[2]] = 3

        query = t.between(time_series[0], time_series[2])
        assert query.min() == 3
        assert query.max() == 10

    def test_sum(self, time_series):
        t = TemporalInt()
        t[time_series[0]] = 10
        t[time_series[1]] = 20
        t[time_series[2]] = 30

        query = t.between(time_series[0], time_series[2])
        assert query.sum() == 60

    def test_simple_average(self, time_series):
        t = TemporalInt()
        t[time_series[0]] = 10
        t[time_series[1]] = 20
        t[time_series[2]] = 30

        query = t.between(time_series[0], time_series[2])
        assert query.simple_average() == 20

    def test_median(self, time_series):
        t = TemporalInt()
        t[time_series[0]] = 10
        t[time_series[1]] = 30
        t[time_series[2]] = 20

        query = t.between(time_series[0], time_series[2])
        assert query.median() == 20

    def test_delta(self, time_series):
        t = TemporalInt()
        t[time_series[0]] = 100
        t[time_series[1]] = 150

        query = t.between(time_series[0], time_series[1])
        assert query.delta() == 50

    def test_empty_query_raises(self, time_series):
        # No entries in range and nothing carried in (range precedes all data).
        t = TemporalInt()
        t[time_series[9]] = 10

        query = t.between(time_series[5], time_series[8])

        with pytest.raises(EmptyTemporalError):
            query.min()
        with pytest.raises(EmptyTemporalError):
            query.max()
        with pytest.raises(EmptyTemporalError):
            query.average()

    def test_exclude_boundaries(self, time_series):
        t = TemporalInt()
        t[time_series[0]] = 1
        t[time_series[1]] = 2
        t[time_series[2]] = 3

        query = t.between(time_series[0], time_series[2], include_start=False, include_end=False)
        assert query.count() == 1
        assert query.values() == [2]

    def test_between_inverted_range_raises(self, time_series):
        t_int = TemporalInt()
        t_int[time_series[0]] = 1

        with pytest.raises(InvalidTimestampError):
            t_int.between(time_series[2], time_series[0])

        t_float = TemporalFloat()
        t_float[time_series[0]] = 1.0

        with pytest.raises(InvalidTimestampError):
            t_float.between(time_series[2], time_series[0])

    def test_filter_in_query(self, time_series):
        t = TemporalInt()
        for i, ts in enumerate(time_series):
            t[ts] = i

        query = t.between(time_series[0], time_series[9])
        filtered = query.filter(lambda x: x > 5)
        assert filtered.values() == [6, 7, 8, 9]

    def test_weighted_average_calculation(self, base_time):
        t = TemporalFloat()
        t[base_time] = 10.0
        t[base_time + timedelta(days=1)] = 20.0

        query = t.between(base_time, base_time + timedelta(days=2))
        avg = query.average()
        assert avg == pytest.approx(15.0, rel=0.1)


class TestCarriedInValue:
    """Regression (#3): range stats include the value active when the range starts."""

    def _salary(self):
        t = TemporalInt()
        t[date(2020, 1, 1)] = 50000
        t[date(2022, 6, 1)] = 65000
        return t

    def test_salary_example(self):
        query = self._salary().between(date(2021, 1, 1), date(2022, 12, 31))
        assert query.min() == 50000
        assert query.max() == 65000
        before = (date(2022, 6, 1) - date(2021, 1, 1)).days
        after = (date(2022, 12, 31) - date(2022, 6, 1)).days
        expected = (50000 * before + 65000 * after) / (before + after)
        assert query.average() == pytest.approx(expected)

    def test_no_entries_in_range_uses_carried_in_value(self, time_series):
        t = TemporalFloat()
        t[time_series[0]] = 10.0
        query = t.between(time_series[5], time_series[8])
        assert query.is_empty()
        assert query.average() == 10.0
        assert query.min() == 10.0
        assert query.max() == 10.0

    def test_single_entry_is_weighted_with_carried_in_value(self, time_series):
        t = TemporalFloat()
        t[time_series[0]] = 10.0
        t[time_series[2]] = 20.0
        # [ts1, ts2) has 10.0 (carried in), [ts2, ts3] has 20.0
        query = t.between(time_series[1], time_series[3])
        assert query.count() == 1
        assert query.average() == pytest.approx(15.0)

    def test_entry_at_range_start_overrides_carried_in_value(self):
        query = self._salary().between(date(2022, 6, 1), date(2022, 12, 31))
        assert query.min() == 65000
        assert query.max() == 65000
        assert query.average() == 65000

    def test_excluded_start_entry_is_the_carried_in_value(self, time_series):
        t = TemporalInt()
        t[time_series[0]] = 10
        t[time_series[1]] = 20
        t[time_series[2]] = 30
        query = t.between(time_series[1], time_series[3], include_start=False)
        assert query.values() == [30]
        # 20 is active on (ts1, ts2), 30 on [ts2, ts3]
        assert query.min() == 20
        assert query.average() == pytest.approx(25.0)

    def test_zero_length_range(self, time_series):
        t = TemporalInt()
        t[time_series[0]] = 7
        mid = time_series[1] + timedelta(hours=3)
        query = t.between(mid, mid)
        assert query.average() == 7
        assert query.min() == query.max() == 7

    def test_range_before_first_entry_still_raises(self, time_series):
        t = TemporalInt()
        t[time_series[5]] = 1
        query = t.between(time_series[0], time_series[3])
        for stat in (query.min, query.max, query.average):
            with pytest.raises(EmptyTemporalError):
                stat()

    def test_partially_preceding_range_ignores_time_before_first_entry(self, time_series):
        t = TemporalFloat()
        t[time_series[2]] = 4.0
        t[time_series[3]] = 8.0
        query = t.between(time_series[0], time_series[4])
        assert query.min() == 4.0
        assert query.average() == pytest.approx(6.0)

    def test_aware_datetimes(self):
        t = TemporalFloat()
        t[datetime(2024, 1, 1, tzinfo=timezone.utc)] = 1.0
        t[datetime(2024, 1, 3, tzinfo=timezone.utc)] = 3.0
        query = t.between(datetime(2024, 1, 2), datetime(2024, 1, 4))
        assert query.average() == pytest.approx(2.0)
