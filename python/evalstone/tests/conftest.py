import pytest

from evalstone.checks import registry


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts with an empty check registry and leaves it empty."""
    registry.clear()
    yield
    registry.clear()
