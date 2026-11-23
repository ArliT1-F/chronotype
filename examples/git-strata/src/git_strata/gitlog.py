"""Read a repository's history from ``git log``.

Everything is read from NUL-separated (``-z``) output, so paths with spaces,
tabs, quotes or newlines come through unchanged. Each commit's ``--raw``
entries (what happened to a path: added, modified, deleted, renamed) are
matched with its ``--numstat`` entries (how many lines were added and deleted).
The output is streamed, so large histories are never held in memory as text.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

#: The id of the empty tree; ``git diff EMPTY_TREE <rev>`` lists every file in ``rev``.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

_RECORD = b"\x1e"
_FIELD = "\x1f"
# The subject goes last: it is the only field that may itself contain a separator.
_FORMAT = "%x1e%H%x1f%ct%x1f%at%x1f%aN%x1f%aE%x1f%P%x1f%s"

# Neutralise user configuration that would change the output we parse.
_CONFIG = (
    "-c", "log.showRoot=true",
    "-c", "log.showSignature=false",
    "-c", "diff.relative=false",
    "-c", "core.quotePath=false",
)  # fmt: skip

_DIFF_OPTIONS = ("--raw", "--numstat", "-M", "-z", "--no-abbrev", "--no-textconv", "--no-ext-diff")


class GitError(RuntimeError):
    """A git command failed."""


@dataclass(frozen=True)
class Change:
    """What one commit did to one path."""

    status: str
    """``A`` added, ``M`` modified, ``D`` deleted, ``R`` renamed, ``C`` copied, ``T`` new type."""
    path: str
    """The path after the change (for a deletion: the deleted path)."""
    old_path: str | None = None
    """The source path of a rename or copy."""
    added: int | None = None
    """Lines added; ``None`` for a binary file."""
    deleted: int | None = None
    """Lines deleted; ``None`` for a binary file."""

    @property
    def binary(self) -> bool:
        return self.added is None


@dataclass(frozen=True)
class Commit:
    sha: str
    committed: datetime
    authored: datetime
    author: str
    email: str
    parents: tuple[str, ...]
    subject: str
    changes: tuple[Change, ...] = ()


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def _timestamp(raw: str) -> datetime:
    return datetime.fromtimestamp(int(raw), tz=timezone.utc)


def split_nul(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Turn a stream of byte chunks into NUL-terminated tokens."""
    pending = b""
    for chunk in chunks:
        pending += chunk
        *tokens, pending = pending.split(b"\0")
        yield from tokens
    if pending:
        yield pending


@dataclass
class _Pending:
    header: list[str]
    raw: list[tuple[str, str | None, str]] = field(default_factory=list)
    stats: dict[str, tuple[int | None, int | None]] = field(default_factory=dict)

    def build(self) -> Commit:
        sha, committed, authored, author, email, parents, subject = self.header
        changes = tuple(
            Change(status, path, old_path, *self.stats.get(path, (None, None)))
            for status, old_path, path in self.raw
        )
        return Commit(
            sha=sha,
            committed=_timestamp(committed),
            authored=_timestamp(authored),
            author=author,
            email=email,
            parents=tuple(parents.split()),
            subject=subject,
            changes=changes,
        )


def _count(raw: bytes) -> int | None:
    return None if raw == b"-" else int(raw)


def parse_log(tokens: Iterable[bytes]) -> Iterator[Commit]:
    """Parse ``git log --format=<_FORMAT> --raw --numstat -z`` output, given as NUL tokens."""
    stream = iter(tokens)
    pending: _Pending | None = None
    for token in stream:
        token = token.lstrip(b"\n")
        if not token:
            continue
        if token.startswith(_RECORD):
            if pending is not None:
                yield pending.build()
            pending = _Pending(_decode(token[1:]).split(_FIELD, 6))
            continue
        if pending is None:
            raise GitError(f"unexpected git log output: {token[:80]!r}")
        if token.startswith(b":"):
            # ":100644 100644 <sha> <sha> R075", then the path(s) as separate tokens.
            status = token.rsplit(b" ", 1)[-1].decode()[0]
            old_path = _decode(next(stream)) if status in "RC" else None
            pending.raw.append((status, old_path, _decode(next(stream))))
        else:
            # "added<TAB>deleted<TAB>path", or for a rename "added<TAB>deleted<TAB>" + old + new.
            added, deleted, path = token.split(b"\t", 2)
            if not path:
                next(stream)  # the old path; the raw entry already has it
                path = next(stream)
            pending.stats[_decode(path)] = (_count(added), _count(deleted))
    if pending is not None:
        yield pending.build()


