from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable, Iterator


REQUIRED_COLUMNS = (
    "# Timestamp",
    "Type of mobile",
    "MMSI",
    "Latitude",
    "Longitude",
    "SOG",
    "Draught",
)


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build CLI argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Collect parser statistics for the current branch/version of the "
            "project and save them for comparison across branches."
        )
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to the input AIS CSV file.",
    )
    parser.add_argument(
        "--encoding",
        type=str,
        default="utf-8",
        help="CSV file encoding.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit of data rows to inspect. 0 means full file.",
    )
    parser.add_argument(
        "--sample-invalid",
        type=int,
        default=20,
        help="How many invalid row examples to store.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to save stats as JSON.",
    )
    return parser


def iter_dict_rows(
    file_path: Path,
    encoding: str,
) -> Iterator[dict[str, str]]:
    """
    Yield rows from a CSV file using DictReader.

    Args:
        file_path: CSV path.
        encoding: File encoding.

    Yields:
        Row dictionaries.
    """
    with file_path.open("r", encoding=encoding, errors="replace", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            yield row


def iter_reader_rows(
    file_path: Path,
    encoding: str,
) -> tuple[list[str], Iterator[list[str]]]:
    """
    Return CSV header and iterator over raw rows from csv.reader.

    Args:
        file_path: CSV path.
        encoding: File encoding.

    Returns:
        Header and iterator of raw rows.
    """
    file = file_path.open("r", encoding=encoding, errors="replace", newline="")
    reader = csv.reader(file)
    header = next(reader, None)
    if header is None:
        file.close()
        return [], iter(())

    def generator() -> Iterator[list[str]]:
        try:
            for row in reader:
                yield row
        finally:
            file.close()

    return header, generator()


def row_signature_from_record(record) -> str:
    """
    Build a stable signature string from a parsed AISRecord.

    Args:
        record: Parsed AISRecord instance.

    Returns:
        Stable string representation for digesting.
    """
    draught_value = "" if record.draught is None else f"{record.draught:.6f}"
    sog_value = "" if record.sog is None else f"{record.sog:.6f}"

    return "|".join(
        [
            str(record.mmsi),
            record.timestamp.isoformat(sep=" "),
            f"{record.latitude:.6f}",
            f"{record.longitude:.6f}",
            sog_value,
            draught_value,
        ]
    )


def update_digest(digest: "hashlib._Hash", text: str) -> None:
    """
    Update a digest with one text line.

    Args:
        digest: Hash object.
        text: Text to append.
    """
    digest.update(text.encode("utf-8", errors="replace"))
    digest.update(b"\n")


def collect_stats_old_branch(
    file_path: Path,
    encoding: str,
    limit: int,
    sample_invalid: int,
) -> dict:
    """
    Collect parser stats using the old branch interface based on DictReader.

    Expected old interface:
        from src.streaming.parser import AISRowParser
        parser = AISRowParser()
        parser.parse_row(row_dict)

    Args:
        file_path: CSV path.
        encoding: File encoding.
        limit: Max number of rows to inspect, 0 for all.
        sample_invalid: Number of invalid examples to save.

    Returns:
        Stats dictionary.
    """
    from src.streaming.parser import AISRowParser

    parser = AISRowParser()

    raw_rows = 0
    valid_rows = 0
    invalid_rows = 0

    valid_digest = hashlib.sha256()
    valid_mmsi_digest = hashlib.sha256()

    invalid_examples: list[dict] = []

    for row in iter_dict_rows(file_path, encoding):
        raw_rows += 1
        if limit and raw_rows > limit:
            break

        record = parser.parse_row(row)

        if record is None:
            invalid_rows += 1
            if len(invalid_examples) < sample_invalid:
                invalid_examples.append(
                    {
                        "row_number": raw_rows,
                        "row": {key: row.get(key, "") for key in REQUIRED_COLUMNS},
                    }
                )
            continue

        valid_rows += 1
        signature = row_signature_from_record(record)
        update_digest(valid_digest, signature)
        update_digest(valid_mmsi_digest, f"{record.mmsi}|{record.timestamp.isoformat(sep=' ')}")

    return {
        "mode": "old_branch_dict_reader",
        "raw_rows": raw_rows,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "valid_signature_sha256": valid_digest.hexdigest(),
        "valid_mmsi_timestamp_sha256": valid_mmsi_digest.hexdigest(),
        "invalid_examples": invalid_examples,
    }


def collect_stats_new_branch(
    file_path: Path,
    encoding: str,
    limit: int,
    sample_invalid: int,
) -> dict:
    """
    Collect parser stats using the refactored branch interface based on raw rows.

    Expected new interface:
        from src.streaming.parser import (
            AISRowParser,
            build_raw_row_column_indices,
            extract_raw_row,
        )

    Args:
        file_path: CSV path.
        encoding: File encoding.
        limit: Max number of rows to inspect, 0 for all.
        sample_invalid: Number of invalid examples to save.

    Returns:
        Stats dictionary.
    """
    from src.streaming.parser import (
        AISRowParser,
        build_raw_row_column_indices,
        extract_raw_row,
    )

    parser = AISRowParser()

    header, rows = iter_reader_rows(file_path, encoding)
    indices = build_raw_row_column_indices(header)

    raw_rows = 0
    valid_rows = 0
    invalid_rows = 0

    valid_digest = hashlib.sha256()
    valid_mmsi_digest = hashlib.sha256()

    invalid_examples: list[dict] = []

    for row in rows:
        raw_rows += 1
        if limit and raw_rows > limit:
            break

        raw_row = extract_raw_row(row, indices)
        record = parser.parse_row(raw_row)

        if record is None:
            invalid_rows += 1
            if len(invalid_examples) < sample_invalid:
                invalid_examples.append(
                    {
                        "row_number": raw_rows,
                        "raw_row": list(raw_row),
                    }
                )
            continue

        valid_rows += 1
        signature = row_signature_from_record(record)
        update_digest(valid_digest, signature)
        update_digest(valid_mmsi_digest, f"{record.mmsi}|{record.timestamp.isoformat(sep=' ')}")

    return {
        "mode": "new_branch_raw_row",
        "raw_rows": raw_rows,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "valid_signature_sha256": valid_digest.hexdigest(),
        "valid_mmsi_timestamp_sha256": valid_mmsi_digest.hexdigest(),
        "invalid_examples": invalid_examples,
    }


def detect_branch_mode() -> str:
    """
    Detect whether the current branch uses the old or new parser interface.

    Returns:
        One of:
            - "old"
            - "new"

    Raises:
        RuntimeError: If neither interface can be detected.
    """
    import src.streaming.parser as parser_module

    has_build_indices = hasattr(parser_module, "build_raw_row_column_indices")
    has_extract_raw = hasattr(parser_module, "extract_raw_row")

    if has_build_indices and has_extract_raw:
        return "new"

    if hasattr(parser_module, "AISRowParser"):
        return "old"

    raise RuntimeError("Could not detect parser interface in src.streaming.parser")


def print_summary(stats: dict, input_file: Path) -> None:
    """
    Print human-readable summary.

    Args:
        stats: Collected stats.
        input_file: Processed CSV path.
    """
    print("=" * 80)
    print("PARSER DIAGNOSTIC SUMMARY")
    print("=" * 80)
    print(f"Input file:                    {input_file}")
    print(f"Detected mode:                 {stats['mode']}")
    print(f"Raw rows inspected:            {stats['raw_rows']}")
    print(f"Valid rows:                    {stats['valid_rows']}")
    print(f"Invalid rows:                  {stats['invalid_rows']}")
    print(f"Valid signature SHA256:        {stats['valid_signature_sha256']}")
    print(f"MMSI+timestamp SHA256:         {stats['valid_mmsi_timestamp_sha256']}")
    print("=" * 80)

    examples = stats.get("invalid_examples", [])
    if examples:
        print("Sample invalid rows:")
        for example in examples:
            print(json.dumps(example, ensure_ascii=False))
    else:
        print("No invalid sample rows stored.")


def main() -> None:
    """
    Run parser diagnostics for the current branch implementation.
    """
    parser = build_argument_parser()
    args = parser.parse_args()

    input_file: Path = args.input_file
    encoding: str = args.encoding
    limit: int = args.limit
    sample_invalid: int = args.sample_invalid
    output_json: Path | None = args.output_json

    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    mode = detect_branch_mode()

    if mode == "old":
        stats = collect_stats_old_branch(
            file_path=input_file,
            encoding=encoding,
            limit=limit,
            sample_invalid=sample_invalid,
        )
    elif mode == "new":
        stats = collect_stats_new_branch(
            file_path=input_file,
            encoding=encoding,
            limit=limit,
            sample_invalid=sample_invalid,
        )
    else:
        raise RuntimeError(f"Unsupported mode: {mode}")

    print_summary(stats, input_file)

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(stats, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nStats JSON written to: {output_json}")


if __name__ == "__main__":
    main()
