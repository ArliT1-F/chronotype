"""The ``git-strata`` command line (also runs as ``git strata``)."""

from __future__ import annotations

import argparse
import difflib
import posixpath
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from rich import box
from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from git_strata import __version__
from git_strata.gitlog import Git, GitError
from git_strata.history import (
    ACTIVE_WINDOW,
    AUTHOR_THRESHOLD,
    PERIODS,
    RepoHistory,
    auto_period,
    group_by_directory,
    label,
    periods,
    share,
    top_owner,
    under,
)
from git_strata.render import (
    bar,
    day,
    moment,
    number,
    people,
    percent,
    plural,
    short,
    signed,
    span,
    sparkline,
)
from git_strata.when import parse_when

DESCRIPTION = f"""\
Dig through the layers of a git repository: what it looked like at any point in
time, who wrote which parts, and how that changed.

Ownership counts the lines each person added to a file, following renames. A
file's authors are everyone with at least {AUTHOR_THRESHOLD:.0%} as many lines as its top
author; the bus factor is how many of the most prolific authors would have to
leave before more than half of the files have no author left.
"""

TABLE: dict[str, Any] = {
    "box": box.SIMPLE_HEAD,
    "title_justify": "left",
    "title_style": "bold",
    "header_style": "bold dim",
    "pad_edge": False,
}

WHEN_HELP = (
    "a date (2023-04-01), month (2023-04), year (2023), 'now', a relative time "
    "(90d, 6 months ago) or a git revision such as a tag"
)


class Strata:
    """One run of the command: the repository, its history and the consoles."""

    def __init__(self, git: Git, rev: str, out: Console, err: Console) -> None:
        self.git = git
        self.rev = rev
        self.out = out
        self.err = err
        self.sha = git.resolve(rev)
        self.prefix = git.prefix()
        with err.status("Reading history…") as status:
            self.history = RepoHistory.from_git(
                git,
                self.sha,
                progress=lambda stream, n: status.update(f"Reading history… {n:,} {stream}"),
            )

    # --- arguments --------------------------------------------------------------------

    def when(self, text: str | None, default: datetime | None = None) -> datetime:
        if text is None:
            return default if default is not None else self.history.end
        return parse_when(text, self.git)

    def path(self, text: str | None) -> str:
        """A path argument (relative to the current directory) as a path from the top."""
        if text is None:
            return self.prefix.rstrip("/")
        joined = posixpath.normpath(posixpath.join(self.prefix, text.replace("\\", "/")))
        if joined == ".":
            return ""
        if joined.startswith("../") or joined == "..":
            raise ValueError(f"{text} is outside the repository")
        return joined.strip("/")

    def require_known(self, path: str) -> None:
        if not path:
            return
        known = self.history.known_paths()
        if path in known or any(under(p, path) for p in known):
            return
        directories = {posixpath.dirname(p) for p in known}
        close = difflib.get_close_matches(path, sorted(known | directories), n=3)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        raise ValueError(f"{path} never existed in this history.{hint}")

    def describe(self, path: str) -> str:
        return path or "the whole repository"

    def title(self, path: str) -> str:
        return path or "The whole repository"

    # --- shared pieces ----------------------------------------------------------------

    def path_width(self, paths: Sequence[str], other_columns: int) -> int:
        """A minimum width for a path column: the longest path, if the terminal has room."""
        longest = max((len(p) for p in paths), default=4)
        return max(4, min(longest, self.out.width - other_columns))

    def table(self, title: str | None = None) -> Table:
        """A table that fills the terminal, up to MAX_WIDTH (see FLEXIBLE)."""
        return Table(title=title, expand=True, width=min(self.out.width, MAX_WIDTH), **TABLE)

    def heading(self, title: str, subtitle: str = "") -> None:
        self.out.print()
        self.out.print(Text(title, style="bold"))
        if subtitle:
            self.out.print(Text(subtitle, style="dim"))
        self.out.print()

    def as_of_line(self, when: datetime) -> Text:
        sha = self.history.head_at(when)
        if sha is None:
            return Text(f"{moment(when)}: before the first commit", style="dim")
        committed = self.history.head.between(self.history.start, when).last()
        line = Text(f"{moment(when)}: ")
        line.append(f"{self.git.describe_branch(self.rev)} was at ")
        line.append(short(sha), style="yellow")
        line.append(f" {self.history.subjects.get(sha, '')}", style="italic")
        if committed is not None:
            line.append(f" (committed {day(committed[0])})", style="dim")
        return line

    def timeline_points(self, start: datetime, end: datetime, count: int = 48) -> list[datetime]:
        if end <= start:
            return [end]
        step = (end - start) / (count - 1)
        # The last point is exactly `end`: start + step * (count - 1) can fall short by rounding.
        return [start + step * i for i in range(count - 1)] + [end]


