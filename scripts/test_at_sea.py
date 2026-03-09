from __future__ import annotations

from datetime import datetime, timedelta

from src.anomaly_detection import detect_draft_change
from src.models import AISRecord
from src.utils import load_port_zones, is_blackout_at_sea


def make_record(
    *,
    timestamp: datetime,
    mmsi: int,
    latitude: float,
    longitude: float,
    draught: float,
    sog: float = 0.0,
) -> AISRecord:
    return AISRecord(
        timestamp=timestamp,
        mmsi=mmsi,
        latitude=latitude,
        longitude=longitude,
        sog=sog,
        draught=draught,
    )


def main() -> None:
    port_zones = load_port_zones()
    print(f"Loaded port zones: {len(port_zones)}")

    base_time = datetime(2024, 1, 1, 0, 0, 0)

    # Case 1: Near Copenhagen -> should NOT be at sea
    near_port_prev = make_record(
        timestamp=base_time,
        mmsi=123456789,
        latitude=55.70,
        longitude=12.60,
        draught=10.0,
    )
    near_port_curr = make_record(
        timestamp=base_time + timedelta(hours=3),
        mmsi=123456789,
        latitude=55.72,
        longitude=12.62,
        draught=11.0,  # +10%
    )

    near_port_at_sea = is_blackout_at_sea(
        start_latitude=near_port_prev.latitude,
        start_longitude=near_port_prev.longitude,
        end_latitude=near_port_curr.latitude,
        end_longitude=near_port_curr.longitude,
        port_zones=port_zones,
    )

    near_port_event = detect_draft_change(
        previous=near_port_prev,
        current=near_port_curr,
        port_zones=port_zones,
    )

    print("\nCASE 1: near port")
    print(f"is_blackout_at_sea -> {near_port_at_sea}")
    print(f"detect_draft_change -> {near_port_event}")

    # Case 2: Far from ports -> must be at sea
    at_sea_prev = make_record(
        timestamp=base_time,
        mmsi=123456790,
        latitude=56.50,
        longitude=5.00,
        draught=10.0,
    )
    at_sea_curr = make_record(
        timestamp=base_time + timedelta(hours=3),
        mmsi=123456790,
        latitude=56.70,
        longitude=5.20,
        draught=11.0,  # +10%
    )

    at_sea_flag = is_blackout_at_sea(
        start_latitude=at_sea_prev.latitude,
        start_longitude=at_sea_prev.longitude,
        end_latitude=at_sea_curr.latitude,
        end_longitude=at_sea_curr.longitude,
        port_zones=port_zones,
    )

    at_sea_event = detect_draft_change(
        previous=at_sea_prev,
        current=at_sea_curr,
        port_zones=port_zones,
    )

    print("\nCASE 2: far from ports")
    print(f"is_blackout_at_sea -> {at_sea_flag}")
    print(f"detect_draft_change -> {at_sea_event}")


if __name__ == "__main__":
    main()
