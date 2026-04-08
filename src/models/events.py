from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(slots=True, frozen=True)
class GoingDarkEvent:
    """
    Detected AIS blackout where the vessel likely continued moving.

    This event corresponds to anomaly A ("Going Dark"): a time gap longer
    than the configured threshold where the distance between consecutive
    AIS positions suggests that the vessel was not anchored.

    Attributes:
        mmsi: Vessel MMSI identifier.
        start_timestamp: Timestamp of the last AIS message before blackout.
        end_timestamp: Timestamp of the first AIS message after blackout.
        gap_hours: Duration of the AIS gap in hours.
        start_latitude: Latitude before blackout.
        start_longitude: Longitude before blackout.
        end_latitude: Latitude after blackout.
        end_longitude: Longitude after blackout.
        distance_km: Distance between blackout endpoints in kilometers.
    """

    mmsi: int
    start_timestamp: datetime
    end_timestamp: datetime
    gap_hours: float
    start_latitude: float
    start_longitude: float
    end_latitude: float
    end_longitude: float
    distance_km: float


@dataclass(slots=True, frozen=True)
class DraftChangeEvent:
    """
    Detected significant draught change during an AIS blackout.

    This event corresponds to anomaly C ("Draft Changes at Sea"): a gap
    longer than the configured threshold where vessel draught changes by
    more than the allowed relative percentage.

    Attributes:
        mmsi: Vessel MMSI identifier.
        start_timestamp: Timestamp of the last AIS message before blackout.
        end_timestamp: Timestamp of the first AIS message after blackout.
        gap_hours: Duration of the AIS gap in hours.
        draught_before: Draught value before blackout.
        draught_after: Draught value after blackout.
        draught_change_abs: Absolute draught change.
        draught_change_ratio: Relative draught change, e.g. 0.08 means 8%.
    """

    mmsi: int
    start_timestamp: datetime
    end_timestamp: datetime
    gap_hours: float
    draught_before: float
    draught_after: float
    draught_change_abs: float
    draught_change_ratio: float


TeleportationSubtype = Literal["D1", "D2"]
TeleportationQualityFlag = Literal[
    "ok",
    "suspect_land_point",
    "suspect_land_point_near_port",
]


@dataclass(slots=True, frozen=True)
class TeleportationEvent:
    """
    Detected anomaly D for the same MMSI.

    The project now splits anomaly D into two deterministic subtypes:
    - D1: near-simultaneous cloning, where the same MMSI appears in an
      incompatible location within a short time window;
    - D2: impossible relocation, where the same MMSI reappears after a
      longer blackout at a location that still requires impossible speed.

    Attributes:
        mmsi: Vessel MMSI identifier.
        subtype: "D1" for near-simultaneous cloning, "D2" for impossible
            relocation after blackout.
        start_timestamp: Timestamp of the earlier AIS message.
        end_timestamp: Timestamp of the later AIS message.
        gap_hours: Time difference between the two messages in hours.
        start_latitude: Latitude of the earlier position.
        start_longitude: Longitude of the earlier position.
        end_latitude: Latitude of the later position.
        end_longitude: Longitude of the later position.
        distance_km: Great-circle distance in kilometers.
        implied_speed_knots: Required speed in knots to cover the distance.
        start_on_land: Optional coarse land-mask result for the earlier point.
        end_on_land: Optional coarse land-mask result for the later point.
        quality_flag: Quality classification for the event record.
        counts_for_dfsi: Whether this event should contribute to DFSI.
    """

    mmsi: int
    subtype: TeleportationSubtype
    start_timestamp: datetime
    end_timestamp: datetime
    gap_hours: float
    start_latitude: float
    start_longitude: float
    end_latitude: float
    end_longitude: float
    distance_km: float
    implied_speed_knots: float
    start_on_land: bool | None = None
    end_on_land: bool | None = None
    quality_flag: TeleportationQualityFlag = "ok"
    counts_for_dfsi: bool = True


@dataclass(slots=True, frozen=True)
class LoiteringTransferEvent:
    """
    Detected anomaly B ("Loitering & Transfers") between two vessels.

    Two distinct MMSI are repeatedly observed within a small distance,
    at low speed, for a prolonged period of time away from ports.

    Attributes:
        mmsi_a: First vessel MMSI.
        mmsi_b: Second vessel MMSI.
        start_timestamp: Start of the detected co-location period.
        end_timestamp: End of the detected co-location period.
        duration_hours: Total bucket-based event duration in hours.

        start_lat_a: Start latitude of vessel A.
        start_lon_a: Start longitude of vessel A.
        start_lat_b: Start latitude of vessel B.
        start_lon_b: Start longitude of vessel B.

        end_lat_a: End latitude of vessel A.
        end_lon_a: End longitude of vessel A.
        end_lat_b: End latitude of vessel B.
        end_lon_b: End longitude of vessel B.

        min_distance_km: Minimum distance observed during the event.
        avg_distance_km: Average pair distance across retained observations.
    """

    mmsi_a: int
    mmsi_b: int

    start_timestamp: datetime
    end_timestamp: datetime
    duration_hours: float

    start_lat_a: float
    start_lon_a: float
    start_lat_b: float
    start_lon_b: float

    end_lat_a: float
    end_lon_a: float
    end_lat_b: float
    end_lon_b: float

    min_distance_km: float
    avg_distance_km: float
