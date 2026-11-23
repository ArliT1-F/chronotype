# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project follows [Semantic Versioning](https://semver.org/).

## [0.1.2] - Unreleased

### Fixed
- **Serialization round-trips for every subclass (#1).** `from_dict()`/`from_json()` called
  `cls(serializer=..., deserializer=...)`, which raised `TypeError` for `TemporalInt`,
  `TemporalFloat`, `TemporalBool`, `TemporalString`, `TemporalList` and `TemporalDict`.
  `to_dict()` now also stores the configuration (`"config": {"interpolation": "linear"}`),
  so a linearly interpolated `TemporalFloat` still interpolates after a round trip.
  Payloads written by 0.1.1 (no `"config"`) still load.
- **Range statistics use the value carried into the range (#3).** On numeric `between()`
  queries, `average()` no longer raises when no entry falls inside the range but a value
  was active the whole time; `average()` with a single entry is now time-weighted with the
  carried-in value instead of returning that entry; `min()`/`max()` include the carried-in
  value. They raise `EmptyTemporalError` only when there are no entries *and* nothing is
  carried in. With `include_start=False`, an entry exactly at `start` is now the carried-in
  value.
- **Backfilled container mutations (#4).** `TemporalList` and `TemporalDict` mutation
  methods given a past timestamp built on `current()`; they now build on `at(ts)` (or an
  empty container), validate against it, and rebase later snapshots: list additions are
  applied to every later snapshot, list removals until a later snapshot no longer holds the
  element, and dict changes per key until a later snapshot changed that key.
  E.g. `append(a, d1)`, `append(c, d3)`, `append(b, d2)` gives `d2=[a, b]`, `d3=[a, c, b]`.
  The rules are documented in the `chronotype.containers` module docstring.
- **Empty initial containers (#5).** `TemporalList(initial=[])` and
  `TemporalDict(initial={})` now record an entry.
- **Mixed numeric types (#6).** `TemporalInt + 1.5` no longer crashes and returns a
  `TemporalFloat`; `TemporalInt <op> TemporalFloat` (either order) returns a
  `TemporalFloat` instead of a `TemporalInt` holding floats; `TemporalInt ** -1` promotes.
  `bool` is rejected as a numeric scalar, and unsupported operands make operators return
  `NotImplemented` (so Python raises `TypeError`) instead of raising `AttributeError`. The
  same applies to `TemporalBool` (`&`, `|`, `^`) and `TemporalString` (`+`).
- **Division by zero no longer corrupts results (#8).** A zero divisor used to drop the
  point, so step interpolation carried the previous quotient forward (`10 / 0` showed as
  `5.0`). Float results now store `math.nan` at that timestamp (`/` always; `//` and `%`
  when the result is a `TemporalFloat`; `0 ** -n`). Integer `//` and `%` cannot hold NaN
  and raise `ZeroDivisionError` (use `.to_float()` first to get NaN).
- **`slice()`, `merge()`, `copy()` and `deepcopy()` keep the subclass (#9)**, its
  interpolation strategy, serializer/deserializer and any subclass attributes (a sliced
  `TemporalInt` is a `TemporalInt` with `.between().average()`).
- **`when_true()`/`when_false()` never return negative ranges (#10).** A range still open
  at the last entry ends at the new optional `until` argument (default: now), clamped to
  the range start. `duration_true()`/`duration_false()` accept `until` too.
- **Integer linear interpolation rounds instead of truncating (#11).** `int()` sent -1.5 to
  -1 and 2.75 to 2; results are now `round()`ed (ties to even, as Python's `round()`), and
  remain ints.
- Unpickled temporals lost their serializer attributes, so `to_json()` raised
  `AttributeError`.

### Added
- `TemporalSet` with `add`/`discard`/`remove`/`update`/`clear_set` (optional timestamp,
  same backfill semantics as `TemporalDict`), `contains_at`/`len_at`, stored copies and
  JSON support (#2).
- `TemporalString`, `NearestInterpolation` and `TemporalSet` are exported from
  `chronotype` (#2).
- `interpolation=` argument on `TemporalInt` and `TemporalFloat` (#12).
- `Temporal.eq()`/`Temporal.ne()` returning a point-by-point `TemporalBool` (#14).
- `Temporal.set_now(value)` to record a value at the current time (#14).
- `from_dict()`/`from_json()` accept `interpolation=` to restore custom strategies, which
  are stored by class name.
- `TemporalList`/`TemporalDict` accept keyword-only `serializer`/`deserializer`.
- `NumericTemporalQuery.value_before_range`.
- `TemporalFloat` gains `//` and `%`; both numeric types now support the full operator set
  including reflected forms (`10 / t`, `2 ** t`, ...) and unary `+`.
- A test that runs every code example in `README.md`.

### Changed
- All numeric operators share one implementation (#7). Arithmetic results keep the
  interpolation strategy of the temporal operand they were called on, and
  `TemporalInt.to_float()` keeps it too.
- `__eq__` is documented as structural equality returning a `bool` (#14).
- Precise operator return types for type checkers (e.g. `TemporalInt + int` is a
  `TemporalInt`, `TemporalInt + float` a `TemporalFloat`), and `copy()`/`slice()`/
  `merge()`/`from_json()` are typed to return the class they are called on.

### Deprecated
- `TemporalFloat(interpolate=True/False)` (keyword or third positional argument). Use
  `interpolation=LinearInterpolation()` / `StepInterpolation()`. Emits
  `DeprecationWarning` (#12).

### Removed
- The unused `chronotype.exceptions.ImmutableTemporalError` (#14).

### Performance
- Lookups are `O(log n)` (#13): a cached timestamp index replaces rebuilding the timestamp
  list on every `at()`/`set()`, and `between()`/`slice()`/`in` use binary search instead of
  scanning. Appending 20k entries in order went from about 3 s to about 0.01 s.

### Packaging
- The sdist now includes the whole test suite, including `tests/conftest.py`. The 0.1.1
  sdist omitted it, so most tests failed with "fixture 'base_time' not found".
  `CHANGELOG.md` is included as well.
