from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.anomaly_detection.rules import (
    calculate_implied_speed_knots,
    calculate_time_gap_hours,
    detect_all_pair_anomalies,
    detect_draft_change,
    detect_going_dark,
    detect_teleportation,
)
from src.config import (
    DEFAULT_DETECTION_CONFIG,
    DetectionConfig,
    DraftChangeConfig,
    GoingDarkConfig,
    TeleportationConfig,
)
from src.utils.ports import PortZone


# -------------------------
# Helper / utility tests
# -------------------------

def test_calculate_time_gap_hours_returns_expected_value(make_record) -> None:
    previous = make_record(timestamp=datetime(2025, 1, 1, 0, 0, 0))
    current = make_record(timestamp=datetime(2025, 1, 1, 6, 30, 0))

    gap_hours = calculate_time_gap_hours(previous, current)

    assert gap_hours == 6.5


def test_calculate_time_gap_hours_raises_for_negative_gap(make_record) -> None:
    previous = make_record(timestamp=datetime(2025, 1, 1, 6, 0, 0))
    current = make_record(timestamp=datetime(2025, 1, 1, 5, 0, 0))

    with pytest.raises(ValueError, match="timestamp must be greater than or equal"):
        calculate_time_gap_hours(previous, current)


def test_calculate_implied_speed_knots_raises_for_non_positive_gap() -> None:
    with pytest.raises(ValueError, match="gap_hours must be greater than 0"):
        calculate_implied_speed_knots(distance_km=100.0, gap_hours=0.0)


# -------------------------
# detect_going_dark
# -------------------------

def test_detect_going_dark_returns_event_when_gap_and_distance_exceed_thresholds(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 5, 0, 0),
        latitude=10.02,
        longitude=20.0,
    )

    event = detect_going_dark(previous, current)

    assert event is not None
    assert event.mmsi == previous.mmsi
    assert event.start_timestamp == previous.timestamp
    assert event.end_timestamp == current.timestamp
    assert event.gap_hours == 5.0
    assert event.distance_km > DEFAULT_DETECTION_CONFIG.going_dark.min_distance_km


def test_detect_going_dark_returns_none_when_gap_equals_threshold(make_record) -> None:
    config = GoingDarkConfig(min_gap_hours=4.0, min_distance_km=1.0)

    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 4, 0, 0),
        latitude=10.02,
        longitude=20.0,
    )

    event = detect_going_dark(previous, current, config=config)

    assert event is None


def test_detect_going_dark_returns_none_when_distance_is_too_small(make_record) -> None:
    config = GoingDarkConfig(min_gap_hours=4.0, min_distance_km=5.0)

    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 6, 0, 0),
        latitude=10.01,
        longitude=20.0,
    )

    event = detect_going_dark(previous, current, config=config)

    assert event is None


def test_detect_going_dark_raises_for_different_mmsi(make_record) -> None:
    previous = make_record(mmsi=111111111)
    current = make_record(mmsi=222222222, timestamp=previous.timestamp + timedelta(hours=5))

    with pytest.raises(ValueError, match="same MMSI"):
        detect_going_dark(previous, current)


# -------------------------
# detect_draft_change
# -------------------------

def test_detect_draft_change_returns_event_when_conditions_are_met(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        draught=10.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 3, 0, 0),
        draught=11.0,
    )

    event = detect_draft_change(previous, current)

    assert event is not None
    assert event.mmsi == previous.mmsi
    assert event.gap_hours == 3.0
    assert event.draught_before == 10.0
    assert event.draught_after == 11.0
    assert event.draught_change_abs == 1.0
    assert event.draught_change_ratio == 0.1


def test_detect_draft_change_returns_none_when_previous_draught_is_none(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        draught=None,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 3, 0, 0),
        draught=11.0,
    )

    event = detect_draft_change(previous, current)

    assert event is None


def test_detect_draft_change_returns_none_when_current_draught_is_none(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        draught=10.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 3, 0, 0),
        draught=None,
    )

    event = detect_draft_change(previous, current)

    assert event is None


