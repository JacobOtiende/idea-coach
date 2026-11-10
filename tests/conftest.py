import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db as dbmod  # noqa: E402


@pytest.fixture
def db():
    return dbmod.DB(":memory:")
