"""
Chronotype - Temporal-native data types for Python.

Every value inherently carries its full history.
"""

from chronotype.base import Temporal
from chronotype.containers import TemporalDict, TemporalList, TemporalSet
from chronotype.exceptions import (
    ChronotypeError,
    EmptyTemporalError,
    InterpolationError,
    InvalidTimestampError,
)
from chronotype.interpolation import (
    InterpolationStrategy,
    LinearInterpolation,
    NearestInterpolation,
    StepInterpolation,
)
from chronotype.numeric import TemporalBool, TemporalFloat, TemporalInt, TemporalString
from chronotype.query import TemporalQuery

__version__ = "0.1.1"

__all__ = [
    # Core
    "Temporal",
    # Numeric types
    "TemporalInt",
    "TemporalFloat",
    "TemporalBool",
    "TemporalString",
    # Containers
    "TemporalList",
    "TemporalDict",
    "TemporalSet",
    # Query
    "TemporalQuery",
    # Interpolation
    "InterpolationStrategy",
    "LinearInterpolation",
    "StepInterpolation",
    "NearestInterpolation",
    # Exceptions
    "ChronotypeError",
    "EmptyTemporalError",
    "InvalidTimestampError",
    "InterpolationError",
]
