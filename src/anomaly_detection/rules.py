from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import math
from pathlib import Path
from typing import DefaultDict, Sequence

import geopandas as gpd
from shapely.geometry import Point
from shapely.prepared import prep

from src.models import (
    AISRecord,
    DraftChangeEvent,
    GoingDarkEvent,
    LoiteringTransferEvent,
    TeleportationEvent,
    TeleportationQualityFlag,
    VesselGlobalSummary,
)
from src.utils.geo import calculate_distance
from src.utils.ports import PortZone, is_blackout_at_sea, is_near_any_port
from config.detection_config import (
    DEFAULT_DETECTION_CONFIG,
    DetectionConfig,
    DraftChangeConfig,
    GoingDarkConfig,
    TeleportationConfig,
)

SECONDS_IN_HOUR = 3600.0
KM_PER_NAUTICAL_MILE = 1.852
NATURAL_EARTH_LOWRES_PATH = Path(
    "/opt/pyvenv/lib/python3.13/site-packages/pyogrio/tests/fixtures/"
    "naturalearth_lowres/naturalearth_lowres.shp"
)


@dataclass(slots=True, frozen=True)
class _LoiteringPoint:
    """Filtered sampled AIS point used for anomaly B detection."""

    mmsi: int
    timestamp: datetime
    latitude: float
    longitude: float
    sog: float


@dataclass(slots=True)
class _ActiveLoiteringPair:
    """Rolling state for one candidate anomaly B pair across time buckets."""

    mmsi_a: int
    mmsi_b: int
    start_timestamp: datetime
    end_timestamp: datetime

    start_lat_a: float
    start_lon_a: float
    start_lat_b: float
    start_lon_b: float

    end_lat_a: float
    end_lon_a: float
    end_lat_b: float
    end_lon_b: float

    min_distance_km: float
    total_distance_km: float
    observation_count: int


@lru_cache(maxsize=1)
def _get_prepared_land_geometry():
    """Load a coarse global land mask for event-level quality checks."""
    if not NATURAL_EARTH_LOWRES_PATH.exists():
        return None

    land = gpd.read_file(NATURAL_EARTH_LOWRES_PATH)["geometry"].union_all()
    return prep(land)


def _is_point_on_land(latitude: float, longitude: float) -> bool | None:
    """Return coarse land-mask result using a low-resolution Natural Earth layer."""
    prepared_land = _get_prepared_land_geometry()

    if prepared_land is None:
        return None

    return prepared_land.contains(Point(longitude, latitude))


