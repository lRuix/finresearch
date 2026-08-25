"""Shared fixtures and import path setup."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = ROOT / "warehouse"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WAREHOUSE))

import pytest


@pytest.fixture(scope="session")
def dsn():
    return "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse_test"
