"""Execute every ``python`` code block in README.md (regression for #2)."""

import ast
import pathlib
import re
import warnings

README = pathlib.Path(__file__).resolve().parent.parent / "README.md"
_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)
_PRINT_WITH_EXPECTATION = re.compile(r"^(\s*)print\((.+)\)\s*#\s*(.+?)\s*$")


def _expected_literal(comment):
    """``# 50000`` or ``# 22.5 (interpolated)`` -> the literal, else None."""
    for candidate in (comment, comment.split()[0]):
        try:
            return repr(ast.literal_eval(candidate))
        except (ValueError, SyntaxError):
            continue
    return None


def _with_checks(code):
    """Turn ``print(expr)  # literal`` lines into assertions."""
    lines = []
    for line in code.splitlines():
        match = _PRINT_WITH_EXPECTATION.match(line)
        expected = _expected_literal(match.group(3)) if match else None
        if match and expected is not None:
            indent, expr = match.group(1), match.group(2)
            line = f"{indent}assert ({expr}) == {expected}, ({expr!r}, {expr})"
        lines.append(line)
    return "\n".join(lines)


def test_readme_has_examples():
    assert len(_BLOCK.findall(README.read_text(encoding="utf-8"))) >= 5


def test_readme_examples_run():
    """Blocks run in order in one namespace, as a reader would type them."""
    namespace = {"__name__": "readme_examples"}
    blocks = _BLOCK.findall(README.read_text(encoding="utf-8"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # README must not use deprecated APIs
        for number, block in enumerate(blocks, start=1):
            code = compile(_with_checks(block), f"README.md block {number}", "exec")
            exec(code, namespace)
