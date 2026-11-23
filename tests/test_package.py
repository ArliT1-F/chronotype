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