def _classify_d2_quality(
    previous: AISRecord,
    current: AISRecord,
    port_zones: Sequence[PortZone] | None,
    teleportation_config: TeleportationConfig,
) -> tuple[bool | None, bool | None, TeleportationQualityFlag, bool]:
    """Classify D2 event quality and whether it should contribute to DFSI."""
    start_on_land = _is_point_on_land(previous.latitude, previous.longitude)
    end_on_land = _is_point_on_land(current.latitude, current.longitude)

    if start_on_land is None or end_on_land is None:
        return start_on_land, end_on_land, "suspect_land_point", False

    if start_on_land is False and end_on_land is False:
        return start_on_land, end_on_land, "ok", True

    if port_zones is None:
        return start_on_land, end_on_land, "suspect_land_point", False

    port_radius_km = max(
        teleportation_config.minimum_port_radius_km,
        teleportation_config.d2_port_proximity_km,
    )

    start_near_port = is_near_any_port(
        latitude=previous.latitude,
        longitude=previous.longitude,
        port_zones=port_zones,
        minimum_radius_km=port_radius_km,
    )
    end_near_port = is_near_any_port(
        latitude=current.latitude,
        longitude=current.longitude,
        port_zones=port_zones,
        minimum_radius_km=port_radius_km,
    )

    if start_near_port or end_near_port:
        return start_on_land, end_on_land, "suspect_land_point_near_port", False

    return start_on_land, end_on_land, "suspect_land_point", False


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
    config: GoingDarkConfig = DEFAULT_DETECTION_CONFIG.going_dark,
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
    if gap_hours <= config.min_gap_hours:
        return None

    distance_km = calculate_distance(
        previous.latitude,
        previous.longitude,
        current.latitude,
        current.longitude,
    )
    if distance_km <= config.min_distance_km:
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
    config: DraftChangeConfig = DEFAULT_DETECTION_CONFIG.draft_change,
    port_zones: Sequence[PortZone] | None = None,
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
    if gap_hours <= config.min_gap_hours:
        return None

    if previous.draught is None or current.draught is None:
        return None

    if previous.draught <= 0:
        return None

    draught_change_abs = abs(current.draught - previous.draught)
    draught_change_ratio = draught_change_abs / previous.draught

    if draught_change_ratio <= config.min_relative_change:
        return None

    if port_zones is not None and not is_blackout_at_sea(
        start_latitude=previous.latitude,
        start_longitude=previous.longitude,
        end_latitude=current.latitude,
        end_longitude=current.longitude,
        port_zones=port_zones,
        minimum_radius_km=config.minimum_port_radius_km,
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
    config: TeleportationConfig = DEFAULT_DETECTION_CONFIG.teleportation,
    port_zones: Sequence[PortZone] | None = None,
) -> TeleportationEvent | None:
    """
    Detect anomaly D for a pair of AIS records.

    The logic distinguishes two deterministic subtypes:
    - D1: near-simultaneous cloning within ``d1_max_gap_hours``;
    - D2: impossible relocation after a longer blackout, up to
      ``d2_max_gap_hours``.

    For D2, the event is additionally quality-classified with a coarse
    land-mask check so obvious inland/bad-coordinate cases can be excluded
    from DFSI while still being preserved for post-analysis.
    """
    _validate_same_mmsi(previous, current)

    gap_hours = calculate_time_gap_hours(previous, current)
    gap_seconds = gap_hours * SECONDS_IN_HOUR
    if gap_seconds < config.min_gap_seconds:
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
    if distance_km <= config.min_distance_km:
        return None

    implied_speed_knots = calculate_implied_speed_knots(distance_km, gap_hours)
    if implied_speed_knots <= config.max_speed_knots:
        return None

    if gap_hours <= config.d1_max_gap_hours:
        return TeleportationEvent(
            mmsi=previous.mmsi,
            subtype="D1",
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

    if gap_hours > config.d2_max_gap_hours:
        return None

    start_on_land, end_on_land, quality_flag, counts_for_dfsi = _classify_d2_quality(
        previous=previous,
        current=current,
        port_zones=port_zones,
        teleportation_config=config,
    )

    return TeleportationEvent(
        mmsi=previous.mmsi,
        subtype="D2",
        start_timestamp=previous.timestamp,
        end_timestamp=current.timestamp,
        gap_hours=gap_hours,
        start_latitude=previous.latitude,
        start_longitude=previous.longitude,
        end_latitude=current.latitude,
        end_longitude=current.longitude,
        distance_km=distance_km,
        implied_speed_knots=implied_speed_knots,
        start_on_land=start_on_land,
        end_on_land=end_on_land,
        quality_flag=quality_flag,
        counts_for_dfsi=counts_for_dfsi,
    )


def detect_all_pair_anomalies(
    previous: AISRecord,
    current: AISRecord,
    config: DetectionConfig = DEFAULT_DETECTION_CONFIG,
    port_zones: Sequence[PortZone] | None = None,
) -> tuple[GoingDarkEvent | None, DraftChangeEvent | None, TeleportationEvent | None]:
    """
    Detect all supported pairwise anomalies for two AIS records.

    This helper runs anomaly A, C, and D detection for a pair of consecutive
    records belonging to the same vessel.
    """
    going_dark_event = detect_going_dark(
        previous=previous,
        current=current,
        config=config.going_dark,
    )
    draft_change_event = detect_draft_change(
        previous=previous,
        current=current,
        config=config.draft_change,
        port_zones=port_zones,
    )
    teleportation_event = detect_teleportation(
        previous=previous,
        current=current,
        config=config.teleportation,
        port_zones=port_zones,
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
                "point_a_timestamp": event.start_timestamp.isoformat(),
                "point_a_latitude": event.start_latitude,
                "point_a_longitude": event.start_longitude,
                "point_b_timestamp": event.end_timestamp.isoformat(),
                "point_b_latitude": event.end_latitude,
                "point_b_longitude": event.end_longitude,
                "gap_hours": event.gap_hours,
                "implied_speed_knots": event.implied_speed_knots,
                "distance_km": event.distance_km,
                "point_a_on_land": "" if event.start_on_land is None else str(event.start_on_land).lower(),
                "point_b_on_land": "" if event.end_on_land is None else str(event.end_on_land).lower(),
                "quality_flag": event.quality_flag,
                "counts_for_dfsi": str(event.counts_for_dfsi).lower(),
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


def _record_to_loitering_point(
    record: AISRecord,
    port_zones: Sequence[PortZone],
    max_sog_knots: float,
    minimum_port_radius_km: float,
) -> _LoiteringPoint | None:
    """Convert one sampled record into a valid anomaly B point candidate."""
    if record.sog is None or record.sog >= max_sog_knots:
        return None

    if is_near_any_port(
        latitude=record.latitude,
        longitude=record.longitude,
        port_zones=port_zones,
        minimum_radius_km=minimum_port_radius_km,
    ):
        return None

    return _LoiteringPoint(
        mmsi=record.mmsi,
        timestamp=record.timestamp,
        latitude=record.latitude,
        longitude=record.longitude,
        sog=record.sog,
    )


def _bucketize_timestamp(timestamp: datetime, bucket_seconds: int) -> datetime:
    """Floor a timestamp to a fixed bucket size in seconds."""
    epoch_seconds = int(timestamp.timestamp())
    bucketed = epoch_seconds - (epoch_seconds % bucket_seconds)
    return datetime.fromtimestamp(bucketed, tz=timestamp.tzinfo)


def _grid_cell_for_point(
    latitude: float,
    longitude: float,
    cell_size_deg: float,
) -> tuple[int, int]:
    """Map one coordinate to a coarse spatial grid cell."""
    lat_idx = math.floor(latitude / cell_size_deg)
    lon_idx = math.floor(longitude / cell_size_deg)
    return lat_idx, lon_idx


def _find_close_pairs_in_bucket(
    points: list[_LoiteringPoint],
    max_distance_km: float,
) -> dict[tuple[int, int], tuple[_LoiteringPoint, _LoiteringPoint, float]]:
    """Find all vessel pairs within the distance threshold inside one time bucket."""
    if len(points) < 2:
        return {}

    # ~0.5 km in latitude degrees; using a slightly larger cell keeps candidate
    # generation simple while exact haversine filtering preserves correctness.
    cell_size_deg = max_distance_km / 111.0 * 1.2

    grid: DefaultDict[tuple[int, int], list[_LoiteringPoint]] = defaultdict(list)
    for point in points:
        grid[_grid_cell_for_point(point.latitude, point.longitude, cell_size_deg)].append(point)

    results: dict[tuple[int, int], tuple[_LoiteringPoint, _LoiteringPoint, float]] = {}

    for point in points:
        cell = _grid_cell_for_point(point.latitude, point.longitude, cell_size_deg)
        for neigh_lat in range(cell[0] - 1, cell[0] + 2):
            for neigh_lon in range(cell[1] - 1, cell[1] + 2):
                for other in grid.get((neigh_lat, neigh_lon), []):
                    if other.mmsi <= point.mmsi:
                        continue

                    distance_km = calculate_distance(
                        point.latitude,
                        point.longitude,
                        other.latitude,
                        other.longitude,
                    )
                    if distance_km > max_distance_km:
                        continue

                    pair_key = (point.mmsi, other.mmsi)
                    existing = results.get(pair_key)
                    if existing is None or distance_km < existing[2]:
                        results[pair_key] = (point, other, distance_km)

    return results


def _start_active_loitering_pair(
    pair_obs: tuple[_LoiteringPoint, _LoiteringPoint, float],
    bucket_time: datetime,
) -> _ActiveLoiteringPair:
    """Create a new rolling anomaly B pair state from one observation."""
    point_a, point_b, distance_km = pair_obs
    return _ActiveLoiteringPair(
        mmsi_a=point_a.mmsi,
        mmsi_b=point_b.mmsi,
        start_timestamp=bucket_time,
        end_timestamp=bucket_time,
        start_lat_a=point_a.latitude,
        start_lon_a=point_a.longitude,
        start_lat_b=point_b.latitude,
        start_lon_b=point_b.longitude,
        end_lat_a=point_a.latitude,
        end_lon_a=point_a.longitude,
        end_lat_b=point_b.latitude,
        end_lon_b=point_b.longitude,
        min_distance_km=distance_km,
        total_distance_km=distance_km,
        observation_count=1,
    )


def _update_active_loitering_pair(
    active: _ActiveLoiteringPair,
    pair_obs: tuple[_LoiteringPoint, _LoiteringPoint, float],
    bucket_time: datetime,
) -> None:
    """Extend an existing rolling anomaly B pair state by one bucket."""
    point_a, point_b, distance_km = pair_obs
    active.end_timestamp = bucket_time
    active.end_lat_a = point_a.latitude
    active.end_lon_a = point_a.longitude
    active.end_lat_b = point_b.latitude
    active.end_lon_b = point_b.longitude
    active.min_distance_km = min(active.min_distance_km, distance_km)
    active.total_distance_km += distance_km
    active.observation_count += 1


def _finalize_active_loitering_pair(
    active: _ActiveLoiteringPair,
    min_duration_hours: float,
) -> LoiteringTransferEvent | None:
    """Convert an active pair state into a final anomaly B event if long enough."""
    duration_hours = (active.end_timestamp - active.start_timestamp).total_seconds() / SECONDS_IN_HOUR
    if duration_hours < min_duration_hours:
        return None

    avg_distance_km = active.total_distance_km / active.observation_count

    return LoiteringTransferEvent(
        mmsi_a=active.mmsi_a,
        mmsi_b=active.mmsi_b,
        start_timestamp=active.start_timestamp,
        end_timestamp=active.end_timestamp,
        duration_hours=duration_hours,
        start_lat_a=active.start_lat_a,
        start_lon_a=active.start_lon_a,
        start_lat_b=active.start_lat_b,
        start_lon_b=active.start_lon_b,
        end_lat_a=active.end_lat_a,
        end_lon_a=active.end_lon_a,
        end_lat_b=active.end_lat_b,
        end_lon_b=active.end_lon_b,
        min_distance_km=active.min_distance_km,
        avg_distance_km=avg_distance_km,
    )


def _validate_same_mmsi(previous: AISRecord, current: AISRecord) -> None:
    """Validate that two AIS records belong to the same vessel."""
    if previous.mmsi != current.mmsi:
        raise ValueError("AIS records must belong to the same MMSI")


def _is_zero_coordinate(latitude: float, longitude: float) -> bool:
    """Return True for the common placeholder coordinate (0, 0)."""
    return latitude == 0.0 and longitude == 0.0


def get_top_teleportation_d1_vessel_visualization_data(global_summaries):
    best_mmsi = None
    best_count = 0

    for mmsi, summary in global_summaries.items():
        count = len(summary.teleportation_d1_events)
        if count > best_count:
            best_count = count
            best_mmsi = mmsi
        elif count == best_count and count > 0 and best_mmsi is not None:
            if mmsi < best_mmsi:
                best_mmsi = mmsi

    if best_mmsi is None or best_count == 0:
        return None

    summary = global_summaries[best_mmsi]

    rows = []
    for i, event in enumerate(summary.teleportation_d1_events, start=1):
        rows.append({
            "mmsi": event.mmsi,
            "event_index": i,
            "subtype": "D1",
            "point_a_timestamp": event.start_timestamp.isoformat(),
            "point_a_latitude": event.start_latitude,
            "point_a_longitude": event.start_longitude,
            "point_b_timestamp": event.end_timestamp.isoformat(),
            "point_b_latitude": event.end_latitude,
            "point_b_longitude": event.end_longitude,
            "gap_hours": event.gap_hours,
            "implied_speed_knots": event.implied_speed_knots,
            "distance_km": event.distance_km,
            "point_a_on_land": "" if event.start_on_land is None else str(event.start_on_land).lower(),
            "point_b_on_land": "" if event.end_on_land is None else str(event.end_on_land).lower(),
            "quality_flag": event.quality_flag,
            "counts_for_dfsi": str(event.counts_for_dfsi).lower(),
        })

    return best_mmsi, rows


def get_top_teleportation_d2_vessel_visualization_data(global_summaries):
    best_mmsi = None
    best_count = 0

    for mmsi, summary in global_summaries.items():
        valid_events = [event for event in summary.teleportation_d2_events if event.counts_for_dfsi]
        count = len(valid_events)

        if count > best_count:
            best_count = count
            best_mmsi = mmsi
        elif count == best_count and count > 0 and best_mmsi is not None:
            if mmsi < best_mmsi:
                best_mmsi = mmsi

    if best_mmsi is None or best_count == 0:
        return None

    summary = global_summaries[best_mmsi]
    valid_events = [event for event in summary.teleportation_d2_events if event.counts_for_dfsi]

    rows = []
    for i, event in enumerate(valid_events, start=1):
        rows.append({
            "mmsi": event.mmsi,
            "event_index": i,
            "subtype": "D2",
            "point_a_timestamp": event.start_timestamp.isoformat(),
            "point_a_latitude": event.start_latitude,
            "point_a_longitude": event.start_longitude,
            "point_b_timestamp": event.end_timestamp.isoformat(),
            "point_b_latitude": event.end_latitude,
            "point_b_longitude": event.end_longitude,
            "gap_hours": event.gap_hours,
            "implied_speed_knots": event.implied_speed_knots,
            "distance_km": event.distance_km,
            "point_a_on_land": "" if event.start_on_land is None else str(event.start_on_land).lower(),
            "point_b_on_land": "" if event.end_on_land is None else str(event.end_on_land).lower(),
            "quality_flag": event.quality_flag,
            "counts_for_dfsi": str(event.counts_for_dfsi).lower(),
        })

    return best_mmsi, rows
