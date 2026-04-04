from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from src.anomaly_detection import detect_all_pair_anomalies
from src.anomaly_detection.rules import (
    _ActiveLoiteringPair,
    _LoiteringPoint,
    _bucketize_timestamp,
    _find_close_pairs_in_bucket,
    _finalize_active_loitering_pair,
    _record_to_loitering_point,
    _start_active_loitering_pair,
    _update_active_loitering_pair,
)
from config.detection_config import DEFAULT_DETECTION_CONFIG, DetectionConfig
from src.models import AISRecord, ChunkProcessingResult, VesselChunkSummary
from src.models.events import LoiteringTransferEvent
from src.models.processing import VesselGlobalSummary
from src.utils.ports import PortZone


@dataclass(slots=True)
class BoundaryState:
    """
    Track the latest known record for a vessel while merging chunk results.
    """

    last_record: AISRecord
    last_chunk_id: int
    last_sampled_record: AISRecord | None


@dataclass(slots=True)
class LoiteringState:
    """Incremental state for anomaly B detection during ordered merge."""

    pending_bucket_points: dict[datetime, list[_LoiteringPoint]] = field(
        default_factory=lambda: defaultdict(list)
    )
    active_pairs: dict[tuple[int, int], _ActiveLoiteringPair] = field(default_factory=dict)
    finished_events: list[LoiteringTransferEvent] = field(default_factory=list)
    bucket_seconds: int = 5 * 60
    max_distance_km: float = 0.5
    max_sog_knots: float = 1.0
    min_duration_hours: float = 2.0
    max_continuation_gap_seconds: int = 2 * 5 * 60
    minimum_port_radius_km: float = 0.0
    finalized: bool = False


@dataclass(slots=True)
class MergeState:
    """
    Incremental merge state maintained by the main process.
    """

    global_summaries: dict[int, VesselGlobalSummary] = field(default_factory=dict)
    boundary_states: dict[int, BoundaryState] = field(default_factory=dict)
    loitering_state: LoiteringState | None = None
    detection_config: DetectionConfig = field(default_factory=lambda: DEFAULT_DETECTION_CONFIG)


def create_merge_state(
    detection_config: DetectionConfig = DEFAULT_DETECTION_CONFIG,
    enable_loitering_detection: bool = False,
) -> MergeState:
    """Create an empty merge state for incremental chunk merging."""
    loitering_state = None
    if enable_loitering_detection:
        loitering_cfg = detection_config.loitering
        loitering_state = LoiteringState(
            bucket_seconds=loitering_cfg.bucket_seconds,
            max_distance_km=loitering_cfg.max_distance_km,
            max_sog_knots=loitering_cfg.max_sog_knots,
            min_duration_hours=loitering_cfg.min_duration_hours,
            max_continuation_gap_seconds=loitering_cfg.max_continuation_gap_seconds,
            minimum_port_radius_km=loitering_cfg.minimum_port_radius_km,
        )

    return MergeState(
        loitering_state=loitering_state,
        detection_config=detection_config,
    )


def merge_chunk_result_into_state(
    merge_state: MergeState,
    chunk_result: ChunkProcessingResult,
    port_zones: Sequence[PortZone] | None = None,
) -> None:
    """Merge a single chunk result into the incremental global state."""
    latest_sampled_timestamp: datetime | None = None

    for mmsi, chunk_summary in chunk_result.vessel_summaries.items():
        global_summary = merge_state.global_summaries.get(mmsi)
        if global_summary is None:
            global_summary = VesselGlobalSummary(
                mmsi=mmsi,
                record_count=0,
            )
            merge_state.global_summaries[mmsi] = global_summary

        _merge_local_chunk_summary(global_summary, chunk_summary)
        _merge_boundary_anomalies(
            global_summary=global_summary,
            boundary_state=merge_state.boundary_states.get(mmsi),
            current_chunk_id=chunk_result.chunk_id,
            current_summary=chunk_summary,
            port_zones=port_zones,
            detection_config=merge_state.detection_config,
        )

        if chunk_summary.sampled_records:
            last_sampled_timestamp = chunk_summary.sampled_records[-1].timestamp
            if latest_sampled_timestamp is None or last_sampled_timestamp > latest_sampled_timestamp:
                latest_sampled_timestamp = last_sampled_timestamp

            _merge_loitering_sampled_records(
                merge_state=merge_state,
                sampled_records=chunk_summary.sampled_records,
                port_zones=port_zones,
            )

        merge_state.boundary_states[mmsi] = BoundaryState(
            last_record=chunk_summary.last_record,
            last_chunk_id=chunk_result.chunk_id,
            last_sampled_record=(
                chunk_summary.sampled_records[-1]
                if chunk_summary.sampled_records
                else None
            ),
        )

    if merge_state.loitering_state is not None and latest_sampled_timestamp is not None:
        current_bucket_time = _bucketize_timestamp(
            latest_sampled_timestamp,
            merge_state.loitering_state.bucket_seconds,
        )
        _process_ready_loitering_buckets(
            merge_state=merge_state,
            watermark_bucket_time=current_bucket_time,
            flush_all=False,
        )


