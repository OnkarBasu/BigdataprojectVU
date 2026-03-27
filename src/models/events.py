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
