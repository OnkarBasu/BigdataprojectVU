from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from src.anomaly_detection import detect_all_pair_anomalies
from src.models import AISRecord, ChunkProcessingResult, VesselChunkSummary
from src.models.processing import VesselGlobalSummary
from src.utils.ports import PortZone


@dataclass(slots=True)
class BoundaryState:
    last_record: AISRecord
    last_chunk_id: int


@dataclass(slots=True)
class MergeState:
    global_summaries: dict[int, VesselGlobalSummary] = field(default_factory=dict)
    boundary_states: dict[int, BoundaryState] = field(default_factory=dict)


def create_merge_state() -> MergeState:
    return MergeState()


def merge_chunk_result_into_state(
    merge_state: MergeState,
    chunk_result: ChunkProcessingResult,
    port_zones: Sequence[PortZone] | None = None,
    minimum_port_radius_km: float = 0.0,
) -> None:
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
        )


def merge_chunk_results(
    chunk_results: list[ChunkProcessingResult],
    port_zones: Sequence[PortZone] | None = None,
    minimum_port_radius_km: float = 0.0,
) -> dict[int, VesselGlobalSummary]:
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


def _merge_boundary_anomalies(
    global_summary: VesselGlobalSummary,
    boundary_state: BoundaryState | None,
    current_chunk_id: int,
    current_summary: VesselChunkSummary,
    port_zones: Sequence[PortZone] | None = None,
    minimum_port_radius_km: float = 0.0,
) -> None:
    if boundary_state is None:
        return

    if boundary_state.last_chunk_id == current_chunk_id:
        return

    previous_record = boundary_state.last_record
    current_record = current_summary.first_record

    going_dark_event, draft_change_event, teleportation_event = detect_all_pair_anomalies(
        previous=previous_record,
        current=current_record,
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

    if teleportation_event is not None:
        global_summary.teleportation_events.append(teleportation_event)
        global_summary.total_impossible_jump_km += teleportation_event.distance_km
