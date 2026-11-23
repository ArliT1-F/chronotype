"""A repository's history as chronotype temporals, and the questions you can ask of it.

Two streams of commits feed the model:

* The **mainline** (first-parent history of the branch) says what the branch
  looked like at any moment: which files existed and how long they were.
  Timestamps are commit times, i.e. when a change landed on the branch.
* The **authored** stream (every non-merge commit, including work done on
  merged branches) says who did the work. Timestamps are author times.

The model keeps one small temporal per path instead of one big temporal
container for the whole tree. A ``TemporalSet`` of every path would store a
full copy of the set at each commit, so memory would grow with
commits x files. Per-path temporals grow with the number of changes instead.

Each stream is fed to chronotype in time order. Timestamps that go backwards
(clock skew, rebases) are clamped to the previous one, so no write is ever
backfilled into the past.
"""

from __future__ import annotations

import posixpath
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from chronotype import TemporalBool, TemporalDict, TemporalInt, TemporalSet, TemporalString

from git_strata.gitlog import Change, Commit, Git

#: Authors with at least this share of a file's top author's lines also count as its authors.
AUTHOR_THRESHOLD = 0.75
#: Default window for "active contributors".
ACTIVE_WINDOW = timedelta(days=90)


def under(path: str, prefix: str) -> bool:
    """Whether ``path`` is ``prefix`` or inside the directory ``prefix`` (``""``: everything)."""
    return not prefix or path == prefix or path.startswith(prefix + "/")


def _value(temporal: TemporalInt | None, when: datetime) -> int:
    """The value at ``when``, or 0 before the first entry."""
    if temporal is None:
        return 0
    value = temporal.at(when)
    return value if value is not None else 0


def growth(temporal: TemporalInt | None, start: datetime, end: datetime) -> int:
    """
    How much a cumulative counter grew from ``start`` to ``end``.

    Not ``temporal.between(start, end).delta()``: that only looks at entries
    inside the range (ignoring the value carried in) and needs two of them.
    """
    return _value(temporal, end) - _value(temporal, start)


class _Clock:
    """Hands out non-decreasing timestamps, so every write goes at the end of a timeline."""

    def __init__(self) -> None:
        self.last: datetime | None = None

    def tick(self, when: datetime) -> datetime:
        if self.last is not None and when < self.last:
            when = self.last
        self.last = when
        return when


@dataclass(frozen=True)
class BusFactor:
    """How many people would have to leave before most files have no remaining author."""

    value: int
    people: tuple[str, ...]
    files: int
    """Files with known authorship that the calculation considered."""


@dataclass(frozen=True)
class Hotspot:
    path: str
    churn: int
    commits: int
    authors: tuple[str, ...]
    lines: int


@dataclass(frozen=True)
class FileStory:
    path: str
    lifetimes: list[tuple[datetime, datetime]]
    """When the path existed on the branch (a range still open ends at the end of history)."""
    alive: bool
    ancestry: list[tuple[datetime, str, str]]
    """Renames that led to this path, newest first: ``(when, old path, new path)``."""
    lines: list[tuple[datetime, int]]
    """Line count after each change on the branch, including the paths it was renamed from."""
    binary: bool
    commits: int
    churn: int
    authors: Counter[str]


