from __future__ import annotations

import time
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path

from src.anomaly_detection import (
    calculate_all_dfsi,
    create_merge_state,
    finalize_loitering_detection,
    merge_chunk_result_into_state,
)
from src.models import ChunkProcessingResult
from src.parallel import process_chunk, worker_init
from src.performance import get_current_process, get_rss_mb
from src.performance.memory_profile import MemoryMonitor, MemorySummary
from src.streaming import stream_csv_files_in_chunks
from src.utils import load_port_zones


@dataclass(slots=True, frozen=True)
class DetectionPipelineResult:
    global_summaries: dict
    dfsi_scores: dict[int, float]
    ranked_scores: list[tuple[int, float]]
    loitering_events: list
    processed_valid_records: int
    completed_chunks: int
    total_runtime_sec: float
    final_memory_rss_mb: float
    memory_output_file: Path
    worker_memory_output_file: Path
    memory_summary_output_file: Path
    memory_summary: MemorySummary


def merge_ready_results(
    pending_results: dict[int, ChunkProcessingResult],
    next_chunk_id_to_merge: int,
    merge_state,
    port_zones,
    processed_valid_records: int,
    completed_chunks: int,
    process,
    verbose: bool = True,
) -> tuple[int, int, int]:
    """
    Merge all consecutively available chunk results in strict chunk order.
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

        if verbose:
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


def run_detection_pipeline(
    input_files: list[Path],
    chunk_size: int,
    workers: int,
    encoding: str = "utf-8",
    enable_loitering_detection: bool = True,
    memory_output_file: Path = Path("data/output/memory_profile.csv"),
    verbose: bool = True,
) -> DetectionPipelineResult:
    """
    Run the full streaming + multiprocessing detection pipeline and return
    structured results without exporting final anomaly CSV files.
    """
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
                verbose=verbose,
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
        verbose=verbose,
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

    memory_monitor.take_sample(event_label="before_final_save")
    memory_monitor.stop()

    worker_memory_output_file = memory_output_file.with_name("worker_memory_profile.csv")
    memory_summary_output_file = memory_output_file.with_name("memory_summary.csv")

    memory_monitor.save_aggregated_csv(memory_output_file)
    memory_monitor.save_worker_csv(worker_memory_output_file)
    memory_monitor.save_summary_csv(memory_summary_output_file)

    total_time = time.perf_counter() - start_time
    final_memory_rss_mb = get_rss_mb(process)
    memory_summary = memory_monitor.build_summary()

    return DetectionPipelineResult(
        global_summaries=global_summaries,
        dfsi_scores=dfsi_scores,
        ranked_scores=ranked_scores,
        loitering_events=loitering_events,
        processed_valid_records=processed_valid_records,
        completed_chunks=completed_chunks,
        total_runtime_sec=total_time,
        final_memory_rss_mb=final_memory_rss_mb,
        memory_output_file=memory_output_file,
        worker_memory_output_file=worker_memory_output_file,
        memory_summary_output_file=memory_summary_output_file,
        memory_summary=memory_summary,
    )
