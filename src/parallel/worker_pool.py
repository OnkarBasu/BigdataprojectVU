from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import DefaultDict, Sequence

from src.anomaly_detection import detect_all_pair_anomalies, preload_land_geometry
from src.config import DEFAULT_DETECTION_CONFIG, DetectionConfig
from src.models import AISRecord, ChunkProcessingResult, VesselChunkSummary
from src.streaming import Chunk
from src.streaming.parser import AISRowParser
from src.utils import load_port_zones
from src.utils.ports import PortZone


PORT_ZONES: Sequence[PortZone] | None = None
ROW_PARSER: AISRowParser | None = None
DETECTION_CONFIG: DetectionConfig = DEFAULT_DETECTION_CONFIG


def worker_init(
    detection_config: DetectionConfig = DEFAULT_DETECTION_CONFIG,
) -> None:
    """
    Initialize per-process worker state.

    Each worker loads reusable local resources once at startup:
    - port zones for geographic filtering;
    - the raw AIS row parser;
    - the active detection configuration;
    - the coarse land geometry used for D2 quality checks.

    This avoids reloading heavy shared resources for every chunk.
    """
    global PORT_ZONES
    global ROW_PARSER
    global DETECTION_CONFIG

    PORT_ZONES = load_port_zones()
    ROW_PARSER = AISRowParser()
    DETECTION_CONFIG = detection_config
    preload_land_geometry()

    import os
    print(f"Worker started: PID={os.getpid()}")


def process_chunk(task: Chunk) -> ChunkProcessingResult:
    """
    Process one raw AIS chunk inside a worker process.

    The worker:
    - parses and validates raw AIS rows;
    - groups valid records by MMSI;
    - sorts each vessel stream by timestamp;
    - builds a per-vessel chunk summary with:
      - local A/C anomalies on sampled records;
      - local D anomalies on full-resolution records;
      - sampled record streams needed later for cross-chunk merge
        and anomaly B detection.
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
    Parse raw AIS rows into valid ``AISRecord`` objects, skipping rows that
    fail validation or are not relevant to the project.
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
    Group parsed AIS records by vessel MMSI before per-vessel sorting and
    anomaly analysis.
    """
    grouped: DefaultDict[int, list[AISRecord]] = defaultdict(list)

    for record in records:
        grouped[record.mmsi].append(record)

    return grouped


def _bucket_start(timestamp: datetime, sampling_seconds: int) -> datetime:
    """Anchor a timestamp to a fixed global sampling bucket."""
    epoch_seconds = int(timestamp.timestamp())
    bucketed = epoch_seconds - (epoch_seconds % sampling_seconds)
    return datetime.fromtimestamp(bucketed, tz=timestamp.tzinfo)


def _sample_records_by_global_buckets(
    records: list[AISRecord],
    sampling_seconds: int,
) -> list[AISRecord]:
    """
    Keep one representative per globally anchored time bucket for one vessel.

    Bucket boundaries are fixed in absolute time rather than relative to the
    start of the chunk. This makes sampling stable across chunk boundaries,
    so the main process can safely deduplicate repeated bucket
    representatives during ordered merge.
    """
    if sampling_seconds <= 0 or len(records) <= 1:
        return records

    sampled: list[AISRecord] = []
    last_bucket_start: datetime | None = None

    for record in records:
        bucket_start = _bucket_start(record.timestamp, sampling_seconds)
        if bucket_start != last_bucket_start:
            sampled.append(record)
            last_bucket_start = bucket_start

    return sampled


def _build_vessel_chunk_summary(
    mmsi: int,
    records: list[AISRecord],
) -> VesselChunkSummary:
    """
    Build a partial anomaly summary for one vessel inside a single chunk.

    The summary includes:
    - first/last full-resolution records for cross-chunk boundary checks;
    - globally bucketed sampled records for anomaly A/C merge logic;
    - separately sampled records for anomaly B;
    - locally detected A and C anomalies on sampled records;
    - locally detected D anomalies on full-resolution consecutive records.
    """
    if not records:
        raise ValueError("records must not be empty")

    if PORT_ZONES is None:
        raise RuntimeError("PORT_ZONES is not initialized in worker process")

    first_record = records[0]
    last_record = records[-1]

    ac_sampled_records = _sample_records_by_global_buckets(
        records,
        DETECTION_CONFIG.sampling.ac_sampling_seconds,
    )
    loitering_sampled_records = _sample_records_by_global_buckets(
        records,
        DETECTION_CONFIG.sampling.loitering_sampling_seconds,
    )

    summary = VesselChunkSummary(
        mmsi=mmsi,
        record_count=len(records),
        first_record=first_record,
        last_record=last_record,
        ac_sampled_records=ac_sampled_records,
        loitering_sampled_records=loitering_sampled_records,
    )

    # A and C on globally anchored bucket samples inside the chunk
    for previous, current in zip(ac_sampled_records, ac_sampled_records[1:]):
        going_dark_event, draft_change_event, _ = detect_all_pair_anomalies(
            previous=previous,
            current=current,
            config=DETECTION_CONFIG,
            port_zones=PORT_ZONES,
        )

        if going_dark_event is not None:
            summary.going_dark_events.append(going_dark_event)
            summary.max_gap_hours = max(summary.max_gap_hours, going_dark_event.gap_hours)

        if draft_change_event is not None:
            summary.draft_change_events.append(draft_change_event)
            summary.draft_change_count += 1

    # D on full-resolution records
    for previous, current in zip(records, records[1:]):
        _, _, teleportation_event = detect_all_pair_anomalies(
            previous=previous,
            current=current,
            config=DETECTION_CONFIG,
            port_zones=PORT_ZONES,
        )

        if teleportation_event is not None:
            summary.teleportation_events.append(teleportation_event)
            if teleportation_event.subtype == "D1":
                summary.teleportation_d1_events.append(teleportation_event)
            else:
                summary.teleportation_d2_events.append(teleportation_event)
                if teleportation_event.counts_for_dfsi:
                    summary.total_impossible_jump_km += teleportation_event.distance_km

    return summary
