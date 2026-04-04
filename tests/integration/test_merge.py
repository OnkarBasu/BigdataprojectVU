from __future__ import annotations

from datetime import datetime, timedelta

from src.anomaly_detection.merge import (
    create_merge_state,
    finalize_loitering_detection,
    merge_chunk_result_into_state,
    merge_chunk_results,
)
from src.config import DetectionConfig, DraftChangeConfig, GoingDarkConfig, TeleportationConfig
from src.models import AISRecord, ChunkProcessingResult, VesselChunkSummary
from src.utils.ports import PortZone


def make_record(
    *,
    mmsi: int,
    timestamp: datetime,
    latitude: float,
    longitude: float,
    sog: float | None = 12.0,
    draught: float | None = 8.0,
) -> AISRecord:
    return AISRecord(
        timestamp=timestamp,
        mmsi=mmsi,
        latitude=latitude,
        longitude=longitude,
        sog=sog,
        draught=draught,
    )


def make_summary(
    *,
    mmsi: int,
    records: list[AISRecord],
    sampled_records: list[AISRecord] | None = None,
) -> VesselChunkSummary:
    ordered = sorted(records, key=lambda r: r.timestamp)
    return VesselChunkSummary(
        mmsi=mmsi,
        record_count=len(ordered),
        first_record=ordered[0],
        last_record=ordered[-1],
        sampled_records=ordered if sampled_records is None else sampled_records,
    )


def make_chunk_result(
    *,
    chunk_id: int,
    vessel_summaries: dict[int, VesselChunkSummary],
) -> ChunkProcessingResult:
    valid_count = sum(summary.record_count for summary in vessel_summaries.values())
    return ChunkProcessingResult(
        chunk_id=chunk_id,
        raw_row_count=valid_count,
        valid_record_count=valid_count,
        elapsed_time=0.0,
        vessel_summaries=vessel_summaries,
    )


def make_test_detection_config() -> DetectionConfig:
    return DetectionConfig(
        going_dark=GoingDarkConfig(
            min_gap_hours=4.0,
            min_distance_km=1.0,
        ),
        draft_change=DraftChangeConfig(
            min_gap_hours=2.0,
            min_relative_change=0.05,
            minimum_port_radius_km=0.0,
        ),
        teleportation=TeleportationConfig(
            max_speed_knots=60.0,
            d1_max_gap_hours=0.5,
            d2_max_gap_hours=24.0,
            min_gap_seconds=30.0,
            min_distance_km=1.0,
            d2_port_proximity_km=15.0,
            minimum_port_radius_km=0.0,
        ),
    )


def test_merge_chunk_results_accumulates_record_counts_for_same_vessel() -> None:
    mmsi = 245014000
    base_time = datetime(2025, 9, 1, 0, 0, 0)

    chunk_1 = make_chunk_result(
        chunk_id=1,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[
                    make_record(
                        mmsi=mmsi,
                        timestamp=base_time,
                        latitude=10.0,
                        longitude=20.0,
                    ),
                    make_record(
                        mmsi=mmsi,
                        timestamp=base_time + timedelta(minutes=5),
                        latitude=10.01,
                        longitude=20.0,
                    ),
                ],
            ),
        },
    )

    chunk_2 = make_chunk_result(
        chunk_id=2,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[
                    make_record(
                        mmsi=mmsi,
                        timestamp=base_time + timedelta(minutes=10),
                        latitude=10.02,
                        longitude=20.0,
                    ),
                ],
            ),
        },
    )

    merged = merge_chunk_results([chunk_1, chunk_2])

    assert mmsi in merged
    assert merged[mmsi].record_count == 3


def test_merge_chunk_results_merges_results_in_chunk_id_order() -> None:
    mmsi = 245014000
    base_time = datetime(2025, 9, 1, 0, 0, 0)

    chunk_2 = make_chunk_result(
        chunk_id=2,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[
                    make_record(
                        mmsi=mmsi,
                        timestamp=base_time + timedelta(minutes=10),
                        latitude=10.02,
                        longitude=20.0,
                    ),
                ],
            ),
        },
    )

    chunk_1 = make_chunk_result(
        chunk_id=1,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[
                    make_record(
                        mmsi=mmsi,
                        timestamp=base_time,
                        latitude=10.0,
                        longitude=20.0,
                    ),
                ],
            ),
        },
    )

    merged = merge_chunk_results([chunk_2, chunk_1])

    assert merged[mmsi].record_count == 2


def test_merge_detects_going_dark_across_chunk_boundary() -> None:
    config = make_test_detection_config()
    mmsi = 245014000
    base_time = datetime(2025, 9, 1, 0, 0, 0)

    chunk_1_record = make_record(
        mmsi=mmsi,
        timestamp=base_time,
        latitude=10.0,
        longitude=20.0,
    )
    chunk_2_record = make_record(
        mmsi=mmsi,
        timestamp=base_time + timedelta(hours=5),
        latitude=10.02,
        longitude=20.0,
    )

    chunk_1 = make_chunk_result(
        chunk_id=1,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[chunk_1_record],
                sampled_records=[chunk_1_record],
            ),
        },
    )
    chunk_2 = make_chunk_result(
        chunk_id=2,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[chunk_2_record],
                sampled_records=[chunk_2_record],
            ),
        },
    )

    merged = merge_chunk_results(
        [chunk_1, chunk_2],
        detection_config=config,
    )

    summary = merged[mmsi]
    assert len(summary.going_dark_events) == 1
    assert summary.max_gap_hours == 5.0


