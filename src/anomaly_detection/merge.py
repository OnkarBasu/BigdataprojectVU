from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from src.anomaly_detection import detect_all_pair_anomalies
from src.models import AISRecord, ChunkProcessingResult, VesselChunkSummary
from src.models.processing import VesselGlobalSummary
from src.utils.ports import PortZone


@dataclass(slots=True)
class BoundaryState:
    """
    Track the latest known record for a vessel while merging chunk results.

    This state is used to detect anomalies that occur across chunk boundaries,
    where the last record of a vessel in one chunk must be compared with the
    first record of the same vessel in a later chunk.
    """

    last_record: AISRecord
    last_chunk_id: int
    last_sampled_record: AISRecord | None


@dataclass(slots=True)
class MergeState:
    """
    Incremental merge state maintained by the main process.

    Attributes:
        global_summaries: Fully merged per-vessel summaries.
        boundary_states: Latest known boundary record for each vessel.
    """

    global_summaries: dict[int, VesselGlobalSummary] = field(default_factory=dict)
    boundary_states: dict[int, BoundaryState] = field(default_factory=dict)


def create_merge_state() -> MergeState:
    """Create an empty merge state for incremental chunk merging."""
    return MergeState()


def merge_chunk_result_into_state(
    merge_state: MergeState,
    chunk_result: ChunkProcessingResult,
    port_zones: Sequence[PortZone] | None = None,
    minimum_port_radius_km: float = 0.0,
) -> None:
    """Merge a single chunk result into the incremental global state."""
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
            minimum_port_radius_km=minimum_port_radius_km,
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


def merge_chunk_results(
    chunk_results: list[ChunkProcessingResult],
    port_zones: Sequence[PortZone] | None = None,
    minimum_port_radius_km: float = 0.0,
) -> dict[int, VesselGlobalSummary]:
    """Merge per-chunk worker results into global per-vessel summaries."""
    merge_state = create_merge_state()

    for chunk_result in sorted(chunk_results, key=lambda result: result.chunk_id):
        merge_chunk_result_into_state(
            merge_state=merge_state,
            chunk_result=chunk_result,
            port_zones=port_zones,
            minimum_port_radius_km=minimum_port_radius_km,
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
    global_summary.sampled_records.extend(chunk_summary.sampled_records)


def _merge_boundary_anomalies(
    global_summary: VesselGlobalSummary,
    boundary_state: BoundaryState | None,
    current_chunk_id: int,
    current_summary: VesselChunkSummary,
    port_zones: Sequence[PortZone] | None = None,
    minimum_port_radius_km: float = 0.0,
) -> None:
    """Detect and merge anomalies spanning across chunk boundaries."""
    if boundary_state is None:
        return

    if boundary_state.last_chunk_id >= current_chunk_id:
        return

    if (
            boundary_state.last_sampled_record is not None
            and current_summary.sampled_records
    ):
        prev_sampled = boundary_state.last_sampled_record
        curr_sampled = current_summary.sampled_records[0]

        going_dark_event, draft_change_event, _ = detect_all_pair_anomalies(
            previous=prev_sampled,
            current=curr_sampled,
            port_zones=port_zones,
            minimum_port_radius_km=minimum_port_radius_km,
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
        port_zones=port_zones,
        minimum_port_radius_km=minimum_port_radius_km,
    )

    if teleportation_event is not None:
        global_summary.teleportation_events.append(teleportation_event)
        if teleportation_event.subtype == "D1":
            global_summary.teleportation_d1_events.append(teleportation_event)
        else:
            global_summary.teleportation_d2_events.append(teleportation_event)
            global_summary.total_impossible_jump_km += teleportation_event.distance_km
