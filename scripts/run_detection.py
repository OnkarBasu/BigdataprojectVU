from __future__ import annotations

import argparse
import csv
import time
from multiprocessing import Pool
from pathlib import Path

from src.anomaly_detection import (
    calculate_all_dfsi,
    create_merge_state,
    get_top_going_dark_vessel_visualization_data,
    merge_chunk_result_into_state,
    calculate_d1_episode_count,
    finalize_loitering_detection
)
from src.anomaly_detection.rules import (
    get_top_teleportation_d1_vessel_visualization_data,
    get_top_teleportation_d2_vessel_visualization_data
)
from src.parallel import process_chunk, worker_init
from src.performance import get_current_process, get_rss_mb
from src.performance.memory_profile import MemoryMonitor
from src.streaming import stream_csv_files_in_chunks
from src.models import ChunkProcessingResult
from src.models.events import LoiteringTransferEvent
from src.utils import load_port_zones


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
                    len(summary.teleportation_d2_events),
                    calculate_d1_episode_count(summary),
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
    Write the top Anomaly D vessel's teleportation coordinates for map visualization.

    Each row represents one impossible jump (origin -> destination) for the
    vessel with the highest number of teleportation events.

    Args:
        output_file: Path to the output CSV file.
        mmsi: Vessel MMSI identifier.
        rows: List of dicts with lat_origin, lon_origin, lat_destination,
            lon_destination, event_index, implied_speed_knots, distance_km.
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
    Write the top Anomaly A vessel's going dark coordinates for map visualization.

    Each row represents one going dark event (origin -> destination) for the
    vessel with the highest number of going dark events.

    Args:
        output_file: Path to the output CSV file.
        mmsi: Vessel MMSI identifier.
        rows: List of dicts with lat_origin, lon_origin, lat_destination,
            lon_destination, event_index, gap_hours, distance_km.
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
    """Write the top Anomaly B vessel's paired coordinates for map visualization."""
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


def attach_loitering_events_to_summaries(
    global_summaries: dict,
    loitering_events: list[LoiteringTransferEvent],
) -> None:
    """Attach each anomaly B event to both vessels that participate in it."""
    for event in loitering_events:
        summary_a = global_summaries.get(event.mmsi_a)
        if summary_a is not None:
            summary_a.loitering_transfer_events.append(event)

        summary_b = global_summaries.get(event.mmsi_b)
        if summary_b is not None and event.mmsi_b != event.mmsi_a:
            summary_b.loitering_transfer_events.append(event)


def merge_ready_results(
    pending_results: dict[int, ChunkProcessingResult],
    next_chunk_id_to_merge: int,
    merge_state,
    port_zones,
    processed_valid_records: int,
    completed_chunks: int,
    process,
) -> tuple[int, int, int]:
    """
    Merge all consecutively available chunk results in strict chunk order.

    Even if worker results arrive out of order, global merging must stay
    ordered because cross-chunk anomaly detection depends on chunk sequence.

    Args:
        pending_results: Buffer of completed worker results keyed by chunk ID.
        next_chunk_id_to_merge: Next chunk ID expected by the ordered reducer.
        merge_state: Global incremental merge state.
        port_zones: Loaded port zones used for boundary anomaly checks.
        processed_valid_records: Accumulated count of valid records merged so far.
        completed_chunks: Number of merged chunks so far.
        process: Current main process handle.

    Returns:
        Tuple of updated:
            - next_chunk_id_to_merge
            - processed_valid_records
            - completed_chunks
    """
    while next_chunk_id_to_merge in pending_results:
        chunk_result = pending_results.pop(next_chunk_id_to_merge)

        merge_chunk_result_into_state(
            merge_state=merge_state,
            chunk_result=chunk_result,
            port_zones=port_zones,
        )

        processed_valid_records += chunk_result.valid_record_count
        completed_chunks += 1

        print(
            f"Chunk {chunk_result.chunk_id} processed in "
            f"{chunk_result.elapsed_time:.4f} sec | "
            f"Raw rows in chunk: {chunk_result.raw_row_count} | "
            f"Valid records in chunk: {chunk_result.valid_record_count} | "
            f"Processed valid records: {processed_valid_records} | "
            f"Completed chunks: {completed_chunks} | "
            f"Main RSS: {get_rss_mb(process):.2f} MB"
        )

        next_chunk_id_to_merge += 1

    return next_chunk_id_to_merge, processed_valid_records, completed_chunks