def test_merge_detects_draft_change_across_chunk_boundary() -> None:
    config = make_test_detection_config()
    mmsi = 245014000
    base_time = datetime(2025, 9, 1, 0, 0, 0)
    port_zones = (
        PortZone(
            name="Far Port",
            country="Test",
            latitude=0.0,
            longitude=0.0,
            radius_km=5.0,
        ),
    )

    chunk_1_record = make_record(
        mmsi=mmsi,
        timestamp=base_time,
        latitude=20.0,
        longitude=30.0,
        draught=10.0,
    )
    chunk_2_record = make_record(
        mmsi=mmsi,
        timestamp=base_time + timedelta(hours=3),
        latitude=20.02,
        longitude=30.0,
        draught=11.0,
    )

    chunk_1 = make_chunk_result(
        chunk_id=1,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[chunk_1_record],
                sampled_records=[chunk_1_record],
            ),
        },
    )
    chunk_2 = make_chunk_result(
        chunk_id=2,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[chunk_2_record],
                sampled_records=[chunk_2_record],
            ),
        },
    )

    merged = merge_chunk_results(
        [chunk_1, chunk_2],
        port_zones=port_zones,
        detection_config=config,
    )

    summary = merged[mmsi]
    assert len(summary.draft_change_events) == 1
    assert summary.draft_change_count == 1


def test_merge_detects_d1_teleportation_across_chunk_boundary() -> None:
    config = make_test_detection_config()
    mmsi = 245014000
    base_time = datetime(2025, 9, 1, 0, 0, 0)

    chunk_1_record = make_record(
        mmsi=mmsi,
        timestamp=base_time,
        latitude=10.0,
        longitude=20.0,
    )
    chunk_2_record = make_record(
        mmsi=mmsi,
        timestamp=base_time + timedelta(minutes=20),
        latitude=12.0,
        longitude=20.0,
    )

    chunk_1 = make_chunk_result(
        chunk_id=1,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[chunk_1_record],
                sampled_records=[chunk_1_record],
            ),
        },
    )
    chunk_2 = make_chunk_result(
        chunk_id=2,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[chunk_2_record],
                sampled_records=[chunk_2_record],
            ),
        },
    )

    merged = merge_chunk_results(
        [chunk_1, chunk_2],
        detection_config=config,
    )

    summary = merged[mmsi]
    assert len(summary.teleportation_events) == 1
    assert len(summary.teleportation_d1_events) == 1
    assert len(summary.teleportation_d2_events) == 0
    assert summary.teleportation_events[0].subtype == "D1"


def test_merge_detects_d2_teleportation_and_updates_total_impossible_jump_km(
    monkeypatch,
) -> None:
    def fake_classify_d2_quality(
        _previous,
        _current,
        _port_zones,
        _teleportation_config,
    ):
        return False, False, "ok", True

    monkeypatch.setattr(
        "src.anomaly_detection.rules._classify_d2_quality",
        fake_classify_d2_quality,
    )

    config = make_test_detection_config()
    mmsi = 245014000
    base_time = datetime(2025, 9, 1, 0, 0, 0)

    chunk_1_record = make_record(
        mmsi=mmsi,
        timestamp=base_time,
        latitude=10.0,
        longitude=20.0,
    )
    chunk_2_record = make_record(
        mmsi=mmsi,
        timestamp=base_time + timedelta(hours=2),
        latitude=12.0,
        longitude=20.0,
    )

    chunk_1 = make_chunk_result(
        chunk_id=1,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[chunk_1_record],
                sampled_records=[chunk_1_record],
            ),
        },
    )
    chunk_2 = make_chunk_result(
        chunk_id=2,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[chunk_2_record],
                sampled_records=[chunk_2_record],
            ),
        },
    )

    merged = merge_chunk_results(
        [chunk_1, chunk_2],
        detection_config=config,
    )

    summary = merged[mmsi]
    assert len(summary.teleportation_events) == 1
    assert len(summary.teleportation_d1_events) == 0
    assert len(summary.teleportation_d2_events) == 1
    assert summary.teleportation_events[0].subtype == "D2"
    assert summary.teleportation_events[0].counts_for_dfsi is True
    assert summary.total_impossible_jump_km > 0.0


def test_merge_does_not_duplicate_boundary_anomaly_when_chunk_ids_are_not_increasing() -> None:
    config = make_test_detection_config()
    mmsi = 245014000
    base_time = datetime(2025, 9, 1, 0, 0, 0)

    record_a = make_record(
        mmsi=mmsi,
        timestamp=base_time,
        latitude=10.0,
        longitude=20.0,
    )
    record_b = make_record(
        mmsi=mmsi,
        timestamp=base_time + timedelta(hours=5),
        latitude=10.02,
        longitude=20.0,
    )

    chunk = make_chunk_result(
        chunk_id=1,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[record_a],
                sampled_records=[record_a],
            ),
        },
    )

    later_chunk_same_id = make_chunk_result(
        chunk_id=1,
        vessel_summaries={
            mmsi: make_summary(
                mmsi=mmsi,
                records=[record_b],
                sampled_records=[record_b],
            ),
        },
    )

    merge_state = create_merge_state(detection_config=config)
    merge_chunk_result_into_state(merge_state, chunk)
    merge_chunk_result_into_state(merge_state, later_chunk_same_id)

    summary = merge_state.global_summaries[mmsi]
    assert len(summary.going_dark_events) == 0


def test_finalize_loitering_detection_returns_empty_when_loitering_disabled() -> None:
    merge_state = create_merge_state(enable_loitering_detection=False)

    events = finalize_loitering_detection(merge_state)

    assert events == []
