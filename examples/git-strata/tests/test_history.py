from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import NEWLINE, WEIRD, Repo, utc

from git_strata.gitlog import Git, GitError
from git_strata.history import RepoHistory, auto_period, group_by_directory, label, periods

END = utc(2030, 1, 1)


@pytest.fixture(scope="module")
def history(story: Repo) -> RepoHistory:
    return RepoHistory.from_git(Git(story.path))


def assert_matches_git(history: RepoHistory, git: Git) -> int:
    """Every commit on the branch: the reconstructed tree equals git's own."""
    checked = 0
    for when, sha in history.head.history():
        files = git.tree_files(sha)
        assert set(history.files_at(when)) == files, sha
        expected = {path: count or 0 for path, count in git.line_counts(sha).items()}
        assert {path: history.lines[path].at(when) for path in files} == expected, sha
        assert history.file_count.at(when) == len(files)
        assert history.total_lines.at(when) == sum(expected.values())
        checked += 1
    return checked


def test_every_commit_matches_git(history: RepoHistory, story: Repo) -> None:
    assert assert_matches_git(history, Git(story.path)) == 7  # 6 commits + 1 merge on main


def test_chronotype_repository_matches_git() -> None:
    """The repository this example lives in: real merges, real renames."""
    try:
        top = Git(Path(__file__).parent).toplevel()
    except GitError:
        pytest.skip("not inside a git repository")
    git = Git(top)
    assert assert_matches_git(RepoHistory.from_git(git), git) > 0


def test_shallow_clone(story: Repo, tmp_path: Path) -> None:
    clone = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "3", f"file://{story.path}", str(clone)], check=True
    )
    git = Git(clone)
    history = RepoHistory.from_git(git)
    assert assert_matches_git(history, git) == 3
    assert set(history.files_at(END)) == git.tree_files("HEAD")


def test_files_at_points_in_time(history: RepoHistory) -> None:
    assert history.files_at(utc(2023, 1, 1)) == []
    assert history.files_at(utc(2023, 3, 15)) == ["logo.png", "src/app.py", "src/util.py"]
    after_merge = history.files_at(utc(2023, 4, 2))
    assert "src/core/util.py" in after_merge and "src/util.py" not in after_merge
    core = history.files_at(utc(2023, 4, 2), "src/core")
    assert core == ["src/core/extra.py", "src/core/util.py"]
    assert set(history.files_at(END)) == {
        "docs/guide.md", "logo.png", "src/app.py", "src/core/extra.py", "src/core/util.py",
        WEIRD, NEWLINE,
    }  # fmt: skip


def test_lines_and_binary_files(history: RepoHistory) -> None:
    assert history.lines["src/app.py"].current() == 45
    assert history.lines_at(utc(2023, 3, 15)) == 15 + 20
    assert history.lines_at(END, "src") == 45 + 26 + 8
    assert "logo.png" in history.binary
    assert history.lines["logo.png"].current() == 0


def test_renamed_file_keeps_its_history(history: RepoHistory) -> None:
    story = history.story("src/core/util.py")
    assert story.ancestry == [(utc(2023, 4, 1), "src/util.py", "src/core/util.py")]
    assert [n for _, n in story.lines] == [20, 24, 26]
    assert story.authors == {"bob": 22, "carol": 4}
    assert story.commits == 3  # created, moved, tweaked
    # The old path is gone from the merge on.
    assert history.alive["src/util.py"].when_true(until=END) == [(utc(2023, 2, 1), utc(2023, 4, 1))]


def test_deleted_and_recreated_file(history: RepoHistory) -> None:
    story = history.story("docs/guide.md")
    assert story.lifetimes == [
        (utc(2023, 1, 10), utc(2023, 3, 1)),
        (utc(2023, 7, 1), history.end),
    ]
    assert story.alive
    # The new file has new authors; the old one's are still there for its own lifetime.
    assert story.authors == {"eve": 2}
    assert history.authors_of("docs/guide.md", utc(2023, 2, 1)) == {"alice": 3}


