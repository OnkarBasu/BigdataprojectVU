from __future__ import annotations

import time
from collections import defaultdict
from typing import DefaultDict

from src.anomaly_detection import detect_all_pair_anomalies

from src.models import AISRecord, ChunkProcessingResult, VesselChunkSummary
from src.streaming import Chunk


def process_chunk(task: Chunk) -> ChunkProcessingResult:
    """
    Process a single AIS chunk and compute per-vessel partial anomaly summaries.

    The worker groups records by MMSI, sorts each vessel's records by timestamp,
    analyzes consecutive record pairs for anomalies A, C, and D, and builds
    a partial summary for each vessel. The returned result is designed to be
    merged later in the main process, including cross-chunk boundary checks.

    Args:
        task: A chunk represented as ``(chunk_id, records)``.

    Returns:
        ChunkProcessingResult containing per-vessel summaries for the chunk.
    """
    chunk_id, records = task
    start_time = time.perf_counter()

    grouped_records = _group_records_by_mmsi(records)
    vessel_summaries: dict[int, VesselChunkSummary] = {}

    for mmsi, vessel_records in grouped_records.items():
        sorted_records = sorted(vessel_records, key=lambda record: record.timestamp)
        vessel_summary = _build_vessel_chunk_summary(mmsi, sorted_records)
        vessel_summaries[mmsi] = vessel_summary

    elapsed_time = time.perf_counter() - start_time
    return ChunkProcessingResult(
        chunk_id=chunk_id,
        row_count=len(records),
        elapsed_time=elapsed_time,
        vessel_summaries=vessel_summaries,
    )


def _group_records_by_mmsi(records: list[AISRecord]) -> dict[int, list[AISRecord]]:
    """
    Group AIS records by MMSI.

    Args:
        records: List of AIS records from a single chunk.

    Returns:
        Dictionary mapping MMSI to the list of records belonging to that vessel.
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
    Build a partial per-vessel anomaly summary for a single chunk.

    Args:
        mmsi: Vessel MMSI identifier.
        records: Time-sorted records for this vessel inside one chunk.

    Returns:
        VesselChunkSummary with local aggregates, boundary records,
        and anomaly events detected fully inside the chunk.

    Raises:
        ValueError: If ``records`` is empty.
    """
    if not records:
        raise ValueError("records must not be empty")

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