# =====================================================================================
# Commands
# =====================================================================================


def trend(delta: int) -> str:
    return "green" if delta > 0 else "red" if delta < 0 else "dim"


Cell = str | Text

# For a column of names or subjects: it takes the width the other columns leave
# (with expand=True on the table) and cuts its text short. A plain no_wrap column
# would instead squeeze the other columns, down to nothing on a narrow terminal.
FLEXIBLE: dict[str, Any] = {"no_wrap": True, "overflow": "ellipsis", "ratio": 1}
MAX_WIDTH = 110


def fill(table: Table, columns: list[tuple[str, dict[str, Any]]], rows: list[list[Cell]]) -> None:
    """Add columns and rows; right-aligned (number) columns never shrink below their content."""
    for index, (header, options) in enumerate(columns):
        if options.get("justify") == "right":
            widths = [Text(c).cell_len if isinstance(c, str) else c.cell_len for c in
                      (row[index] for row in rows)]  # fmt: skip
            longest_word = max(len(word) for word in header.split())
            options = {"min_width": max([longest_word, *widths]), **options}
        table.add_column(header, **options)
    for row in rows:
        table.add_row(*row)


def cmd_overview(app: Strata, args: argparse.Namespace) -> int:
    h = app.history
    start, end = h.start, h.end
    every = args.every or auto_period(start, end)
    name = app.git.toplevel().name
    sha = h.head.current()
    contributors = h.contributors_at(end)
    bus = h.bus_factor(end)

    app.heading(
        f"{name} · {app.git.describe_branch(app.rev)} @ {short(sha)}",
        f"{day(start)} → {day(end)} ({span(end - start)})",
    )
    summary = Table.grid(padding=(0, 3))
    for _ in range(5):
        summary.add_column()
    summary.add_row(
        *(Text(label_, style="dim") for label_ in
          ("Commits", "Contributors", "Files", "Lines", "Bus factor"))
    )  # fmt: skip
    summary.add_row(
        Text(number(h.commits.current()), style="bold"),
        Text(number(len(contributors)), style="bold"),
        Text(number(h.file_count.current()), style="bold"),
        Text(number(h.total_lines.current()), style="bold"),
        Text(f"{bus.value}", style="bold").append(
            f"  {people(list(bus.people))}" if bus.people else "", style="not bold"
        ),
    )
    app.out.print(Padding(summary, (0, 0, 1, 0)))

    right: dict[str, Any] = {"justify": "right"}
    columns: list[tuple[str, dict[str, Any]]] = [
        (every.capitalize(), {}),
        ("Files", right),
        ("Lines", right),
        ("Δ lines", right),
        ("Commits", right),
        ("Active", right),
        ("Busiest", FLEXIBLE),
        ("Bus factor", right),
    ]
    rows: list[list[Cell]] = []
    series: dict[str, list[int]] = {"lines": [], "files": [], "commits": [], "active": []}
    for lower, upper in periods(start, end, every):
        authors = h.top_authors(lower, upper)
        files = h.file_count.at(upper) or 0
        lines = h.total_lines.at(upper) or 0
        delta = lines - (h.total_lines.at(lower) or 0)
        commits = sum(row[1] for row in authors)
        busiest = Text(f"{authors[0][0]} ({authors[0][1]})") if authors else Text("–", style="dim")
        factor = h.bus_factor(upper)
        rows.append([
            label(lower, every),
            number(files),
            number(lines),
            Text(signed(delta), style=trend(delta)),
            number(commits) if commits else Text("0", style="dim"),
            str(len(authors)) if authors else Text("0", style="dim"),
            busiest,
            str(factor.value) if factor.files else Text("–", style="dim"),
        ])  # fmt: skip
        for key, value in (
            ("lines", lines),
            ("files", files),
            ("commits", commits),
            ("active", len(authors)),
        ):
            series[key].append(value)  # fmt: skip
    table = app.table(f"History by {every}")
    fill(table, columns, rows)
    app.out.print(table)

    if len(series["lines"]) > 1:
        trends = Table.grid(padding=(0, 2))
        trends.add_column(style="dim")
        trends.add_column(style="cyan")
        for key, title in (
            ("lines", "Lines"),
            ("files", "Files"),
            ("commits", "Commits"),
            ("active", "Active people"),
        ):
            trends.add_row(title, sparkline(series[key]))  # fmt: skip
        app.out.print(Padding(trends, (1, 0, 0, 0)))
    return 0


