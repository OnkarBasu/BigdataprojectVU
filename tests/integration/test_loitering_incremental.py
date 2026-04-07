from __future__ import annotations

from datetime import datetime, timedelta

from src.anomaly_detection.merge import (
    create_merge_state,
    finalize_loitering_detection,
    merge_chunk_result_into_state,
)
from src.config import DetectionConfig, LoiteringConfig, SamplingConfig
from src.models import AISRecord, ChunkProcessingResult, VesselChunkSummary


def make_record(
    *,
    mmsi: int,
    timestamp: datetime,
    latitude: float,
    longitude: float,
    sog: float = 0.2,
) -> AISRecord:
    return AISRecord(
        timestamp=timestamp,
        mmsi=mmsi,
        latitude=latitude,
        longitude=longitude,
        sog=sog,
        draught=None,
    )


def make_summary(
    *,
    mmsi: int,
    records: list[AISRecord],
    loitering_sampled_records: list[AISRecord] | None = None,
) -> VesselChunkSummary:
    ordered = sorted(records, key=lambda r: r.timestamp)
    sampled = ordered if loitering_sampled_records is None else loitering_sampled_records
    return VesselChunkSummary(
        mmsi=mmsi,
        record_count=len(ordered),
        first_record=ordered[0],
        last_record=ordered[-1],
        ac_sampled_records=ordered,
        loitering_sampled_records=sampled,
    )


def make_chunk_result(
    *,
    chunk_id: int,
    vessel_records: dict[int, list[AISRecord]],
) -> ChunkProcessingResult:
    vessel_summaries = {
        mmsi: make_summary(mmsi=mmsi, records=records)
        for mmsi, records in vessel_records.items()
    }
    valid_count = sum(len(records) for records in vessel_records.values())

    return ChunkProcessingResult(
        chunk_id=chunk_id,
        raw_row_count=valid_count,
        valid_record_count=valid_count,
        elapsed_time=0.0,
        vessel_summaries=vessel_summaries,
    )


def make_loitering_config(loitering_sampling_seconds: int = 30 * 60) -> DetectionConfig:
    return DetectionConfig(
        loitering=LoiteringConfig(
            max_distance_km=0.5,
            max_sog_knots=1.0,
            min_duration_hours=2.0,
            bucket_seconds=5 * 60,
            max_continuation_gap_seconds=2 * 5 * 60,
            minimum_port_radius_km=0.0,
        ),
        sampling=SamplingConfig(
            ac_sampling_seconds=5 * 60,
            loitering_sampling_seconds=loitering_sampling_seconds,
        ),
    )


def test_loitering_is_detected_across_chunk_boundary() -> None:
    merge_state = create_merge_state(
        detection_config=make_loitering_config(),
        enable_loitering_detection=True,
    )
    port_zones = ()

    base_time = datetime(2025, 9, 1, 0, 0, 0)
    lat_a = 0.0
    lon_a = 0.0
    lat_b = 0.0
    lon_b = 0.002

    chunk_1 = make_chunk_result(
        chunk_id=1,
        vessel_records={
            111000111: [
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=0), latitude=lat_a, longitude=lon_a),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=30), latitude=lat_a, longitude=lon_a),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=60), latitude=lat_a, longitude=lon_a),
            ],
            222000222: [
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=0), latitude=lat_b, longitude=lon_b),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=30), latitude=lat_b, longitude=lon_b),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=60), latitude=lat_b, longitude=lon_b),
            ],
        },
    )

    merge_chunk_result_into_state(merge_state=merge_state, chunk_result=chunk_1, port_zones=port_zones)

    assert len(merge_state.global_summaries[111000111].loitering_transfer_events) == 0
    assert len(merge_state.global_summaries[222000222].loitering_transfer_events) == 0

    chunk_2 = make_chunk_result(
        chunk_id=2,
        vessel_records={
            111000111: [
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=90), latitude=lat_a, longitude=lon_a),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=120), latitude=lat_a, longitude=lon_a),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=150), latitude=lat_a, longitude=lon_a),
            ],
            222000222: [
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=90), latitude=lat_b, longitude=lon_b),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=120), latitude=lat_b, longitude=lon_b),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=150), latitude=lat_b, longitude=lon_b),
            ],
        },
    )

    merge_chunk_result_into_state(merge_state=merge_state, chunk_result=chunk_2, port_zones=port_zones)
    events = finalize_loitering_detection(merge_state)

    assert len(events) == 1
    assert len(merge_state.global_summaries[111000111].loitering_transfer_events) == 1
    assert len(merge_state.global_summaries[222000222].loitering_transfer_events) == 1

    event = events[0]
    assert {event.mmsi_a, event.mmsi_b} == {111000111, 222000222}
    assert event.start_timestamp == base_time
    assert event.end_timestamp == base_time + timedelta(minutes=150)
    assert event.duration_hours > 2.0
    assert event.min_distance_km <= 0.5
    assert event.avg_distance_km <= 0.5


