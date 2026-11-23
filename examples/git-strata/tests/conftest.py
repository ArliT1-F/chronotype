"""Fixtures: small git repositories with a known, scripted history."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)  # type: ignore[arg-type,misc]


@dataclass
class Repo:
    path: Path

    def git(self, *args: str, when: datetime | None = None, author: str = "nobody") -> str:
        env = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": author,
            "GIT_AUTHOR_EMAIL": f"{author}@example.com",
            "GIT_COMMITTER_NAME": author,
            "GIT_COMMITTER_EMAIL": f"{author}@example.com",
        }
        if when is not None:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when.isoformat()
        result = subprocess.run(
            ["git", "-C", str(self.path), *args], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def write(self, name: str, content: str | bytes) -> None:
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)

    def append(self, name: str, lines: int, word: str) -> None:
        (self.path / name).parent.mkdir(parents=True, exist_ok=True)
        with (self.path / name).open("a") as handle:
            handle.writelines(f"{word} {i}\n" for i in range(lines))

    def commit(self, author: str, when: datetime, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message, when=when, author=author)
        return self.git("rev-parse", "HEAD")


def new_repo(path: Path) -> Repo:
    path.mkdir(parents=True, exist_ok=True)
    repo = Repo(path)
    repo.git("init", "-q", "-b", "main")
    return repo


WEIRD = "weird [name].txt"
NEWLINE = "\nstarts with a newline\t.txt"


def build_story(repo: Repo) -> Repo:
    """
    The history used by most tests (all times UTC):

    * 2023-01-10 alice: src/app.py (10 lines), docs/guide.md (3), logo.png (binary)
    * 2023-02-01 bob:   src/app.py +5; src/util.py (20)
    * branch feature, from there:
      * 2023-02-15 carol: renames src/util.py -> src/core/util.py, +4
      * 2023-02-20 carol: src/core/extra.py (8)
    * 2023-03-01 alice: deletes docs/guide.md (on main)
    * 2023-04-01 dave:  merges feature into main (tag v1)
    * 2023-06-01 dave:  src/app.py +30
    * 2023-07-01 eve:   docs/guide.md again (2), "weird [name].txt" (1), a name with a newline (1)
    * 2024-01-15 bob:   src/core/util.py +2
    """
    repo.append("src/app.py", 10, "alice")
    repo.append("docs/guide.md", 3, "guide")
    repo.write("logo.png", b"\x89PNG\0\0binary")
    repo.commit("alice", utc(2023, 1, 10), "Start")

    repo.append("src/app.py", 5, "bob")
    repo.append("src/util.py", 20, "util")
    repo.commit("bob", utc(2023, 2, 1), "Add util")

    repo.git("checkout", "-q", "-b", "feature")
    (repo.path / "src/core").mkdir()
    repo.git("mv", "src/util.py", "src/core/util.py")
    repo.append("src/core/util.py", 4, "carol")
    repo.commit("carol", utc(2023, 2, 15), "Move util into core")
    repo.append("src/core/extra.py", 8, "extra")
    repo.commit("carol", utc(2023, 2, 20), "Add extra")

    repo.git("checkout", "-q", "main")
    repo.git("rm", "-q", "docs/guide.md")
    repo.commit("alice", utc(2023, 3, 1), "Drop the guide")

    repo.git(
        "merge", "-q", "--no-ff", "feature", "-m", "Merge feature", when=utc(2023, 4, 1),
        author="dave",
    )  # fmt: skip
    repo.git("tag", "v1")

    repo.append("src/app.py", 30, "dave")
    repo.commit("dave", utc(2023, 6, 1), "Grow app")

    repo.append("docs/guide.md", 2, "new guide")
    repo.append(WEIRD, 1, "weird")
    repo.append(NEWLINE, 1, "newline")
    repo.commit("eve", utc(2023, 7, 1), "Bring the guide back")

    repo.append("src/core/util.py", 2, "bob again")
    repo.commit("bob", utc(2024, 1, 15), "Tweak util")
    return repo


@pytest.fixture(scope="session")
def story(tmp_path_factory: pytest.TempPathFactory) -> Repo:
    return build_story(new_repo(tmp_path_factory.mktemp("story")))


@pytest.fixture
def empty_repo(tmp_path: Path) -> Iterator[Repo]:
    yield new_repo(tmp_path / "empty")
