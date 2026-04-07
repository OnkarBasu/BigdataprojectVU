from __future__ import annotations

import csv
from pathlib import Path

from src.anomaly_detection import calculate_d1_episode_count


def write_results_csv(
    output_file: Path,
    ranked_scores: list[tuple[int, float]],
    global_summaries: dict,
) -> None:
    """
    Write vessel DFSI results to a CSV file.

    Args:
        output_file: Path to the output CSV file.
        ranked_scores: Ranked list of (MMSI, DFSI) pairs.
        global_summaries: Final merged vessel summaries keyed by MMSI.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        writer.writerow(
            [
                "MMSI",
                "DFSI",
                "record_count",
                "max_gap_hours",
                "impossible_relocation_km_d2",
                "draft_change_count",
                "going_dark_events",
                "draft_change_events",
                "teleportation_events",
                "teleportation_d1_events",
                "d1_episode_count",
                "teleportation_d2_events",
                "teleportation_d2_valid_events",
                "teleportation_d2_flagged_events",
                "loitering_transfer_events",
            ]
        )

        for mmsi, score in ranked_scores:
            summary = global_summaries[mmsi]

            writer.writerow(
                [
                    mmsi,
                    f"{score:.6f}",
                    summary.record_count,
                    f"{summary.max_gap_hours:.3f}",
                    f"{summary.total_impossible_jump_km:.3f}",
                    summary.draft_change_count,
                    len(summary.going_dark_events),
                    len(summary.draft_change_events),
                    len(summary.teleportation_events),
                    len(summary.teleportation_d1_events),
                    calculate_d1_episode_count(summary),
                    len(summary.teleportation_d2_events),
                    sum(1 for event in summary.teleportation_d2_events if event.counts_for_dfsi),
                    sum(1 for event in summary.teleportation_d2_events if not event.counts_for_dfsi),
                    len(summary.loitering_transfer_events),
                ]
            )


def write_teleportation_visualization_csv(
    output_file: Path,
    mmsi: int,
    rows: list[dict[str, int | float | str]],
) -> None:
    """
    Write teleportation coordinates for map visualization.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "mmsi",
        "event_index",
        "subtype",
        "point_a_timestamp",
        "point_a_latitude",
        "point_a_longitude",
        "point_b_timestamp",
        "point_b_latitude",
        "point_b_longitude",
        "gap_hours",
        "implied_speed_knots",
        "distance_km",
        "point_a_on_land",
        "point_b_on_land",
        "quality_flag",
        "counts_for_dfsi",
    ]

    with output_file.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(
                [
                    row["mmsi"],
                    row["event_index"],
                    row["subtype"],
                    row["point_a_timestamp"],
                    f"{row['point_a_latitude']:.6f}",
                    f"{row['point_a_longitude']:.6f}",
                    row["point_b_timestamp"],
                    f"{row['point_b_latitude']:.6f}",
                    f"{row['point_b_longitude']:.6f}",
                    f"{row['gap_hours']:.6f}",
                    f"{row['implied_speed_knots']:.3f}",
                    f"{row['distance_km']:.3f}",
                    row["point_a_on_land"],
                    row["point_b_on_land"],
                    row["quality_flag"],
                    row["counts_for_dfsi"],
                ]
            )


def write_going_dark_visualization_csv(
    output_file: Path,
    mmsi: int,
    rows: list[dict[str, int | float]],
) -> None:
    """
    Write going-dark coordinates for map visualization.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "mmsi",
        "event_index",
        "lat_origin",
        "lon_origin",
        "lat_destination",
        "lon_destination",
        "gap_hours",
        "distance_km",
    ]

    with output_file.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(
                [
                    row["mmsi"],
                    row["event_index"],
                    f"{row['lat_origin']:.6f}",
                    f"{row['lon_origin']:.6f}",
                    f"{row['lat_destination']:.6f}",
                    f"{row['lon_destination']:.6f}",
                    f"{row['gap_hours']:.3f}",
                    f"{row['distance_km']:.3f}",
                ]
            )


def write_loitering_visualization_csv(
    output_file: Path,
    mmsi: int,
    rows: list[dict[str, int | float | str]],
) -> None:
    """Write loitering paired coordinates for map visualization."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "focus_mmsi",
        "event_index",
        "mmsi_a",
        "mmsi_b",
        "start_timestamp",
        "end_timestamp",
        "duration_hours",
        "start_lat_a",
        "start_lon_a",
        "start_lat_b",
        "start_lon_b",
        "end_lat_a",
        "end_lon_a",
        "end_lat_b",
        "end_lon_b",
        "min_distance_km",
        "avg_distance_km",
    ]

    with output_file.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(
                [
                    row["focus_mmsi"],
                    row["event_index"],
                    row["mmsi_a"],
                    row["mmsi_b"],
                    row["start_timestamp"],
                    row["end_timestamp"],
                    f"{row['duration_hours']:.3f}",
                    f"{row['start_lat_a']:.6f}",
                    f"{row['start_lon_a']:.6f}",
                    f"{row['start_lat_b']:.6f}",
                    f"{row['start_lon_b']:.6f}",
                    f"{row['end_lat_a']:.6f}",
                    f"{row['end_lon_a']:.6f}",
                    f"{row['end_lat_b']:.6f}",
                    f"{row['end_lon_b']:.6f}",
                    f"{row['min_distance_km']:.3f}",
                    f"{row['avg_distance_km']:.3f}",
                ]
            )


def write_pipeline_profile_csv(
    output_file: Path,
    chunk_profiles: list,
) -> None:
    """
    Write per-chunk pipeline profiling data to a CSV file.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "chunk_id",
        "raw_row_count",
        "valid_record_count",
        "vessel_count",
        "ac_sampled_record_count",
        "loitering_sampled_record_count",
        "worker_elapsed_sec",
        "queue_wait_sec",
        "merge_elapsed_sec",
        "pending_results_before_merge",
        "pending_results_after_merge",
        "main_rss_mb_after_merge",
    ]

    with output_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for profile in chunk_profiles:
            writer.writerow({name: getattr(profile, name) for name in fieldnames})