def cmd_at(app: Strata, args: argparse.Namespace) -> int:
    h = app.history
    when = app.when(args.when)
    prefix = app.path(args.path)
    app.require_known(prefix)
    window = timedelta(days=args.window)
    end = h.end

    app.heading(f"{app.title(prefix)}, as of {day(when)}")
    app.out.print(app.as_of_line(when))
    app.out.print()

    files_then = set(h.files_at(when, prefix))
    files_now = set(h.files_at(end, prefix))
    lines_then = h.lines_at(when, prefix, files_then)
    lines_now = h.lines_at(end, prefix, files_now)
    active = h.active_contributors(when, window)
    bus = h.bus_factor(when, prefix)

    facts = Table.grid(padding=(0, 2))
    facts.add_column(style="dim")
    facts.add_column()
    facts.add_row(
        "Files",
        Text(number(len(files_then)), style="bold").append(
            f"   now {number(len(files_now))} ({signed(len(files_now) - len(files_then))})",
            style="dim not bold",
        ),
    )
    facts.add_row(
        "Lines",
        Text(number(lines_then), style="bold").append(
            f"   now {number(lines_now)} ({signed(lines_now - lines_then)})", style="dim not bold"
        ),
    )
    facts.add_row("Contributors so far", number(len(h.contributors_at(when))))
    facts.add_row(
        f"Active in the {args.window} days before",
        Text(number(len(active)), style="bold").append(
            f"   {people([a for a, _ in active.most_common()], 5)}" if active else "",
            style="not bold",
        ),
    )
    facts.add_row(
        "Bus factor",
        Text(str(bus.value), style="bold").append(
            f"   {people(list(bus.people), 5)}" if bus.people else "", style="not bold"
        ),
    )
    app.out.print(facts)

    if files_then:
        groups = group_by_directory(files_then, prefix, args.depth)
        found = []
        for key, paths in groups.items():
            ownership: dict[str, int] = {}
            for path in paths:
                for author, n in h.authors_of(path, when).items():
                    ownership[author] = ownership.get(author, 0) + n
            factor = h.bus_factor(when, key.rstrip("/")) if key.endswith("/") else None
            lines = h.lines_at(when, files=paths)
            found.append((lines, key, len(paths), top_owner(ownership), factor))
        found.sort(key=lambda row: (-row[0], row[1]))
        shown = found[: args.limit]
        table = app.table(f"Inside {prefix or 'the repository'}")
        fill(table, [
            ("Path", {"overflow": "fold", "min_width": app.path_width([r[1] for r in shown], 36)}),
            ("Files", {"justify": "right"}),
            ("Lines", {"justify": "right"}),
            ("Main author", FLEXIBLE),
            ("Bus factor", {"justify": "right"}),
        ], [
            [
                Text(key, style="bold" if key.endswith("/") else ""),
                number(count),
                number(lines),
                Text(f"{owner[0]} ({percent(owner[1])})") if owner else Text("–", style="dim"),
                str(factor.value) if factor and factor.files else Text("–", style="dim"),
            ]
            for lines, key, count, owner, factor in shown
        ])  # fmt: skip
        if len(found) > args.limit:
            table.caption = f"{len(found) - args.limit} more not shown (use --limit)"
        app.out.print()
        app.out.print(table)

    gone = sorted(files_then - files_now)
    new = files_now - files_then
    if when < end and (gone or new):
        app.out.print()
        app.out.print(
            Text(f"Since then: {number(len(new))} files added, {number(len(gone))} removed.",
                 style="dim")
        )  # fmt: skip
        if gone:
            biggest = sorted(gone, key=lambda p: -(h.lines[p].at(when) or 0))[:5]
            for path in biggest:
                lines = h.lines[path].at(when) or 0
                lifetimes = h.alive[path].when_true(until=end)
                last = lifetimes[-1][1] if lifetimes else end
                app.out.print(
                    Text("  gone: ", style="dim")
                    .append(path)
                    .append(f" ({number(lines)} lines, removed {day(last)})", style="dim")
                )
    return 0


