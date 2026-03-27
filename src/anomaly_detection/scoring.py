from __future__ import annotations

from src.models import VesselGlobalSummary
from src.anomaly_detection import kilometers_to_nautical_miles


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

    return (
        (summary.max_gap_hours / 2.0)
        + (total_impossible_jump_nm / 10.0)
        + (summary.draft_change_count * 15.0)
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
