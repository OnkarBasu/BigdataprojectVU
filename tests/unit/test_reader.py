from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.streaming.reader import (
    stream_csv_files_in_chunks,
    stream_csv_in_chunks,
    stream_raw_rows,
    stream_raw_rows_from_files,
)


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def make_header() -> list[str]:
    return [
        "# Timestamp",
        "Type of mobile",
        "MMSI",
        "Latitude",
        "Longitude",
        "SOG",
        "Draught",
    ]


def make_row(
    timestamp: str,
    mmsi: str,
    latitude: str = "10.5",
    longitude: str = "20.5",
    mobile_type: str = "Class A",
    sog: str = "7.2",
    draught: str = "8.5",
) -> list[str]:
    return [
        timestamp,
        mobile_type,
        mmsi,
        latitude,
        longitude,
        sog,
        draught,
    ]


# -------------------------
# stream_raw_rows
# -------------------------

def test_stream_raw_rows_yields_required_fields_in_expected_order(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.csv"
    write_csv(
        file_path,
        make_header(),
        [
            make_row("01/09/2025 12:00:00", "223456789"),
            make_row("01/09/2025 12:05:00", "245014000"),
        ],
    )

    rows = list(stream_raw_rows(file_path))

    assert rows == [
        (
            "01/09/2025 12:00:00",
            "Class A",
            "223456789",
            "10.5",
            "20.5",
            "7.2",
            "8.5",
        ),
        (
            "01/09/2025 12:05:00",
            "Class A",
            "245014000",
            "10.5",
            "20.5",
            "7.2",
            "8.5",
        ),
    ]


def test_stream_raw_rows_returns_empty_for_file_with_only_header(tmp_path: Path) -> None:
    file_path = tmp_path / "empty.csv"
    write_csv(file_path, make_header(), [])

    rows = list(stream_raw_rows(file_path))

    assert rows == []


def test_stream_raw_rows_returns_empty_for_truly_empty_file(tmp_path: Path) -> None:
    file_path = tmp_path / "empty.csv"
    file_path.write_text("", encoding="utf-8")

    rows = list(stream_raw_rows(file_path))

    assert rows == []


def test_stream_raw_rows_raises_when_required_columns_are_missing(tmp_path: Path) -> None:
    file_path = tmp_path / "bad.csv"
    write_csv(
        file_path,
        ["# Timestamp", "MMSI", "Latitude", "Longitude"],
        [["01/09/2025 12:00:00", "223456789", "10.5", "20.5"]],
    )

    with pytest.raises(ValueError, match="Missing required CSV columns"):
        list(stream_raw_rows(file_path))


# -------------------------
# stream_raw_rows_from_files
# -------------------------

def test_stream_raw_rows_from_files_reads_multiple_files_in_order(tmp_path: Path) -> None:
    file_a = tmp_path / "a.csv"
    file_b = tmp_path / "b.csv"

    write_csv(
        file_a,
        make_header(),
        [
            make_row("01/09/2025 12:00:00", "223456789"),
        ],
    )
    write_csv(
        file_b,
        make_header(),
        [
            make_row("01/09/2025 12:05:00", "245014000"),
        ],
    )

    rows = list(stream_raw_rows_from_files([file_a, file_b]))

    assert rows == [
        (
            "01/09/2025 12:00:00",
            "Class A",
            "223456789",
            "10.5",
            "20.5",
            "7.2",
            "8.5",
        ),
        (
            "01/09/2025 12:05:00",
            "Class A",
            "245014000",
            "10.5",
            "20.5",
            "7.2",
            "8.5",
        ),
    ]


# -------------------------
# stream_csv_in_chunks / stream_csv_files_in_chunks
# -------------------------

def test_stream_csv_in_chunks_splits_single_file_into_fixed_size_chunks(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.csv"
    write_csv(
        file_path,
        make_header(),
        [
            make_row("01/09/2025 12:00:00", "223456789"),
            make_row("01/09/2025 12:05:00", "245014000"),
            make_row("01/09/2025 12:10:00", "538009722"),
        ],
    )

    chunks = list(stream_csv_in_chunks(file_path, chunk_size=2))

    assert len(chunks) == 2

    chunk_id_1, rows_1 = chunks[0]
    chunk_id_2, rows_2 = chunks[1]

    assert chunk_id_1 == 1
    assert chunk_id_2 == 2
    assert len(rows_1) == 2
    assert len(rows_2) == 1


def test_stream_csv_files_in_chunks_keeps_chunk_ids_across_file_boundaries(tmp_path: Path) -> None:
    file_a = tmp_path / "a.csv"
    file_b = tmp_path / "b.csv"

    write_csv(
        file_a,
        make_header(),
        [
            make_row("01/09/2025 12:00:00", "223456789"),
            make_row("01/09/2025 12:05:00", "245014000"),
        ],
    )
    write_csv(
        file_b,
        make_header(),
        [
            make_row("01/09/2025 12:10:00", "538009722"),
        ],
    )

    chunks = list(stream_csv_files_in_chunks([file_a, file_b], chunk_size=2))

    assert len(chunks) == 2
    assert chunks[0][0] == 1
    assert chunks[1][0] == 2
    assert len(chunks[0][1]) == 2
    assert len(chunks[1][1]) == 1


def test_stream_csv_files_in_chunks_returns_no_chunks_when_all_files_are_empty(tmp_path: Path) -> None:
    file_a = tmp_path / "a.csv"
    file_b = tmp_path / "b.csv"

    write_csv(file_a, make_header(), [])
    write_csv(file_b, make_header(), [])

    chunks = list(stream_csv_files_in_chunks([file_a, file_b], chunk_size=2))

    assert chunks == []


def test_stream_csv_files_in_chunks_raises_for_non_positive_chunk_size(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.csv"
    write_csv(
        file_path,
        make_header(),
        [make_row("01/09/2025 12:00:00", "223456789")],
    )

    with pytest.raises(ValueError, match="chunk_size must be greater than 0"):
        list(stream_csv_files_in_chunks([file_path], chunk_size=0))


def test_stream_csv_files_in_chunks_preserves_row_order_across_chunks(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.csv"
    write_csv(
        file_path,
        make_header(),
        [
            make_row("01/09/2025 12:00:00", "223456789"),
            make_row("01/09/2025 12:05:00", "245014000"),
            make_row("01/09/2025 12:10:00", "538009722"),
            make_row("01/09/2025 12:15:00", "257056010"),
        ],
    )

    chunks = list(stream_csv_files_in_chunks([file_path], chunk_size=2))

    flattened_rows = [row for _, chunk_rows in chunks for row in chunk_rows]

    assert [row[2] for row in flattened_rows] == [
        "223456789",
        "245014000",
        "538009722",
        "257056010",
    ]
