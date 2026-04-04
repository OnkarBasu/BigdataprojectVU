from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add project root to sys.path so imports like `from src...` work in pytest.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import AISRecord


@pytest.fixture
def make_record():
    def _make_record(
        *,
        mmsi: int = 123456789,
        timestamp: datetime = datetime(2025, 1, 1, 0, 0, 0),
        latitude: float = 10.0,
        longitude: float = 20.0,
        sog: float | None = 12.0,
        draught: float | None = 8.0,
    ) -> AISRecord:
        return AISRecord(
            timestamp=timestamp,
            mmsi=mmsi,
            latitude=latitude,
            longitude=longitude,
            sog=sog,
            draught=draught,
        )

    return _make_record
