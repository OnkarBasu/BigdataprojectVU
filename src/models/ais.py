from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class AISRecord:
    """
    Normalized AIS observation used throughout parsing, detection, and merge.

    Attributes:
        timestamp: Observation timestamp.
        mmsi: Vessel MMSI identifier.
        latitude: Latitude in decimal degrees.
        longitude: Longitude in decimal degrees.
        sog: Speed over ground in knots, if available.
        draught: Reported vessel draught, if available.
    """
    timestamp: datetime
    mmsi: int
    latitude: float
    longitude: float
    sog: float | None
    draught: float | None
