"""Generate a large repository with a realistic-looking history, for timing git-strata.

    python benchmarks/synthetic_repo.py /tmp/big --commits 20000 --authors 40

The history is deterministic for a given seed: files are added, edited (lines
inserted and removed), renamed and deleted by a pool of authors, and every so
often a short-lived branch is merged back with a merge commit.
"""

from __future__ import annotations

import argparse
import random
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


class Generator:
    def __init__(self, seed: int, authors: int) -> None:
        self.random = random.Random(seed)
        self.authors = [f"Author {i:02d}" for i in range(authors)]
        # A few people do most of the work.
        self.weights = [1 / (i + 1) ** 1.1 for i in range(authors)]
        self.files: dict[str, list[str]] = {}
        self.counter = 0
        self.mark = 0
        self.when = datetime(2018, 1, 1, tzinfo=timezone.utc)
        self.out: list[bytes] = []

    def emit(self, text: str) -> None:
        self.out.append(text.encode())

    def data(self, payload: str) -> None:
        raw = payload.encode()
        self.out.append(f"data {len(raw)}\n".encode() + raw + b"\n")

    def new_line(self) -> str:
        self.counter += 1
        return f"line {self.counter} {self.random.random():.6f}\n"

    def new_path(self) -> str:
        r = self.random
        parts = [r.choice(["src", "src", "src", "lib", "tests", "docs", "tools"])]
        parts += [r.choice(["core", "api", "ui", "db", "net", "util", "io"])
                  for _ in range(r.randint(0, 2))]  # fmt: skip
        return "/".join(parts + [f"f{self.counter}_{r.randint(0, 999)}.py"])

    def commit(self, ref: str, parents: list[int], author: str) -> int:
        r = self.random
        self.when += timedelta(minutes=r.randint(5, 600))
        self.mark += 1
        stamp = f"{int(self.when.timestamp())} +0000"
        self.emit(f"commit {ref}\nmark :{self.mark}\n")
        self.emit(f"author {author} <{author.replace(' ', '.').lower()}@example.com> {stamp}\n")
        self.emit(f"committer {author} <{author.replace(' ', '.').lower()}@example.com> {stamp}\n")
        self.data(f"change {self.mark}")
        if parents:
            self.emit(f"from :{parents[0]}\n")
            for parent in parents[1:]:
                self.emit(f"merge :{parent}\n")
        return self.mark

    def change_files(self) -> None:
        r = self.random
        for _ in range(r.randint(1, 4)):
            roll = r.random()
            if not self.files or roll < 0.12:
                path = self.new_path()
                self.files[path] = [self.new_line() for _ in range(r.randint(5, 200))]
            elif roll < 0.14 and len(self.files) > 20:
                path = r.choice(sorted(self.files))
                del self.files[path]
                self.emit(f'D "{path}"\n')
                continue
            elif roll < 0.16:
                old = r.choice(sorted(self.files))
                path = self.new_path()
                self.files[path] = self.files.pop(old)
                self.emit(f'R "{old}" "{path}"\n')
            else:
                path = r.choice(sorted(self.files))
                lines = self.files[path]
                for _ in range(r.randint(0, min(10, len(lines) // 4))):
                    lines.pop(r.randrange(len(lines)))
                at = r.randint(0, len(lines))
                lines[at:at] = [self.new_line() for _ in range(r.randint(0, 30))]
            self.emit(f'M 100644 inline "{path}"\n')
            self.data("".join(self.files[path]))

    def run(self, commits: int) -> bytes:
        r = self.random
        tip = 0
        made = 0
        while made < commits:
            if made and r.random() < 0.03:
                # A short branch, merged back with a merge commit.
                saved = {p: list(lines) for p, lines in self.files.items()}
                branch_tip = tip
                for _ in range(r.randint(1, 5)):
                    branch_tip = self.commit("refs/heads/topic", [branch_tip], self.author())
                    self.change_files()
                    made += 1
                branch_files = self.files
                self.files = saved
                # Main moves on meanwhile, touching only files the branch left alone.
                tip = self.commit("refs/heads/main", [tip], self.author())
                self.change_files()
                made += 1
                merged = {**self.files, **branch_files}
                for path in set(self.files) - set(branch_files):
                    if path in saved:  # deleted or renamed on the branch
                        merged.pop(path, None)
                tip = self.commit("refs/heads/main", [tip, branch_tip], self.author())
                self.emit("deleteall\n")
                for path, lines in sorted(merged.items()):
                    self.emit(f'M 100644 inline "{path}"\n')
                    self.data("".join(lines))
                self.files = merged
            else:
                tip = self.commit("refs/heads/main", [tip] if tip else [], self.author())
                self.change_files()
                made += 1
        return b"".join(self.out)

    def author(self) -> str:
        return self.random.choices(self.authors, self.weights)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--commits", type=int, default=5000)
    parser.add_argument("--authors", type=int, default=30)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    args.path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(args.path)], check=True)
    stream = Generator(args.seed, args.authors).run(args.commits)
    git = ["git", "-C", str(args.path)]
    subprocess.run([*git, "fast-import", "--quiet"], input=stream, check=True)
    subprocess.run([*git, "checkout", "-q", "main"], check=True)


if __name__ == "__main__":
    main()
