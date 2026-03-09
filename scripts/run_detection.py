from __future__ import annotations

import csv
import argparse
import time
from multiprocessing import Pool
from pathlib import Path

from src.anomaly_detection import calculate_all_dfsi, merge_chunk_results
from src.parallel import process_chunk
from src.streaming import stream_csv_files_in_chunks
from src.performance import (
    collect_memory_sample,
    get_current_process,
    get_rss_mb,
    MemorySample
)


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
        default=50_000,
        help="Number of valid AIS records per chunk.",
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
    return parser


def write_results_csv(
    output_file: Path,
    ranked_scores: list[tuple[int, float]],
    global_summaries: dict,
) -> None:
    """
    Write vessel DFSI results to a CSV file.
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
                "impossible_jump_km",
                "draft_change_count",
                "going_dark_events",
                "draft_change_events",
                "teleportation_events",
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


def main() -> None:
    """
    Run the full anomaly-detection pipeline on one or more AIS CSV files.
    """
    parser = build_argument_parser()
    args = parser.parse_args()

    input_files: list[Path] = args.input_files
    output_file: Path = args.output
    memory_output_file: Path = args.memory_output
    chunk_size: int = args.chunk_size
    workers: int = args.workers
    encoding: str = args.encoding
    top_n: int = args.top

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if workers <= 0:
        raise ValueError("workers must be greater than 0")

    for input_file in input_files:
        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

    start_time = time.perf_counter()
    process = get_current_process()

    memory_samples = []

    print("=" * 80)
    print("SHADOW FLEET DETECTION")
    print("=" * 80)
    print("Input files:")
    for input_file in input_files:
        print(f"  - {input_file}")
    print(f"Chunk size: {chunk_size}")
    print(f"Workers:    {workers}")
    print("=" * 80)

    chunk_results = []
    processed_valid_records = 0
    completed_chunks = 0

    tasks = stream_csv_files_in_chunks(
        file_paths=input_files,
        chunk_size=chunk_size,
        encoding=encoding,
    )

    with Pool(processes=workers) as pool:
        for chunk_result in pool.imap_unordered(process_chunk, tasks, chunksize=1):
            chunk_results.append(chunk_result)
            processed_valid_records += chunk_result.row_count
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
                f"Valid records in chunk: {chunk_result.row_count} | "
                f"Processed valid records: {processed_valid_records} | "
                f"Completed chunks: {completed_chunks} | "
                f"Main RSS: {sample.main_rss_mb:.2f} MB | "
                f"Workers RSS: {sample.workers_rss_mb:.2f} MB | "
                f"Total RSS: {sample.total_rss_mb:.2f} MB"
            )

    global_summaries = merge_chunk_results(chunk_results)
    dfsi_scores = calculate_all_dfsi(global_summaries)

    ranked_scores = sorted(
        dfsi_scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    total_time = time.perf_counter() - start_time

    peak_main_rss_mb = max((sample.main_rss_mb for sample in memory_samples), default=0.0)
    peak_workers_rss_mb = max((sample.workers_rss_mb for sample in memory_samples), default=0.0)
    peak_total_rss_mb = max((sample.total_rss_mb for sample in memory_samples), default=0.0)
    final_memory_rss_mb = get_rss_mb(process)

    # write_results_csv(output_file, ranked_scores, global_summaries)
    print(f"\nResults written to: {output_file}")

    write_memory_samples_csv(memory_output_file, memory_samples)
    print(f"Memory profile written to: {memory_output_file}")

    print("\n" + "=" * 80)
    print("RESULT SUMMARY")
    print("=" * 80)
    print(f"Processed vessels:       {len(global_summaries)}")
    print(f"Processed valid records: {processed_valid_records}")
    print(f"Completed chunks:        {completed_chunks}")
    print(f"Total runtime:           {total_time:.2f} sec")
    print(f"Peak main RSS:          {peak_main_rss_mb:.2f} MB")
    print(f"Peak workers RSS:       {peak_workers_rss_mb:.2f} MB")
    print(f"Peak total RSS:         {peak_total_rss_mb:.2f} MB")
    print(f"Final memory RSS:       {final_memory_rss_mb:.2f} MB")
    print("=" * 80)

    print(f"Top {min(top_n, len(ranked_scores))} vessels by DFSI:")
    for rank, (mmsi, score) in enumerate(ranked_scores[:top_n], start=1):
        summary = global_summaries[mmsi]
        print(
            f"{rank:>2}. MMSI={mmsi} | "
            f"DFSI={score:.3f} | "
            f"max_gap_hours={summary.max_gap_hours:.2f} | "
            f"impossible_jump_km={summary.total_impossible_jump_km:.2f} | "
            f"draft_changes={summary.draft_change_count} | "
            f"going_dark={len(summary.going_dark_events)} | "
            f"teleportation={len(summary.teleportation_events)}"
        )


if __name__ == "__main__":
    main()
