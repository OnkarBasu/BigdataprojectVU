from __future__ import annotations

from typing import Sequence

from src.models import (
    AISRecord,
    DraftChangeEvent,
    GoingDarkEvent,
    TeleportationEvent,
    VesselGlobalSummary,
)
from src.utils.geo import calculate_distance
from src.utils.ports import PortZone, is_blackout_at_sea


HOURS_IN_DAY = 24.0
MINUTES_IN_HOUR = 60.0
SECONDS_IN_HOUR = 3600.0
KM_PER_NAUTICAL_MILE = 1.852
DEFAULT_D1_MAX_GAP_HOURS = 0.5
DEFAULT_D2_MAX_GAP_HOURS = 24.0
DEFAULT_D_MIN_GAP_SECONDS = 30.0
DEFAULT_D_MIN_DISTANCE_KM = 1.0


def calculate_time_gap_hours(previous: AISRecord, current: AISRecord) -> float:
    """
    Calculate the time difference between two AIS records in hours.

    Args:
        previous: Earlier AIS record.
        current: Later AIS record.

    Returns:
        Time gap between records in hours.

    Raises:
        ValueError: If ``current.timestamp`` is earlier than ``previous.timestamp``.
    """
    time_delta = current.timestamp - previous.timestamp
    gap_seconds = time_delta.total_seconds()

    if gap_seconds < 0:
        raise ValueError("current record timestamp must be greater than or equal to previous timestamp")

    return gap_seconds / SECONDS_IN_HOUR


def calculate_implied_speed_knots(
    distance_km: float,
    gap_hours: float,
) -> float:
    """
    Calculate the implied travel speed in knots.

    Args:
        distance_km: Distance traveled in kilometers.
        gap_hours: Travel time in hours.

    Returns:
        Implied speed in knots.

    Raises:
        ValueError: If ``gap_hours`` is less than or equal to zero.
    """
    if gap_hours <= 0:
        raise ValueError("gap_hours must be greater than 0")

    distance_nm = kilometers_to_nautical_miles(distance_km)
    return distance_nm / gap_hours


def kilometers_to_nautical_miles(distance_km: float) -> float:
    """
    Convert distance from kilometers to nautical miles.

    Args:
        distance_km: Distance in kilometers.

    Returns:
        Distance in nautical miles.
    """
    return distance_km / KM_PER_NAUTICAL_MILE


def detect_going_dark(
    previous: AISRecord,
    current: AISRecord,
    min_gap_hours: float = 4.0,
    min_distance_km: float = 1.0,
) -> GoingDarkEvent | None:
    """
    Detect anomaly A ("Going Dark") for a pair of consecutive AIS records.

    The anomaly is flagged when the AIS gap exceeds ``min_gap_hours`` and
    the vessel appears to have moved at least ``min_distance_km`` between
    the last known position before blackout and the first known position
    after blackout.
    """
    _validate_same_mmsi(previous, current)

    gap_hours = calculate_time_gap_hours(previous, current)
    if gap_hours <= min_gap_hours:
        return None

    distance_km = calculate_distance(
        previous.latitude,
        previous.longitude,
        current.latitude,
        current.longitude,
    )
    if distance_km <= min_distance_km:
        return None

    return GoingDarkEvent(
        mmsi=previous.mmsi,
        start_timestamp=previous.timestamp,
        end_timestamp=current.timestamp,
        gap_hours=gap_hours,
        start_latitude=previous.latitude,
        start_longitude=previous.longitude,
        end_latitude=current.latitude,
        end_longitude=current.longitude,
        distance_km=distance_km,
    )