def test_detect_draft_change_returns_none_when_previous_draught_is_non_positive(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        draught=0.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 3, 0, 0),
        draught=2.0,
    )

    event = detect_draft_change(previous, current)

    assert event is None


def test_detect_draft_change_returns_none_when_relative_change_equals_threshold(make_record) -> None:
    config = DraftChangeConfig(min_gap_hours=2.0, min_relative_change=0.05)

    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        draught=10.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 3, 0, 0),
        draught=10.5,
    )

    event = detect_draft_change(previous, current, config=config)

    assert event is None


def test_detect_draft_change_returns_none_when_blackout_is_not_at_sea(make_record) -> None:
    port_zones = (
        PortZone(
            name="Test Port",
            country="Test Country",
            latitude=10.0,
            longitude=20.0,
            radius_km=5.0,
        ),
    )

    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
        draught=10.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 3, 0, 0),
        latitude=10.03,
        longitude=20.0,
        draught=11.0,
    )

    event = detect_draft_change(previous, current, port_zones=port_zones)

    assert event is None


def test_detect_draft_change_returns_event_when_blackout_is_at_sea(make_record) -> None:
    port_zones = (
        PortZone(
            name="Test Port",
            country="Test Country",
            latitude=0.0,
            longitude=0.0,
            radius_km=5.0,
        ),
    )

    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=20.0,
        longitude=30.0,
        draught=10.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 3, 0, 0),
        latitude=20.02,
        longitude=30.0,
        draught=11.0,
    )

    event = detect_draft_change(previous, current, port_zones=port_zones)

    assert event is not None
    assert event.mmsi == previous.mmsi


def test_detect_draft_change_raises_for_different_mmsi(make_record) -> None:
    previous = make_record(mmsi=111111111, draught=10.0)
    current = make_record(
        mmsi=222222222,
        timestamp=previous.timestamp + timedelta(hours=3),
        draught=11.0,
    )

    with pytest.raises(ValueError, match="same MMSI"):
        detect_draft_change(previous, current)


# -------------------------
# detect_teleportation
# -------------------------

def test_detect_teleportation_returns_d1_event_for_short_gap_and_impossible_speed(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 0, 20, 0),
        latitude=12.0,
        longitude=20.0,
    )

    event = detect_teleportation(previous, current)

    assert event is not None
    assert event.subtype == "D1"
    assert event.mmsi == previous.mmsi
    assert event.counts_for_dfsi is True
    assert event.quality_flag == "ok"
    assert event.implied_speed_knots > DEFAULT_DETECTION_CONFIG.teleportation.max_speed_knots


def test_detect_teleportation_returns_d2_event_for_longer_gap_and_impossible_speed(
    make_record,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify_d2_quality(
        previous,
        current,
        port_zones,
        teleportation_config,
    ):
        return (False, False, "ok", True)

    monkeypatch.setattr(
        "src.anomaly_detection.rules._classify_d2_quality",
        fake_classify_d2_quality,
    )

    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 2, 0, 0),
        latitude=12.0,
        longitude=20.0,
    )

    event = detect_teleportation(previous, current)

    assert event is not None
    assert event.subtype == "D2"
    assert event.start_on_land is False
    assert event.end_on_land is False
    assert event.quality_flag == "ok"
    assert event.counts_for_dfsi is True


def test_detect_teleportation_returns_none_when_gap_is_below_minimum(make_record) -> None:
    config = TeleportationConfig(
        min_gap_seconds=30.0,
        min_distance_km=1.0,
        max_speed_knots=60.0,
        d1_max_gap_hours=0.5,
        d2_max_gap_hours=24.0,
    )

    previous = make_record(timestamp=datetime(2025, 1, 1, 0, 0, 0))
    current = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 20),
        latitude=11.0,
        longitude=20.0,
    )

    event = detect_teleportation(previous, current, config=config)

    assert event is None


def test_detect_teleportation_returns_none_for_zero_coordinate_in_previous(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=0.0,
        longitude=0.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 1, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )

    event = detect_teleportation(previous, current)

    assert event is None


def test_detect_teleportation_returns_none_for_zero_coordinate_in_current(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 1, 0, 0),
        latitude=0.0,
        longitude=0.0,
    )

    event = detect_teleportation(previous, current)

    assert event is None


