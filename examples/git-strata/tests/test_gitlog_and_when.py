from __future__ import annotations

import pytest
from conftest import NEWLINE, Repo, utc

from git_strata.gitlog import Change, Git, GitError, parse_log, split_nul
from git_strata.when import months_before, parse_when

HEADER = (
    "\x1e{sha}\x1f1704103200\x1f1704100000\x1fAda\x1fada@example.com\x1f{parents}"
    "\x1fSubject \x1f with separator"
)


def tokens(*parts: str) -> list[bytes]:
    return list(split_nul([("\0".join(parts) + "\0").encode()]))


def test_split_nul_across_chunk_boundaries() -> None:
    chunks = [b"ab", b"c\0d", b"\0\0e"]
    assert list(split_nul(chunks)) == [b"abc", b"d", b"", b"e"]


def test_parse_log() -> None:
    raw = ":000000 100644 " + "0" * 40 + " " + "1" * 40
    stream = tokens(
        HEADER.format(sha="a" * 40, parents=""),
        f"\n{raw} A", "new file.txt",
        f"{raw} R087", "old\tname", "\nnew name",
        f"{raw} D", "gone.bin",
        "3\t0\tnew file.txt",
        "1\t2\t", "old\tname", "\nnew name",
        "-\t-\tgone.bin",
        HEADER.format(sha="b" * 40, parents="a" * 40),  # an empty commit
    )  # fmt: skip
    first, second = parse_log(stream)
    assert first.sha == "a" * 40
    assert first.committed == utc(2024, 1, 1, 10, 0)
    assert (first.author, first.email, first.parents) == ("Ada", "ada@example.com", ())
    assert first.subject == "Subject \x1f with separator"
    assert first.changes == (
        Change("A", "new file.txt", None, 3, 0),
        Change("R", "\nnew name", "old\tname", 1, 2),
        Change("D", "gone.bin", None, None, None),
    )
    assert first.changes[2].binary
    assert second.parents == ("a" * 40,) and second.changes == ()


def test_parse_log_rejects_garbage() -> None:
    with pytest.raises(GitError):
        list(parse_log([b"not a header"]))


def test_git_reads_odd_paths(story: Repo) -> None:
    git = Git(story.path)
    assert NEWLINE in git.tree_files("HEAD")
    commits = list(git.mainline())
    assert [c.subject for c in commits][-1] == "Tweak util"
    merge = next(c for c in commits if len(c.parents) == 2)
    assert {(c.status, c.path, c.old_path) for c in merge.changes} == {
        ("R", "src/core/util.py", "src/util.py"),
        ("A", "src/core/extra.py", None),
    }


def test_git_errors(tmp_path: pytest.TempPathFactory, story: Repo) -> None:
    with pytest.raises(GitError, match="not a commit"):
        Git(story.path).resolve("no-such-branch")
    with pytest.raises(GitError):
        Git(tmp_path).toplevel()  # type: ignore[arg-type]


NOW = utc(2024, 3, 31, 12, 0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("now", NOW),
        ("2023", utc(2023, 1, 1)),
        ("2023-04", utc(2023, 4, 1)),
        ("2023-04-05", utc(2023, 4, 5)),
        ("2023-04-05T06:07", utc(2023, 4, 5, 6, 7)),
        ("2023-04-05T06:07Z", utc(2023, 4, 5, 6, 7)),
        ("2023-04-05T08:07+02:00", utc(2023, 4, 5, 6, 7)),
        ("90d", utc(2024, 1, 1, 12, 0)),
        ("2 weeks ago", utc(2024, 3, 17, 12, 0)),
        ("1 month ago", utc(2024, 2, 29, 12, 0)),  # clamped to the end of February
        ("6m", utc(2023, 9, 30, 12, 0)),
        ("2y", utc(2022, 3, 31, 12, 0)),
    ],
)
def test_parse_when(text: str, expected: object) -> None:
    assert parse_when(text, now=NOW) == expected


def test_parse_when_revisions(story: Repo) -> None:
    git = Git(story.path)
    assert parse_when("v1", git) == utc(2023, 4, 1)
    assert parse_when("HEAD~1", git) == utc(2023, 7, 1)
    with pytest.raises(ValueError, match="can't read"):
        parse_when("not-a-thing", git)


def test_months_before() -> None:
    assert months_before(utc(2024, 1, 15), 1) == utc(2023, 12, 15)
    assert months_before(utc(2024, 3, 31), 13) == utc(2023, 2, 28)
