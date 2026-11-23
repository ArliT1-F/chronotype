from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import WEIRD, Repo
from rich.console import Console

from git_strata.cli import main


def run(*argv: str, width: int = 120) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(
        list(argv),
        out=Console(file=out, width=width, markup=False, highlight=False),
        err=Console(file=err, width=width, markup=False, highlight=False),
    )
    return code, out.getvalue(), err.getvalue()


def test_overview(story: Repo) -> None:
    code, out, _ = run("-C", str(story.path), "overview", "--every", "quarter")
    assert code == 0
    assert "2023-01-10 → 2024-01-15" in out
    assert "2023-Q1" in out and "2024-Q1" in out
    assert "alice (2)" in out  # busiest in 2023-Q1 (carol also has 2; alphabetical)


def test_at(story: Repo) -> None:
    code, out, _ = run("-C", str(story.path), "at", "2023-03-15")
    assert code == 0
    assert "Drop the guide" in out  # the commit main was at
    assert "src/" in out and "logo.png" in out and "docs/" not in out
    assert "5 files added, 1 removed" in out  # src/util.py moved to src/core/util.py

    code, out, _ = run("-C", str(story.path), "at", "v1", "src", "--depth", "2")
    assert code == 0
    assert "src/core/util.py" in out and "src/app.py" in out
    assert "gone: src/util.py" not in out  # it was renamed before v1, not after


def test_at_shows_files_that_disappeared(story: Repo) -> None:
    code, out, _ = run("-C", str(story.path), "at", "2023-02-02")
    assert code == 0
    assert "gone: src/util.py" in out


def test_owner(story: Repo) -> None:
    code, out, _ = run("-C", str(story.path), "owner", "src/app.py")
    assert code == 0
    assert "dave" in out and "67%" in out
    assert "Main author over time" in out

    code, out, _ = run("-C", str(story.path), "owner", "docs/guide.md", "--at", "2023-05-01")
    assert "did not exist then" in out and "2023-07-01" in out


def test_owner_from_a_subdirectory(story: Repo) -> None:
    code, out, _ = run("-C", str(story.path / "src"), "owner", "core")
    assert code == 0
    assert "Who wrote src/core" in out and "bob" in out


def test_file(story: Repo) -> None:
    code, out, _ = run("-C", str(story.path), "file", "src/core/util.py")
    assert code == 0
    assert "src/util.py → src/core/util.py" in out
    assert "Tweak util" in out

    code, out, _ = run("-C", str(story.path), "file", WEIRD)
    assert code == 0 and WEIRD in out  # no markup surprises from the brackets


def test_hotspots(story: Repo) -> None:
    code, out, _ = run("-C", str(story.path), "hotspots", "--since", "2023-05-01")
    assert code == 0
    first_row = next(line for line in out.splitlines() if line.strip().startswith("1 "))
    assert "src/app.py" in first_row and "dave" in first_row


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["file", "src/nope.py"], "never existed"),
        (["file", "src/apq.py"], "Did you mean src/app.py"),
        (["file", "src"], "is a directory"),
        (["owner", "../elsewhere"], "outside the repository"),
        (["at", "someday"], "can't read 'someday'"),
        (["hotspots", "--since", "2024", "--until", "2023"], "--since is after --until"),
        (["--rev", "nope", "overview"], "not a commit: nope"),
    ],
)
def test_errors(story: Repo, argv: list[str], message: str) -> None:
    code, _, err = run("-C", str(story.path), *argv)
    assert code == 1
    assert message in err.replace("\n", " ")


def test_empty_repository(empty_repo: Repo) -> None:
    code, _, err = run("-C", str(empty_repo.path), "overview")
    assert code == 1 and "no commits yet" in err


def test_not_a_repository(tmp_path: Path) -> None:
    code, _, err = run("-C", str(tmp_path), "overview")
    assert code == 1 and "not a git repository" in err


def test_runs_as_a_git_subcommand(story: Repo) -> None:
    """With git-strata on PATH, `git strata` finds it."""
    script = Path(sys.executable).parent / "git-strata"
    if not script.exists():
        pytest.skip("git-strata is not installed in this environment")
    env_path = f"{script.parent}:{__import__('os').environ.get('PATH', '')}"
    result = subprocess.run(
        ["git", "-C", str(story.path), "strata", "owner", "src/app.py"],
        capture_output=True, text=True, env={"PATH": env_path, "COLUMNS": "100"},
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert "dave" in result.stdout