def merge_chunk_results(
    chunk_results: list[ChunkProcessingResult],
    port_zones: Sequence[PortZone] | None = None,
    detection_config: DetectionConfig = DEFAULT_DETECTION_CONFIG,
    enable_loitering_detection: bool = False,
) -> dict[int, VesselGlobalSummary]:
    """Merge per-chunk worker results into global per-vessel summaries."""
    merge_state = create_merge_state(
        detection_config=detection_config,
        enable_loitering_detection=enable_loitering_detection,
    )

    for chunk_result in sorted(chunk_results, key=lambda result: result.chunk_id):
        merge_chunk_result_into_state(
            merge_state=merge_state,
            chunk_result=chunk_result,
            port_zones=port_zones,
        )

    return merge_state.global_summaries


def _merge_local_chunk_summary(
    global_summary: VesselGlobalSummary,
    chunk_summary: VesselChunkSummary,
) -> None:
    """Merge local worker results for one vessel into the global summary."""
    global_summary.record_count += chunk_summary.record_count
    global_summary.max_gap_hours = max(
        global_summary.max_gap_hours,
        chunk_summary.max_gap_hours,
    )
    global_summary.total_impossible_jump_km += chunk_summary.total_impossible_jump_km
    global_summary.draft_change_count += chunk_summary.draft_change_count

    global_summary.going_dark_events.extend(chunk_summary.going_dark_events)
    global_summary.draft_change_events.extend(chunk_summary.draft_change_events)
    global_summary.teleportation_events.extend(chunk_summary.teleportation_events)
    global_summary.teleportation_d1_events.extend(chunk_summary.teleportation_d1_events)
    global_summary.teleportation_d2_events.extend(chunk_summary.teleportation_d2_events)


def _merge_boundary_anomalies(
    global_summary: VesselGlobalSummary,
    boundary_state: BoundaryState | None,
    current_chunk_id: int,
    current_summary: VesselChunkSummary,
    port_zones: Sequence[PortZone] | None = None,
    detection_config: DetectionConfig = DEFAULT_DETECTION_CONFIG,
) -> None:
    """Detect and merge anomalies spanning across chunk boundaries."""
    if boundary_state is None:
        return

    if boundary_state.last_chunk_id >= current_chunk_id:
        return

    if boundary_state.last_sampled_record is not None and current_summary.sampled_records:
        prev_sampled = boundary_state.last_sampled_record
        curr_sampled = current_summary.sampled_records[0]

        going_dark_event, draft_change_event, _ = detect_all_pair_anomalies(
            previous=prev_sampled,
            current=curr_sampled,
            config=detection_config,
            port_zones=port_zones,
        )

        if going_dark_event is not None:
            global_summary.going_dark_events.append(going_dark_event)
            global_summary.max_gap_hours = max(
                global_summary.max_gap_hours,
                going_dark_event.gap_hours,
            )

        if draft_change_event is not None:
            global_summary.draft_change_events.append(draft_change_event)
            global_summary.draft_change_count += 1

    previous = boundary_state.last_record
    current = current_summary.first_record

    _, _, teleportation_event = detect_all_pair_anomalies(
        previous=previous,
        current=current,
        config=detection_config,
        port_zones=port_zones,
    )

    if teleportation_event is not None:
        global_summary.teleportation_events.append(teleportation_event)
        if teleportation_event.subtype == "D1":
            global_summary.teleportation_d1_events.append(teleportation_event)
        else:
            global_summary.teleportation_d2_events.append(teleportation_event)
            if teleportation_event.counts_for_dfsi:
                global_summary.total_impossible_jump_km += teleportation_event.distance_km