class Git:
    """A thin wrapper around the ``git`` command for one repository."""

    def __init__(self, repo: str | os.PathLike[str] = ".") -> None:
        self.repo = Path(repo)

    def _command(self, *args: str) -> list[str]:
        return ["git", "-C", str(self.repo), *_CONFIG, *args]

    def run(self, *args: str) -> str:
        """Run a git command and return its output (stripped of the final newline)."""
        result = subprocess.run(self._command(*args), capture_output=True)
        if result.returncode != 0:
            raise GitError(_decode(result.stderr).strip() or f"git {args[0]} failed")
        return _decode(result.stdout).rstrip("\n")

    def _stream(self, *args: str) -> Iterator[bytes]:
        """Run a git command and stream its NUL-separated output."""
        # stderr goes to a file: a full stderr pipe would block git while we read stdout.
        with tempfile.TemporaryFile() as errors:
            with subprocess.Popen(
                self._command(*args), stdout=subprocess.PIPE, stderr=errors
            ) as process:
                assert process.stdout is not None
                yield from split_nul(iter(lambda: process.stdout.read(1 << 16), b""))  # type: ignore[union-attr]
            if process.returncode != 0:
                errors.seek(0)
                raise GitError(_decode(errors.read()).strip() or f"git {args[0]} failed")

    # --- repository facts -------------------------------------------------------------

    def toplevel(self) -> Path:
        return Path(self.run("rev-parse", "--show-toplevel"))

    def prefix(self) -> str:
        """The current directory relative to the top of the work tree (``""`` at the top)."""
        return self.run("rev-parse", "--show-prefix")

    def resolve(self, rev: str) -> str:
        """The full commit id of ``rev``."""
        try:
            return self.run(
                "rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"
            )
        except GitError:
            raise GitError(f"not a commit: {rev}") from None

    def commit_time(self, rev: str) -> datetime:
        """When ``rev`` was committed."""
        return _timestamp(self.run("show", "-s", "--format=%ct", self.resolve(rev)))

    def describe_branch(self, rev: str) -> str:
        """A readable name for ``rev``: the branch name for ``HEAD``, otherwise ``rev`` itself."""
        if rev != "HEAD":
            return rev
        try:
            return self.run("symbolic-ref", "--short", "-q", "HEAD")
        except GitError:
            return "HEAD"

    # --- history ------------------------------------------------------------------------

    def mainline(self, rev: str = "HEAD") -> Iterator[Commit]:
        """
        The first-parent history of ``rev``, oldest first.

        Merge commits are diffed against their first parent, so applying the
        changes in order reproduces the exact tree of every commit on the branch.
        """
        yield from parse_log(
            self._stream(
                "log", f"--format={_FORMAT}", "--first-parent", "-m", "--reverse",
                *_DIFF_OPTIONS, self.resolve(rev), "--",
            )
        )  # fmt: skip

    def authored(self, rev: str = "HEAD") -> Iterator[Commit]:
        """
        Every non-merge commit reachable from ``rev``, roughly by author date, oldest first.

        Parents still come before their children. This is the stream that says
        who wrote what, including work done on branches that were merged later.
        """
        yield from parse_log(
            self._stream(
                "log", f"--format={_FORMAT}", "--no-merges", "--author-date-order", "--reverse",
                *_DIFF_OPTIONS, self.resolve(rev), "--",
            )
        )  # fmt: skip

    def tree_files(self, rev: str) -> set[str]:
        """Every file path in the tree of ``rev``."""
        tokens = self._stream("ls-tree", "-r", "-z", "--name-only", self.resolve(rev))
        return {_decode(token) for token in tokens if token}

    def line_counts(self, rev: str) -> dict[str, int | None]:
        """Lines per file in ``rev``, counted as ``--numstat`` counts them (``None``: binary)."""
        counts: dict[str, int | None] = {}
        stream = self._stream(
            "diff", "--numstat", "-z", "--no-renames", "--no-textconv", "--no-ext-diff",
            EMPTY_TREE, self.resolve(rev), "--",
        )  # fmt: skip
        for token in stream:
            if token:
                added, _deleted, path = token.split(b"\t", 2)
                counts[_decode(path)] = _count(added)
        return counts
