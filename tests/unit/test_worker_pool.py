from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.models import AISRecord
from src.parallel import worker_pool
from src.streaming.parser import AISRowParser
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


def make_port(
    *,
    name: str = "Test Port",
    country: str = "Test Country",
    latitude: float = 0.0,
    longitude: float = 0.0,
    radius_km: float = 5.0,
) -> PortZone:
    return PortZone(
        name=name,
        country=country,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
    )


@pytest.fixture(autouse=True)
def reset_worker_globals():
    old_port_zones = worker_pool.PORT_ZONES
    old_row_parser = worker_pool.ROW_PARSER
    old_detection_config = worker_pool.DETECTION_CONFIG

    worker_pool.PORT_ZONES = None
    worker_pool.ROW_PARSER = None

    try:
        yield
    finally:
        worker_pool.PORT_ZONES = old_port_zones
        worker_pool.ROW_PARSER = old_row_parser
        worker_pool.DETECTION_CONFIG = old_detection_config


def test_parse_raw_rows_raises_when_row_parser_is_not_initialized() -> None:
    with pytest.raises(RuntimeError, match="ROW_PARSER is not initialized"):
        worker_pool._parse_raw_rows(
            [
                (
                    "01/09/2025 12:00:00",
                    "Class A",
                    "223456789",
                    "10.5",
                    "20.5",
                    "7.2",
                    "8.5",
                )
            ]
        )


def test_parse_raw_rows_returns_only_valid_records() -> None:
    worker_pool.ROW_PARSER = AISRowParser()

    raw_rows = [
        (
            "01/09/2025 12:00:00",
            "Class A",
            "223456789",
            "10.5",
            "20.5",
            "7.2",
            "8.5",
        ),
        (
            "01/09/2025 12:05:00",
            "Class B",   # invalid mobile type
            "245014000",
            "10.6",
            "20.6",
            "7.0",
            "8.4",
        ),
    ]

    records = worker_pool._parse_raw_rows(raw_rows)

    assert len(records) == 1
    assert records[0].mmsi == 223456789


def test_group_records_by_mmsi_groups_records_correctly() -> None:
    t0 = datetime(2025, 9, 1, 0, 0, 0)

    records = [
        make_record(mmsi=223456789, timestamp=t0, latitude=10.0, longitude=20.0),
        make_record(mmsi=245014000, timestamp=t0, latitude=11.0, longitude=21.0),
        make_record(mmsi=223456789, timestamp=t0 + timedelta(minutes=5), latitude=10.1, longitude=20.1),
    ]

    grouped = worker_pool._group_records_by_mmsi(records)

    assert set(grouped.keys()) == {223456789, 245014000}
    assert len(grouped[223456789]) == 2
    assert len(grouped[245014000]) == 1


def test_downsample_records_returns_original_when_sampling_is_non_positive() -> None:
    t0 = datetime(2025, 9, 1, 0, 0, 0)
    records = [
        make_record(mmsi=223456789, timestamp=t0, latitude=10.0, longitude=20.0),
        make_record(mmsi=223456789, timestamp=t0 + timedelta(minutes=1), latitude=10.01, longitude=20.0),
    ]

    sampled = worker_pool._downsample_records(records, sampling_seconds=0)

    assert sampled == records


def test_downsample_records_keeps_first_interval_points_and_last_point() -> None:
    t0 = datetime(2025, 9, 1, 0, 0, 0)
    records = [
        make_record(mmsi=223456789, timestamp=t0, latitude=10.0, longitude=20.0),
        make_record(mmsi=223456789, timestamp=t0 + timedelta(minutes=1), latitude=10.01, longitude=20.0),
        make_record(mmsi=223456789, timestamp=t0 + timedelta(minutes=5), latitude=10.02, longitude=20.0),
        make_record(mmsi=223456789, timestamp=t0 + timedelta(minutes=9), latitude=10.03, longitude=20.0),
    ]

    sampled = worker_pool._downsample_records(records, sampling_seconds=300)

    assert sampled[0] == records[0]
    assert sampled[1] == records[2]
    assert sampled[-1] == records[-1]
    assert len(sampled) == 3


def test_build_vessel_chunk_summary_raises_when_records_are_empty() -> None:
    worker_pool.PORT_ZONES = (make_port(),)

    with pytest.raises(ValueError, match="records must not be empty"):
        worker_pool._build_vessel_chunk_summary(223456789, [])


def test_build_vessel_chunk_summary_raises_when_port_zones_are_not_initialized() -> None:
    t0 = datetime(2025, 9, 1, 0, 0, 0)
    records = [
        make_record(mmsi=223456789, timestamp=t0, latitude=10.0, longitude=20.0),
    ]

    with pytest.raises(RuntimeError, match="PORT_ZONES is not initialized"):
        worker_pool._build_vessel_chunk_summary(223456789, records)


