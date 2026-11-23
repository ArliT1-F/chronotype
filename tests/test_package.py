"""Tests for the public package surface."""

import chronotype


class TestExports:
    """Regression (#2): public names are exported from the package root."""

    def test_new_exports(self):
        from chronotype import NearestInterpolation, TemporalSet, TemporalString

        assert TemporalString is chronotype.numeric.TemporalString
        assert NearestInterpolation is chronotype.interpolation.NearestInterpolation
        assert TemporalSet is chronotype.containers.TemporalSet

    def test_all_names_are_importable(self):
        for name in chronotype.__all__:
            assert hasattr(chronotype, name), name
        for name in ("TemporalString", "TemporalSet", "NearestInterpolation"):
            assert name in chronotype.__all__


class TestCleanups:
    """#14: unused API removed."""

    def test_unused_immutable_error_removed(self):
        import chronotype.exceptions

        assert not hasattr(chronotype.exceptions, "ImmutableTemporalError")


class TestVersion:
    def test_version_is_0_1_2_and_matches_pyproject(self):
        import pathlib
        import re

        pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
        match = re.search(r'^version = "([^"]+)"', pyproject.read_text(), re.MULTILINE)
        assert match is not None
        assert chronotype.__version__ == match.group(1) == "0.1.2"