def test_ownership(history: RepoHistory) -> None:
    assert history.authors_of("src/app.py", END) == {"alice": 10, "bob": 5, "dave": 30}
    assert history.authors_of("src/app.py", utc(2023, 3, 1)) == {"alice": 10, "bob": 5}
    assert history.ownership(END, "src") == {"alice": 10, "bob": 27, "carol": 12, "dave": 30}
    # Before the merge, main had no src/core; carol's work was on the branch.
    assert "carol" not in history.ownership(utc(2023, 3, 15))


def test_bus_factor(history: RepoHistory) -> None:
    # Authors per file at the end: app.py dave (alice and bob have less than 75%
    # of dave's lines); util.py bob; extra.py carol; logo.png alice; guide.md
    # (re-created by eve, so alice's old lines don't count), weird and newline eve.
    # Without eve, 4 of 7 files have an author; without alice too, 3 of 7: under half.
    bus = history.bus_factor(END)
    assert (bus.value, bus.people, bus.files) == (2, ("eve", "alice"), 7)
    # Two files, one author each: losing one leaves exactly half, which isn't more than half.
    assert history.bus_factor(END, "src/core").people == ("bob", "carol")
    assert history.bus_factor(utc(2022, 1, 1)).value == 0


def test_contributors_and_activity(history: RepoHistory) -> None:
    assert history.contributors_at(utc(2023, 2, 10)) == {"alice", "bob"}
    assert history.contributors_at(END) == {"alice", "bob", "carol", "dave", "eve"}
    # Merges are not counted as work: dave's merge on 2023-04-01 is not activity.
    assert history.active_contributors(utc(2023, 4, 1)) == {"alice": 2, "bob": 1, "carol": 2}
    assert history.commits.current() == 8
    top = history.top_authors(utc(2023, 1, 1), utc(2023, 3, 1))
    # alice: 10 + 3 lines and a binary file (counted as 1); deleting the guide adds nothing.
    assert top == [("alice", 2, 14), ("carol", 2, 12), ("bob", 1, 25)]


def test_hotspots(history: RepoHistory) -> None:
    spots = history.hotspots(utc(2023, 5, 1), END)
    assert [s.path for s in spots] == [
        "src/app.py", "docs/guide.md", "src/core/util.py", NEWLINE, WEIRD,
    ]  # fmt: skip
    assert (spots[0].churn, spots[0].commits, spots[0].authors) == (30, 1, ("dave",))
    # A rename carries churn along, so the whole lineage counts.
    whole = {s.path: s for s in history.hotspots(history.start, END)}
    assert whole["src/core/util.py"].churn == 20 + 4 + 2
    assert whole["src/core/util.py"].authors == ("bob", "carol")


def test_out_of_order_timestamps_are_clamped(tmp_path: Path) -> None:
    from conftest import new_repo

    repo = new_repo(tmp_path / "skew")
    repo.append("a.txt", 1, "a")
    repo.commit("alice", utc(2024, 5, 1), "first")
    repo.append("a.txt", 1, "b")
    repo.commit("bob", utc(2024, 4, 1), "committed with a clock in the past")
    history = RepoHistory.from_git(Git(repo.path))
    assert history.lines["a.txt"].history() == [(utc(2024, 5, 1), 2)]
    assert history.authors_of("a.txt", END) == {"alice": 1, "bob": 1}


def test_periods() -> None:
    rows = list(periods(utc(2023, 11, 20), utc(2024, 2, 10), "month"))
    assert [label(a, "month") for a, _ in rows] == ["2023-11", "2023-12", "2024-01", "2024-02"]
    assert rows[-1] == (utc(2024, 2, 1), utc(2024, 2, 10))
    quarters = periods(utc(2023, 11, 1), utc(2024, 4, 1), "quarter")
    assert [label(a, "quarter") for a, _ in quarters] == ["2023-Q4", "2024-Q1", "2024-Q2"]
    assert auto_period(utc(2023, 1, 1), utc(2023, 2, 1)) == "week"
    assert auto_period(utc(2020, 1, 1), utc(2023, 1, 1)) == "quarter"


def test_group_by_directory() -> None:
    paths = ["a/b/c.py", "a/d.py", "e.py"]
    assert group_by_directory(paths, "", 1) == {"a/": ["a/b/c.py", "a/d.py"], "e.py": ["e.py"]}
    assert group_by_directory(paths[:2], "a", 1) == {"a/b/": ["a/b/c.py"], "a/d.py": ["a/d.py"]}
