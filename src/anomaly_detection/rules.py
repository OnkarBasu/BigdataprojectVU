from __future__ import annotations

from typing import Sequence

from src.models import AISRecord, DraftChangeEvent, GoingDarkEvent, TeleportationEvent
from src.utils.geo import calculate_distance
from src.utils.ports import PortZone, is_blackout_at_sea


HOURS_IN_DAY = 24.0
MINUTES_IN_HOUR = 60.0
SECONDS_IN_HOUR = 3600.0
KM_PER_NAUTICAL_MILE = 1.852


def calculate_time_gap_hours(previous: AISRecord, current: AISRecord) -> float:
    time_delta = current.timestamp - previous.timestamp
    gap_seconds = time_delta.total_seconds()

    if gap_seconds < 0:
        raise ValueError("current record timestamp must be greater than or equal to previous timestamp")

    return gap_seconds / SECONDS_IN_HOUR


def calculate_implied_speed_knots(
    distance_km: float,
    gap_hours: float,
) -> float:
    if gap_hours <= 0:
        raise ValueError("gap_hours must be greater than 0")

    distance_nm = kilometers_to_nautical_miles(distance_km)
    return distance_nm / gap_hours


def kilometers_to_nautical_miles(distance_km: float) -> float:
    return distance_km / KM_PER_NAUTICAL_MILE


def detect_going_dark(
    previous: AISRecord,
    current: AISRecord,
    min_gap_hours: float = 4.0,
    min_distance_km: float = 1.0,
) -> GoingDarkEvent | None:
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
) -> TeleportationEvent | None:
    _validate_same_mmsi(previous, current)

    gap_hours = calculate_time_gap_hours(previous, current)
    if gap_hours <= 0:
        return None

    distance_km = calculate_distance(
        previous.latitude,
        previous.longitude,
        current.latitude,
        current.longitude,
    )
    implied_speed_knots = calculate_implied_speed_knots(distance_km, gap_hours)

    if implied_speed_knots <= max_speed_knots:
        return None

    return TeleportationEvent(
        mmsi=previous.mmsi,
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
    port_zones: Sequence[PortZone] | None = None,
    minimum_port_radius_km: float = 0.0,
) -> tuple[GoingDarkEvent | None, DraftChangeEvent | None, TeleportationEvent | None]:
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
    )

    return going_dark_event, draft_change_event, teleportation_event


def _validate_same_mmsi(previous: AISRecord, current: AISRecord) -> None:
    if previous.mmsi != current.mmsi:
        raise ValueError("AIS records must belong to the same MMSI")