def test_build_vessel_chunk_summary_sets_basic_fields() -> None:
    worker_pool.PORT_ZONES = (make_port(),)

    t0 = datetime(2025, 9, 1, 0, 0, 0)
    records = [
        make_record(mmsi=223456789, timestamp=t0, latitude=10.0, longitude=20.0),
        make_record(mmsi=223456789, timestamp=t0 + timedelta(minutes=5), latitude=10.1, longitude=20.1),
    ]

    summary = worker_pool._build_vessel_chunk_summary(223456789, records)

    assert summary.mmsi == 223456789
    assert summary.record_count == 2
    assert summary.first_record == records[0]
    assert summary.last_record == records[1]
    assert summary.sampled_records[0] == records[0]
    assert summary.sampled_records[-1] == records[-1]


def test_build_vessel_chunk_summary_detects_going_dark_and_draft_change_on_sampled_records() -> None:
    worker_pool.PORT_ZONES = (
        make_port(latitude=0.0, longitude=0.0, radius_km=5.0),
    )

    t0 = datetime(2025, 9, 1, 0, 0, 0)
    records = [
        make_record(
            mmsi=223456789,
            timestamp=t0,
            latitude=20.0,
            longitude=30.0,
            draught=10.0,
        ),
        make_record(
            mmsi=223456789,
            timestamp=t0 + timedelta(hours=5),
            latitude=20.02,
            longitude=30.0,
            draught=11.0,
        ),
    ]

    summary = worker_pool._build_vessel_chunk_summary(223456789, records)

    assert len(summary.going_dark_events) == 1
    assert len(summary.draft_change_events) == 1
    assert summary.draft_change_count == 1
    assert summary.max_gap_hours == 5.0


def test_build_vessel_chunk_summary_detects_d1_on_full_resolution_records() -> None:
    worker_pool.PORT_ZONES = (make_port(),)

    t0 = datetime(2025, 9, 1, 0, 0, 0)
    records = [
        make_record(
            mmsi=223456789,
            timestamp=t0,
            latitude=10.0,
            longitude=20.0,
        ),
        make_record(
            mmsi=223456789,
            timestamp=t0 + timedelta(minutes=20),
            latitude=12.0,
            longitude=20.0,
        ),
    ]

    summary = worker_pool._build_vessel_chunk_summary(223456789, records)

    assert len(summary.teleportation_events) == 1
    assert len(summary.teleportation_d1_events) == 1
    assert len(summary.teleportation_d2_events) == 0
    assert summary.teleportation_events[0].subtype == "D1"


def test_build_vessel_chunk_summary_detects_d2_and_accumulates_jump_distance_when_counts_for_dfsi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify_d2_quality(
        previous,
        current,
        port_zones,
        teleportation_config,
    ):
        _ = previous, current, port_zones, teleportation_config
        return False, False, "ok", True

    monkeypatch.setattr(
        "src.anomaly_detection.rules._classify_d2_quality",
        fake_classify_d2_quality,
    )

    worker_pool.PORT_ZONES = (make_port(),)

    t0 = datetime(2025, 9, 1, 0, 0, 0)
    records = [
        make_record(
            mmsi=223456789,
            timestamp=t0,
            latitude=10.0,
            longitude=20.0,
        ),
        make_record(
            mmsi=223456789,
            timestamp=t0 + timedelta(hours=2),
            latitude=12.0,
            longitude=20.0,
        ),
    ]

    summary = worker_pool._build_vessel_chunk_summary(223456789, records)

    assert len(summary.teleportation_events) == 1
    assert len(summary.teleportation_d1_events) == 0
    assert len(summary.teleportation_d2_events) == 1
    assert summary.teleportation_d2_events[0].counts_for_dfsi is True
    assert summary.total_impossible_jump_km > 0.0


def test_process_chunk_builds_vessel_summaries_for_multiple_mmsi() -> None:
    worker_pool.ROW_PARSER = AISRowParser()
    worker_pool.PORT_ZONES = (make_port(),)

    task = (
        1,
        [
            (
                "01/09/2025 12:00:00",
                "Class A",
                "223456789",
                "10.5",
                "20.5",
                "7.2",
                "8.5",
            ),
            (
                "01/09/2025 12:05:00",
                "Class A",
                "245014000",
                "11.5",
                "21.5",
                "7.0",
                "8.0",
            ),
            (
                "01/09/2025 12:10:00",
                "Class B",
                "538009722",
                "12.5",
                "22.5",
                "6.5",
                "7.5",
            ),
        ],
    )

    result = worker_pool.process_chunk(task)

    assert result.chunk_id == 1
    assert result.raw_row_count == 3
    assert result.valid_record_count == 2
    assert set(result.vessel_summaries.keys()) == {223456789, 245014000}
    assert result.elapsed_time >= 0.0
