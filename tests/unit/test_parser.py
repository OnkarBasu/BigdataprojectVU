from __future__ import annotations

from datetime import datetime

import pytest

from src.models import AISRecord
from src.streaming.parser import (
    AISRowParser,
    RawRowColumnIndices,
    build_raw_row_column_indices,
    extract_raw_row,
)


# -------------------------
# build_raw_row_column_indices
# -------------------------

def test_build_raw_row_column_indices_returns_expected_indices() -> None:
    fieldnames = [
        "Longitude",
        "SOG",
        "# Timestamp",
        "Draught",
        "MMSI",
        "Latitude",
        "Type of mobile",
    ]

    indices = build_raw_row_column_indices(fieldnames)

    assert indices.timestamp == 2
    assert indices.mobile_type == 6
    assert indices.mmsi == 4
    assert indices.latitude == 5
    assert indices.longitude == 0
    assert indices.sog == 1
    assert indices.draught == 3


def test_build_raw_row_column_indices_raises_when_required_columns_are_missing() -> None:
    fieldnames = [
        "# Timestamp",
        "MMSI",
        "Latitude",
        "Longitude",
    ]

    with pytest.raises(ValueError, match="Missing required CSV columns"):
        build_raw_row_column_indices(fieldnames)


# -------------------------
# extract_raw_row
# -------------------------

def test_extract_raw_row_returns_fields_in_project_order() -> None:
    row = [
        "223456789",             # MMSI
        "10.5",                  # Latitude
        "20.5",                  # Longitude
        "Class A",               # Type of mobile
        "01/09/2025 12:00:00",   # Timestamp
        "7.2",                   # SOG
        "8.5",                   # Draught
    ]

    indices = RawRowColumnIndices(
        timestamp=4,
        mobile_type=3,
        mmsi=0,
        latitude=1,
        longitude=2,
        sog=5,
        draught=6,
    )

    raw_row = extract_raw_row(row, indices)

    assert raw_row == (
        "01/09/2025 12:00:00",
        "Class A",
        "223456789",
        "10.5",
        "20.5",
        "7.2",
        "8.5",
    )


def test_extract_raw_row_fills_missing_trailing_values_with_empty_strings() -> None:
    row = [
        "223456789",
        "10.5",
    ]

    indices = RawRowColumnIndices(
        timestamp=5,
        mobile_type=4,
        mmsi=0,
        latitude=1,
        longitude=6,
        sog=7,
        draught=8,
    )

    raw_row = extract_raw_row(row, indices)

    assert raw_row == (
        "",
        "",
        "223456789",
        "10.5",
        "",
        "",
        "",
    )


# -------------------------
# AISRowParser validation helpers
# -------------------------

def test_is_valid_mobile_type_accepts_class_a() -> None:
    assert AISRowParser._is_valid_mobile_type("Class A") is True


def test_is_valid_mobile_type_rejects_other_types() -> None:
    assert AISRowParser._is_valid_mobile_type("Class B") is False


@pytest.mark.parametrize("mmsi", [223456789, 245014000, 538009722])
def test_is_valid_mmsi_accepts_valid_values(mmsi: int) -> None:
    assert AISRowParser._is_valid_mmsi(mmsi) is True


@pytest.mark.parametrize(
    "mmsi",
    [
        0,
        111111111,
        123456789,   # explicitly forbidden by project rules
        1234567890,  # too long
        12345678,    # too short
        999999999,
    ],
)
def test_is_valid_mmsi_rejects_invalid_values(mmsi: int) -> None:
    assert AISRowParser._is_valid_mmsi(mmsi) is False


def test_is_valid_latitude_accepts_valid_value() -> None:
    assert AISRowParser._is_valid_latitude(45.0) is True


def test_is_valid_latitude_rejects_out_of_range_value() -> None:
    assert AISRowParser._is_valid_latitude(95.0) is False


def test_is_valid_longitude_accepts_valid_value() -> None:
    assert AISRowParser._is_valid_longitude(120.0) is True


