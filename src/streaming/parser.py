from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
import math

from src.models import AISRecord
from src.streaming.types import RawRow


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

INVALID_MMSI_VALUES = frozenset({
    0,
    111111111,
    123456789,
    999999999,
})

RAW_ROW_FIELD_COUNT = 7

TIMESTAMP_INDEX = 0
MOBILE_TYPE_INDEX = 1
MMSI_INDEX = 2
LATITUDE_INDEX = 3
LONGITUDE_INDEX = 4
SOG_INDEX = 5
DRAUGHT_INDEX = 6


@dataclass(frozen=True, slots=True)
class RawRowColumnIndices:
    """
    Positional indices of required AIS CSV columns.

    The main process uses this structure to extract only the required string
    fields from each CSV row before sending compact raw rows to workers.
    """

    timestamp: int
    mobile_type: int
    mmsi: int
    latitude: int
    longitude: int
    sog: int
    draught: int


def build_raw_row_column_indices(fieldnames: Iterable[str] | None) -> RawRowColumnIndices:
    """
    Build positional indices for all required AIS CSV columns.

    Args:
        fieldnames: Header row from ``csv.reader``.

    Returns:
        RawRowColumnIndices with positions of required columns.

    Raises:
        ValueError: If one or more required columns are missing.
    """
    headers = list(fieldnames or ())
    header_to_index = {header: index for index, header in enumerate(headers)}

    required_columns = {
        TIMESTAMP_COLUMN,
        MOBILE_TYPE_COLUMN,
        MMSI_COLUMN,
        LATITUDE_COLUMN,
        LONGITUDE_COLUMN,
        SOG_COLUMN,
        DRAUGHT_COLUMN,
    }

    missing_columns = required_columns - set(header_to_index)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required CSV columns: {missing}")

    return RawRowColumnIndices(
        timestamp=header_to_index[TIMESTAMP_COLUMN],
        mobile_type=header_to_index[MOBILE_TYPE_COLUMN],
        mmsi=header_to_index[MMSI_COLUMN],
        latitude=header_to_index[LATITUDE_COLUMN],
        longitude=header_to_index[LONGITUDE_COLUMN],
        sog=header_to_index[SOG_COLUMN],
        draught=header_to_index[DRAUGHT_COLUMN],
    )


def extract_raw_row(
    row: list[str],
    indices: RawRowColumnIndices,
) -> RawRow:
    """
    Extract the required AIS fields from a CSV row as a compact raw tuple.

    Missing trailing columns are normalized to empty strings.

    Args:
        row: Raw CSV row returned by ``csv.reader``.
        indices: Required column positions.

    Returns:
        RawRow tuple with the project-required AIS fields.
    """
    return (
        _get_cell(row, indices.timestamp),
        _get_cell(row, indices.mobile_type),
        _get_cell(row, indices.mmsi),
        _get_cell(row, indices.latitude),
        _get_cell(row, indices.longitude),
        _get_cell(row, indices.sog),
        _get_cell(row, indices.draught),
    )


def _get_cell(row: list[str], index: int) -> str:
    """
    Safely return a CSV cell by index.

    Args:
        row: Raw CSV row.
        index: Cell position.

    Returns:
        Cell value if present, otherwise an empty string.
    """
    if 0 <= index < len(row):
        return row[index]

    return ""


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
        except (ValueError, OSError):
            # OSError can occur in multiprocessing due to locale._getlang() issues
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
    Parse compact raw AIS rows into ``AISRecord`` objects.

    The parser:
    - validates required fields and numeric ranges;
    - converts raw strings into typed AIS fields;
    - skips malformed rows and rows irrelevant to the project.

    Project-specific filtering:
    - only vessel AIS messages of type ``Class A`` are accepted;
    - invalid MMSI values are rejected;
    - invalid or placeholder coordinates (including 0, 0) are rejected.
    """

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
        Validates if the given latitude is a finite number within the range [-90, 90].

        Args:
            latitude: The latitude value to validate.

        Returns:
            True if the latitude is finite and within range, False otherwise (including None).
        """
        if latitude is None:
            return False
        if not math.isfinite(latitude):
            return False
        if not (-90.0 <= latitude <= 90.0):
            return False
        return True

    @staticmethod
    def _is_valid_longitude(longitude: float) -> bool:
        """
        Validates if the given longitude is a finite number within the range [-180, 180].

        Args:
            longitude: The longitude value to validate.

        Returns:
            True if the longitude is finite and within range, False otherwise (including None).
        """
        if longitude is None:
            return False
        if not math.isfinite(longitude):
            return False
        if not (-180.0 <= longitude <= 180.0):
            return False
        return True

    @staticmethod
    def _is_zero_coordinate(lat: float, lon: float) -> bool:
        """
        Checks if the coordinates are effectively zero (0,0).

        This is often used to identify placeholder or invalid GPS/AIS data where
        latitude and longitude are missing or reset to origin.

        Args:
            lat: The latitude value to check.
            lon: The longitude value to check.

        Returns:
            True if both latitude and longitude are within a small epsilon of 0.0,
            False otherwise.
        """
        return abs(lat) < 1e-6 and abs(lon) < 1e-6

    def parse_row(self, row: RawRow) -> AISRecord | None:
        """
        Parse one compact raw AIS row into an ``AISRecord``.
    
        The row is accepted only if it:
        - has the expected compact field layout;
        - represents a supported AIS mobile type;
        - contains a valid timestamp and MMSI;
        - contains finite in-range coordinates;
        - does not use the placeholder coordinate (0, 0).
    
        Optional numeric fields such as draught may remain ``None`` when
        missing or null-like.
    
        Returns:
            Parsed ``AISRecord`` if the row is valid for the project,
            otherwise ``None``.
        """
        if len(row) != RAW_ROW_FIELD_COUNT:
            return None

        mobile_type = _clean_text(row[MOBILE_TYPE_INDEX])
        if not self._is_valid_mobile_type(mobile_type):
            return None

        timestamp = _parse_timestamp(row[TIMESTAMP_INDEX])
        if timestamp is None:
            return None

        mmsi = _parse_int(row[MMSI_INDEX])
        if mmsi is None or not self._is_valid_mmsi(mmsi):
            return None

        latitude = _parse_float(row[LATITUDE_INDEX])
        if latitude is None or not self._is_valid_latitude(latitude):
            return None

        longitude = _parse_float(row[LONGITUDE_INDEX])
        if longitude is None or not self._is_valid_longitude(longitude):
            return None

        if self._is_zero_coordinate(latitude, longitude):
            return None

        sog = _parse_float(row[SOG_INDEX])
        draught = None if _is_null_like(row[DRAUGHT_INDEX]) else _parse_float(row[DRAUGHT_INDEX])

        return AISRecord(
            timestamp=timestamp,
            mmsi=mmsi,
            latitude=latitude,
            longitude=longitude,
            sog=sog,
            draught=draught,
        )