def detect_draft_change(
    previous: AISRecord,
    current: AISRecord,
    min_gap_hours: float = 2.0,
    min_relative_change: float = 0.05,
    port_zones: Sequence[PortZone] | None = None,
    minimum_port_radius_km: float = 0.0,
) -> DraftChangeEvent | None:
    """
    Detect anomaly C ("Draft Changes at Sea").

    The base anomaly is the same as before:
    - AIS blackout longer than ``min_gap_hours``
    - relative draught change greater than ``min_relative_change``

    If ``port_zones`` is provided, the anomaly is only confirmed when both
    blackout endpoints are outside all configured port zones. This adds the
    "at sea" condition required by the task without changing anomalies A or D.
    """
    _validate_same_mmsi(previous, current)

    gap_hours = calculate_time_gap_hours(previous, current)
    if gap_hours <= min_gap_hours:
        return None

    if previous.draught is None or current.draught is None:
        return None

    if previous.draught <= 0:
        return None

    draught_change_abs = abs(current.draught - previous.draught)
    draught_change_ratio = draught_change_abs / previous.draught

    if draught_change_ratio <= min_relative_change:
        return None

    if port_zones is not None and not is_blackout_at_sea(
        start_latitude=previous.latitude,
        start_longitude=previous.longitude,
        end_latitude=current.latitude,
        end_longitude=current.longitude,
        port_zones=port_zones,
        minimum_radius_km=minimum_port_radius_km,
    ):
        return None

    return DraftChangeEvent(
        mmsi=previous.mmsi,
        start_timestamp=previous.timestamp,
        end_timestamp=current.timestamp,
        gap_hours=gap_hours,
        draught_before=previous.draught,
        draught_after=current.draught,
        draught_change_abs=draught_change_abs,
        draught_change_ratio=draught_change_ratio,
    )


def detect_teleportation(
    previous: AISRecord,
    current: AISRecord,
    max_speed_knots: float = 60.0,
    d1_max_gap_hours: float = DEFAULT_D1_MAX_GAP_HOURS,
    d2_max_gap_hours: float = DEFAULT_D2_MAX_GAP_HOURS,
    min_gap_seconds: float = DEFAULT_D_MIN_GAP_SECONDS,
    min_distance_km: float = DEFAULT_D_MIN_DISTANCE_KM,
) -> TeleportationEvent | None:
    """
    Detect anomaly D for a pair of AIS records.

    The logic distinguishes two deterministic subtypes:
    - D1: near-simultaneous cloning within ``d1_max_gap_hours``;
    - D2: impossible relocation after a longer blackout, up to
      ``d2_max_gap_hours``.

    The pair is ignored when the time gap is too small, when a coordinate is
    the common placeholder ``(0, 0)``, or when the spatial displacement is too
    small to be meaningful.
    """
    _validate_same_mmsi(previous, current)

    gap_hours = calculate_time_gap_hours(previous, current)
    gap_seconds = gap_hours * SECONDS_IN_HOUR
    if gap_seconds < min_gap_seconds:
        return None

    if _is_zero_coordinate(previous.latitude, previous.longitude):
        return None
    if _is_zero_coordinate(current.latitude, current.longitude):
        return None

    distance_km = calculate_distance(
        previous.latitude,
        previous.longitude,
        current.latitude,
        current.longitude,
    )
    if distance_km <= min_distance_km:
        return None

    implied_speed_knots = calculate_implied_speed_knots(distance_km, gap_hours)
    if implied_speed_knots <= max_speed_knots:
        return None

    if gap_hours <= d1_max_gap_hours:
        subtype = "D1"
    elif gap_hours <= d2_max_gap_hours:
        subtype = "D2"
    else:
        return None

    return TeleportationEvent(
        mmsi=previous.mmsi,
        subtype=subtype,
        start_timestamp=previous.timestamp,
        end_timestamp=current.timestamp,
        gap_hours=gap_hours,
        start_latitude=previous.latitude,
        start_longitude=previous.longitude,
        end_latitude=current.latitude,
        end_longitude=current.longitude,
        distance_km=distance_km,
        implied_speed_knots=implied_speed_knots,
    )


