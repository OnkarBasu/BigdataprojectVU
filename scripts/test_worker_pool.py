from __future__ import annotations

from datetime import datetime

from src.parallel.worker_pool import process_chunk
from src.models import AISRecord


def main() -> None:
    """
    Run a simple manual test for worker chunk processing.

    The script creates an in-memory chunk with AIS records designed to
    trigger anomalies A, C, and D, then passes the chunk to
    ``process_chunk`` and prints the resulting summary.
    """
    records = [
        # MMSI 111000111
        # Pair 1 -> Pair 2:
        # gap > 4h and significant movement => Going Dark
        # draught changes by > 5% during blackout => Draft Change
        AISRecord(
            timestamp=datetime(2026, 3, 1, 0, 0, 0),
            mmsi=111000111,
            latitude=55.0000,
            longitude=12.0000,
            sog=10.0,
            draught=10.0,
        ),
        AISRecord(
            timestamp=datetime(2026, 3, 1, 5, 30, 0),
            mmsi=111000111,
            latitude=55.3000,
            longitude=12.4000,
            sog=9.5,
            draught=11.0,
        ),
        # Pair 2 -> Pair 3:
        # very short gap with large distance => Teleportation
        AISRecord(
            timestamp=datetime(2026, 3, 1, 5, 40, 0),
            mmsi=111000111,
            latitude=57.0000,
            longitude=18.0000,
            sog=12.0,
            draught=11.0,
        ),
        # Another vessel with no anomalies
        AISRecord(
            timestamp=datetime(2026, 3, 1, 1, 0, 0),
            mmsi=222000222,
            latitude=54.0000,
            longitude=11.0000,
            sog=8.0,
            draught=7.5,
        ),
        AISRecord(
            timestamp=datetime(2026, 3, 1, 1, 30, 0),
            mmsi=222000222,
            latitude=54.0100,
            longitude=11.0200,
            sog=8.2,
            draught=7.5,
        ),
    ]

    chunk = (1, records)
    result = process_chunk(chunk)

    print("=" * 80)
    print(f"Chunk ID: {result.chunk_id}")
    print(f"Row count: {result.row_count}")
    print(f"Elapsed time: {result.elapsed_time:.6f} sec")
    print(f"Vessels in chunk: {len(result.vessel_summaries)}")
    print("=" * 80)

    for mmsi, summary in sorted(result.vessel_summaries.items()):
        print(f"\nMMSI: {mmsi}")
        print(f"  Record count: {summary.record_count}")
        print(f"  First record: {summary.first_record.timestamp}")
        print(f"  Last record:  {summary.last_record.timestamp}")
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
