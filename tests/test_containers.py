"""Tests for temporal container types."""

from datetime import timedelta

import pytest

from chronotype import TemporalDict, TemporalList, TemporalSet


class TestTemporalList:
    def test_create_with_initial(self, base_time):
        t = TemporalList(initial=[1, 2, 3], initial_time=base_time)
        assert t.current() == [1, 2, 3]

    def test_append(self, base_time):
        t = TemporalList(initial=[1], initial_time=base_time)
        t.append(2, base_time + timedelta(days=1))

        assert t.at(base_time) == [1]
        assert t.at(base_time + timedelta(days=1)) == [1, 2]

    def test_extend(self, base_time):
        t = TemporalList(initial=[1], initial_time=base_time)
        t.extend([2, 3], base_time + timedelta(days=1))

        assert t.current() == [1, 2, 3]

    def test_insert(self, base_time):
        t = TemporalList(initial=[1, 3], initial_time=base_time)
        t.insert(1, 2, base_time + timedelta(days=1))

        assert t.current() == [1, 2, 3]

    def test_remove(self, base_time):
        t = TemporalList(initial=[1, 2, 3], initial_time=base_time)
        t.remove(2, base_time + timedelta(days=1))

        assert t.at(base_time) == [1, 2, 3]
        assert t.current() == [1, 3]

    def test_pop(self, base_time):
        t = TemporalList(initial=[1, 2, 3], initial_time=base_time)
        value = t.pop(timestamp=base_time + timedelta(days=1))

        assert value == 3
        assert t.current() == [1, 2]

    def test_history_preserves_copies(self, base_time):
        t = TemporalList(initial=[1], initial_time=base_time)
        t.append(2, base_time + timedelta(days=1))

        history = t.history()
        assert history[0][1] == [1]
        assert history[1][1] == [1, 2]

    def test_contains_at(self, base_time):
        t = TemporalList(initial=[1, 2, 3], initial_time=base_time)
        assert t.contains_at(base_time, 2) is True
        assert t.contains_at(base_time, 5) is False

    def test_get_item_at(self, base_time):
        t = TemporalList(initial=[10, 20, 30], initial_time=base_time)
        assert t.get_item_at(base_time, 1) == 20
        assert t.get_item_at(base_time, -1) == 30

    def test_len_at(self, base_time):
        t = TemporalList(initial=[1, 2, 3], initial_time=base_time)
        t.append(4, base_time + timedelta(days=1))

        assert t.len_at(base_time) == 3
        assert t.len_at(base_time + timedelta(days=1)) == 4

    def test_current_returns_copy(self, base_time):
        t = TemporalList(initial=[1, 2], initial_time=base_time)
        current = t.current()
        current.append(3)

        assert t.current() == [1, 2]

    def test_at_returns_copy(self, base_time):
        t = TemporalList(initial=[1, 2], initial_time=base_time)
        value = t.at(base_time)
        assert value is not None
        value.append(3)

        assert t.at(base_time) == [1, 2]

