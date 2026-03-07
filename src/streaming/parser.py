from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping

from src.models import AISRecord


TIMESTAMP_COLUMN = "# Timestamp"
MOBILE_TYPE_COLUMN = "Type of mobile"
MMSI_COLUMN = "MMSI"
LATITUDE_COLUMN = "Latitude"
LONGITUDE_COLUMN = "Longitude"
SOG_COLUMN = "SOG"
DRAUGHT_COLUMN = "Draught"

TIMESTAMP_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)

NULL_VALUES = frozenset({
    "",
    "unknown",
    "undefined",
    "n/a",
    "na",
    "none",
    "null",
})

INVALID_MMSI_VALUES = frozenset({
    0,
    111111111,
    123456789,
    999999999,
})


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()
    return value or None


def _is_null_like(value: str | None) -> bool:
    cleaned = _clean_text(value)
    if cleaned is None:
        return True

    return cleaned.lower() in NULL_VALUES


def _parse_timestamp(value: str | None) -> datetime | None:
    cleaned = _clean_text(value)
    if cleaned is None or cleaned.lower() in NULL_VALUES:
        return None

    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    return None


def _parse_int(value: str | None) -> int | None:
    cleaned = _clean_text(value)
    if cleaned is None or cleaned.lower() in NULL_VALUES:
        return None

    try:
        return int(cleaned)
    except ValueError:
        try:
            as_float = float(cleaned)
        except ValueError:
            return None

        if not as_float.is_integer():
            return None

        return int(as_float)


def _parse_float(value: str | None) -> float | None:
    cleaned = _clean_text(value)
    if cleaned is None or cleaned.lower() in NULL_VALUES:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


class AISRowParser:
    def __init__(self, fieldnames: Iterable[str] | None) -> None:
        headers = set(fieldnames or ())

        required_columns = {
            TIMESTAMP_COLUMN,
            MOBILE_TYPE_COLUMN,
            MMSI_COLUMN,
            LATITUDE_COLUMN,
            LONGITUDE_COLUMN,
            SOG_COLUMN,
            DRAUGHT_COLUMN,
        }

        missing_columns = required_columns - headers
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Missing required CSV columns: {missing}")

        self.timestamp_key = TIMESTAMP_COLUMN
        self.mobile_type_key = MOBILE_TYPE_COLUMN
        self.mmsi_key = MMSI_COLUMN
        self.latitude_key = LATITUDE_COLUMN
        self.longitude_key = LONGITUDE_COLUMN
        self.sog_key = SOG_COLUMN
        self.draught_key = DRAUGHT_COLUMN

    @staticmethod
    def _is_valid_mmsi(mmsi: int) -> bool:
        if not (100_000_000 <= mmsi <= 999_999_999):
            return False
        if mmsi in INVALID_MMSI_VALUES:
            return False

        mmsi_str = str(mmsi)
        if len(set(mmsi_str)) == 1:
            return False

        return True

    @staticmethod
    def _is_valid_latitude(latitude: float) -> bool:
        return -90.0 <= latitude <= 90.0

    @staticmethod
    def _is_valid_longitude(longitude: float) -> bool:
        return -180.0 <= longitude <= 180.0

    @staticmethod
    def _is_valid_sog(sog: float | None) -> bool:
        if sog is None:
            return True
        return 0.0 <= sog <= 100.0

    @staticmethod
    def _is_valid_draught(draught: float | None) -> bool:
        if draught is None:
            return True
        return 0.0 <= draught <= 50.0

    def parse_row(self, row: Mapping[str, str]) -> AISRecord | None:
        mobile_type = _clean_text(row.get(self.mobile_type_key))
        if mobile_type == "Base Station":
            return None

        timestamp = _parse_timestamp(row.get(self.timestamp_key))
        mmsi = _parse_int(row.get(self.mmsi_key))
        latitude = _parse_float(row.get(self.latitude_key))
        longitude = _parse_float(row.get(self.longitude_key))
        sog = _parse_float(row.get(self.sog_key))
        draught = _parse_float(row.get(self.draught_key))

        if timestamp is None or mmsi is None or latitude is None or longitude is None:
            return None

        if not self._is_valid_mmsi(mmsi):
            return None

        if not self._is_valid_latitude(latitude):
            return None

        if not self._is_valid_longitude(longitude):
            return None

        if not self._is_valid_sog(sog):
            return None

        if not self._is_valid_draught(draught):
            return None

        return AISRecord(
            timestamp=timestamp,
            mmsi=mmsi,
            latitude=latitude,
            longitude=longitude,
            sog=sog,
            draught=draught,
        )
