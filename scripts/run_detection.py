from __future__ import annotations

import argparse
from pathlib import Path

from src.anomaly_detection import get_top_going_dark_vessel_visualization_data
from src.anomaly_detection.rules import (
    get_top_teleportation_d1_vessel_visualization_data,
    get_top_teleportation_d2_vessel_visualization_data,
)
from src.output import (
    write_results_csv,
    write_teleportation_visualization_csv,
    write_going_dark_visualization_csv,
    write_loitering_visualization_csv,
)
from src.pipeline import run_detection_pipeline


def build_argument_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the detection script.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Run shadow fleet anomaly detection on one or more AIS CSV files.",
    )
    parser.add_argument(
        "input_files",
        nargs="+",
        type=Path,
        help="Path(s) to input AIS CSV file(s).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100_000,
        help="Number of raw AIS rows per chunk.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of worker processes.",
    )
    parser.add_argument(
        "--encoding",
        type=str,
        default="utf-8",
        help="Input file encoding.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top vessels by DFSI to display.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/output/dfsi_results.csv"),
        help="Path to output CSV file.",
    )
    parser.add_argument(
        "--memory-output",
        type=Path,
        default=Path("data/output/memory_profile.csv"),
        help="Path to output memory profile CSV file.",
    )
    parser.add_argument(
        "--teleportation-d1-viz-output",
        type=Path,
        default=Path("data/output/top_teleportation_d1_vessel_map.csv"),
    )
    parser.add_argument(
        "--teleportation-d2-viz-output",
        type=Path,
        default=Path("data/output/top_teleportation_d2_vessel_map.csv"),
    )
    parser.add_argument(
        "--going-dark-viz-output",
        type=Path,
        default=Path("data/output/top_going_dark_vessel_map.csv"),
        help="Path to output CSV of top Anomaly A vessel coordinates for map visualization.",
    )
    parser.add_argument(
        "--disable-loitering-detection",
        action="store_true",
        default=False,
        help="Disable anomaly B (loitering & transfers) detection.",
    )
    parser.add_argument(
        "--loitering-viz-output",
        type=Path,
        default=Path("data/output/top_loitering_vessel_map.csv"),
        help="Path to output CSV of top Anomaly B vessel coordinates for map visualization.",
    )
    return parser


def get_top_loitering_vessel_visualization_data(
    global_summaries: dict,
) -> tuple[int, list[dict[str, int | float | str]]] | None:
    """Find the MMSI with the most anomaly B events and extract paired coordinates."""
    if not global_summaries:
        return None

    best_mmsi: int | None = None
    best_count = 0

    for mmsi, summary in global_summaries.items():
        count = len(summary.loitering_transfer_events)
        if count > best_count:
            best_count = count
            best_mmsi = mmsi
        elif count == best_count and count > 0 and best_mmsi is not None and mmsi < best_mmsi:
            best_mmsi = mmsi

    if best_mmsi is None or best_count == 0:
        return None

    summary = global_summaries[best_mmsi]
    rows: list[dict[str, int | float | str]] = []

    for event_index, event in enumerate(summary.loitering_transfer_events, start=1):
        rows.append(
            {
                "focus_mmsi": best_mmsi,
                "event_index": event_index,
                "mmsi_a": event.mmsi_a,
                "mmsi_b": event.mmsi_b,
                "start_timestamp": event.start_timestamp.isoformat(),
                "end_timestamp": event.end_timestamp.isoformat(),
                "duration_hours": event.duration_hours,
                "start_lat_a": event.start_lat_a,
                "start_lon_a": event.start_lon_a,
                "start_lat_b": event.start_lat_b,
                "start_lon_b": event.start_lon_b,
                "end_lat_a": event.end_lat_a,
                "end_lon_a": event.end_lon_a,
                "end_lat_b": event.end_lat_b,
                "end_lon_b": event.end_lon_b,
                "min_distance_km": event.min_distance_km,
                "avg_distance_km": event.avg_distance_km,
            }
        )

    return best_mmsi, rows


