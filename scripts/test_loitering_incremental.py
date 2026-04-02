from __future__ import annotations

from datetime import datetime, timedelta

from src.anomaly_detection.merge import (
    create_merge_state,
    merge_chunk_result_into_state,
    finalize_loitering_detection,
)
from src.models import AISRecord, ChunkProcessingResult, VesselChunkSummary


def _make_record(
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


def _make_summary(
    *,
    mmsi: int,
    records: list[AISRecord],
) -> VesselChunkSummary:
    records = sorted(records, key=lambda r: r.timestamp)
    return VesselChunkSummary(
        mmsi=mmsi,
        record_count=len(records),
        first_record=records[0],
        last_record=records[-1],
        sampled_records=records,
    )


def _make_chunk_result(
    *,
    chunk_id: int,
    vessel_records: dict[int, list[AISRecord]],
) -> ChunkProcessingResult:
    vessel_summaries = {
        mmsi: _make_summary(mmsi=mmsi, records=records)
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


def test_loitering_is_detected_across_chunk_boundary() -> None:
    """
    Checks that anomaly B is correctly stitched between two chunks.

    Scenario:
    - two vessels are within 500 m;
    - both have SOG < 1 knot;
    - observation begins in chunk 1 and continues in chunk 2;
    - total duration > 2 hours;
    - the event should only appear after the second chunk is merged.
    """
    merge_state = create_merge_state(enable_loitering_detection=True)
    port_zones = ()

    base_time = datetime(2025, 9, 1, 0, 0, 0)

    lat_a = 0.0
    lon_a = 0.0
    lat_b = 0.0
    lon_b = 0.002  # ~222 m near equator

    # Chunk 1: 00:00, 00:30, 01:00
    chunk_1 = _make_chunk_result(
        chunk_id=1,
        vessel_records={
            111000111: [
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=0),
                    latitude=lat_a,
                    longitude=lon_a,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=30),
                    latitude=lat_a,
                    longitude=lon_a,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=60),
                    latitude=lat_a,
                    longitude=lon_a,
                ),
            ],
            222000222: [
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=0),
                    latitude=lat_b,
                    longitude=lon_b,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=30),
                    latitude=lat_b,
                    longitude=lon_b,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=60),
                    latitude=lat_b,
                    longitude=lon_b,
                ),
            ],
        },
    )

    merge_chunk_result_into_state(
        merge_state=merge_state,
        chunk_result=chunk_1,
        port_zones=port_zones,
    )

    summary_a_after_chunk_1 = merge_state.global_summaries[111000111]
    summary_b_after_chunk_1 = merge_state.global_summaries[222000222]

    assert len(summary_a_after_chunk_1.loitering_transfer_events) == 0
    assert len(summary_b_after_chunk_1.loitering_transfer_events) == 0

    chunk_2 = _make_chunk_result(
        chunk_id=2,
        vessel_records={
            111000111: [
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=90),
                    latitude=lat_a,
                    longitude=lon_a,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=120),
                    latitude=lat_a,
                    longitude=lon_a,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=150),
                    latitude=lat_a,
                    longitude=lon_a,
                ),
            ],
            222000222: [
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=90),
                    latitude=lat_b,
                    longitude=lon_b,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=120),
                    latitude=lat_b,
                    longitude=lon_b,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=150),
                    latitude=lat_b,
                    longitude=lon_b,
                ),
            ],
        },
    )

    merge_chunk_result_into_state(
        merge_state=merge_state,
        chunk_result=chunk_2,
        port_zones=port_zones,
    )

    events = finalize_loitering_detection(merge_state)

    assert len(events) == 1

    summary_a = merge_state.global_summaries[111000111]
    summary_b = merge_state.global_summaries[222000222]

    assert len(summary_a.loitering_transfer_events) == 1
    assert len(summary_b.loitering_transfer_events) == 1

    event = events[0]

    assert {event.mmsi_a, event.mmsi_b} == {111000111, 222000222}
    assert event.start_timestamp == base_time
    assert event.end_timestamp == base_time + timedelta(minutes=150)
    assert event.duration_hours > 2.0
    assert event.min_distance_km <= 0.5
    assert event.avg_distance_km <= 0.5