def detect_all_pair_anomalies(
    previous: AISRecord,
    current: AISRecord,
    going_dark_min_gap_hours: float = 4.0,
    going_dark_min_distance_km: float = 1.0,
    draft_change_min_gap_hours: float = 2.0,
    draft_change_min_relative_change: float = 0.05,
    teleportation_max_speed_knots: float = 60.0,
    teleportation_d1_max_gap_hours: float = DEFAULT_D1_MAX_GAP_HOURS,
    teleportation_d2_max_gap_hours: float = DEFAULT_D2_MAX_GAP_HOURS,
    teleportation_min_gap_seconds: float = DEFAULT_D_MIN_GAP_SECONDS,
    teleportation_min_distance_km: float = DEFAULT_D_MIN_DISTANCE_KM,
    port_zones: Sequence[PortZone] | None = None,
    minimum_port_radius_km: float = 0.0,
) -> tuple[GoingDarkEvent | None, DraftChangeEvent | None, TeleportationEvent | None]:
    """
    Detect all supported pairwise anomalies for two AIS records.

    This helper runs anomaly A, C, and D detection for a pair of consecutive
    records belonging to the same vessel.
    """
    going_dark_event = detect_going_dark(
        previous=previous,
        current=current,
        min_gap_hours=going_dark_min_gap_hours,
        min_distance_km=going_dark_min_distance_km,
    )
    draft_change_event = detect_draft_change(
        previous=previous,
        current=current,
        min_gap_hours=draft_change_min_gap_hours,
        min_relative_change=draft_change_min_relative_change,
        port_zones=port_zones,
        minimum_port_radius_km=minimum_port_radius_km,
    )
    teleportation_event = detect_teleportation(
        previous=previous,
        current=current,
        max_speed_knots=teleportation_max_speed_knots,
        d1_max_gap_hours=teleportation_d1_max_gap_hours,
        d2_max_gap_hours=teleportation_d2_max_gap_hours,
        min_gap_seconds=teleportation_min_gap_seconds,
        min_distance_km=teleportation_min_distance_km,
    )

    return going_dark_event, draft_change_event, teleportation_event


def get_top_teleportation_vessel_visualization_data(
    global_summaries: dict[int, VesselGlobalSummary],
) -> tuple[int, list[dict[str, int | float | str]]] | None:
    """
    Find the MMSI with the most anomaly D events and extract coordinate pairs.

    D1 and D2 are both included in the ranking for visualization, while the
    subtype is exported per row so the map can distinguish them.
    """
    if not global_summaries:
        return None

    best_mmsi: int | None = None
    best_count = 0

    for mmsi, summary in global_summaries.items():
        count = len(summary.teleportation_events)
        if count > best_count:
            best_count = count
            best_mmsi = mmsi
        elif count == best_count and count > 0 and best_mmsi is not None:
            if mmsi < best_mmsi:
                best_mmsi = mmsi

    if best_mmsi is None or best_count == 0:
        return None

    summary = global_summaries[best_mmsi]
    rows: list[dict[str, int | float | str]] = []

    for event_index, event in enumerate(summary.teleportation_events, start=1):
        rows.append(
            {
                "mmsi": event.mmsi,
                "event_index": event_index,
                "subtype": event.subtype,
                "lat_origin": event.start_latitude,
                "lon_origin": event.start_longitude,
                "lat_destination": event.end_latitude,
                "lon_destination": event.end_longitude,
                "implied_speed_knots": event.implied_speed_knots,
                "distance_km": event.distance_km,
            }
        )

    return best_mmsi, rows


def get_top_going_dark_vessel_visualization_data(
    global_summaries: dict[int, VesselGlobalSummary],
) -> tuple[int, list[dict[str, int | float]]] | None:
    """
    Find the MMSI with the most Anomaly A (going dark) events and extract
    coordinate pairs for map visualization.
    """
    if not global_summaries:
        return None

    best_mmsi: int | None = None
    best_count = 0

    for mmsi, summary in global_summaries.items():
        count = len(summary.going_dark_events)
        if count > best_count:
            best_count = count
            best_mmsi = mmsi
        elif count == best_count and count > 0 and best_mmsi is not None:
            if mmsi < best_mmsi:
                best_mmsi = mmsi

    if best_mmsi is None or best_count == 0:
        return None

    summary = global_summaries[best_mmsi]
    rows: list[dict[str, int | float]] = []

    for event_index, event in enumerate(summary.going_dark_events, start=1):
        rows.append(
            {
                "mmsi": event.mmsi,
                "event_index": event_index,
                "lat_origin": event.start_latitude,
                "lon_origin": event.start_longitude,
                "lat_destination": event.end_latitude,
                "lon_destination": event.end_longitude,
                "gap_hours": event.gap_hours,
                "distance_km": event.distance_km,
            }
        )

    return best_mmsi, rows


def _validate_same_mmsi(previous: AISRecord, current: AISRecord) -> None:
    """Validate that two AIS records belong to the same vessel."""
    if previous.mmsi != current.mmsi:
        raise ValueError("AIS records must belong to the same MMSI")


def _is_zero_coordinate(latitude: float, longitude: float) -> bool:
    """Return True for the common placeholder coordinate (0, 0)."""
    return latitude == 0.0 and longitude == 0.0