class TestTemporalDict:
    def test_create_with_initial(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        assert t.current() == {"a": 1}

    def test_set_item(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        t.set_item("b", 2, base_time + timedelta(days=1))

        assert t.at(base_time) == {"a": 1}
        assert t.current() == {"a": 1, "b": 2}

    def test_delete_item(self, base_time):
        t = TemporalDict(initial={"a": 1, "b": 2}, initial_time=base_time)
        t.delete_item("a", base_time + timedelta(days=1))

        assert t.at(base_time) == {"a": 1, "b": 2}
        assert t.current() == {"b": 2}

    def test_update_dict(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        t.update_dict({"b": 2, "c": 3}, base_time + timedelta(days=1))

        assert t.current() == {"a": 1, "b": 2, "c": 3}

    def test_pop_item(self, base_time):
        t = TemporalDict(initial={"a": 1, "b": 2}, initial_time=base_time)
        value = t.pop_item("a", base_time + timedelta(days=1))

        assert value == 1
        assert t.current() == {"b": 2}

    def test_get_item_at(self, base_time):
        t = TemporalDict(initial={"a": 1, "b": 2}, initial_time=base_time)
        assert t.get_item_at(base_time, "a") == 1
        assert t.get_item_at(base_time, "c") is None

    def test_contains_key_at(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        assert t.contains_key_at(base_time, "a") is True
        assert t.contains_key_at(base_time, "b") is False

    def test_keys_values_items_at(self, base_time):
        t = TemporalDict(initial={"a": 1, "b": 2}, initial_time=base_time)

        keys = t.keys_at(base_time)
        values = t.values_at(base_time)
        items = t.items_at(base_time)

        assert keys is not None and set(keys) == {"a", "b"}
        assert values is not None and set(values) == {1, 2}
        assert items is not None and set(items) == {("a", 1), ("b", 2)}

    def test_key_history(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        t.set_item("a", 2, base_time + timedelta(days=1))
        t.set_item("a", 3, base_time + timedelta(days=2))

        history = t.key_history("a")
        assert len(history) == 3
        assert history[0][1] == 1
        assert history[1][1] == 2
        assert history[2][1] == 3

    def test_history_preserves_copies(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        t.set_item("b", 2, base_time + timedelta(days=1))

        history = t.history()
        assert history[0][1] == {"a": 1}
        assert history[1][1] == {"a": 1, "b": 2}

    def test_current_returns_copy(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        current = t.current()
        current["b"] = 2

        assert t.current() == {"a": 1}

    def test_at_returns_copy(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        value = t.at(base_time)
        assert value is not None
        value["b"] = 2

        assert t.at(base_time) == {"a": 1}


class TestEmptyInitialContainer:
    """Regression: an explicitly empty initial container must create an entry."""

    def test_list_empty_initial_creates_entry(self, base_time):
        t = TemporalList(initial=[], initial_time=base_time)
        assert len(t) == 1
        assert t.current() == []
        assert t.at(base_time) == []

    def test_dict_empty_initial_creates_entry(self, base_time):
        t = TemporalDict(initial={}, initial_time=base_time)
        assert len(t) == 1
        assert t.current() == {}
        assert t.at(base_time) == {}

    def test_none_initial_creates_no_entry(self):
        assert len(TemporalList()) == 0
        assert len(TemporalDict()) == 0


class TestDerivedContainers:
    """Regression (#9): slice/merge/deepcopy keep the container type."""

    def test_list_slice_and_merge(self, base_time):
        t = TemporalList(initial=[1], initial_time=base_time)
        t.append(2, base_time + timedelta(days=1))
        sliced = t.slice(base_time, base_time + timedelta(days=1))
        merged = t.merge(TemporalList())
        for derived in (sliced, merged, t.deepcopy()):
            assert isinstance(derived, TemporalList)
            assert derived.contains_at(base_time + timedelta(days=1), 2)

    def test_list_copy_does_not_share_snapshots(self, base_time):
        t = TemporalList(initial=[1], initial_time=base_time)
        for derived in (t.copy(), t.slice(base_time, base_time), t.merge(TemporalList())):
            derived.history()[0][1].append(99)
            assert t.at(base_time) == [1]

    def test_dict_slice_and_merge(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        sliced = t.slice(base_time, base_time)
        merged = t.merge(TemporalDict())
        for derived in (sliced, merged, t.deepcopy()):
            assert isinstance(derived, TemporalDict)
            assert derived.key_history("a") == [(base_time, 1)]


class TestContainerSerializationRoundTrip:
    """Regression (#1): container subclasses round-trip through JSON and dicts."""

    def test_list_round_trip(self, base_time):
        t = TemporalList(initial=[1, 2], initial_time=base_time)
        t.append(3, base_time + timedelta(days=1))
        for restored in (TemporalList.from_json(t.to_json()), TemporalList.from_dict(t.to_dict())):
            assert type(restored) is TemporalList
            assert restored.history() == t.history()
            restored.append(4)
            assert t.current() == [1, 2, 3]

    def test_dict_round_trip(self, base_time):
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        t.set_item("b", [1, 2], base_time + timedelta(days=1))
        for restored in (TemporalDict.from_json(t.to_json()), TemporalDict.from_dict(t.to_dict())):
            assert type(restored) is TemporalDict
            assert restored.history() == t.history()
            assert restored.key_history("b") == [(base_time + timedelta(days=1), [1, 2])]

    def test_list_with_custom_serializer(self, base_time):
        from datetime import date

        def ser(value):
            return {"type": "dates", "value": [d.isoformat() for d in value]}

        def de(payload):
            return [date.fromisoformat(d) for d in payload["value"]]

        t = TemporalList(
            initial=[date(2024, 1, 1)], initial_time=base_time, serializer=ser, deserializer=de
        )
        restored = TemporalList.from_json(t.to_json(), serializer=ser, deserializer=de)
        assert restored.current() == [date(2024, 1, 1)]
        assert restored.to_json() == t.to_json()


def _days(base_time, *offsets):
    return [base_time + timedelta(days=o) for o in offsets]


class TestBackfilledListMutations:
    """Regression (#4): past-dated list mutations build on at(ts) and rebase later snapshots."""

    def test_append_example_from_issue(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalList()
        t.append("a", d1)
        t.append("c", d3)
        t.append("b", d2)
        assert t.history() == [(d1, ["a"]), (d2, ["a", "b"]), (d3, ["a", "c", "b"])]
        assert t.current() == ["a", "c", "b"]

    def test_extend_and_insert(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalList(initial=[1, 3], initial_time=d1)
        t.append(4, d3)
        t.insert(1, 2, d2)
        assert t.at(d2) == [1, 2, 3]
        assert t.at(d3) == [1, 2, 3, 4]
        t.extend([9], d2)
        assert t.at(d2) == [1, 2, 3, 9]
        assert t.at(d3) == [1, 2, 3, 4, 9]

    def test_remove_propagates(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalList(initial=["a", "b"], initial_time=d1)
        t.append("c", d3)
        t.remove("b", d2)
        assert t.at(d1) == ["a", "b"]
        assert t.at(d2) == ["a"]
        assert t.at(d3) == ["a", "c"]

    def test_remove_stops_where_a_later_entry_already_removed_it(self, base_time):
        d1, d2, d3, d4 = _days(base_time, 1, 2, 3, 4)
        t = TemporalList(initial=["a"], initial_time=d1)
        t.remove("a", d3)
        t.append("a", d4)  # re-added later: must survive the backfilled removal
        t.remove("a", d2)
        assert [v for _, v in t.history()] == [["a"], [], [], ["a"]]

    def test_remove_checks_snapshot_at_timestamp(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalList(initial=["a"], initial_time=d1)
        t.append("b", d3)
        before = t.history()
        with pytest.raises(ValueError):
            t.remove("b", d2)  # "b" only exists from d3 on
        assert t.history() == before

    def test_pop_backfill_removes_the_popped_element_later(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalList(initial=["x"], initial_time=d1)
        t.append("y", d3)
        assert t.pop(timestamp=d2) == "x"
        assert t.at(d2) == []
        assert t.at(d3) == ["y"]

    def test_pop_by_index_keeps_position(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalList(initial=["x", "a", "x"], initial_time=d1)
        t.append("b", d3)
        assert t.pop(-1, timestamp=d2) == "x"
        assert t.at(d3) == ["x", "a", "b"]

    def test_pop_errors(self, base_time):
        d0, d1 = _days(base_time, 0, 1)
        t = TemporalList(initial=["x"], initial_time=d1)
        with pytest.raises(IndexError):
            t.pop(timestamp=d0)  # nothing in effect yet
        with pytest.raises(IndexError):
            t.pop(5, timestamp=d1)
        assert len(t) == 1

    def test_clear_list_removes_only_elements_present_at_timestamp(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalList(initial=["a", "b"], initial_time=d1)
        t.append("c", d3)
        t.clear_list(d2)
        assert t.at(d2) == []
        assert t.at(d3) == ["c"]

    def test_mutation_before_first_entry_starts_from_empty(self, base_time):
        d0, d1 = _days(base_time, 0, 1)
        t = TemporalList(initial=["a"], initial_time=d1)
        t.append("z", d0)
        assert t.at(d0) == ["z"]
        assert t.at(d1) == ["a", "z"]

    def test_default_timestamp_builds_on_value_now_not_latest(self, base_time):
        from chronotype.utils import now

        future = now() + timedelta(days=30)
        t = TemporalList(initial=["x"], initial_time=base_time)
        t.append("y", future)
        t.append("z")  # now: builds on ["x"], and is rebased onto the future entry
        assert t.at(now()) == ["x", "z"]
        assert t.at(future) == ["x", "y", "z"]

    def test_set_does_not_touch_other_snapshots(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalList(initial=["a"], initial_time=d1)
        t.append("c", d3)
        t[d2] = ["q"]
        assert t.at(d3) == ["a", "c"]


class TestBackfilledDictMutations:
    """Regression (#4): past-dated dict mutations build on at(ts) and rebase later snapshots."""

    def test_set_item_propagates(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalDict(initial={"a": 1}, initial_time=d1)
        t.set_item("b", 2, d3)
        t.set_item("c", 3, d2)
        assert t.at(d2) == {"a": 1, "c": 3}  # used to include "b"
        assert t.at(d3) == {"a": 1, "b": 2, "c": 3}

    def test_later_change_to_same_key_wins(self, base_time):
        d1, d2, d3, d4 = _days(base_time, 1, 2, 3, 4)
        t = TemporalDict(initial={"a": 1}, initial_time=d1)
        t.set_item("a", 3, d3)
        t.set_item("a", 1, d4)
        t.set_item("a", 2, d2)
        assert [v["a"] for _, v in t.history()] == [1, 2, 3, 1]

    def test_delete_item_propagates_and_validates(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalDict(initial={"a": 1, "b": 2}, initial_time=d1)
        t.set_item("c", 3, d3)
        t.delete_item("a", d2)
        assert t.at(d2) == {"b": 2}
        assert t.at(d3) == {"b": 2, "c": 3}
        with pytest.raises(KeyError):
            t.delete_item("c", d2)  # "c" only exists from d3 on

    def test_update_dict_is_per_key(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalDict(initial={"a": 1}, initial_time=d1)
        t.set_item("a", 5, d3)
        t.update_dict({"a": 2, "b": 2}, d2)
        assert t.at(d2) == {"a": 2, "b": 2}
        assert t.at(d3) == {"a": 5, "b": 2}

    def test_pop_item_propagates(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalDict(initial={"a": 1, "b": 2}, initial_time=d1)
        t.set_item("c", 3, d3)
        assert t.pop_item("a", d2) == 1
        assert t.at(d3) == {"b": 2, "c": 3}
        assert t.pop_item("zzz", d2, default=0) == 0

    def test_pop_item_before_first_entry_returns_default(self, base_time):
        d0, d1 = _days(base_time, 0, 1)
        t = TemporalDict(initial={"a": 1}, initial_time=d1)
        assert t.pop_item("a", d0, default="none") == "none"
        assert len(t) == 1

    def test_clear_dict_keeps_later_changes(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalDict(initial={"a": 1, "b": 2}, initial_time=d1)
        t.update_dict({"b": 9, "c": 3}, d3)
        t.clear_dict(d2)
        assert t.at(d2) == {}
        assert t.at(d3) == {"b": 9, "c": 3}

    def test_default_timestamp_builds_on_value_now_not_latest(self, base_time):
        from chronotype.utils import now

        future = now() + timedelta(days=30)
        t = TemporalDict(initial={"a": 1}, initial_time=base_time)
        t.set_item("f", 1, future)
        t.set_item("n", 1)
        assert t.at(now()) == {"a": 1, "n": 1}
        assert t.at(future) == {"a": 1, "f": 1, "n": 1}


class TestTemporalSet:
    """TemporalSet (#2): same pattern as TemporalList, with per-element backfill."""

    def test_create_and_copies(self, base_time):
        source = {1, 2}
        t = TemporalSet(initial=source, initial_time=base_time)
        source.add(3)
        assert t.current() == {1, 2}
        t.current().add(4)
        t.at(base_time).add(5)
        assert t.at(base_time) == {1, 2}
        assert len(TemporalSet(initial=set(), initial_time=base_time)) == 1
        assert len(TemporalSet()) == 0

    def test_add_discard_remove_update(self, base_time):
        d1, d2, d3, d4 = _days(base_time, 1, 2, 3, 4)
        t = TemporalSet()
        t.add("a", d1)
        t.update(["b", "c"], d2)
        t.discard("a", d3)
        t.remove("b", d4)
        assert [v for _, v in t.history()] == [{"a"}, {"a", "b", "c"}, {"b", "c"}, {"c"}]
        t.discard("zzz", d4)  # absent: no error
        with pytest.raises(KeyError):
            t.remove("zzz", d4)

    def test_contains_at_and_len_at(self, base_time):
        d0, d1, d2 = _days(base_time, 0, 1, 2)
        t = TemporalSet(initial={"a"}, initial_time=d1)
        t.add("b", d2)
        assert t.contains_at(d1, "a") is True
        assert t.contains_at(d1, "b") is False
        assert t.contains_at(d2, "b") is True
        assert t.contains_at(d0, "a") is False
        assert t.len_at(d2) == 2
        assert t.len_at(d0) is None

    def test_default_timestamp_is_now(self):
        t = TemporalSet()
        t.add(1)
        t.add(2)
        assert t.current() == {1, 2}
        assert len(t) == 2

    def test_backfill_add(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalSet(initial={"a"}, initial_time=d1)
        t.add("c", d3)
        t.add("b", d2)
        assert t.at(d2) == {"a", "b"}
        assert t.at(d3) == {"a", "b", "c"}

    def test_backfill_add_does_not_undo_later_discard(self, base_time):
        d1, d2, d3, d4 = _days(base_time, 1, 2, 3, 4)
        t = TemporalSet(initial=set(), initial_time=d1)
        t.add("x", d3)
        t.discard("x", d4)
        t.add("x", d2)
        assert [v for _, v in t.history()] == [set(), {"x"}, {"x"}, set()]

    def test_backfill_discard_and_remove(self, base_time):
        d1, d2, d3, d4 = _days(base_time, 1, 2, 3, 4)
        t = TemporalSet(initial={"a", "b"}, initial_time=d1)
        t.add("c", d3)
        t.discard("a", d2)
        assert t.at(d3) == {"b", "c"}
        t.discard("b", d4)
        t.add("b", d4 + timedelta(days=1))
        t.remove("b", d2 + timedelta(hours=1))
        assert t.at(d3) == {"c"}
        assert t.at(d4 + timedelta(days=1)) == {"b", "c"}  # re-added later

    def test_remove_validates_at_timestamp(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalSet(initial={"a"}, initial_time=d1)
        t.add("b", d3)
        with pytest.raises(KeyError):
            t.remove("b", d2)

    def test_clear_set(self, base_time):
        d1, d2, d3 = _days(base_time, 1, 2, 3)
        t = TemporalSet(initial={"a", "b"}, initial_time=d1)
        t.add("c", d3)
        t.clear_set(d2)
        assert t.at(d2) == set()
        assert t.at(d3) == {"c"}

    def test_serialization_round_trip(self, base_time):
        t = TemporalSet(initial={3, 1, 2}, initial_time=base_time)
        t.discard(2, base_time + timedelta(days=1))
        data = t.to_dict()
        assert data["entries"][0]["value"] == [1, 2, 3]  # sorted, JSON-friendly
        for restored in (TemporalSet.from_json(t.to_json()), TemporalSet.from_dict(data)):
            assert type(restored) is TemporalSet
            assert restored.history() == t.history()

    def test_derived_keep_type(self, base_time):
        t = TemporalSet(initial={1}, initial_time=base_time)
        for derived in (t.copy(), t.slice(base_time, base_time), t.merge(TemporalSet())):
            assert type(derived) is TemporalSet
            derived.history()[0][1].add(99)
            assert t.current() == {1}
