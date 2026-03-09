from __future__ import annotations

from src.models import VesselGlobalSummary
from src.anomaly_detection import kilometers_to_nautical_miles


def calculate_dfsi(summary: VesselGlobalSummary) -> float:
    """
    Calculate the Dark Fleet Suspicion Index (DFSI) for one vessel.

    The DFSI formula is defined as:

        DFSI = (Max Gap in Hours / 2)
             + (Total Impossible Distance Jump in Nautical Miles / 10)
             + (C * 15)

    where:
        - Max Gap in Hours is the vessel's maximum detected AIS blackout;
        - Total Impossible Distance Jump is the sum of anomaly D jump distances;
        - C is the number of illicit draft changes detected for the vessel.

    Args:
        summary: Fully merged anomaly summary for one vessel.

    Returns:
        Calculated DFSI score.
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
    """
    Calculate DFSI scores for all vessels in the provided summaries.

    Args:
        vessel_summaries: Global merged vessel summaries keyed by MMSI.

    Returns:
        Dictionary mapping MMSI to DFSI score.
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
    Rank vessels by their DFSI scores.

    Args:
        vessel_summaries: Global merged vessel summaries keyed by MMSI.
        descending: Whether to sort from highest DFSI to lowest.

    Returns:
        List of ``(mmsi, dfsi)`` tuples sorted by DFSI score.
    """
    scores = calculate_all_dfsi(vessel_summaries)
    return sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=descending,
    )
