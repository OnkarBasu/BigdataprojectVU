from __future__ import annotations

import csv
from pathlib import Path
from typing import Generator

from src.models import AISRecord
from src.streaming.parser import AISRowParser


Chunk = tuple[int, list[AISRecord]]


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


def stream_csv_in_chunks(
    file_path: str | Path,
    chunk_size: int,
    encoding: str = "utf-8",
) -> Generator[Chunk, None, None]:
    """
    Stream AIS records from a CSV file in fixed-size chunks.

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
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    chunk: list[AISRecord] = []
    chunk_id = 0

    for record in stream_records(file_path=file_path, encoding=encoding):
        chunk.append(record)

        if len(chunk) >= chunk_size:
            chunk_id += 1
            yield chunk_id, chunk
            chunk = []

    if chunk:
        chunk_id += 1
        yield chunk_id, chunk