def test_loitering_is_not_detected_when_sog_is_too_high() -> None:
    """
    Checks that anomaly B is not detected when vessels are close enough
    but one of them has SOG >= 1 knot.

    Scenario:
    - two vessels are within 500 m;
    - total duration > 2 hours;
    - but one vessel has SOG >= 1 knot for all points;
    - no loitering-transfer event should be detected.
    """
    merge_state = create_merge_state(enable_loitering_detection=True)
    port_zones = ()

    base_time = datetime(2025, 9, 1, 0, 0, 0)

    lat_a = 0.0
    lon_a = 0.0
    lat_b = 0.0
    lon_b = 0.002  # ~222 m near equator

    chunk_1 = _make_chunk_result(
        chunk_id=1,
        vessel_records={
            111000111: [
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=0),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=30),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=60),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
            ],
            222000222: [
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=0),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=1.0,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=30),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=1.0,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=60),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=1.0,
                ),
            ],
        },
    )

    chunk_2 = _make_chunk_result(
        chunk_id=2,
        vessel_records={
            111000111: [
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=90),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=120),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=150),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
            ],
            222000222: [
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=90),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=1.0,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=120),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=1.0,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=150),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=1.0,
                ),
            ],
        },
    )

    merge_chunk_result_into_state(
        merge_state=merge_state,
        chunk_result=chunk_1,
        port_zones=port_zones,
    )
    merge_chunk_result_into_state(
        merge_state=merge_state,
        chunk_result=chunk_2,
        port_zones=port_zones,
    )

    events = finalize_loitering_detection(merge_state)

    assert events == []

    summary_a = merge_state.global_summaries[111000111]
    summary_b = merge_state.global_summaries[222000222]

    assert len(summary_a.loitering_transfer_events) == 0
    assert len(summary_b.loitering_transfer_events) == 0


def test_loitering_is_not_detected_when_distance_is_too_large() -> None:
    """
    Checks that anomaly B is not detected when vessels move slowly long enough
    but stay farther apart than 500 meters.

    Scenario:
    - two vessels have SOG < 1 knot;
    - total duration > 2 hours;
    - but the distance between them is > 500 m;
    - no loitering-transfer event should be detected.
    """
    merge_state = create_merge_state(enable_loitering_detection=True)
    port_zones = ()

    base_time = datetime(2025, 9, 1, 0, 0, 0)

    lat_a = 0.0
    lon_a = 0.0
    lat_b = 0.0
    lon_b = 0.006  # ~666 m near equator, i.e. > 500 m

    chunk_1 = _make_chunk_result(
        chunk_id=1,
        vessel_records={
            111000111: [
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=0),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=30),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=60),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
            ],
            222000222: [
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=0),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=30),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=60),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=0.2,
                ),
            ],
        },
    )

    chunk_2 = _make_chunk_result(
        chunk_id=2,
        vessel_records={
            111000111: [
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=90),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=120),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=111000111,
                    timestamp=base_time + timedelta(minutes=150),
                    latitude=lat_a,
                    longitude=lon_a,
                    sog=0.2,
                ),
            ],
            222000222: [
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=90),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=120),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=0.2,
                ),
                _make_record(
                    mmsi=222000222,
                    timestamp=base_time + timedelta(minutes=150),
                    latitude=lat_b,
                    longitude=lon_b,
                    sog=0.2,
                ),
            ],
        },
    )

    merge_chunk_result_into_state(
        merge_state=merge_state,
        chunk_result=chunk_1,
        port_zones=port_zones,
    )
    merge_chunk_result_into_state(
        merge_state=merge_state,
        chunk_result=chunk_2,
        port_zones=port_zones,
    )

    events = finalize_loitering_detection(merge_state)

    assert events == []

    summary_a = merge_state.global_summaries[111000111]
    summary_b = merge_state.global_summaries[222000222]

    assert len(summary_a.loitering_transfer_events) == 0
    assert len(summary_b.loitering_transfer_events) == 0