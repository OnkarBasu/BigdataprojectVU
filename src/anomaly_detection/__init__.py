"""
Anomaly detection utilities.

This package provides rule-based detection and scoring logic for AIS
anomaly analysis used in the shadow fleet detection pipeline.
"""

from .rules import (
    calculate_implied_speed_knots,
    calculate_time_gap_hours,
    detect_all_pair_anomalies,
    detect_draft_change,
    detect_going_dark,
    detect_teleportation,
    get_top_going_dark_vessel_visualization_data,
    get_top_teleportation_vessel_visualization_data,
    kilometers_to_nautical_miles,
)
from .merge import (
    MergeState,
    create_merge_state,
    merge_chunk_result_into_state,
    merge_chunk_results,
)
from .scoring import (
    calculate_all_dfsi,
    calculate_dfsi,
    rank_vessels_by_dfsi
)

__all__ = [
    "calculate_time_gap_hours",
    "calculate_implied_speed_knots",
    "kilometers_to_nautical_miles",
    "detect_going_dark",
    "detect_draft_change",
    "detect_teleportation",
    "detect_all_pair_anomalies",
    "get_top_going_dark_vessel_visualization_data",
    "get_top_teleportation_vessel_visualization_data",
    "MergeState",
    "create_merge_state",
    "merge_chunk_result_into_state",
    "merge_chunk_results",
    "calculate_dfsi",
    "calculate_all_dfsi",
    "rank_vessels_by_dfsi",
]
