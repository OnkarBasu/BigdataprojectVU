from __future__ import annotations

import time
from collections import defaultdict
from typing import DefaultDict, Sequence

from src.anomaly_detection import detect_all_pair_anomalies
from src.models import AISRecord, ChunkProcessingResult, VesselChunkSummary
from src.streaming import Chunk
from src.streaming.parser import AISRowParser
from src.utils import load_port_zones
from src.utils.ports import PortZone


PORT_ZONES: Sequence[PortZone] | None = None
ROW_PARSER: AISRowParser | None = None


def worker_init() -> None:
    """
    Initialize per-process worker state.

    This avoids doing repeated setup work for every processed chunk.
    """
    global PORT_ZONES
    global ROW_PARSER

    PORT_ZONES = load_port_zones()
    ROW_PARSER = AISRowParser()

    import os
    print(f"Worker started: PID={os.getpid()}")


def process_chunk(task: Chunk) -> ChunkProcessingResult:
    """
    Process a single raw AIS chunk and compute per-vessel partial summaries.

    The worker:
    - parses raw rows into ``AISRecord`` objects;
    - drops invalid rows;
    - groups valid records by MMSI;
    - sorts records per vessel by timestamp;
    - detects local pairwise anomalies inside the chunk.

    Args:
        task: Chunk represented as ``(chunk_id, raw_rows)``.

    Returns:
        ChunkProcessingResult containing local per-vessel summaries.
    """
    chunk_id, raw_rows = task
    start_time = time.perf_counter()

    records = _parse_raw_rows(raw_rows)
    grouped_records = _group_records_by_mmsi(records)

    vessel_summaries: dict[int, VesselChunkSummary] = {}
    for mmsi, vessel_records in grouped_records.items():
        sorted_records = sorted(vessel_records, key=lambda record: record.timestamp)
        vessel_summaries[mmsi] = _build_vessel_chunk_summary(mmsi, sorted_records)

    elapsed_time = time.perf_counter() - start_time

    return ChunkProcessingResult(
        chunk_id=chunk_id,
        raw_row_count=len(raw_rows),
        valid_record_count=len(records),
        elapsed_time=elapsed_time,
        vessel_summaries=vessel_summaries,
    )


def _parse_raw_rows(raw_rows: list[tuple[str, str, str, str, str, str, str]]) -> list[AISRecord]:
    """
    Parse all raw rows in a chunk into valid AIS records.

    Args:
        raw_rows: Compact raw AIS rows.

    Returns:
        List of successfully parsed AIS records.
    """
    if ROW_PARSER is None:
        raise RuntimeError("ROW_PARSER is not initialized in worker process")

    records: list[AISRecord] = []

    for raw_row in raw_rows:
        record = ROW_PARSER.parse_row(raw_row)
        if record is not None:
            records.append(record)

    return records


def _group_records_by_mmsi(records: list[AISRecord]) -> dict[int, list[AISRecord]]:
    """
    Group AIS records by MMSI.

    Args:
        records: Valid AIS records from a single chunk.

    Returns:
        Dictionary mapping MMSI to records for that vessel.
    """
    grouped: DefaultDict[int, list[AISRecord]] = defaultdict(list)

    for record in records:
        grouped[record.mmsi].append(record)

    return grouped


def _build_vessel_chunk_summary(
    mmsi: int,
    records: list[AISRecord],
) -> VesselChunkSummary:
    """
    Build a partial per-vessel anomaly summary for one chunk.

    Args:
        mmsi: Vessel MMSI identifier.
        records: Time-sorted valid AIS records for this vessel inside one chunk.

    Returns:
        VesselChunkSummary with local aggregates, boundary records,
        and anomaly events detected fully inside the chunk.

    Raises:
        ValueError: If ``records`` is empty.
    """
    if not records:
        raise ValueError("records must not be empty")

    if PORT_ZONES is None:
        raise RuntimeError("PORT_ZONES is not initialized in worker process")

    first_record = records[0]
    last_record = records[-1]

    summary = VesselChunkSummary(
        mmsi=mmsi,
        record_count=len(records),
        first_record=first_record,
        last_record=last_record,
    )

    for previous, current in zip(records, records[1:]):
        going_dark_event, draft_change_event, teleportation_event = detect_all_pair_anomalies(
            previous=previous,
            current=current,
            port_zones=PORT_ZONES,
        )

        if going_dark_event is not None:
            summary.going_dark_events.append(going_dark_event)
            summary.max_gap_hours = max(summary.max_gap_hours, going_dark_event.gap_hours)

        if draft_change_event is not None:
            summary.draft_change_events.append(draft_change_event)
            summary.draft_change_count += 1

        if teleportation_event is not None:
            summary.teleportation_events.append(teleportation_event)
            summary.total_impossible_jump_km += teleportation_event.distance_km

    return summary
