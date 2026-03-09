from __future__ import annotations

from datetime import datetime

from src.anomaly_detection.merge import merge_chunk_results
from src.models import AISRecord
from src.parallel.worker_pool import process_chunk


def main() -> None:
    """
    Run a manual test for cross-chunk anomaly detection during merge.

    The script creates two chunks such that some anomalies are not detectable
    inside individual chunks, but become detectable only when comparing the
    last record of one chunk with the first record of the next chunk.
    """
    chunk_1_records = [
        # Vessel 1: first half of a future Going Dark + Draft Change event
        AISRecord(
            timestamp=datetime(2026, 3, 1, 0, 0, 0),
            mmsi=111000111,
            latitude=55.0000,
            longitude=12.0000,
            sog=10.0,
            draught=10.0,
        ),
        # Vessel 2: first half of a future Teleportation event
        AISRecord(
            timestamp=datetime(2026, 3, 1, 2, 0, 0),
            mmsi=333000333,
            latitude=54.0000,
            longitude=11.0000,
            sog=9.0,
            draught=8.0,
        ),
    ]

    chunk_2_records = [
        # Vessel 1: second half of Going Dark + Draft Change
        AISRecord(
            timestamp=datetime(2026, 3, 1, 5, 30, 0),
            mmsi=111000111,
            latitude=55.3000,
            longitude=12.4000,
            sog=9.5,
            draught=11.0,
        ),
        # Vessel 2: second half of Teleportation
        AISRecord(
            timestamp=datetime(2026, 3, 1, 2, 10, 0),
            mmsi=333000333,
            latitude=57.0000,
            longitude=18.0000,
            sog=12.0,
            draught=8.0,
        ),
        # Control vessel with no anomalies
        AISRecord(
            timestamp=datetime(2026, 3, 1, 4, 0, 0),
            mmsi=222000222,
            latitude=53.0000,
            longitude=10.0000,
            sog=7.0,
            draught=6.5,
        ),
    ]

    chunk_1 = (1, chunk_1_records)
    chunk_2 = (2, chunk_2_records)

    chunk_result_1 = process_chunk(chunk_1)
    chunk_result_2 = process_chunk(chunk_2)

    print("=" * 80)
    print("LOCAL CHUNK RESULTS")
    print("=" * 80)
    for chunk_result in (chunk_result_1, chunk_result_2):
        print(
            f"Chunk {chunk_result.chunk_id}: "
            f"rows={chunk_result.row_count}, "
            f"vessels={len(chunk_result.vessel_summaries)}"
        )
        for mmsi, summary in sorted(chunk_result.vessel_summaries.items()):
            print(
                f"  MMSI {mmsi}: "
                f"going_dark={len(summary.going_dark_events)}, "
                f"draft_change={len(summary.draft_change_events)}, "
                f"teleportation={len(summary.teleportation_events)}"
            )

    global_summaries = merge_chunk_results([chunk_result_2, chunk_result_1])

    print("\n" + "=" * 80)
    print("MERGED GLOBAL RESULTS")
    print("=" * 80)

    for mmsi, summary in sorted(global_summaries.items()):
        print(f"\nMMSI: {mmsi}")
        print(f"  Record count: {summary.record_count}")
        print(f"  Max gap hours: {summary.max_gap_hours:.3f}")
        print(f"  Total impossible jump km: {summary.total_impossible_jump_km:.3f}")
        print(f"  Draft change count: {summary.draft_change_count}")

        print(f"  Going dark events: {len(summary.going_dark_events)}")
        for event in summary.going_dark_events:
            print(
                "    - "
                f"{event.start_timestamp} -> {event.end_timestamp}, "
                f"gap={event.gap_hours:.2f}h, "
                f"distance={event.distance_km:.2f} km"
            )

        print(f"  Draft change events: {len(summary.draft_change_events)}")
        for event in summary.draft_change_events:
            print(
                "    - "
                f"{event.start_timestamp} -> {event.end_timestamp}, "
                f"gap={event.gap_hours:.2f}h, "
                f"draught {event.draught_before:.2f} -> {event.draught_after:.2f}, "
                f"ratio={event.draught_change_ratio:.3f}"
            )

        print(f"  Teleportation events: {len(summary.teleportation_events)}")
        for event in summary.teleportation_events:
            print(
                "    - "
                f"{event.start_timestamp} -> {event.end_timestamp}, "
                f"gap={event.gap_hours:.2f}h, "
                f"distance={event.distance_km:.2f} km, "
                f"speed={event.implied_speed_knots:.2f} kn"
            )

    print("\nDone.")


if __name__ == "__main__":
    main()