def main() -> None:
    """
    Run the full anomaly-detection pipeline on one or more AIS CSV files.
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

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if workers <= 0:
        raise ValueError("workers must be greater than 0")

    for input_file in input_files:
        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

    start_time = time.perf_counter()
    process = get_current_process()

    completed_chunks = 0
    processed_valid_records = 0

    def get_progress() -> tuple[int, int]:
        return completed_chunks, processed_valid_records

    memory_monitor = MemoryMonitor(
        sampling_interval_sec=0.25,
        progress_callback=get_progress,
        track_per_worker=True,
    )

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

    merge_state = create_merge_state(
        enable_loitering_detection=enable_loitering_detection,
    )
    port_zones = load_port_zones()

    tasks = stream_csv_files_in_chunks(
        file_paths=input_files,
        chunk_size=chunk_size,
        encoding=encoding,
    )

    pending_results: dict[int, ChunkProcessingResult] = {}
    next_chunk_id_to_merge = 1

    memory_monitor.start()
    memory_monitor.take_sample(event_label="pipeline_started")

    with Pool(processes=workers, initializer=worker_init) as pool:
        for chunk_result in pool.imap_unordered(process_chunk, tasks, chunksize=1):
            pending_results[chunk_result.chunk_id] = chunk_result
            memory_monitor.take_sample(event_label="worker_result_received")

            (
                next_chunk_id_to_merge,
                processed_valid_records,
                completed_chunks,
            ) = merge_ready_results(
                pending_results=pending_results,
                next_chunk_id_to_merge=next_chunk_id_to_merge,
                merge_state=merge_state,
                port_zones=port_zones,
                processed_valid_records=processed_valid_records,
                completed_chunks=completed_chunks,
                process=process,
            )
            memory_monitor.take_sample(event_label="after_merge")

    (
        next_chunk_id_to_merge,
        processed_valid_records,
        completed_chunks,
    ) = merge_ready_results(
        pending_results=pending_results,
        next_chunk_id_to_merge=next_chunk_id_to_merge,
        merge_state=merge_state,
        port_zones=port_zones,
        processed_valid_records=processed_valid_records,
        completed_chunks=completed_chunks,
        process=process,
    )
    memory_monitor.take_sample(event_label="after_final_merge")

    if pending_results:
        missing = sorted(pending_results)
        raise RuntimeError(f"Unexpected pending results after pool completion: {missing}")

    global_summaries = merge_state.global_summaries

    if enable_loitering_detection:
        loitering_events = finalize_loitering_detection(merge_state)
    else:
        loitering_events = []

    dfsi_scores = calculate_all_dfsi(global_summaries)

    ranked_scores = sorted(
        dfsi_scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    write_results_csv(output_file, ranked_scores, global_summaries)
    print(f"\nResults written to: {output_file}")

    memory_monitor.take_sample(event_label="before_final_save")
    memory_monitor.stop()

    memory_monitor.save_aggregated_csv(memory_output_file)
    worker_memory_output_file = memory_output_file.with_name("worker_memory_profile.csv")
    memory_summary_output_file = memory_output_file.with_name("memory_summary.csv")
    memory_monitor.save_worker_csv(worker_memory_output_file)
    memory_monitor.save_summary_csv(memory_summary_output_file)

    print(f"Memory profile written to: {memory_output_file}")
    print(f"Worker memory profile written to: {worker_memory_output_file}")
    print(f"Memory summary written to: {memory_summary_output_file}")

    # D1
    viz_d1 = get_top_teleportation_d1_vessel_visualization_data(global_summaries)
    if viz_d1 is not None:
        mmsi, rows = viz_d1
        write_teleportation_visualization_csv(
            teleportation_d1_viz_output, mmsi, rows
        )
        print(f"Top D1 vessel (MMSI={mmsi}) written to {teleportation_d1_viz_output}")
    else:
        print("No D1 events detected")

    # D2
    viz_d2 = get_top_teleportation_d2_vessel_visualization_data(global_summaries)
    if viz_d2 is not None:
        mmsi, rows = viz_d2
        write_teleportation_visualization_csv(
            teleportation_d2_viz_output, mmsi, rows
        )
        print(f"Top D2 vessel (MMSI={mmsi}) written to {teleportation_d2_viz_output}")
    else:
        print("No D2 events detected")

    going_dark_viz_data = get_top_going_dark_vessel_visualization_data(global_summaries)
    if going_dark_viz_data is not None:
        top_dark_mmsi, going_dark_viz_rows = going_dark_viz_data
        write_going_dark_visualization_csv(
            going_dark_viz_output, top_dark_mmsi, going_dark_viz_rows
        )
        print(
            f"Top Anomaly A vessel (MMSI={top_dark_mmsi}) map data written to: "
            f"{going_dark_viz_output}"
        )
    else:
        print(
            "No going dark events detected; skipping top vessel map output."
        )

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
            print(
                "No loitering-transfer events detected; skipping top vessel map output."
            )
    else:
        print(
            "Loitering-transfer detection disabled; skipping anomaly B final step."
        )

    total_time = time.perf_counter() - start_time
    final_memory_rss_mb = get_rss_mb(process)
    memory_summary = memory_monitor.build_summary()

    peak_main_rss_mb = memory_summary.peak_main_rss_mb
    peak_workers_rss_mb = memory_summary.peak_workers_rss_mb
    peak_total_rss_mb = memory_summary.peak_total_rss_mb

    print("\n" + "=" * 80)
    print("RESULT SUMMARY")
    print("=" * 80)
    print(f"Processed vessels:       {len(global_summaries)}")
    print(f"Processed valid records: {processed_valid_records}")
    print(f"Completed chunks:        {completed_chunks}")
    print(f"Total runtime:           {total_time:.2f} sec")
    print(f"Peak main RSS:           {peak_main_rss_mb:.2f} MB")
    print(f"Peak workers RSS:        {peak_workers_rss_mb:.2f} MB")
    print(f"Peak total RSS:          {peak_total_rss_mb:.2f} MB")
    print(f"Final memory RSS:        {final_memory_rss_mb:.2f} MB")
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
