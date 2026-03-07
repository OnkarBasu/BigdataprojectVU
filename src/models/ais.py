from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class AISRecord:
    timestamp: datetime
    mmsi: int
    latitude: float
    longitude: float
    sog: float | None
    draught: float | None
