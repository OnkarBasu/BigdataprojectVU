from __future__ import annotations

from datetime import datetime, timedelta

from src.anomaly_detection.scoring import (
    calculate_all_dfsi,
    calculate_d1_episode_count,
    calculate_dfsi,
    rank_vessels_by_dfsi,
)
from src.models import VesselGlobalSummary, TeleportationEvent


def make_d1_event(start: datetime, end: datetime) -> TeleportationEvent:
    return TeleportationEvent(
        mmsi=123,
        subtype="D1",
        start_timestamp=start,
        end_timestamp=end,
        gap_hours=(end - start).total_seconds() / 3600,
        start_latitude=0,
        start_longitude=0,
        end_latitude=1,
        end_longitude=1,
        distance_km=100,
        implied_speed_knots=200,
    )


# -------------------------
# calculate_d1_episode_count
# -------------------------

def test_d1_episode_count_empty() -> None:
    summary = VesselGlobalSummary(mmsi=1, record_count=0)

    assert calculate_d1_episode_count(summary) == 0


def test_d1_episode_count_single_event() -> None:
    t0 = datetime(2025, 1, 1, 0, 0)

    summary = VesselGlobalSummary(
        mmsi=1,
        record_count=0,
        teleportation_d1_events=[make_d1_event(t0, t0 + timedelta(minutes=10))],
    )

    assert calculate_d1_episode_count(summary) == 1


def test_d1_episode_count_merged_events_within_2_hours() -> None:
    t0 = datetime(2025, 1, 1, 0, 0)

    e1 = make_d1_event(t0, t0 + timedelta(minutes=10))
    e2 = make_d1_event(t0 + timedelta(hours=1), t0 + timedelta(hours=1, minutes=10))

    summary = VesselGlobalSummary(
        mmsi=1,
        record_count=0,
        teleportation_d1_events=[e1, e2],
    )

    assert calculate_d1_episode_count(summary) == 1


def test_d1_episode_count_separate_events() -> None:
    t0 = datetime(2025, 1, 1, 0, 0)

    e1 = make_d1_event(t0, t0 + timedelta(minutes=10))
    e2 = make_d1_event(t0 + timedelta(hours=3), t0 + timedelta(hours=3, minutes=10))

    summary = VesselGlobalSummary(
        mmsi=1,
        record_count=0,
        teleportation_d1_events=[e1, e2],
    )

    assert calculate_d1_episode_count(summary) == 2


# -------------------------
# calculate_dfsi
# -------------------------

def test_dfsi_zero_summary() -> None:
    summary = VesselGlobalSummary(mmsi=1, record_count=0)

    assert calculate_dfsi(summary) == 0.0


def test_dfsi_only_gap() -> None:
    summary = VesselGlobalSummary(
        mmsi=1,
        record_count=0,
        max_gap_hours=10,
    )

    assert calculate_dfsi(summary) == 5.0  # 10 / 2


def test_dfsi_only_draft_change() -> None:
    summary = VesselGlobalSummary(
        mmsi=1,
        record_count=0,
        draft_change_count=2,
    )

    assert calculate_dfsi(summary) == 30.0  # 2 * 15


def test_dfsi_only_d1_episodes() -> None:
    t0 = datetime(2025, 1, 1, 0, 0)

    summary = VesselGlobalSummary(
        mmsi=1,
        record_count=0,
        teleportation_d1_events=[
            make_d1_event(t0, t0 + timedelta(minutes=10)),
            make_d1_event(t0 + timedelta(hours=3), t0 + timedelta(hours=3, minutes=10)),
        ],
    )

    # 2 episodes * 20
    assert calculate_dfsi(summary) == 40.0


def test_dfsi_combined_case() -> None:
    t0 = datetime(2025, 1, 1, 0, 0)

    summary = VesselGlobalSummary(
        mmsi=1,
        record_count=0,
        max_gap_hours=10,              # -> 5
        total_impossible_jump_km=185.2,  # 100 NM -> 10
        draft_change_count=1,          # -> 15
        teleportation_d1_events=[
            make_d1_event(t0, t0 + timedelta(minutes=10)),
        ],  # -> 1 episode = 20
    )

    # 5 + 10 + 15 + 20 = 50
    assert round(calculate_dfsi(summary), 5) == 50.0


# -------------------------
# calculate_all_dfsi
# -------------------------

def test_calculate_all_dfsi_multiple_vessels() -> None:
    summaries = {
        1: VesselGlobalSummary(mmsi=1, record_count=0, max_gap_hours=10),
        2: VesselGlobalSummary(mmsi=2, record_count=0, max_gap_hours=4),
    }

    result = calculate_all_dfsi(summaries)

    assert result[1] == 5.0
    assert result[2] == 2.0


# -------------------------
# rank_vessels_by_dfsi
# -------------------------

def test_rank_vessels_descending() -> None:
    summaries = {
        1: VesselGlobalSummary(mmsi=1, record_count=0, max_gap_hours=10),
        2: VesselGlobalSummary(mmsi=2, record_count=0, max_gap_hours=4),
    }

    ranked = rank_vessels_by_dfsi(summaries, descending=True)

    assert ranked[0][0] == 1
    assert ranked[1][0] == 2


def test_rank_vessels_ascending() -> None:
    summaries = {
        1: VesselGlobalSummary(mmsi=1, record_count=0, max_gap_hours=10),
        2: VesselGlobalSummary(mmsi=2, record_count=0, max_gap_hours=4),
    }

    ranked = rank_vessels_by_dfsi(summaries, descending=False)

    assert ranked[0][0] == 2
    assert ranked[1][0] == 1