def finalize_loitering_detection(merge_state: MergeState) -> list[LoiteringTransferEvent]:
    """Finalize incremental anomaly B detection and return all events."""
    loitering_state = merge_state.loitering_state
    if loitering_state is None:
        return []

    if loitering_state.finalized:
        return list(loitering_state.finished_events)

    _process_ready_loitering_buckets(
        merge_state=merge_state,
        watermark_bucket_time=None,
        flush_all=True,
    )

    for active in list(loitering_state.active_pairs.values()):
        event = _finalize_active_loitering_pair(
            active=active,
            min_duration_hours=loitering_state.min_duration_hours,
        )
        if event is not None:
            _store_loitering_event(merge_state, event)

    loitering_state.active_pairs.clear()
    loitering_state.finalized = True
    return list(loitering_state.finished_events)


def _merge_loitering_sampled_records(
    merge_state: MergeState,
    sampled_records: list[AISRecord],
    port_zones: Sequence[PortZone] | None,
) -> None:
    """Convert sampled vessel records into incremental anomaly B bucket state."""
    loitering_state = merge_state.loitering_state
    if loitering_state is None or port_zones is None:
        return

    for record in sampled_records:
        point = _record_to_loitering_point(
            record=record,
            port_zones=port_zones,
            max_sog_knots=loitering_state.max_sog_knots,
            minimum_port_radius_km=loitering_state.minimum_port_radius_km,
        )
        if point is None:
            continue

        bucket_time = _bucketize_timestamp(
            point.timestamp,
            loitering_state.bucket_seconds,
        )
        loitering_state.pending_bucket_points[bucket_time].append(point)


def _process_ready_loitering_buckets(
    merge_state: MergeState,
    watermark_bucket_time: datetime | None,
    flush_all: bool,
) -> None:
    """Process all anomaly B buckets that are ready for ordered reduction."""
    loitering_state = merge_state.loitering_state
    if loitering_state is None:
        return

    ready_bucket_times = [
        bucket_time
        for bucket_time in loitering_state.pending_bucket_points
        if flush_all or (watermark_bucket_time is not None and bucket_time < watermark_bucket_time)
    ]

    for bucket_time in sorted(ready_bucket_times):
        points = loitering_state.pending_bucket_points.pop(bucket_time)
        _process_loitering_bucket(merge_state, bucket_time, points)


def _process_loitering_bucket(
    merge_state: MergeState,
    bucket_time: datetime,
    points: list[_LoiteringPoint],
) -> None:
    """Update incremental anomaly B pair state using one closed time bucket."""
    loitering_state = merge_state.loitering_state
    if loitering_state is None:
        return

    pairs_in_bucket = _find_close_pairs_in_bucket(
        points=points,
        max_distance_km=loitering_state.max_distance_km,
    )

    current_keys = set(pairs_in_bucket)

    expired_keys: list[tuple[int, int]] = []
    for pair_key, active in loitering_state.active_pairs.items():
        gap_seconds = (bucket_time - active.end_timestamp).total_seconds()
        if pair_key not in current_keys and gap_seconds > loitering_state.max_continuation_gap_seconds:
            event = _finalize_active_loitering_pair(
                active=active,
                min_duration_hours=loitering_state.min_duration_hours,
            )
            if event is not None:
                _store_loitering_event(merge_state, event)
            expired_keys.append(pair_key)

    for pair_key in expired_keys:
        loitering_state.active_pairs.pop(pair_key, None)

    for pair_key, pair_obs in pairs_in_bucket.items():
        existing = loitering_state.active_pairs.get(pair_key)
        if existing is None:
            loitering_state.active_pairs[pair_key] = _start_active_loitering_pair(
                pair_obs=pair_obs,
                bucket_time=bucket_time,
            )
        else:
            _update_active_loitering_pair(
                active=existing,
                pair_obs=pair_obs,
                bucket_time=bucket_time,
            )


def _store_loitering_event(
    merge_state: MergeState,
    event: LoiteringTransferEvent,
) -> None:
    """Attach a finalized anomaly B event to global summaries and event list."""
    loitering_state = merge_state.loitering_state
    if loitering_state is None:
        return

    loitering_state.finished_events.append(event)

    summary_a = merge_state.global_summaries.get(event.mmsi_a)
    if summary_a is not None:
        summary_a.loitering_transfer_events.append(event)

    summary_b = merge_state.global_summaries.get(event.mmsi_b)
    if summary_b is not None and event.mmsi_b != event.mmsi_a:
        summary_b.loitering_transfer_events.append(event)