def test_detect_teleportation_returns_none_when_distance_is_too_small(make_record) -> None:
    config = TeleportationConfig(
        min_gap_seconds=30.0,
        min_distance_km=500.0,
        max_speed_knots=60.0,
        d1_max_gap_hours=0.5,
        d2_max_gap_hours=24.0,
    )

    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 1, 0, 0),
        latitude=10.2,
        longitude=20.0,
    )

    event = detect_teleportation(previous, current, config=config)

    assert event is None


def test_detect_teleportation_returns_none_when_implied_speed_is_not_impossible(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 10, 0, 0),
        latitude=10.1,
        longitude=20.0,
    )

    event = detect_teleportation(previous, current)

    assert event is None


def test_detect_teleportation_returns_none_when_gap_exceeds_d2_window(make_record) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 2, 1, 0, 0),
        latitude=20.0,
        longitude=20.0,
    )

    event = detect_teleportation(previous, current)

    assert event is None


def test_detect_teleportation_propagates_d2_quality_fields(
    make_record,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_classify_d2_quality(
        previous,
        current,
        port_zones,
        teleportation_config,
    ):
        return (True, False, "suspect_land_point", False)

    monkeypatch.setattr(
        "src.anomaly_detection.rules._classify_d2_quality",
        fake_classify_d2_quality,
    )

    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 2, 0, 0),
        latitude=12.0,
        longitude=20.0,
    )

    event = detect_teleportation(previous, current)

    assert event is not None
    assert event.subtype == "D2"
    assert event.start_on_land is True
    assert event.end_on_land is False
    assert event.quality_flag == "suspect_land_point"
    assert event.counts_for_dfsi is False


def test_detect_teleportation_raises_for_different_mmsi(make_record) -> None:
    previous = make_record(mmsi=111111111)
    current = make_record(
        mmsi=222222222,
        timestamp=previous.timestamp + timedelta(hours=1),
        latitude=20.0,
        longitude=20.0,
    )

    with pytest.raises(ValueError, match="same MMSI"):
        detect_teleportation(previous, current)


# -------------------------
# detect_all_pair_anomalies
# -------------------------

def test_detect_all_pair_anomalies_returns_tuple_with_expected_components(
    make_record,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = make_record()
    current = make_record(timestamp=previous.timestamp + timedelta(hours=5))

    expected_going_dark = object()
    expected_draft_change = object()
    expected_teleportation = object()

    def fake_detect_going_dark(previous, current, config):
        return expected_going_dark

    def fake_detect_draft_change(previous, current, config, port_zones):
        return expected_draft_change

    def fake_detect_teleportation(previous, current, config, port_zones):
        return expected_teleportation

    monkeypatch.setattr(
        "src.anomaly_detection.rules.detect_going_dark",
        fake_detect_going_dark,
    )
    monkeypatch.setattr(
        "src.anomaly_detection.rules.detect_draft_change",
        fake_detect_draft_change,
    )
    monkeypatch.setattr(
        "src.anomaly_detection.rules.detect_teleportation",
        fake_detect_teleportation,
    )

    config = DetectionConfig()

    going_dark_event, draft_change_event, teleportation_event = detect_all_pair_anomalies(
        previous=previous,
        current=current,
        config=config,
        port_zones=(),
    )

    assert going_dark_event is expected_going_dark
    assert draft_change_event is expected_draft_change
    assert teleportation_event is expected_teleportation


def test_detect_all_pair_anomalies_on_real_inputs_can_trigger_going_dark_and_draft_change_but_not_teleportation(
    make_record,
) -> None:
    previous = make_record(
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        latitude=10.0,
        longitude=20.0,
        draught=10.0,
    )
    current = make_record(
        timestamp=datetime(2025, 1, 1, 5, 0, 0),
        latitude=10.02,
        longitude=20.0,
        draught=11.0,
    )

    going_dark_event, draft_change_event, teleportation_event = detect_all_pair_anomalies(
        previous=previous,
        current=current,
    )

    assert going_dark_event is not None
    assert draft_change_event is not None
    assert teleportation_event is None
