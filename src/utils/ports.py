from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from src.utils.geo import calculate_distance


DEFAULT_PORTS_CSV_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "ports_dma_region.csv"
)


@dataclass(frozen=True, slots=True)
class PortZone:
    """
    Simplified port-area definition used for "at sea" validation.

    Attributes:
        name: Human-readable port name.
        country: Country name from the source catalog.
        latitude: Representative port latitude.
        longitude: Representative port longitude.
        radius_km: Radius of the port influence zone. A position inside this
            radius is treated as "near port", not "at sea".
    """
    name: str
    country: str
    latitude: float
    longitude: float
    radius_km: float


def _parse_float(value: str) -> float:
    return float(value.strip())


@lru_cache(maxsize=4)
def load_port_zones(csv_path: str | Path = DEFAULT_PORTS_CSV_PATH) -> tuple[PortZone, ...]:
    """
    Load port zones from a CSV file.

    Expected columns:
        - port_name
        - country
        - latitude
        - longitude
        - radius_km
    """
    path = Path(csv_path)

    port_zones: list[PortZone] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            port_zones.append(
                PortZone(
                    name=row["port_name"].strip(),
                    country=row["country"].strip(),
                    latitude=_parse_float(row["latitude"]),
                    longitude=_parse_float(row["longitude"]),
                    radius_km=_parse_float(row["radius_km"]),
                )
            )

    return tuple(port_zones)


def find_nearest_port(
    latitude: float,
    longitude: float,
    port_zones: Sequence[PortZone],
) -> tuple[PortZone, float] | None:
    """
    Find the nearest port zone to a position.

    Returns:
        Tuple of (nearest_port, distance_km), or None if the catalog is empty.
    """
    if not port_zones:
        return None

    nearest_port: PortZone | None = None
    nearest_distance_km: float | None = None

    for port in port_zones:
        distance_km = calculate_distance(
            latitude,
            longitude,
            port.latitude,
            port.longitude,
        )

        if nearest_distance_km is None or distance_km < nearest_distance_km:
            nearest_port = port
            nearest_distance_km = distance_km

    if nearest_port is None or nearest_distance_km is None:
        return None

    return nearest_port, nearest_distance_km


def is_near_any_port(
    latitude: float,
    longitude: float,
    port_zones: Sequence[PortZone],
    minimum_radius_km: float = 0.0,
) -> bool:
    """
    Check whether a position is inside any port influence zone.

    The effective radius for each port is:
        max(port.radius_km, minimum_radius_km)

    This allows a per-port radius from the catalog plus an optional global floor.
    """
    for port in port_zones:
        distance_km = calculate_distance(
            latitude,
            longitude,
            port.latitude,
            port.longitude,
        )
        effective_radius_km = max(port.radius_km, minimum_radius_km)

        if distance_km <= effective_radius_km:
            return True

    return False


def is_position_at_sea(
    latitude: float,
    longitude: float,
    port_zones: Sequence[PortZone],
    minimum_radius_km: float = 0.0,
) -> bool:
    """
    Treat a position as "at sea" when it is not near any configured port zone.
    """
    return not is_near_any_port(
        latitude=latitude,
        longitude=longitude,
        port_zones=port_zones,
        minimum_radius_km=minimum_radius_km,
    )


def is_blackout_at_sea(
    start_latitude: float,
    start_longitude: float,
    end_latitude: float,
    end_longitude: float,
    port_zones: Sequence[PortZone],
    minimum_radius_km: float = 0.0,
) -> bool:
    """
    Validate that both ends of a blackout are away from ports.

    This is the simplest practical interpretation of "at sea" for anomaly C:
    only confirm the anomaly if both the pre-blackout and post-blackout
    positions are outside all configured port zones.
    """
    return (
        is_position_at_sea(
            latitude=start_latitude,
            longitude=start_longitude,
            port_zones=port_zones,
            minimum_radius_km=minimum_radius_km,
        )
        and
        is_position_at_sea(
            latitude=end_latitude,
            longitude=end_longitude,
            port_zones=port_zones,
            minimum_radius_km=minimum_radius_km,
        )
    )
