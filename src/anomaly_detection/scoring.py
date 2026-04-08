from __future__ import annotations
from datetime import timedelta

from src.models import VesselGlobalSummary
from src.anomaly_detection import kilometers_to_nautical_miles


def calculate_d1_episode_count(summary: VesselGlobalSummary) -> int:
    """
    Aggregate D1 teleportation events into temporal episodes.

    Consecutive D1 events are merged into the same episode when the next
    event starts within 2 hours of the current episode end. The returned
    count is used in DFSI instead of the raw D1 event count.
    """
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

        DFSI = (Max Gap Hours / 2)
             + (Draft Change Count * 15)
             + (D1 Episode Count * 20)
             + (Valid D2 Distance in Nautical Miles / 10)

    Notes:
        - D1 events are first aggregated into temporal episodes using
          ``calculate_d1_episode_count``.
        - Only D2 distance marked as valid for DFSI is accumulated into
          ``summary.total_impossible_jump_km`` before scoring.
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
    """
    Calculate DFSI scores for all vessels in the provided global summaries.

    Returns:
        Mapping from MMSI to final DFSI score.
    """
    return {
        mmsi: calculate_dfsi(summary)
        for mmsi, summary in vessel_summaries.items()
    }


def rank_vessels_by_dfsi(
    vessel_summaries: dict[int, VesselGlobalSummary],
    descending: bool = True,
) -> list[tuple[int, float]]:
    """
    Rank vessels by DFSI score.

    Args:
        vessel_summaries: Global per-vessel summaries.
        descending: If True, highest-risk vessels are returned first.

    Returns:
        List of ``(mmsi, dfsi_score)`` pairs sorted by score.
    """
    scores = calculate_all_dfsi(vessel_summaries)
    return sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=descending,
    )
