# git-strata

Dig through the layers of a git repository: what it looked like at any point in time,
who wrote which parts, and how that changed. Built on
[chronotype](../../README.md): every fact about the repository is a temporal value, so
"what was true on 2023-04-01?" is a lookup, not a replay of history.

It is also a field test of chronotype on real data. [FINDINGS.md](FINDINGS.md) lists what it
showed about the library.

## Install

```bash
pip install -e .            # from this directory; needs chronotype and rich
git strata overview         # installed as git-strata, so git finds it as a subcommand
```

Run it inside any repository, or point it at one with `-C DIR`. `--rev` picks another
branch. Times are UTC.

## Commands

### `overview`: the whole history at a glance

```
$ git strata overview --every quarter

chronotype · main @ ee8f79c9
2025-12-30 → 2026-11-23 (10 months)

Commits   Contributors   Files   Lines   Bus factor
24        2              24      4,838   1  Arli

History by quarter

 Quarter   Files   Lines   Δ lines   Commits   Active   Busiest                Bus factor
 ────────────────────────────────────────────────────────────────────────────────────────
 2025-Q4      20   2,712    +2,712         3        1   Arli (3)                        1
 2026-Q1      20   2,886      +174         7        1   Arli (7)                        1
 2026-Q2      20   2,886         0         0        0   –                               1
 2026-Q3      20   2,886         0         0        0   –                               1
 2026-Q4      24   4,838    +1,952        14        1   Claude (14)                     1

Lines          ▅▅▅▅█
Files          ▇▇▇▇█
Commits        ▃▅▁▁█
Active people  ██▁▁█
```

### `at WHEN [PATH]`: the repository (or a directory) as it was

`WHEN` can be a date (`2023-04-01`), a month (`2023-04`), a year, `now`, a relative time
(`90d`, `6 months ago`) or any git revision, such as a tag: `git strata at v1.0`.

```
$ git strata at 2026-01-15

The whole repository, as of 2026-01-15

2026-01-15 00:00 UTC: main was at 6934a564 small fixes (committed 2025-12-30)

Files                         20   now 24 (+4)
Lines                         2,712   now 4,838 (+2,126)
Contributors so far           1
Active in the 90 days before  1   Arli
Bus factor                    1   Arli

Inside the repository

 Path             Files   Lines   Main author                                  Bus factor
 ────────────────────────────────────────────────────────────────────────────────────────
 src/                 9   1,730   Arli (100%)                                           1
 tests/               6     690   Arli (100%)                                           1
 README.md            1     137   Arli (100%)                                           –
 ...

Since then: 4 files added, 0 removed.
```

`--depth N` groups deeper, and `--window DAYS` changes what counts as "active".
Files removed since then are listed with their size and the date they went.

### `owner [PATH] [--at WHEN]`: who wrote it, and how that changed

```
$ git strata owner src/chronotype

Who wrote src/chronotype, as of 2026-11-23
Lines added per person, following renames. Lines removed later still count.

Arli    ██████████████            58%  1,835 lines
Claude  ██████████                42%  1,321 lines

Bus factor 1  Arli   (9 files)

Main author over time

 From      Main author   Share then
 ──────────────────────────────────
 2025-12   Arli                100%
```

### `file PATH`: the life story of one file

When it existed (including deletions and comebacks), the renames that led to it, its
size over time, its authors and the commits that changed its size.

```
$ git strata file src/chronotype/containers.py --limit 3

src/chronotype/containers.py

Existed        2025-12-30 → now (10 months)
Lines          579   peak 579 on 2026-11-23
Commits        9
Lines changed  885

Size  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄█  2025-12-30 → 2026-11-23

Authors
Claude  ████████████▍         62%
Arli    ███████▋              38%

Latest size changes on the branch

 Date         Lines   Change   Commit
 ────────────────────────────────────────────────────────────────────────────────────────
 2026-11-23     579     +300   ee8f79c9 Merge pull request #1 from ArliT1-F/fix/0.1.2: r…
 2026-01-16     279      +19   bb3afdc5 Added defensive copying for TemporalList/Tempora…
 2025-12-30     260     +260   a5c43a45 Initial commit: chronotype v0.1.0
```

