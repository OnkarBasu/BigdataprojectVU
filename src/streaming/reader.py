from __future__ import annotations

import csv
from pathlib import Path
from typing import Generator, Iterable

from src.models import AISRecord
from .parser import AISRowParser
from .types import Chunk


def stream_records(
    file_path: str | Path,
    encoding: str = "utf-8",
) -> Generator[AISRecord, None, None]:
    """
    Stream valid AIS records from a CSV file.

    This function reads the CSV file row by row using ``csv.DictReader``,
    parses each row into an ``AISRecord`` using ``AISRowParser``, and yields
    only valid records.

    Invalid or filtered rows (e.g., base stations, malformed data, or rows
    failing validation) are skipped.

    Args:
        file_path: Path to the CSV file containing AIS data.
        encoding: File encoding used when opening the CSV file.

    Yields:
        AISRecord: Parsed and validated AIS records.
    """
    path = Path(file_path)

    with path.open("r", encoding=encoding, errors="replace", newline="") as file:
        reader = csv.DictReader(file)
        parser = AISRowParser(reader.fieldnames)

        for row in reader:
            record = parser.parse_row(row)
            if record is not None:
                yield record


def stream_records_from_files(
    file_paths: Iterable[str | Path],
    encoding: str = "utf-8",
) -> Generator[AISRecord, None, None]:
    """
    Stream valid AIS records sequentially from multiple CSV files.

    Files are processed in the order they are provided. This makes it possible
    to treat several daily AIS files as one continuous input stream for
    downstream chunking and anomaly detection.

    Args:
        file_paths: Iterable of paths to AIS CSV files.
        encoding: File encoding used when opening each file.

    Yields:
        AISRecord: Parsed and validated AIS records from all input files.
    """
    for file_path in file_paths:
        yield from stream_records(file_path=file_path, encoding=encoding)


def stream_csv_in_chunks(
    file_path: str | Path,
    chunk_size: int,
    encoding: str = "utf-8",
) -> Generator[Chunk, None, None]:
    """
    Stream AIS records from a single CSV file in fixed-size chunks.

    This function uses ``stream_records`` to read AIS records and groups them
    into chunks of a specified size. Each chunk is assigned a sequential
    identifier starting from 1.

    Chunks are useful for parallel processing pipelines where each worker
    processes a batch of AIS records.

    Args:
        file_path: Path to the CSV file containing AIS data.
        chunk_size: Number of AIS records per chunk.
        encoding: File encoding used when opening the CSV file.

    Yields:
        Chunk: A tuple containing:
            - chunk_id (int): Sequential chunk identifier.
            - records (list[AISRecord]): List of AIS records in the chunk.

    Raises:
        ValueError: If ``chunk_size`` is less than or equal to zero.
    """
    yield from stream_csv_files_in_chunks(
        file_paths=[file_path],
        chunk_size=chunk_size,
        encoding=encoding,
    )


def stream_csv_files_in_chunks(
    file_paths: Iterable[str | Path],
    chunk_size: int,
    encoding: str = "utf-8",
) -> Generator[Chunk, None, None]:
    """
    Stream AIS records from multiple CSV files in fixed-size chunks.

    Files are processed sequentially in the order they are provided, and
    chunk IDs continue across file boundaries. This allows the downstream
    pipeline to treat multiple daily AIS files as one continuous stream.

    Args:
        file_paths: Iterable of paths to AIS CSV files.
        chunk_size: Number of AIS records per chunk.
        encoding: File encoding used when opening each file.

    Yields:
        Chunk: A tuple containing:
            - chunk_id (int): Sequential chunk identifier.
            - records (list[AISRecord]): List of AIS records in the chunk.

    Raises:
        ValueError: If ``chunk_size`` is less than or equal to zero.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    chunk: list[AISRecord] = []
    chunk_id = 0

    for record in stream_records_from_files(file_paths=file_paths, encoding=encoding):
        chunk.append(record)

        if len(chunk) >= chunk_size:
            chunk_id += 1
            yield chunk_id, chunk
            chunk = []

    if chunk:
        chunk_id += 1
        yield chunk_id, chunk
