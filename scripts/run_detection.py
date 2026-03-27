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
    get_top_teleportation_vessel_visualization_data,
    merge_chunk_result_into_state,
)
from src.parallel import process_chunk, worker_init
from src.performance import (
    MemorySample,
    collect_memory_sample,
    get_current_process,
    get_rss_mb,
)
from src.streaming import stream_csv_files_in_chunks
from src.models import ChunkProcessingResult
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
        "--teleportation-viz-output",
        type=Path,
        default=Path("data/output/top_teleportation_vessel_map.csv"),
        help="Path to output CSV of top Anomaly D vessel coordinates for map visualization.",
    )
    parser.add_argument(
        "--going-dark-viz-output",
        type=Path,
        default=Path("data/output/top_going_dark_vessel_map.csv"),
        help="Path to output CSV of top Anomaly A vessel coordinates for map visualization.",
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
                "teleportation_d2_events",
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
                ]
            )


def write_memory_samples_csv(
    output_file: Path,
    memory_samples: list[MemorySample],
) -> None:
    """
    Write collected memory usage samples to a CSV file.

    Args:
        output_file: Path to the output CSV file.
        memory_samples: Collected memory samples during pipeline execution.
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        writer.writerow(
            [
                "elapsed_time_sec",
                "completed_chunks",
                "processed_valid_records",
                "main_rss_mb",
                "workers_rss_mb",
                "total_rss_mb",
            ]
        )

        for sample in memory_samples:
            writer.writerow(
                [
                    f"{sample.elapsed_time_sec:.6f}",
                    sample.completed_chunks,
                    sample.processed_valid_records,
                    f"{sample.main_rss_mb:.3f}",
                    f"{sample.workers_rss_mb:.3f}",
                    f"{sample.total_rss_mb:.3f}",
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
        "lat_origin",
        "lon_origin",
        "lat_destination",
        "lon_destination",
        "subtype",
        "implied_speed_knots",
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
                    row["subtype"],
                    f"{row['implied_speed_knots']:.3f}",
                    f"{row['distance_km']:.3f}",
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


def merge_ready_results(
    pending_results: dict[int, ChunkProcessingResult],
    next_chunk_id_to_merge: int,
    merge_state,
    port_zones,
    processed_valid_records: int,
    completed_chunks: int,
    memory_samples: list[MemorySample],
    start_time: float,
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
        memory_samples: Output list for collected memory samples.
        start_time: Pipeline start time.
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

        sample = collect_memory_sample(
            start_time=start_time,
            completed_chunks=completed_chunks,
            processed_valid_records=processed_valid_records,
            process=process,
        )
        memory_samples.append(sample)

        print(
            f"Chunk {chunk_result.chunk_id} processed in "
            f"{chunk_result.elapsed_time:.4f} sec | "
            f"Raw rows in chunk: {chunk_result.raw_row_count} | "
            f"Valid records in chunk: {chunk_result.valid_record_count} | "
            f"Processed valid records: {processed_valid_records} | "
            f"Completed chunks: {completed_chunks} | "
            f"Main RSS: {sample.main_rss_mb:.2f} MB | "
            f"Workers RSS: {sample.workers_rss_mb:.2f} MB | "
            f"Total RSS: {sample.total_rss_mb:.2f} MB"
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
    teleportation_viz_output: Path = args.teleportation_viz_output
    going_dark_viz_output: Path = args.going_dark_viz_output

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if workers <= 0:
        raise ValueError("workers must be greater than 0")

    for input_file in input_files:
        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

    start_time = time.perf_counter()
    process = get_current_process()
    memory_samples: list[MemorySample] = []

    print("=" * 80)
    print("SHADOW FLEET DETECTION")
    print("=" * 80)
    print("Input files:")
    for input_file in input_files:
        print(f"  - {input_file}")
    print(f"Chunk size: {chunk_size}")
    print(f"Workers:    {workers}")
    print("=" * 80)

    processed_valid_records = 0
    completed_chunks = 0
    merge_state = create_merge_state()
    port_zones = load_port_zones()

    tasks = stream_csv_files_in_chunks(
        file_paths=input_files,
        chunk_size=chunk_size,
        encoding=encoding,
    )

    pending_results: dict[int, ChunkProcessingResult] = {}
    next_chunk_id_to_merge = 1

    with Pool(processes=workers, initializer=worker_init) as pool:
        for chunk_result in pool.imap_unordered(process_chunk, tasks, chunksize=1):
            pending_results[chunk_result.chunk_id] = chunk_result

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
                memory_samples=memory_samples,
                start_time=start_time,
                process=process,
            )

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
        memory_samples=memory_samples,
        start_time=start_time,
        process=process,
    )

    if pending_results:
        missing = sorted(pending_results)
        raise RuntimeError(f"Unexpected pending results after pool completion: {missing}")

    global_summaries = merge_state.global_summaries
    dfsi_scores = calculate_all_dfsi(global_summaries)

    ranked_scores = sorted(
        dfsi_scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    write_results_csv(output_file, ranked_scores, global_summaries)
    print(f"\nResults written to: {output_file}")

    write_memory_samples_csv(memory_output_file, memory_samples)
    print(f"Memory profile written to: {memory_output_file}")

    viz_data = get_top_teleportation_vessel_visualization_data(global_summaries)
    if viz_data is not None:
        top_mmsi, viz_rows = viz_data
        write_teleportation_visualization_csv(
            teleportation_viz_output, top_mmsi, viz_rows
        )
        print(
            f"Top Anomaly D vessel (MMSI={top_mmsi}) map data written to: "
            f"{teleportation_viz_output}"
        )
    else:
        print(
            "No teleportation events detected; skipping top vessel map output."
        )

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

    total_time = time.perf_counter() - start_time
    final_memory_rss_mb = get_rss_mb(process)

    peak_main_rss_mb = max((sample.main_rss_mb for sample in memory_samples), default=0.0)
    peak_workers_rss_mb = max((sample.workers_rss_mb for sample in memory_samples), default=0.0)
    peak_total_rss_mb = max((sample.total_rss_mb for sample in memory_samples), default=0.0)

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
            f"D2={len(summary.teleportation_d2_events)}"
        )


if __name__ == "__main__":
    main()
