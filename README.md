# Chronotype

**Temporal-native data types for Python.** Every value inherently carries its full history.

[![PyPI version](https://badge.fury.io/py/chronotype.svg)](https://badge.fury.io/py/chronotype)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Installation

```bash
pip install chronotype
```

## Quick Start

```python
from datetime import date, datetime
from chronotype import LinearInterpolation, TemporalFloat, TemporalInt, TemporalString

# Create a temporal integer that tracks salary over time
salary = TemporalInt()
salary[date(2020, 1, 1)] = 50000
salary[date(2022, 6, 1)] = 65000
salary[date(2024, 1, 1)] = 80000

# Query at specific points in time
print(salary.at(date(2021, 3, 15)))  # 50000
print(salary.at(date(2023, 1, 1)))   # 65000

# Get the current (latest) value
print(salary.current())  # 80000

# Analyze over time ranges
query = salary.between(date(2020, 1, 1), date(2024, 1, 1))
print(query.average())   # Weighted average by duration
print(query.min())       # 50000
print(query.max())       # 80000

# Interpolation for numeric types
temp = TemporalFloat(interpolation=LinearInterpolation())
temp[datetime(2024, 1, 1, 0, 0)] = 20.0
temp[datetime(2024, 1, 1, 12, 0)] = 25.0

print(temp.at(datetime(2024, 1, 1, 6, 0)))  # 22.5 (interpolated)

# Temporal strings
status = TemporalString()
status[date(2024, 1, 1)] = "draft"
status[date(2024, 2, 1)] = "published"
print(status.upper().at(date(2024, 1, 15)))  # 'DRAFT'
```

## Features

- **Temporal Primitives**: `TemporalInt`, `TemporalFloat`, `TemporalString`, `TemporalBool`
- **Temporal Containers**: `TemporalList`, `TemporalDict`, `TemporalSet`
- **Generic Wrapper**: `Temporal[T]` for any type
- **Time Queries**: `.at()`, `.between()`, `.current()`, `.first()`
- **Aggregations**: `.average()`, `.min()`, `.max()`, `.sum()`, `.count()`
- **Interpolation**: step (default), linear and nearest-neighbour
- **History**: `.history()`, `.changes()`, `.rollback()`, `.slice()`, `.merge()`
- **Arithmetic**: Full operator support for numeric temporals, with int → float promotion
- **Serialization**: JSON and pickle support
- **Fast**: `O(log n)` lookups, so histories with hundreds of thousands of entries stay quick

All timestamps are normalized to timezone-aware UTC; naive datetimes and dates are treated as UTC.

## Documentation

### Creating Temporal Values
```python
from datetime import datetime
from chronotype import Temporal, TemporalInt

# With initial value (uses current time)
count = TemporalInt(initial=0)

# Empty, to be populated
score = TemporalInt()

# Record a value at the current time
score.set_now(10)

# Generic temporal for custom types
from dataclasses import dataclass

@dataclass
class User:
    name: str
    active: bool

user = Temporal[User]()
user[datetime.now()] = User("Alice", True)
```

### Time Range Queries
```python
query = salary.between(date(2020, 1, 1), date(2023, 12, 31))

# Aggregations
query.average()  # weighted by how long each value was active
query.sum()
query.min()
query.max()
query.count()

# Get all entries
query.entries()     # List of (timestamp, value) tuples
query.values()      # List of values only
query.timestamps()  # List of timestamps only
```

`min()`, `max()` and `average()` also account for the value *carried into* the range,
i.e. the value that was already active when the range starts:

```python
query = salary.between(date(2021, 1, 1), date(2022, 12, 31))
print(query.values())  # [65000]
print(query.min())     # 50000  (active from 2021-01-01 until 2022-06-01)
print(round(query.average()))  # 54383
```

### Interpolation
```python
from chronotype import LinearInterpolation, NearestInterpolation, TemporalInt

# Step interpolation (the default) holds the previous value
level = TemporalInt()
level[datetime(2024, 1, 1, 0, 0)] = 0
level[datetime(2024, 1, 1, 4, 0)] = 3
print(level.at(datetime(2024, 1, 1, 2, 0)))  # 0

# Linear interpolation on ints rounds to the nearest int (ties to even)
linear = TemporalInt(interpolation=LinearInterpolation())
linear[datetime(2024, 1, 1, 0, 0)] = 0
linear[datetime(2024, 1, 1, 4, 0)] = 3
print(linear.at(datetime(2024, 1, 1, 2, 0)))  # 2

# Nearest neighbour
nearest = TemporalInt(interpolation=NearestInterpolation())
nearest[datetime(2024, 1, 1, 0, 0)] = 0
nearest[datetime(2024, 1, 1, 4, 0)] = 3
print(nearest.at(datetime(2024, 1, 1, 3, 0)))  # 3
```

`TemporalFloat(interpolate=True)` still works but is deprecated in favour of
`TemporalFloat(interpolation=LinearInterpolation())`.

### Containers
```python
from chronotype import TemporalDict, TemporalList, TemporalSet

tags = TemporalList()
tags.append("a", date(2024, 1, 1))
tags.append("c", date(2024, 1, 3))
print(tags.at(date(2024, 1, 3)))  # ['a', 'c']

# Backfilling: a past-dated change starts from the value at that time and is
# also applied to the later snapshots
tags.append("b", date(2024, 1, 2))
print(tags.at(date(2024, 1, 2)))  # ['a', 'b']
print(tags.at(date(2024, 1, 3)))  # ['a', 'c', 'b']

config = TemporalDict(initial={"debug": False}, initial_time=date(2024, 1, 1))
config.set_item("debug", True, date(2024, 2, 1))
print(config.get_item_at(date(2024, 1, 15), "debug"))  # False
print(config.key_history("debug")[-1][1])               # True

members = TemporalSet(initial={"alice"}, initial_time=date(2024, 1, 1))
members.add("bob", date(2024, 2, 1))
members.discard("alice", date(2024, 3, 1))
print(members.contains_at(date(2024, 2, 15), "alice"))  # True
print(members.at(date(2024, 3, 1)))                      # {'bob'}
print(members.len_at(date(2024, 2, 15)))                 # 2
```

Removals stop propagating at the first later snapshot that no longer holds the element, and
dict/set changes stop at the first later snapshot that changed the same key or element, so a
later change always wins. See the `chronotype.containers` module docstring for the full rules.

### History Operations
```python
# Full history
for timestamp, value in salary.history():
    print(f"{timestamp}: {value}")

# Detect changes
for timestamp, old_val, new_val in salary.changes():
    print(f"{timestamp}: {old_val} -> {new_val}")

# Slices and copies keep the type (and interpolation) of the original
recent = salary.slice(date(2022, 1, 1), date(2024, 12, 31))
print(type(recent).__name__)  # 'TemporalInt'

# Rollback to previous state
salary.rollback()  # Remove last entry
salary.rollback(to=date(2022, 1, 1))  # Remove all entries after date
print(salary.current())  # 50000
```

### Arithmetic Operations
```python
a = TemporalInt(initial=10, initial_time=date(2024, 1, 1))
b = TemporalInt(initial=5, initial_time=date(2024, 1, 1))

# Operations create new temporals with aligned timestamps
c = a + b  # TemporalInt
c = a - b
c = a * b
c = a / b  # Returns TemporalFloat
c = a // b
c = a % b
c = a ** b

# Mixing in floats promotes to TemporalFloat
print(type(a + 1.5).__name__)  # 'TemporalFloat'

# Division by zero stores NaN for float results instead of skipping the point
zero = TemporalInt(initial=0, initial_time=date(2024, 1, 1))
print((a / zero).at(date(2024, 1, 1)))  # nan

# Comparison creates TemporalBool
is_greater = a > b
print(is_greater.at(date(2024, 1, 1)))  # True

# == compares whole histories; .eq()/.ne() compare point by point
print(a == a.copy())                 # True
print(a.eq(b).at(date(2024, 1, 1)))  # False
```

`TemporalInt // 0` and `TemporalInt % 0` raise `ZeroDivisionError` because an int result
cannot hold NaN; use `.to_float()` first if you want NaN instead.

### Boolean Time Ranges
```python
from chronotype import TemporalBool

online = TemporalBool()
online[datetime(2024, 1, 1, 8)] = True
online[datetime(2024, 1, 1, 12)] = False
online[datetime(2024, 1, 1, 13)] = True

# A range still open at the last entry ends at `until` (default: now)
until = datetime(2024, 1, 1, 17)
print(len(online.when_true(until=until)))  # 2
print(online.duration_true(until=until))   # 28800.0
```

### Serialization
```python
data = temp.to_json()
restored = TemporalFloat.from_json(data)
print(restored.at(datetime(2024, 1, 1, 6, 0)))  # 22.5 (interpolation is restored)

import pickle
print(pickle.loads(pickle.dumps(temp)) == temp)  # True
```

Values that are not JSON-native need `serializer`/`deserializer` callables, passed to the
constructor and to `from_json()`.

## License
MIT License - see [LICENSE](LICENSE) file for details.
