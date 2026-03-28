from __future__ import annotations

from dataclasses import dataclass, field

from src.models.ais import AISRecord
from src.models.events import (
    DraftChangeEvent,
    GoingDarkEvent,
    TeleportationEvent,
    LoiteringTransferEvent
)


@dataclass(slots=True)
class VesselChunkSummary:
    """
    Partial anomaly-analysis result for one vessel inside a single chunk.

    A worker process builds this summary for each MMSI that appears in the
    chunk. The summary contains:
    - boundary records needed for cross-chunk comparisons;
    - local aggregate values used later for DFSI calculation;
    - locally detected anomaly events found fully inside the chunk.

    Attributes:
        mmsi: Vessel MMSI identifier.
        record_count: Number of valid AIS records for this MMSI in the chunk.
        first_record: First record for this MMSI in the chunk by timestamp.
        last_record: Last record for this MMSI in the chunk by timestamp.
        max_gap_hours: Maximum AIS gap detected inside this chunk for this MMSI.
        total_impossible_jump_km: Sum of D2 impossible-relocation distances.
        draft_change_count: Number of anomaly C events detected in the chunk.
        going_dark_events: Local anomaly A events detected inside the chunk.
        draft_change_events: Local anomaly C events detected inside the chunk.
        teleportation_events: All local anomaly D events detected inside the chunk.
        teleportation_d1_events: Local D1 near-simultaneous cloning events.
        teleportation_d2_events: Local D2 impossible-relocation events.
        sampled_records: Time discretization.
    """

    mmsi: int
    record_count: int
    first_record: AISRecord
    last_record: AISRecord
    max_gap_hours: float = 0.0
    total_impossible_jump_km: float = 0.0
    draft_change_count: int = 0
    going_dark_events: list[GoingDarkEvent] = field(default_factory=list)
    draft_change_events: list[DraftChangeEvent] = field(default_factory=list)
    teleportation_events: list[TeleportationEvent] = field(default_factory=list)
    teleportation_d1_events: list[TeleportationEvent] = field(default_factory=list)
    teleportation_d2_events: list[TeleportationEvent] = field(default_factory=list)
    sampled_records: list[AISRecord] = field(default_factory=list)


@dataclass(slots=True)
class ChunkProcessingResult:
    """
    Result returned by a worker after processing a single chunk.

    Attributes:
        chunk_id: Sequential chunk identifier.
        raw_row_count: Number of raw CSV rows received by the worker.
        valid_record_count: Number of rows successfully parsed into AIS records.
        elapsed_time: Time spent processing the chunk in seconds.
        vessel_summaries: Partial per-vessel results keyed by MMSI.
    """

    chunk_id: int
    raw_row_count: int
    valid_record_count: int
    elapsed_time: float
    vessel_summaries: dict[int, VesselChunkSummary]
    loitering_transfer_events: list[LoiteringTransferEvent] = field(default_factory=list)


@dataclass(slots=True)
class VesselGlobalSummary:
    """
    Fully merged anomaly summary for a vessel across all processed chunks.

    This object is constructed in the main process after combining the
    partial results produced by worker processes. It aggregates all
    locally detected anomalies and includes additional events detected
    across chunk boundaries.

    The summary contains the final metrics required for computing the
    DFSI (Dark Fleet Suspicion Index).

    Attributes:
        mmsi: Vessel MMSI identifier.
        record_count: Total number of valid AIS records processed
            for this vessel across all chunks.
        max_gap_hours: Maximum AIS blackout duration contributing
            to anomaly A ("Going Dark").
        total_impossible_jump_km: Sum of D2 impossible-relocation distances
            contributing to DFSI.
        draft_change_count: Total number of anomaly C events
            (significant draught changes during AIS blackout).
        going_dark_events: All detected anomaly A events for the vessel.
        draft_change_events: All detected anomaly C events for the vessel.
        teleportation_events: All detected anomaly D events for the vessel.
        teleportation_d1_events: All detected D1 events for the vessel.
        teleportation_d2_events: All detected D2 events for the vessel.
    """

    mmsi: int
    record_count: int
    max_gap_hours: float = 0.0
    total_impossible_jump_km: float = 0.0
    draft_change_count: int = 0
    going_dark_events: list[GoingDarkEvent] = field(default_factory=list)
    draft_change_events: list[DraftChangeEvent] = field(default_factory=list)
    teleportation_events: list[TeleportationEvent] = field(default_factory=list)
    teleportation_d1_events: list[TeleportationEvent] = field(default_factory=list)
    teleportation_d2_events: list[TeleportationEvent] = field(default_factory=list)
    loitering_transfer_events: list[LoiteringTransferEvent] = field(default_factory=list)
    sampled_records: list[AISRecord] = field(default_factory=list)
