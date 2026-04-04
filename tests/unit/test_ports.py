from __future__ import annotations

from pathlib import Path

from src.utils.ports import (
    PortZone,
    find_nearest_port,
    is_blackout_at_sea,
    is_near_any_port,
    is_position_at_sea,
    load_port_zones,
)


def make_port(
    *,
    name: str,
    country: str = "Test Country",
    latitude: float,
    longitude: float,
    radius_km: float,
) -> PortZone:
    return PortZone(
        name=name,
        country=country,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
    )


def test_load_port_zones_reads_csv_into_portzone_objects(tmp_path: Path) -> None:
    csv_path = tmp_path / "ports.csv"
    csv_path.write_text(
        "port_name,country,latitude,longitude,radius_km\n"
        "Port A,Country A,10.0,20.0,5.0\n"
        "Port B,Country B,11.5,21.5,8.0\n",
        encoding="utf-8",
    )

    port_zones = load_port_zones(csv_path)

    assert len(port_zones) == 2
    assert port_zones[0] == PortZone(
        name="Port A",
        country="Country A",
        latitude=10.0,
        longitude=20.0,
        radius_km=5.0,
    )
    assert port_zones[1] == PortZone(
        name="Port B",
        country="Country B",
        latitude=11.5,
        longitude=21.5,
        radius_km=8.0,
    )


def test_load_port_zones_returns_empty_tuple_for_header_only_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "ports.csv"
    csv_path.write_text(
        "port_name,country,latitude,longitude,radius_km\n",
        encoding="utf-8",
    )

    port_zones = load_port_zones(csv_path)

    assert port_zones == ()


def test_find_nearest_port_returns_none_for_empty_catalog() -> None:
    result = find_nearest_port(
        latitude=10.0,
        longitude=20.0,
        port_zones=(),
    )

    assert result is None


def test_find_nearest_port_returns_closest_port() -> None:
    port_a = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=5.0)
    port_b = make_port(name="Port B", latitude=50.0, longitude=60.0, radius_km=5.0)

    result = find_nearest_port(
        latitude=10.02,
        longitude=20.0,
        port_zones=(port_a, port_b),
    )

    assert result is not None
    nearest_port, distance_km = result

    assert nearest_port == port_a
    assert distance_km >= 0.0
    assert distance_km < 5.0


def test_is_near_any_port_returns_true_when_inside_port_radius() -> None:
    port = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=5.0)

    result = is_near_any_port(
        latitude=10.02,
        longitude=20.0,
        port_zones=(port,),
    )

    assert result is True


def test_is_near_any_port_returns_false_when_outside_all_port_radii() -> None:
    port = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=5.0)

    result = is_near_any_port(
        latitude=11.0,
        longitude=20.0,
        port_zones=(port,),
    )

    assert result is False


def test_is_near_any_port_respects_minimum_radius_km() -> None:
    port = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=1.0)

    result_without_override = is_near_any_port(
        latitude=10.03,
        longitude=20.0,
        port_zones=(port,),
        minimum_radius_km=0.0,
    )
    result_with_override = is_near_any_port(
        latitude=10.03,
        longitude=20.0,
        port_zones=(port,),
        minimum_radius_km=5.0,
    )

    assert result_without_override is False
    assert result_with_override is True


def test_is_position_at_sea_returns_false_when_near_port() -> None:
    port = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=5.0)

    result = is_position_at_sea(
        latitude=10.02,
        longitude=20.0,
        port_zones=(port,),
    )

    assert result is False


def test_is_position_at_sea_returns_true_when_far_from_ports() -> None:
    port = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=5.0)

    result = is_position_at_sea(
        latitude=11.0,
        longitude=20.0,
        port_zones=(port,),
    )

    assert result is True


def test_is_blackout_at_sea_returns_true_when_both_endpoints_are_far_from_ports() -> None:
    port = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=5.0)

    result = is_blackout_at_sea(
        start_latitude=11.0,
        start_longitude=20.0,
        end_latitude=12.0,
        end_longitude=20.0,
        port_zones=(port,),
    )

    assert result is True


def test_is_blackout_at_sea_returns_false_when_start_is_near_port() -> None:
    port = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=5.0)

    result = is_blackout_at_sea(
        start_latitude=10.02,
        start_longitude=20.0,
        end_latitude=12.0,
        end_longitude=20.0,
        port_zones=(port,),
    )

    assert result is False


def test_is_blackout_at_sea_returns_false_when_end_is_near_port() -> None:
    port = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=5.0)

    result = is_blackout_at_sea(
        start_latitude=12.0,
        start_longitude=20.0,
        end_latitude=10.02,
        end_longitude=20.0,
        port_zones=(port,),
    )

    assert result is False


def test_is_blackout_at_sea_returns_false_when_both_endpoints_are_near_ports() -> None:
    port = make_port(name="Port A", latitude=10.0, longitude=20.0, radius_km=5.0)

    result = is_blackout_at_sea(
        start_latitude=10.02,
        start_longitude=20.0,
        end_latitude=10.03,
        end_longitude=20.0,
        port_zones=(port,),
    )

    assert result is False
