"""
Anomaly detection utilities.

This package provides rule-based detection logic for AIS anomaly
analysis used in the shadow fleet detection pipeline.
"""

from .rules import (
    calculate_implied_speed_knots,
    calculate_time_gap_hours,
    detect_all_pair_anomalies,
    detect_draft_change,
    detect_going_dark,
    detect_teleportation,
    kilometers_to_nautical_miles,
)

__all__ = [
    "calculate_time_gap_hours",
    "calculate_implied_speed_knots",
    "kilometers_to_nautical_miles",
    "detect_going_dark",
    "detect_draft_change",
    "detect_teleportation",
    "detect_all_pair_anomalies",
]