@dataclass
class RepoHistory:
    """The history of one branch of a repository."""

    # --- what the branch looked like: from the mainline --------------------------------
    alive: dict[str, TemporalBool] = field(default_factory=dict)
    """Per path: whether it exists on the branch."""
    lines: dict[str, TemporalInt] = field(default_factory=dict)
    """Per path: its line count. A renamed file carries the history of its old path."""
    binary: set[str] = field(default_factory=set)
    """Paths whose latest version is binary (no line counts)."""
    renamed_from: dict[str, list[tuple[datetime, str]]] = field(default_factory=dict)
    """Per path: ``(when, old path)`` for each rename on the branch that produced it."""
    file_count: TemporalInt = field(default_factory=TemporalInt)
    total_lines: TemporalInt = field(default_factory=TemporalInt)
    head: TemporalString = field(default_factory=TemporalString)
    """The commit the branch pointed at, at any moment."""
    subjects: dict[str, str] = field(default_factory=dict)
    """Subject line of every mainline commit."""

    # --- who did the work: from the authored stream ------------------------------------
    authorship: dict[str, TemporalDict[str, int]] = field(default_factory=dict)
    """Per path: lines added by each author, carried across renames."""
    churn: dict[str, TemporalInt] = field(default_factory=dict)
    """Per path: lines added plus lines deleted so far, carried across renames."""
    touches: dict[str, TemporalInt] = field(default_factory=dict)
    """Per path: number of commits that changed it so far, carried across renames."""
    commits: TemporalInt = field(default_factory=TemporalInt)
    """Number of non-merge commits so far."""
    commits_by: dict[str, TemporalInt] = field(default_factory=dict)
    """Per author: number of commits so far."""
    lines_by: dict[str, TemporalInt] = field(default_factory=dict)
    """Per author: lines added so far."""
    contributors: TemporalSet[str] = field(default_factory=TemporalSet)
    """Everyone who has committed so far."""

    # --- running state while building -------------------------------------------------
    _mainline_clock: _Clock = field(default_factory=_Clock, repr=False)
    _authored_clock: _Clock = field(default_factory=_Clock, repr=False)
    _current_lines: dict[str, int] = field(default_factory=dict, repr=False)
    _total: int = field(default=0, repr=False)
    _commit_total: int = field(default=0, repr=False)
    _counts: Counter[str] = field(default_factory=Counter, repr=False)
    _added: Counter[str] = field(default_factory=Counter, repr=False)

    # =================================================================================
    # Building
    # =================================================================================

    @classmethod
    def from_git(
        cls,
        git: Git,
        rev: str = "HEAD",
        progress: Callable[[str, int], None] | None = None,
    ) -> RepoHistory:
        """Read the history of ``rev`` (``progress`` is called with a stream name and a count)."""
        history = cls()
        for stream, commits, add in (
            ("mainline", git.mainline(rev), history.add_mainline_commit),
            ("authored", git.authored(rev), history.add_authored_commit),
        ):
            for count, commit in enumerate(commits, 1):
                add(commit)
                if progress is not None and count % 500 == 0:
                    progress(stream, count)
        return history

    def add_mainline_commit(self, commit: Commit) -> None:
        """Apply one first-parent commit (commits must come oldest first)."""
        when = self._mainline_clock.tick(commit.committed)
        for change in commit.changes:
            if change.status == "D":
                self._remove(change.path, when)
            elif change.status == "R" and change.old_path is not None:
                base = self._current_lines.get(change.old_path, 0)
                if change.old_path in self.lines:
                    self.lines[change.path] = self.lines[change.old_path].copy()
                self.renamed_from.setdefault(change.path, []).append((when, change.old_path))
                self._remove(change.old_path, when)
                self._put(change.path, when, base, change)
            elif change.status == "C" and change.old_path is not None:
                self._put(change.path, when, self._current_lines.get(change.old_path, 0), change)
            elif change.status == "A":
                self._put(change.path, when, 0, change)
            else:
                self._put(change.path, when, self._current_lines.get(change.path, 0), change)
        self.file_count[when] = len(self._current_lines)
        self.total_lines[when] = self._total
        self.head[when] = commit.sha
        self.subjects[commit.sha] = commit.subject

    def _put(self, path: str, when: datetime, base: int, change: Change) -> None:
        if change.added is None or change.deleted is None:
            self.binary.add(path)
            count = 0
        else:
            self.binary.discard(path)
            count = max(0, base + change.added - change.deleted)
        if path not in self._current_lines:
            self.alive.setdefault(path, TemporalBool())[when] = True
        self._total += count - self._current_lines.get(path, 0)
        self._current_lines[path] = count
        self.lines.setdefault(path, TemporalInt())[when] = count

    def _remove(self, path: str, when: datetime) -> None:
        if path not in self._current_lines:
            return
        self._total -= self._current_lines.pop(path)
        self.alive[path][when] = False
        self.lines[path][when] = 0

    def add_authored_commit(self, commit: Commit) -> None:
        """Count one non-merge commit (commits must come oldest first)."""
        when = self._authored_clock.tick(commit.authored)
        author = commit.author

        self._commit_total += 1
        self.commits[when] = self._commit_total
        self._counts[author] += 1
        self.commits_by.setdefault(author, TemporalInt())[when] = self._counts[author]
        if self._counts[author] == 1:
            self.contributors.add(author, when)

        added_by_author = 0
        for change in commit.changes:
            path = change.path
            old = change.old_path
            if change.status == "R" and old is not None and old != path:
                # The file carries its history to its new path.
                if old in self.authorship:
                    self.authorship[path] = self.authorship[old].copy()
                for counters in (self.churn, self.touches):
                    if old in counters:
                        counters[path] = counters[old].copy()
            churn = (change.added or 0) + (change.deleted or 0)
            self._bump(self.churn, path, when, churn)
            self._bump(self.touches, path, when, 1)
            if change.status == "D":
                continue
            if change.status == "A" and path in self.authorship:
                # A new file at a path that was used before: its authors start from scratch.
                # (Not cleared on deletion: on a branch, a file can be deleted or moved
                # long before the merge removes it from the mainline.)
                self.authorship[path].set(when, {})
            # A binary file has no line counts; count each change to it as one line.
            added = 1 if change.binary else change.added or 0
            if added:
                authors = self.authorship.setdefault(path, TemporalDict())
                previous = authors.get_item_at(when, author) or 0
                authors.set_item(author, previous + added, when)
                added_by_author += added

        self._added[author] += added_by_author
        self.lines_by.setdefault(author, TemporalInt())[when] = self._added[author]

    @staticmethod
    def _bump(counters: dict[str, TemporalInt], path: str, when: datetime, amount: int) -> None:
        counter = counters.setdefault(path, TemporalInt())
        counter[when] = _value(counter, when) + amount

    # =================================================================================
    # Questions
    # =================================================================================

    @property
    def start(self) -> datetime:
        """When the first commit landed on the branch."""
        return min(self.head.first_entry()[0], self.commits.first_entry()[0])

    @property
    def end(self) -> datetime:
        """The latest timestamp in the history."""
        return max(self.head.current_entry()[0], self.commits.current_entry()[0])

    def head_at(self, when: datetime) -> str | None:
        """The commit the branch pointed at, at ``when`` (``None`` before the first commit)."""
        return self.head.at(when)

    def files_at(self, when: datetime, prefix: str = "") -> list[str]:
        """Paths that existed on the branch at ``when``, optionally only under ``prefix``."""
        return sorted(
            path for path, alive in self.alive.items() if under(path, prefix) and alive.at(when)
        )

    def lines_at(self, when: datetime, prefix: str = "", files: Iterable[str] | None = None) -> int:
        """Lines at ``when`` in ``files`` if given, else in everything under ``prefix``."""
        if files is None and not prefix:
            return _value(self.total_lines, when)
        paths = files if files is not None else self.files_at(when, prefix)
        return sum(_value(self.lines.get(path), when) for path in paths)

    def known_paths(self) -> set[str]:
        return set(self.alive) | set(self.authorship)

    def authors_of(self, path: str, when: datetime) -> dict[str, int]:
        """Lines each author had added to ``path`` (or its earlier paths) by ``when``."""
        temporal = self.authorship.get(path)
        snapshot = temporal.at(when) if temporal is not None else None
        return snapshot or {}

    def ownership(self, when: datetime, prefix: str = "") -> Counter[str]:
        """Lines added per author, over the files under ``prefix`` that existed at ``when``."""
        total: Counter[str] = Counter()
        for path in self.files_at(when, prefix):
            total.update(self.authors_of(path, when))
        return total

    def bus_factor(self, when: datetime, prefix: str = "") -> BusFactor:
        """
        A truck-factor estimate, after Avelino et al. (2016), simplified.

        Each file's authors are the people who added at least
        ``AUTHOR_THRESHOLD`` times as many lines as its top author. The people
        who author the most files are removed one by one, recounting after
        each, until more than half of the files have no author left. The bus
        factor is how many people had to go.
        """
        owners = []
        for path in self.files_at(when, prefix):
            lines = self.authors_of(path, when)
            if lines:
                top = max(lines.values())
                owners.append({a for a, n in lines.items() if n >= AUTHOR_THRESHOLD * top})
        gone: list[str] = []
        remaining = [set(o) for o in owners]
        while sum(1 for o in remaining if o) * 2 >= len(remaining) and any(remaining):
            counts = Counter(a for o in remaining for a in o)
            person = min(counts, key=lambda a: (-counts[a], a))
            gone.append(person)
            for o in remaining:
                o.discard(person)
        return BusFactor(len(gone), tuple(gone), len(owners))

    def active_contributors(
        self, when: datetime, window: timedelta = ACTIVE_WINDOW
    ) -> Counter[str]:
        """Commits per author in the ``window`` before ``when``."""
        return self.contributions(when - window, when)

    def contributions(self, start: datetime, end: datetime) -> Counter[str]:
        """Commits per author between ``start`` and ``end`` (authors with none are left out)."""
        result: Counter[str] = Counter()
        for author, commits in self.commits_by.items():
            count = growth(commits, start, end)
            if count:
                result[author] = count
        return result

    def contributors_at(self, when: datetime) -> set[str]:
        """Everyone who had committed by ``when``."""
        return self.contributors.at(when) or set()

    def hotspots(
        self, start: datetime, end: datetime, prefix: str = "", top: int | None = 20
    ) -> list[Hotspot]:
        """Files that existed at ``end``, ranked by lines changed between ``start`` and ``end``."""
        spots = []
        for path in self.files_at(end, prefix):
            churn = growth(self.churn.get(path), start, end)
            commits = growth(self.touches.get(path), start, end)
            if not commits:
                continue
            before, after = self.authors_of(path, start), self.authors_of(path, end)
            authors = sorted(
                (a for a in after if after[a] > before.get(a, 0)),
                key=lambda a: (before.get(a, 0) - after[a], a),
            )
            lines = _value(self.lines.get(path), end)
            spots.append(Hotspot(path, churn, commits, tuple(authors), lines))
        spots.sort(key=lambda s: (-s.churn, -s.commits, s.path))
        return spots[:top] if top is not None else spots

    def story(self, path: str) -> FileStory:
        """Everything known about one path."""
        end = self.end
        alive = self.alive.get(path)
        lines = self.lines.get(path)
        ancestry: list[tuple[datetime, str, str]] = []
        current, seen = path, {path}
        while current in self.renamed_from:
            when, old = self.renamed_from[current][-1]
            if old in seen:
                break
            ancestry.append((when, old, current))
            seen.add(old)
            current = old
        return FileStory(
            path=path,
            lifetimes=alive.when_true(until=end) if alive is not None else [],
            alive=bool(alive and alive.at(end)),
            ancestry=ancestry,
            lines=lines.history() if lines is not None else [],
            binary=path in self.binary,
            commits=_value(self.touches.get(path), end),
            churn=_value(self.churn.get(path), end),
            authors=Counter(self.authors_of(path, end)),
        )

    def top_authors(self, start: datetime, end: datetime) -> list[tuple[str, int, int]]:
        """``(author, commits, lines added)`` between ``start`` and ``end``, most commits first."""
        rows = [
            (author, count, growth(self.lines_by.get(author), start, end))
            for author, count in self.contributions(start, end).items()
        ]
        rows.sort(key=lambda row: (-row[1], -row[2], row[0]))
        return rows


