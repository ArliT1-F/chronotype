# What git-strata taught us about chronotype

git-strata feeds real git histories, from 24 to 20,571 commits, into chronotype (0.1.2).
Below is what worked, and the gaps it hit, most important first. Each gap names its
workaround in git-strata and a possible fix in chronotype.

## What worked well

* **Fast lookups.** `at()` costs about 0.4 µs. git-strata queries thousands of
  per-path temporals for every period of every report. Once built, each command answers
  in under 0.3 s on a 20,000-commit history.
* **`TemporalBool.when_true(until=…)`** gave a file's lifetimes, including a deletion
  and a later comeback, in one call. The `until` argument added in 0.1.2 was exactly
  what's needed for "still exists".
* **`copy()` keeps the type.** Following a rename is one line:
  `lines[new] = lines[old].copy()`.
* **`changes()`** gave the "latest size changes" table directly.
* **`TemporalDict` snapshots** fit "who had written how much of this file at time *t*",
  where each snapshot is small.

## Gaps, by impact

### 1. Containers store a full copy of themselves per change

`TemporalSet`, `TemporalDict` and `TemporalList` keep a complete snapshot per timestamp,
so memory grows with *changes × size*. The obvious model, one `TemporalSet` of every path
in the repository, needs **139 MB** on the 5,145-commit test repository. A `TemporalDict`
of path → line count needs **78 MB**. git-strata's whole model for the same history
(existence, sizes, authorship, churn, activity) needs **16 MB**. It stores one small
temporal per path instead, at the cost of a less natural API: "files at *t*" means looping
over every path ever seen.

Since snapshots are rebuilt on every write (`at()` copies, then `set()` copies again),
building is also O(size) per change.

**Possible fix:** store containers internally as one timeline per key or element, and
build snapshots on demand in `at()`. Memory would then grow with the number of changes,
`key_history()` would only read that key's changes instead of scanning every snapshot,
and the public API could stay the same.

### 2. A change at a past time can't be an increment

git timestamps go backwards: rebases, cherry-picks and wrong clocks are common. Most of
git-strata's data are running totals (lines per author, commits so far), so a commit
arriving with an earlier timestamp should add its amount to every later value.

Neither the scalar types nor the containers can express that. `set()` writes one entry.
The container backfill rules stop at the first later snapshot whose value differs, which
for a counter is always the next one:

```python
d = TemporalDict()
d.set_item("alice", 1, date(2024, 1, 1))
d.set_item("alice", 2, date(2024, 3, 1))
d.set_item("alice", d.get_item_at(date(2024, 2, 1), "alice") + 1, date(2024, 2, 1))
d.get_item_at(date(2024, 3, 1), "alice")  # 2; a counter would want 3
```

**Workaround:** a `_Clock` in `history.py` clamps every timestamp to be no earlier than
the previous one, so all writes go at the end of the timeline.

**Possible fix:** either a counter type (`TemporalCounter.add(n, ts)` that shifts all
later values), or a general `Temporal.apply(fn, ts)` that rewrites the value at `ts` and
every later entry. An opt-in append-only mode that raises on out-of-order writes would
at least have made the problem visible.

### 3. `between().delta()` ignores the value carried into the range

0.1.2 (#3) made `min()`, `max()` and `average()` include the value already in effect when
the range starts. `delta()` and `rate_of_change()` still only look at entries inside the
range, and raise if there are fewer than two:

```python
t = TemporalInt()
t[date(2024, 1, 1)] = 10
t[date(2024, 2, 1)] = 20
t[date(2024, 3, 1)] = 25
q = t.between(date(2024, 1, 15), date(2024, 3, 15))
q.min()  # 10: includes the carried-in value
q.delta()  # 5: from 20 to 25; the real change over the range is 25 - 10 = 15
t.between(date(2024, 1, 15), date(2024, 2, 15)).delta()  # EmptyTemporalError
```

"How much did this grow during the quarter" is the most common question git-strata asks,
so it uses `at(end) - at(start)` everywhere (`growth()` in `history.py`).

**Possible fix:** start `delta()` from `value_before_range` when there is one, to match
the other statistics, and accept a single entry.

### 4. `at()` returns `None` before the first entry

Every counter lookup needs `or 0`, so git-strata has a `_value()` helper for it. **Possible
fix:** `at(ts, default=…)`.

### 5. No way to get the entry in effect at a time

To print "the branch was at abc123 (committed 2025-12-30)", git-strata needs the
*timestamp* of the entry in effect at *t*, not just its value. The only way is
`between(start, t).last()`, which copies the whole range. **Possible fix:**
`entry_at(ts) -> (timestamp, value) | None`.

### 6. Writing at an existing timestamp silently replaces it

Two commits in the same second become one entry. For running totals that's correct (the
later total includes the earlier one), and git-strata relies on it. For event-like values
it loses data without any sign. This is a reasonable rule, but the README should state it.

### 7. No way to save or load many temporals at once

About 90% of git-strata's startup is `git log` (8.3 s of 9.8 s at 20,000 commits), so
caching the built history is the obvious next step. chronotype serializes one temporal at
a time, and a cache would hold tens of thousands of them. A bulk `dump`/`load` for a
mapping of temporals would make this straightforward. This hasn't been tried yet.
