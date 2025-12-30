"""Pytest configuration and fixtures."""

from datetime import datetime, timedelta

import pytest


@pytest.fixture
def base_time() -> datetime:
    """Base time for testing."""
    return datetime(2024, 1, 1, 0, 0, 0)


@pytest.fixture
def time_series(base_time: datetime) -> list:
    """Series of timestamps."""
    return [base_time + timedelta(days=i) for i in range(10)]