### `hotspots [PATH] [--since WHEN] [--until WHEN]`: what changed most

```
$ git strata hotspots --since 2026-11-01 --limit 5

 #   Path                           Commits   Lines changed   Lines now   By
 ────────────────────────────────────────────────────────────────────────────────────────
 1   src/chronotype/numeric.py            7           1,043         513   Claude
 2   src/chronotype/containers.py         7             606         579   Claude
 3   tests/test_numeric.py                7             529         720   Claude
 4   src/chronotype/base.py               7             443         552   Claude
 5   tests/test_containers.py             6             387         541   Claude
```

## How it works

`git log` is read twice, as NUL-separated `--raw --numstat` output, so odd filenames survive:

* **The mainline** (first-parent history, merges diffed against their first parent)
  replays exactly what the branch looked like after every commit: which files existed
  and how many lines each had. Timestamps are commit times, when a change landed.
* **Every non-merge commit**, including work on branches merged later, says who did the
  work. Timestamps are author times. Names come from `%aN`, so `.mailmap` is respected.

Each fact goes into a chronotype temporal, and every question is answered with `at()`:

| Question | Stored as |
|---|---|
| Did this path exist at *t*? When? | `TemporalBool` per path: `at(t)`, `when_true(until=…)` |
| How many lines did it have? | `TemporalInt` per path: `at(t)`, `history()`, `changes()` |
| Who wrote it, as of *t*? | `TemporalDict[author, lines added]` per path |
| Lines changed or commits touching it between *a* and *b*? | cumulative `TemporalInt` per path: `at(b) - at(a)` |
| Who had contributed by *t*? | one `TemporalSet` of authors |
| Commits per person in a period | cumulative `TemporalInt` per author |
| Which commit was the branch at? | `TemporalString` |

A renamed file takes its history along: the new path starts as a `copy()` of the old
path's temporals. A file re-created at a path that was used before starts with no authors.

There is one small temporal per path rather than one container for the whole tree. A
`TemporalSet` of all paths stores a full copy of the set at every commit, which costs
139 MB for the 5,000-commit test repository. The whole git-strata model for the same
repository takes 16 MB (see [FINDINGS.md](FINDINGS.md)).

### Ownership and bus factor are estimates

* **Ownership** is lines added, following renames. Lines that were later deleted still
  count, and so does reformatting. It's a cheap proxy for `git blame`, not a replacement.
  A binary file counts one "line" per change.
* A file's **authors** are everyone with at least 75% as many lines as its top author.
* The **bus factor** follows a simplified version of Avelino et al., *A novel approach for
  estimating truck factors* (2016). Remove the person who authors the most files,
  recount, and repeat until more than half of the files have no author left. The bus
  factor is how many people were removed. Ties go alphabetically.
* Merge commits count as nobody's work; the conflict resolutions in them are invisible.
* If timestamps go backwards (rebases, wrong clocks), the commit is treated as happening at
  the previous commit's time.

## Performance

Measured on repositories made with `benchmarks/synthetic_repo.py`:

| Commits (merges) | Paths ever | `git strata overview` | Of which `git log` | Model memory | Each command, once built |
|---|---|---|---|---|---|
| 5,145 (145) | 1,788 | 2.3 s | 1.9 s | 16 MB | ≤ 0.25 s |
| 20,571 (571) | 6,980 | 9.8 s | 8.3 s | 63 MB | ≤ 0.3 s |

Model memory is what the built history holds, measured with `tracemalloc`.

At both sizes, the files and line counts were checked against `git ls-tree` and
`git diff --numstat` at a sample of commits (49 and 190), and matched.

Nearly all of the startup time goes to `git log` computing diffs. Caching the built
history, for example with chronotype's JSON serialization, is the obvious next step.

## Development

```bash
pip install -e '../..' -e '.[dev]'
pytest                      # 50 tests
ruff check . && mypy src
python benchmarks/synthetic_repo.py /tmp/big --commits 20000 --authors 60
```

The key test, `test_every_commit_matches_git`, replays a scripted repository (a rename on
a merged branch, a deleted and re-created file, a binary file, names with brackets,
tabs and a newline) and the chronotype repository itself. At every commit on the branch,
the reconstructed files and line counts must equal what git reports for that commit.