def test_is_valid_longitude_rejects_out_of_range_value() -> None:
    assert AISRowParser._is_valid_longitude(190.0) is False


def test_is_zero_coordinate_detects_origin() -> None:
    assert AISRowParser._is_zero_coordinate(0.0, 0.0) is True


def test_is_zero_coordinate_rejects_normal_coordinate() -> None:
    assert AISRowParser._is_zero_coordinate(0.1, 0.0) is False


# -------------------------
# parse_row
# -------------------------

def test_parse_row_returns_ais_record_for_valid_row() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "223456789",
        "10.5",
        "20.5",
        "7.2",
        "8.5",
    )

    record = parser.parse_row(row)

    assert isinstance(record, AISRecord)
    assert record.timestamp == datetime(2025, 9, 1, 12, 34, 56)
    assert record.mmsi == 223456789
    assert record.latitude == 10.5
    assert record.longitude == 20.5
    assert record.sog == 7.2
    assert record.draught == 8.5


def test_parse_row_returns_none_when_row_has_wrong_length() -> None:
    parser = AISRowParser()

    record = parser.parse_row(("01/09/2025 12:34:56", "Class A"))  # type: ignore[arg-type]

    assert record is None


def test_parse_row_accepts_timestamp_without_seconds() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34",
        "Class A",
        "223456789",
        "10.5",
        "20.5",
        "7.2",
        "8.5",
    )

    record = parser.parse_row(row)

    assert record is not None
    assert record.timestamp == datetime(2025, 9, 1, 12, 34)


def test_parse_row_returns_none_for_invalid_mobile_type() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class B",
        "223456789",
        "10.5",
        "20.5",
        "7.2",
        "8.5",
    )

    assert parser.parse_row(row) is None


def test_parse_row_returns_none_for_invalid_timestamp() -> None:
    parser = AISRowParser()
    row = (
        "2025-09-01 12:34:56",
        "Class A",
        "223456789",
        "10.5",
        "20.5",
        "7.2",
        "8.5",
    )

    assert parser.parse_row(row) is None


def test_parse_row_returns_none_for_invalid_mmsi() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "111111111",
        "10.5",
        "20.5",
        "7.2",
        "8.5",
    )

    assert parser.parse_row(row) is None


def test_parse_row_returns_none_for_invalid_latitude() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "223456789",
        "100.0",
        "20.5",
        "7.2",
        "8.5",
    )

    assert parser.parse_row(row) is None


def test_parse_row_returns_none_for_invalid_longitude() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "223456789",
        "10.5",
        "200.0",
        "7.2",
        "8.5",
    )

    assert parser.parse_row(row) is None


def test_parse_row_returns_none_for_zero_coordinate() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "223456789",
        "0.0",
        "0.0",
        "7.2",
        "8.5",
    )

    assert parser.parse_row(row) is None


def test_parse_row_sets_draught_to_none_for_null_like_value() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "223456789",
        "10.5",
        "20.5",
        "7.2",
        "null",
    )

    record = parser.parse_row(row)

    assert record is not None
    assert record.draught is None


def test_parse_row_keeps_none_sog_when_missing() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "223456789",
        "10.5",
        "20.5",
        "",
        "8.5",
    )

    record = parser.parse_row(row)

    assert record is not None
    assert record.sog is None


def test_parse_row_keeps_draught_none_when_invalid_non_null_value() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "223456789",
        "10.5",
        "20.5",
        "7.2",
        "abc",
    )

    record = parser.parse_row(row)

    assert record is not None
    assert record.draught is None


def test_parse_row_accepts_float_like_integer_mmsi() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "223456789.0",
        "10.5",
        "20.5",
        "7.2",
        "8.5",
    )

    record = parser.parse_row(row)

    assert record is not None
    assert record.mmsi == 223456789


def test_parse_row_returns_none_for_non_integer_float_mmsi() -> None:
    parser = AISRowParser()
    row = (
        "01/09/2025 12:34:56",
        "Class A",
        "223456789.5",
        "10.5",
        "20.5",
        "7.2",
        "8.5",
    )

    assert parser.parse_row(row) is None