def cmd_owner(app: Strata, args: argparse.Namespace) -> int:
    h = app.history
    when = app.when(args.at)
    prefix = app.path(args.path)
    app.require_known(prefix)

    app.heading(
        f"Who wrote {app.describe(prefix)}, as of {day(when)}",
        "Lines added per person, following renames. Lines removed later still count.",
    )
    ownership = h.ownership(when, prefix)
    total = sum(ownership.values())
    if not total:
        files = h.files_at(when, prefix)
        story = h.story(prefix) if prefix in h.alive else None
        if story and story.lifetimes and not files:
            ranges = ", ".join(f"{day(a)} → {day(b)}" for a, b in story.lifetimes)
            app.out.print(Text(f"{prefix} did not exist then. It existed {ranges}."))
        else:
            app.out.print("Nothing with known authors existed there then.")
        return 0

    table = Table(box=None, show_header=False, padding=(0, 2, 0, 0))
    table.add_column()
    table.add_column(style="cyan")
    table.add_column(justify="right")
    table.add_column(justify="right", style="dim")
    ranked = ownership.most_common()
    for author, lines in ranked[: args.limit]:
        table.add_row(author, bar(share(lines, total)), percent(share(lines, total)),
                      f"{number(lines)} lines")  # fmt: skip
    if len(ranked) > args.limit:
        rest = sum(n for _, n in ranked[args.limit :])
        table.add_row(
            Text(f"{len(ranked) - args.limit} others", style="dim"), bar(share(rest, total)),
            percent(share(rest, total)), f"{number(rest)} lines",
        )  # fmt: skip
    app.out.print(table)

    bus = h.bus_factor(when, prefix)
    app.out.print()
    app.out.print(
        Text("Bus factor ", style="dim")
        .append(str(bus.value), style="bold")
        .append(f"  {people(list(bus.people), 5)}" if bus.people else "")
        .append(f"   ({plural(bus.files, 'file')})", style="dim")
    )

    # Hand-overs: when the main author changed.
    first = min(
        (alive.first_entry()[0] for path, alive in h.alive.items() if under(path, prefix)),
        default=h.start,
    )
    every = args.every or auto_period(first, when)
    changes: list[tuple[datetime, str, float]] = []
    for lower, upper in periods(first, when, every):
        main_author = top_owner(h.ownership(upper, prefix))
        if main_author and (not changes or changes[-1][1] != main_author[0]):
            changes.append((lower, *main_author))
    if changes:
        table = Table(title="Main author over time", **TABLE)
        table.add_column("From")
        table.add_column("Main author")
        table.add_column("Share then", justify="right")
        for lower, author, fraction in changes:
            table.add_row(label(lower, every), author, percent(fraction))
        app.out.print()
        app.out.print(table)
    return 0