def test_loitering_is_not_detected_when_sog_is_too_high() -> None:
    merge_state = create_merge_state(
        detection_config=make_loitering_config(),
        enable_loitering_detection=True,
    )
    port_zones = ()

    base_time = datetime(2025, 9, 1, 0, 0, 0)
    lat_a = 0.0
    lon_a = 0.0
    lat_b = 0.0
    lon_b = 0.002

    chunk_1 = make_chunk_result(
        chunk_id=1,
        vessel_records={
            111000111: [
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=0), latitude=lat_a, longitude=lon_a, sog=0.2),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=30), latitude=lat_a, longitude=lon_a, sog=0.2),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=60), latitude=lat_a, longitude=lon_a, sog=0.2),
            ],
            222000222: [
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=0), latitude=lat_b, longitude=lon_b, sog=1.0),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=30), latitude=lat_b, longitude=lon_b, sog=1.0),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=60), latitude=lat_b, longitude=lon_b, sog=1.0),
            ],
        },
    )

    chunk_2 = make_chunk_result(
        chunk_id=2,
        vessel_records={
            111000111: [
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=90), latitude=lat_a, longitude=lon_a, sog=0.2),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=120), latitude=lat_a, longitude=lon_a, sog=0.2),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=150), latitude=lat_a, longitude=lon_a, sog=0.2),
            ],
            222000222: [
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=90), latitude=lat_b, longitude=lon_b, sog=1.0),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=120), latitude=lat_b, longitude=lon_b, sog=1.0),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=150), latitude=lat_b, longitude=lon_b, sog=1.0),
            ],
        },
    )

    merge_chunk_result_into_state(merge_state=merge_state, chunk_result=chunk_1, port_zones=port_zones)
    merge_chunk_result_into_state(merge_state=merge_state, chunk_result=chunk_2, port_zones=port_zones)

    events = finalize_loitering_detection(merge_state)
    assert events == []
    assert len(merge_state.global_summaries[111000111].loitering_transfer_events) == 0
    assert len(merge_state.global_summaries[222000222].loitering_transfer_events) == 0


def test_loitering_is_not_detected_when_distance_is_too_large() -> None:
    merge_state = create_merge_state(
        detection_config=make_loitering_config(),
        enable_loitering_detection=True,
    )
    port_zones = ()

    base_time = datetime(2025, 9, 1, 0, 0, 0)
    lat_a = 0.0
    lon_a = 0.0
    lat_b = 0.0
    lon_b = 0.006

    chunk_1 = make_chunk_result(
        chunk_id=1,
        vessel_records={
            111000111: [
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=0), latitude=lat_a, longitude=lon_a, sog=0.2),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=30), latitude=lat_a, longitude=lon_a, sog=0.2),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=60), latitude=lat_a, longitude=lon_a, sog=0.2),
            ],
            222000222: [
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=0), latitude=lat_b, longitude=lon_b, sog=0.2),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=30), latitude=lat_b, longitude=lon_b, sog=0.2),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=60), latitude=lat_b, longitude=lon_b, sog=0.2),
            ],
        },
    )

    chunk_2 = make_chunk_result(
        chunk_id=2,
        vessel_records={
            111000111: [
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=90), latitude=lat_a, longitude=lon_a, sog=0.2),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=120), latitude=lat_a, longitude=lon_a, sog=0.2),
                make_record(mmsi=111000111, timestamp=base_time + timedelta(minutes=150), latitude=lat_a, longitude=lon_a, sog=0.2),
            ],
            222000222: [
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=90), latitude=lat_b, longitude=lon_b, sog=0.2),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=120), latitude=lat_b, longitude=lon_b, sog=0.2),
                make_record(mmsi=222000222, timestamp=base_time + timedelta(minutes=150), latitude=lat_b, longitude=lon_b, sog=0.2),
            ],
        },
    )

    merge_chunk_result_into_state(merge_state=merge_state, chunk_result=chunk_1, port_zones=port_zones)
    merge_chunk_result_into_state(merge_state=merge_state, chunk_result=chunk_2, port_zones=port_zones)

    events = finalize_loitering_detection(merge_state)
    assert events == []
    assert len(merge_state.global_summaries[111000111].loitering_transfer_events) == 0
    assert len(merge_state.global_summaries[222000222].loitering_transfer_events) == 0
