from __future__ import annotations

from src.models import AISRecord, DraftChangeEvent, GoingDarkEvent, TeleportationEvent
from src.utils.geo import calculate_distance


HOURS_IN_DAY = 24.0
MINUTES_IN_HOUR = 60.0
SECONDS_IN_HOUR = 3600.0
KM_PER_NAUTICAL_MILE = 1.852


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

    Args:
        previous: Earlier AIS record for the same MMSI.
        current: Later AIS record for the same MMSI.
        min_gap_hours: Minimum blackout duration required to flag anomaly.
        min_distance_km: Minimum distance indicating vessel movement.

    Returns:
        GoingDarkEvent if anomaly A is detected, otherwise None.

    Raises:
        ValueError: If the records belong to different MMSI values.
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
) -> DraftChangeEvent | None:
    """
    Detect anomaly C ("Draft Changes at Sea") for a pair of AIS records.

    The anomaly is flagged when the AIS gap exceeds ``min_gap_hours`` and
    the vessel draught changes by more than ``min_relative_change``.

    Args:
        previous: Earlier AIS record for the same MMSI.
        current: Later AIS record for the same MMSI.
        min_gap_hours: Minimum blackout duration required to evaluate anomaly.
        min_relative_change: Minimum relative draught change, where 0.05 = 5%.

    Returns:
        DraftChangeEvent if anomaly C is detected, otherwise None.

    Raises:
        ValueError: If the records belong to different MMSI values.
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
    """
    Detect anomaly D ("Identity Cloning / Teleportation") for a pair of AIS records.

    The anomaly is flagged when the movement implied by two consecutive AIS
    messages for the same MMSI requires travel faster than ``max_speed_knots``.

    Args:
        previous: Earlier AIS record for the same MMSI.
        current: Later AIS record for the same MMSI.
        max_speed_knots: Maximum physically plausible speed in knots.

    Returns:
        TeleportationEvent if anomaly D is detected, otherwise None.

    Raises:
        ValueError: If the records belong to different MMSI values.
    """
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
) -> tuple[GoingDarkEvent | None, DraftChangeEvent | None, TeleportationEvent | None]:
    """
    Detect all supported pairwise anomalies for two AIS records.

    This helper runs anomaly A, C, and D detection for a pair of consecutive
    records belonging to the same vessel.

    Args:
        previous: Earlier AIS record.
        current: Later AIS record.
        going_dark_min_gap_hours: Minimum blackout duration for anomaly A.
        going_dark_min_distance_km: Minimum distance for anomaly A.
        draft_change_min_gap_hours: Minimum blackout duration for anomaly C.
        draft_change_min_relative_change: Minimum relative draught change for anomaly C.
        teleportation_max_speed_knots: Maximum plausible speed for anomaly D.

    Returns:
        Tuple of:
            - GoingDarkEvent or None
            - DraftChangeEvent or None
            - TeleportationEvent or None
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
    )
    teleportation_event = detect_teleportation(
        previous=previous,
        current=current,
        max_speed_knots=teleportation_max_speed_knots,
    )

    return going_dark_event, draft_change_event, teleportation_event


def _validate_same_mmsi(previous: AISRecord, current: AISRecord) -> None:
    """
    Validate that two AIS records belong to the same vessel.

    Args:
        previous: Earlier AIS record.
        current: Later AIS record.

    Raises:
        ValueError: If MMSI values differ.
    """
    if previous.mmsi != current.mmsi:
        raise ValueError("AIS records must have the same MMSI")