def cmd_file(app: Strata, args: argparse.Namespace) -> int:
    h = app.history
    path = app.path(args.path)
    if not path:
        raise ValueError("give a file path")
    if path not in h.alive and path not in h.authorship:
        app.require_known(path)
        raise ValueError(f"{path} is a directory; try: git strata owner {path}")

    story = h.story(path)
    end = h.end
    status = "" if story.alive else "  (deleted)"
    app.heading(path + status, "binary file" if story.binary else "")

    facts = Table.grid(padding=(0, 2))
    facts.add_column(style="dim")
    facts.add_column()
    for start, stop in story.lifetimes:
        until = "now" if story.alive and stop == end else day(stop)
        facts.add_row("Existed", f"{day(start)} → {until} ({span(stop - start)})")
    for renamed, before, after in story.ancestry:
        facts.add_row(
            "Renamed", Text(f"{day(renamed)}  ").append(before, style="dim").append(f" → {after}")
        )
    if story.lines:
        peak_when, peak = max(story.lines, key=lambda entry: (entry[1], entry[0]))
        now_lines = story.lines[-1][1]
        facts.add_row(
            "Lines",
            Text(number(now_lines), style="bold").append(
                f"   peak {number(peak)} on {day(peak_when)}", style="dim not bold"
            ),
        )
    facts.add_row("Commits", number(story.commits))
    facts.add_row("Lines changed", number(story.churn))
    app.out.print(facts)

    lines = h.lines.get(path)
    if lines is not None and len(story.lines) > 1:
        points = app.timeline_points(story.lines[0][0], end)
        app.out.print()
        app.out.print(
            Text("Size  ", style="dim")
            .append(sparkline([lines.at(p) or 0 for p in points]), style="cyan")
            .append(f"  {day(story.lines[0][0])} → {day(end)}", style="dim")
        )

    if story.authors:
        total = sum(story.authors.values())
        table = Table(title="Authors", title_justify="left", title_style="bold", box=None,
                      show_header=False, padding=(0, 2, 0, 0))  # fmt: skip
        table.add_column()
        table.add_column(style="cyan")
        table.add_column(justify="right")
        for author, n in story.authors.most_common(args.limit):
            table.add_row(author, bar(share(n, total), 20), percent(share(n, total)))
        app.out.print()
        app.out.print(table)

    if lines is not None:
        changes = lines.changes()[-args.limit :]
        if changes:
            rows: list[list[Cell]] = []
            for changed, previous, count in reversed(changes):
                sha = h.head_at(changed) or ""
                delta = count - (previous or 0)
                commit = Text(short(sha), style="yellow")
                rows.append([
                    day(changed),
                    number(count),
                    Text(signed(delta), style=trend(delta)),
                    commit.append(f" {h.subjects.get(sha, '')}", style="italic"),
                ])  # fmt: skip
            table = app.table("Latest size changes on the branch")
            fill(table, [
                ("Date", {"no_wrap": True, "min_width": 10}),
                ("Lines", {"justify": "right"}),
                ("Change", {"justify": "right"}),
                ("Commit", FLEXIBLE),
            ], rows)  # fmt: skip
            app.out.print()
            app.out.print(table)
    return 0


