from __future__ import annotations
from datetime import timedelta

from src.models import VesselGlobalSummary
from src.anomaly_detection import kilometers_to_nautical_miles


def calculate_d1_episode_count(summary: VesselGlobalSummary) -> int:
    """Aggregate D1 events into episodes using a 2-hour merge window."""
    events = summary.teleportation_d1_events
    if not events:
        return 0

    events_sorted = sorted(events, key=lambda e: e.start_timestamp)

    episode_count = 0
    current_episode_end = None

    for event in events_sorted:
        if current_episode_end is None:
            episode_count += 1
            current_episode_end = event.end_timestamp
            continue

        if event.start_timestamp <= current_episode_end + timedelta(hours=2):
            current_episode_end = max(current_episode_end, event.end_timestamp)
        else:
            episode_count += 1
            current_episode_end = event.end_timestamp

    return episode_count


def calculate_dfsi(summary: VesselGlobalSummary) -> float:
    """
    Calculate the Dark Fleet Suspicion Index (DFSI) for one vessel.

    The DFSI formula is defined as:

        DFSI = (Max Gap in Hours / 2)
             + (Total D2 Impossible Relocation Distance in Nautical Miles / 10)
             + (C * 15)

    D1 near-simultaneous cloning events are intentionally tracked separately
    and do not contribute directly to DFSI.
    """
    total_impossible_jump_nm = kilometers_to_nautical_miles(
        summary.total_impossible_jump_km,
    )

    d1_episode_count = calculate_d1_episode_count(summary)

    return (
        (summary.max_gap_hours / 2.0)
        + (total_impossible_jump_nm / 10.0)
        + (summary.draft_change_count * 15.0)
        + (d1_episode_count * 20.0)
    )


def calculate_all_dfsi(
    vessel_summaries: dict[int, VesselGlobalSummary],
) -> dict[int, float]:
    """Calculate DFSI scores for all vessels in the provided summaries."""
    return {
        mmsi: calculate_dfsi(summary)
        for mmsi, summary in vessel_summaries.items()
    }


def rank_vessels_by_dfsi(
    vessel_summaries: dict[int, VesselGlobalSummary],
    descending: bool = True,
) -> list[tuple[int, float]]:
    """Rank vessels by their DFSI scores."""
    scores = calculate_all_dfsi(vessel_summaries)
    return sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=descending,
    )
