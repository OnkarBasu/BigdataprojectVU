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

# Shadow fleet analytics in this project is focused on vessel messages only.
# By default, keep only Class A AIS transmissions.
VALID_MOBILE_TYPES = frozenset({
    "Class A",       # Large commercial vessels
    # "Class B",       # Small vessels
    # "Base Station",  # Coastal AIS station
    # "AtoN",          # Aid to Navigation (buoy, lighthouse)
    # "SAR Aircraft",  # Rescue aircraft
    # "Unknown",       # Unknown type
})

# Common placeholder or invalid MMSI values found in AIS datasets.
INVALID_MMSI_VALUES = frozenset({
    0,
    111111111,
    123456789,
    999999999,
})


def _clean_text(value: str | None) -> str | None:
    """
    Strip surrounding whitespace and normalize empty strings to None.

    Args:
        value: Raw text value from a CSV cell.

    Returns:
        Cleaned string if non-empty, otherwise None.
    """
    if value is None:
        return None

    cleaned = value.strip()
    return cleaned or None


def _is_null_like(value: str | None) -> bool:
    """
    Check whether a raw text value should be treated as null-like.

    Args:
        value: Raw text value from a CSV cell.

    Returns:
        True if the value is missing or matches a known null marker.
    """
    cleaned = _clean_text(value)
    if cleaned is None:
        return True

    return cleaned.lower() in NULL_VALUES


def _parse_timestamp(value: str | None) -> datetime | None:
    """
    Parse a timestamp using one of the supported AIS timestamp formats.

    Args:
        value: Raw timestamp string.

    Returns:
        Parsed datetime if successful, otherwise None.
    """
    cleaned = _clean_text(value)
    if cleaned is None or cleaned.lower() in NULL_VALUES:
        return None

    for timestamp_format in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(cleaned, timestamp_format)
        except ValueError:
            continue

    return None


def _parse_int(value: str | None) -> int | None:
    """
    Parse an integer value from text.

    Accepts strings like '123' and also float-like integer strings such as
    '123.0'. Rejects non-integer numeric values like '123.5'.

    Args:
        value: Raw numeric string.

    Returns:
        Parsed integer if successful, otherwise None.
    """
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
    """
    Parse a floating-point value from text.

    Args:
        value: Raw numeric string.

    Returns:
        Parsed float if successful, otherwise None.
    """
    cleaned = _clean_text(value)
    if cleaned is None or cleaned.lower() in NULL_VALUES:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


class AISRowParser:
    """
    Parse raw CSV rows into AISRecord objects.

    The parser validates required fields, converts values to typed fields,
    and filters out rows that are irrelevant or invalid for the shadow fleet
    detection task.

    Project-specific policy:
    - only vessel AIS messages of type "Class A" are accepted;
    - malformed rows and unsupported object types are skipped.
    """

    def __init__(self, fieldnames: Iterable[str] | None) -> None:
        """
        Initialize parser and validate that all required columns exist.

        Args:
            fieldnames: Column names from csv.DictReader.

        Raises:
            ValueError: If one or more required CSV columns are missing.
        """
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
    def _is_valid_mobile_type(mobile_type: str | None) -> bool:
        """
        Check whether the mobile type is accepted for the project.

        Args:
            mobile_type: Cleaned mobile type string.

        Returns:
            True if the row belongs to an accepted AIS mobile type.
        """
        if mobile_type is None:
            return False

        return mobile_type in VALID_MOBILE_TYPES

    @staticmethod
    def _is_valid_mmsi(mmsi: int) -> bool:
        """
        Validate MMSI value.

        Args:
            mmsi: Parsed MMSI number.

        Returns:
            True if MMSI looks structurally valid and is not a known placeholder.
        """
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
        """
        Validate latitude range.

        Args:
            latitude: Parsed latitude.

        Returns:
            True if latitude is within [-90, 90].
        """
        return -90.0 <= latitude <= 90.0

    @staticmethod
    def _is_valid_longitude(longitude: float) -> bool:
        """
        Validate longitude range.

        Args:
            longitude: Parsed longitude.

        Returns:
            True if longitude is within [-180, 180].
        """
        return -180.0 <= longitude <= 180.0

    @staticmethod
    def _is_valid_sog(sog: float | None) -> bool:
        """
        Validate speed over ground.

        Args:
            sog: Parsed SOG value.

        Returns:
            True if SOG is missing or falls into a reasonable range.
        """
        if sog is None:
            return True

        return 0.0 <= sog <= 100.0

    @staticmethod
    def _is_valid_draught(draught: float | None) -> bool:
        """
        Validate draught value.

        Args:
            draught: Parsed draught.

        Returns:
            True if draught is missing or falls into a reasonable range.
        """
        if draught is None:
            return True

        return 0.0 <= draught <= 50.0

    def parse_row(self, row: Mapping[str, str]) -> AISRecord | None:
        """
        Parse a single CSV row into an AISRecord.

        The row is skipped if:
        - it is not a supported vessel message type;
        - any required field is missing or malformed;
        - coordinates, MMSI, or numeric values are outside valid ranges.

        Args:
            row: A dictionary-like CSV row from csv.DictReader.

        Returns:
            Parsed AISRecord if the row is valid, otherwise None.
        """
        mobile_type = _clean_text(row.get(self.mobile_type_key))
        if not self._is_valid_mobile_type(mobile_type):
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