def cmd_hotspots(app: Strata, args: argparse.Namespace) -> int:
    h = app.history
    end = app.when(args.until)
    start = app.when(args.since, default=h.start)
    if start > end:
        raise ValueError("--since is after --until")
    prefix = app.path(args.path)
    app.require_known(prefix)

    app.heading(
        f"Hotspots in {app.describe(prefix)}",
        f"{day(start)} → {day(end)}: files that existed at the end, by lines changed",
    )
    spots = h.hotspots(start, end, prefix, top=args.limit)
    if not spots:
        app.out.print("No changes in that time.")
        return 0
    rows: list[list[Cell]] = [
        [str(rank), spot.path, number(spot.commits), number(spot.churn), number(spot.lines),
         people(list(spot.authors))]
        for rank, spot in enumerate(spots, 1)
    ]  # fmt: skip
    path_width = app.path_width([s.path for s in spots], 48)
    table = app.table()
    fill(table, [
        ("#", {"justify": "right", "style": "dim"}),
        ("Path", {"overflow": "fold", "min_width": path_width}),
        ("Commits", {"justify": "right"}),
        ("Lines changed", {"justify": "right"}),
        ("Lines now", {"justify": "right"}),
        ("By", FLEXIBLE),
    ], rows)  # fmt: skip
    app.out.print(table)
    return 0


# =====================================================================================
# Entry point
# =====================================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git strata",
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-C", dest="directory", default=".", metavar="DIR",
                        help="run as if started in DIR (like git -C)")  # fmt: skip
    parser.add_argument("--rev", default="HEAD",
                        help="branch or commit whose history to read (default: HEAD)")  # fmt: skip
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    every = {"choices": PERIODS, "help": "period length (default: picked from the span)"}

    p = commands.add_parser("overview", help="the repository's history at a glance")
    p.add_argument("--every", **every)  # type: ignore[arg-type]
    p.set_defaults(handler=cmd_overview)

    p = commands.add_parser("at", help="what the repository looked like at a point in time")
    p.add_argument("when", help=WHEN_HELP)
    p.add_argument("path", nargs="?", help="only look inside this directory")
    p.add_argument("--depth", type=int, default=1, help="directory depth to group by (default: 1)")
    p.add_argument("--window", type=int, default=ACTIVE_WINDOW.days, metavar="DAYS",
                   help="days that count as 'active' (default: %(default)s)")  # fmt: skip
    p.add_argument("--limit", type=int, default=15, help="rows to show (default: %(default)s)")
    p.set_defaults(handler=cmd_at)

    p = commands.add_parser("owner", help="who wrote a file or directory, and how that changed")
    p.add_argument("path", nargs="?", help="file or directory (default: the current directory)")
    p.add_argument("--at", metavar="WHEN", help=f"as of when (default: the end); {WHEN_HELP}")
    p.add_argument("--every", **every)  # type: ignore[arg-type]
    p.add_argument("--limit", type=int, default=10, help="people to show (default: %(default)s)")
    p.set_defaults(handler=cmd_owner)

    p = commands.add_parser("file", help="the life story of one file")
    p.add_argument("path")
    p.add_argument("--limit", type=int, default=10, help="rows to show (default: %(default)s)")
    p.set_defaults(handler=cmd_file)

    p = commands.add_parser("hotspots", help="files that changed the most")
    p.add_argument("path", nargs="?", help="only look inside this directory")
    p.add_argument("--since", metavar="WHEN", help=f"default: the start; {WHEN_HELP}")
    p.add_argument("--until", metavar="WHEN", help="default: the end")
    p.add_argument("--limit", type=int, default=15, help="rows to show (default: %(default)s)")
    p.set_defaults(handler=cmd_hotspots)
    return parser


def main(
    argv: Sequence[str] | None = None,
    out: Console | None = None,
    err: Console | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    # No markup: paths and names may contain "[", and all styling goes through Text.
    out = out or Console(highlight=False, markup=False)
    err = err or Console(stderr=True, highlight=False, markup=False)
    try:
        git = Git(args.directory)
        try:
            git.resolve(args.rev)
        except GitError:
            if args.rev == "HEAD":
                git.toplevel()  # fails with git's own message outside a repository
                raise GitError("this repository has no commits yet") from None
            raise
        app = Strata(git, args.rev, out, err)
        return int(args.handler(app, args))
    except (GitError, ValueError) as error:
        err.print(Text("error: ", style="bold red").append(str(error)))
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
