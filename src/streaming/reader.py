from __future__ import annotations

import csv
from pathlib import Path
from typing import Generator, Iterable

from .parser import build_raw_row_column_indices, extract_raw_row
from .types import Chunk, RawRow


def stream_raw_rows(
    file_path: str | Path,
    encoding: str = "utf-8",
) -> Generator[RawRow, None, None]:
    """
    Stream compact raw AIS rows from one CSV file.

    The main process performs only lightweight work here:
    - sequential file I/O;
    - header parsing;
    - extraction of the project-required AIS columns as raw strings.

    All CPU-heavy parsing, validation, and ``AISRecord`` construction is
    intentionally deferred to worker processes.

    Args:
        file_path: Path to the CSV file containing AIS data.
        encoding: File encoding used when opening the CSV file.

    Yields:
        Compact ``RawRow`` tuples containing only the required AIS fields.
    """
    path = Path(file_path)

    with path.open("r", encoding=encoding, errors="replace", newline="") as file:
        reader = csv.reader(file)

        header = next(reader, None)
        if header is None:
            return

        indices = build_raw_row_column_indices(header)

        for row in reader:
            yield extract_raw_row(row, indices)


def stream_raw_rows_from_files(
    file_paths: Iterable[str | Path],
    encoding: str = "utf-8",
) -> Generator[RawRow, None, None]:
    """
    Stream compact raw AIS rows sequentially from multiple CSV files.

    Files are processed in the order they are provided, allowing downstream
    processing to treat several files as one continuous AIS stream.

    Args:
        file_paths: Iterable of AIS CSV file paths.
        encoding: File encoding used when opening each file.

    Yields:
        RawRow tuples from all input files.
    """
    for file_path in file_paths:
        yield from stream_raw_rows(file_path=file_path, encoding=encoding)


def stream_csv_in_chunks(
    file_path: str | Path,
    chunk_size: int,
    encoding: str = "utf-8",
) -> Generator[Chunk, None, None]:
    """
    Stream compact raw AIS rows from a single CSV file in fixed-size chunks.

    Args:
        file_path: Path to the CSV file containing AIS data.
        chunk_size: Number of raw AIS rows per chunk.
        encoding: File encoding used when opening the CSV file.

    Yields:
        Chunk tuples containing ``(chunk_id, raw_rows)``.
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
    Stream compact raw AIS rows from multiple files in fixed-size chunks.

    Files are read sequentially, and chunk IDs continue across file
    boundaries so downstream processing can merge worker results in one
    global input order.

    Args:
        file_paths: Iterable of AIS CSV file paths.
        chunk_size: Number of raw AIS rows per chunk.
        encoding: File encoding used when opening each file.

    Yields:
        Chunk tuples of the form ``(chunk_id, raw_rows)``.

    Raises:
        ValueError: If ``chunk_size`` is less than or equal to zero.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    chunk: list[RawRow] = []
    chunk_id = 0

    for raw_row in stream_raw_rows_from_files(file_paths=file_paths, encoding=encoding):
        chunk.append(raw_row)

        if len(chunk) >= chunk_size:
            chunk_id += 1
            yield chunk_id, chunk
            chunk = []

    if chunk:
        chunk_id += 1
        yield chunk_id, chunk