# =====================================================================================
# Periods
# =====================================================================================

PERIODS = ("week", "month", "quarter", "year")


def _floor(when: datetime, every: str) -> datetime:
    when = when.astimezone(timezone.utc)
    if every == "week":
        day = when - timedelta(days=when.weekday())
        return day.replace(hour=0, minute=0, second=0, microsecond=0)
    if every == "month":
        return datetime(when.year, when.month, 1, tzinfo=timezone.utc)
    if every == "quarter":
        return datetime(when.year, (when.month - 1) // 3 * 3 + 1, 1, tzinfo=timezone.utc)
    if every == "year":
        return datetime(when.year, 1, 1, tzinfo=timezone.utc)
    raise ValueError(f"unknown period {every!r}; expected one of {', '.join(PERIODS)}")


def _next(start: datetime, every: str) -> datetime:
    if every == "week":
        return start + timedelta(days=7)
    months = {"month": 1, "quarter": 3, "year": 12}[every]
    month = start.month - 1 + months
    return start.replace(year=start.year + month // 12, month=month % 12 + 1)


def auto_period(start: datetime, end: datetime) -> str:
    """A period length that gives a readable number of rows for the span."""
    days = (end - start).days
    if days <= 120:
        return "week"
    if days <= 3 * 365:
        return "month"
    if days <= 10 * 365:
        return "quarter"
    return "year"


def periods(start: datetime, end: datetime, every: str) -> Iterator[tuple[datetime, datetime]]:
    """Calendar periods covering ``start`` to ``end``; the last one is cut off at ``end``."""
    lower = _floor(start, every)
    while lower <= end:
        upper = _next(lower, every)
        yield lower, min(upper, end)
        lower = upper


def label(start: datetime, every: str) -> str:
    if every == "week":
        return start.strftime("%Y-%m-%d")
    if every == "month":
        return start.strftime("%Y-%m")
    if every == "quarter":
        return f"{start.year}-Q{(start.month - 1) // 3 + 1}"
    return str(start.year)


def group_by_directory(paths: Iterable[str], prefix: str, depth: int) -> dict[str, list[str]]:
    """Group paths by their first ``depth`` path components below ``prefix``."""
    groups: dict[str, list[str]] = {}
    for path in paths:
        rest = path[len(prefix) + 1 :] if prefix else path
        parts = rest.split("/")
        key = "/".join(parts[:depth])
        if len(parts) > depth:
            key += "/"
        groups.setdefault(posixpath.join(prefix, key) if prefix else key, []).append(path)
    return groups


def share(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def top_owner(lines: Mapping[str, int]) -> tuple[str, float] | None:
    """The author with the most lines and their share (``None`` if there are no lines)."""
    total = sum(lines.values())
    if not total:
        return None
    author = min(lines, key=lambda a: (-lines[a], a))
    return author, lines[author] / total