def main() -> None:
    """
    CLI entrypoint for the anomaly-detection pipeline.
    """
    parser = build_argument_parser()
    args = parser.parse_args()

    input_files: list[Path] = args.input_files
    chunk_size: int = args.chunk_size
    workers: int = args.workers
    encoding: str = args.encoding
    top_n: int = args.top
    output_file: Path = args.output
    memory_output_file: Path = args.memory_output
    teleportation_d1_viz_output: Path = args.teleportation_d1_viz_output
    teleportation_d2_viz_output: Path = args.teleportation_d2_viz_output
    going_dark_viz_output: Path = args.going_dark_viz_output
    loitering_viz_output: Path = args.loitering_viz_output
    enable_loitering_detection: bool = not args.disable_loitering_detection

    print("=" * 80)
    print("SHADOW FLEET DETECTION")
    print("=" * 80)
    print("Input files:")
    for input_file in input_files:
        print(f"  - {input_file}")
    print(f"Chunk size: {chunk_size}")
    print(f"Workers:    {workers}")
    print(
        "Loitering detection: "
        f"{'enabled' if enable_loitering_detection else 'disabled (performance mode)'}"
    )
    print("=" * 80)

    pipeline_result = run_detection_pipeline(
        input_files=input_files,
        chunk_size=chunk_size,
        workers=workers,
        encoding=encoding,
        enable_loitering_detection=enable_loitering_detection,
        memory_output_file=memory_output_file,
        verbose=True,
    )

    global_summaries = pipeline_result.global_summaries
    ranked_scores = pipeline_result.ranked_scores
    loitering_events = pipeline_result.loitering_events
    memory_summary = pipeline_result.memory_summary

    write_results_csv(output_file, ranked_scores, global_summaries)
    print(f"\nResults written to: {output_file}")

    print(f"Memory profile written to: {pipeline_result.memory_output_file}")
    print(f"Worker memory profile written to: {pipeline_result.worker_memory_output_file}")
    print(f"Memory summary written to: {pipeline_result.memory_summary_output_file}")

    viz_d1 = get_top_teleportation_d1_vessel_visualization_data(global_summaries)
    if viz_d1 is not None:
        mmsi, rows = viz_d1
        write_teleportation_visualization_csv(
            teleportation_d1_viz_output,
            mmsi,
            rows,
        )
        print(f"Top D1 vessel (MMSI={mmsi}) written to {teleportation_d1_viz_output}")
    else:
        print("No D1 events detected")

    viz_d2 = get_top_teleportation_d2_vessel_visualization_data(global_summaries)
    if viz_d2 is not None:
        mmsi, rows = viz_d2
        write_teleportation_visualization_csv(
            teleportation_d2_viz_output,
            mmsi,
            rows,
        )
        print(f"Top D2 vessel (MMSI={mmsi}) written to {teleportation_d2_viz_output}")
    else:
        print("No D2 events detected")

    going_dark_viz_data = get_top_going_dark_vessel_visualization_data(global_summaries)
    if going_dark_viz_data is not None:
        top_dark_mmsi, going_dark_viz_rows = going_dark_viz_data
        write_going_dark_visualization_csv(
            going_dark_viz_output,
            top_dark_mmsi,
            going_dark_viz_rows,
        )
        print(
            f"Top Anomaly A vessel (MMSI={top_dark_mmsi}) map data written to: "
            f"{going_dark_viz_output}"
        )
    else:
        print("No going dark events detected; skipping top vessel map output.")

    if enable_loitering_detection:
        loitering_viz_data = get_top_loitering_vessel_visualization_data(global_summaries)
        if loitering_viz_data is not None:
            top_loitering_mmsi, loitering_viz_rows = loitering_viz_data
            write_loitering_visualization_csv(
                loitering_viz_output,
                top_loitering_mmsi,
                loitering_viz_rows,
            )
            print(
                f"Top Anomaly B vessel (MMSI={top_loitering_mmsi}) map data written to: "
                f"{loitering_viz_output}"
            )
        else:
            print("No loitering-transfer events detected; skipping top vessel map output.")
    else:
        print("Loitering-transfer detection disabled; skipping anomaly B final step.")

    print("\n" + "=" * 80)
    print("RESULT SUMMARY")
    print("=" * 80)
    print(f"Processed vessels:       {len(global_summaries)}")
    print(f"Processed valid records: {pipeline_result.processed_valid_records}")
    print(f"Completed chunks:        {pipeline_result.completed_chunks}")
    print(f"Total runtime:           {pipeline_result.total_runtime_sec:.2f} sec")
    print(f"Peak main RSS:           {memory_summary.peak_main_rss_mb:.2f} MB")
    print(f"Peak workers RSS:        {memory_summary.peak_workers_rss_mb:.2f} MB")
    print(f"Peak total RSS:          {memory_summary.peak_total_rss_mb:.2f} MB")
    print(f"Final memory RSS:        {pipeline_result.final_memory_rss_mb:.2f} MB")
    print(f"Loitering-transfer events detected: {len(loitering_events)}")
    print("=" * 80)

    print(f"Top {min(top_n, len(ranked_scores))} vessels by DFSI:")
    for rank, (mmsi, score) in enumerate(ranked_scores[:top_n], start=1):
        summary = global_summaries[mmsi]
        print(
            f"{rank:>2}. MMSI={mmsi} | "
            f"DFSI={score:.3f} | "
            f"max_gap_hours={summary.max_gap_hours:.2f} | "
            f"impossible_relocation_km_d2={summary.total_impossible_jump_km:.2f} | "
            f"draft_changes={summary.draft_change_count} | "
            f"going_dark={len(summary.going_dark_events)} | "
            f"teleportation={len(summary.teleportation_events)} | "
            f"D1={len(summary.teleportation_d1_events)} | "
            f"D2={len(summary.teleportation_d2_events)} | "
            f"B={len(summary.loitering_transfer_events)}"
        )


if __name__ == "__main__":
    main()
