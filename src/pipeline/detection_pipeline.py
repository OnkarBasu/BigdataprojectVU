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
from src.config import (
    DEFAULT_DETECTION_CONFIG,
    DEFAULT_RUN_CONFIG,
    DetectionConfig,
    RunConfig,
)
from src.models import ChunkProcessingResult
from src.parallel import process_chunk, worker_init
from src.performance import get_current_process, get_rss_mb
from src.performance.memory_profile import MemoryMonitor, MemorySummary
from src.streaming import stream_csv_files_in_chunks
from src.utils import load_port_zones
from src.output import write_pipeline_profile_csv


COLUMNS_CONSOLE_OUTPUT = {
    "Chunk ID": 8,
    "Work s": 9,
    "QWait s": 9,
    "Merge s": 9,
    "Raw": 8,
    "Valid": 8,
    "Total": 10,
    "AC Samp": 8,
    "B Samp": 8,
    "Pend": 6,
    "Done": 6,
    "Main RSS MB": 9,
}


@dataclass(slots=True, frozen=True)
class ChunkMergeProfile:
    chunk_id: int
    raw_row_count: int
    valid_record_count: int
    vessel_count: int
    ac_sampled_record_count: int
    loitering_sampled_record_count: int
    worker_elapsed_sec: float
    queue_wait_sec: float
    merge_elapsed_sec: float
    pending_results_before_merge: int
    pending_results_after_merge: int
    main_rss_mb_after_merge: float


@dataclass(slots=True, frozen=True)
class DetectionPipelineProfile:
    chunk_profiles: list[ChunkMergeProfile]
    total_worker_elapsed_sec: float
    total_queue_wait_sec: float
    total_merge_elapsed_sec: float
    max_queue_wait_sec: float
    max_merge_elapsed_sec: float
    max_pending_results: int
    finalize_loitering_elapsed_sec: float
    dfsi_elapsed_sec: float
    profile_output_file: Path


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
    pipeline_profile: DetectionPipelineProfile


def _build_loitering_state_snapshot(merge_state) -> tuple[int, int, int]:
    loitering_state = merge_state.loitering_state
    if loitering_state is None:
        return 0, 0, 0

    return (
        len(loitering_state.pending_bucket_points),
        len(loitering_state.active_pairs),
        len(loitering_state.finished_events),
    )


def merge_ready_results(
    pending_results: dict[int, tuple[ChunkProcessingResult, float]],
    next_chunk_id_to_merge: int,
    merge_state,
    port_zones,
    processed_valid_records: int,
    completed_chunks: int,
    process,
    chunk_profiles: list[ChunkMergeProfile],
    max_pending_results_seen: int,
    verbose: bool = True,
) -> tuple[int, int, int, int]:
    """
    Merge all consecutively available chunk results in strict chunk order.
    """
    while next_chunk_id_to_merge in pending_results:
        pending_count_before_merge = len(pending_results)
        max_pending_results_seen = max(max_pending_results_seen, pending_count_before_merge)

        chunk_result, received_at = pending_results.pop(next_chunk_id_to_merge)
        merge_started_at = time.perf_counter()
        queue_wait_sec = merge_started_at - received_at

        merge_chunk_result_into_state(
            merge_state=merge_state,
            chunk_result=chunk_result,
            port_zones=port_zones,
        )

        merge_elapsed_sec = time.perf_counter() - merge_started_at
        main_rss_mb_after_merge = get_rss_mb(process)

        ac_sampled_record_count = sum(
            len(summary.ac_sampled_records)
            for summary in chunk_result.vessel_summaries.values()
        )

        loitering_sampled_record_count = sum(
            len(summary.loitering_sampled_records)
            for summary in chunk_result.vessel_summaries.values()
        )

        chunk_profiles.append(
            ChunkMergeProfile(
                chunk_id=chunk_result.chunk_id,
                vessel_count=len(chunk_result.vessel_summaries),
                worker_elapsed_sec=chunk_result.elapsed_time,
                queue_wait_sec=queue_wait_sec,
                merge_elapsed_sec=merge_elapsed_sec,
                raw_row_count=chunk_result.raw_row_count,
                valid_record_count=chunk_result.valid_record_count,
                ac_sampled_record_count=ac_sampled_record_count,
                loitering_sampled_record_count=loitering_sampled_record_count,
                pending_results_before_merge=pending_count_before_merge,
                pending_results_after_merge=len(pending_results),
                main_rss_mb_after_merge=main_rss_mb_after_merge,
            )
        )

        processed_valid_records += chunk_result.valid_record_count
        completed_chunks += 1

        header_str = " | ".join(f"{name:<{width}}" for name, width in COLUMNS_CONSOLE_OUTPUT.items())
        separator = "-" * len(header_str)

        if verbose:
            if (completed_chunks - 1) % 5 == 0:
                print(f"{separator}")
                print(header_str)
                print(separator)

            profile = chunk_profiles[-1]

            print(
                f"{chunk_result.chunk_id:<{COLUMNS_CONSOLE_OUTPUT['Chunk ID']}} | "
                f"{chunk_result.elapsed_time:<{COLUMNS_CONSOLE_OUTPUT['Work s']}.4f} | "
                f"{queue_wait_sec:<{COLUMNS_CONSOLE_OUTPUT['QWait s']}.4f} | "
                f"{merge_elapsed_sec:<{COLUMNS_CONSOLE_OUTPUT['Merge s']}.4f} | "
                f"{chunk_result.raw_row_count:<{COLUMNS_CONSOLE_OUTPUT['Raw']}} | "
                f"{chunk_result.valid_record_count:<{COLUMNS_CONSOLE_OUTPUT['Valid']}} | "
                f"{processed_valid_records:<{COLUMNS_CONSOLE_OUTPUT['Total']}} | "
                f"{profile.ac_sampled_record_count:<{COLUMNS_CONSOLE_OUTPUT['AC Samp']}} | "
                f"{profile.loitering_sampled_record_count:<{COLUMNS_CONSOLE_OUTPUT['B Samp']}} | "
                f"{pending_count_before_merge:<{COLUMNS_CONSOLE_OUTPUT['Pend']}} | "
                f"{completed_chunks:<{COLUMNS_CONSOLE_OUTPUT['Done']}} | "
                f"{main_rss_mb_after_merge:<{COLUMNS_CONSOLE_OUTPUT['Main RSS MB']}.2f}"
            )

        next_chunk_id_to_merge += 1

    return (
        next_chunk_id_to_merge,
        processed_valid_records,
        completed_chunks,
        max_pending_results_seen,
    )


def run_detection_pipeline(
    input_files: list[Path],
    run_config: RunConfig = DEFAULT_RUN_CONFIG,
    detection_config: DetectionConfig = DEFAULT_DETECTION_CONFIG,
) -> DetectionPipelineResult:
    """
    Run the full streaming + multiprocessing detection pipeline and return
    structured results without exporting final anomaly CSV files.
    """
    if run_config.chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if run_config.workers <= 0:
        raise ValueError("workers must be greater than 0")

    for input_file in input_files:
        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

    start_time = time.perf_counter()
    process = get_current_process()

    completed_chunks = 0
    processed_valid_records = 0
    chunk_profiles: list[ChunkMergeProfile] = []
    max_pending_results_seen = 0

    def get_progress() -> tuple[int, int]:
        return completed_chunks, processed_valid_records

    memory_monitor = MemoryMonitor(
        sampling_interval_sec=0.25,
        progress_callback=get_progress,
        track_per_worker=True,
    )

    merge_state = create_merge_state(
        detection_config=detection_config,
        enable_loitering_detection=run_config.enable_loitering_detection,
    )
    port_zones = load_port_zones()

    tasks = stream_csv_files_in_chunks(
        file_paths=input_files,
        chunk_size=run_config.chunk_size,
        encoding=run_config.encoding,
    )

    pending_results: dict[int, tuple[ChunkProcessingResult, float]] = {}
    next_chunk_id_to_merge = 1

    memory_monitor.start()
    memory_monitor.take_sample(event_label="pipeline_started")

    with Pool(
        processes=run_config.workers,
        initializer=worker_init,
        initargs=(detection_config,),
    ) as pool:
        for chunk_result in pool.imap_unordered(process_chunk, tasks, chunksize=1):
            pending_results[chunk_result.chunk_id] = (chunk_result, time.perf_counter())
            max_pending_results_seen = max(max_pending_results_seen, len(pending_results))
            memory_monitor.take_sample(event_label="worker_result_received")

            (
                next_chunk_id_to_merge,
                processed_valid_records,
                completed_chunks,
                max_pending_results_seen,
            ) = merge_ready_results(
                pending_results=pending_results,
                next_chunk_id_to_merge=next_chunk_id_to_merge,
                merge_state=merge_state,
                port_zones=port_zones,
                processed_valid_records=processed_valid_records,
                completed_chunks=completed_chunks,
                process=process,
                chunk_profiles=chunk_profiles,
                max_pending_results_seen=max_pending_results_seen,
                verbose=run_config.verbose,
            )
            memory_monitor.take_sample(event_label="after_merge")

    (
        next_chunk_id_to_merge,
        processed_valid_records,
        completed_chunks,
        max_pending_results_seen,
    ) = merge_ready_results(
        pending_results=pending_results,
        next_chunk_id_to_merge=next_chunk_id_to_merge,
        merge_state=merge_state,
        port_zones=port_zones,
        processed_valid_records=processed_valid_records,
        completed_chunks=completed_chunks,
        process=process,
        chunk_profiles=chunk_profiles,
        max_pending_results_seen=max_pending_results_seen,
        verbose=run_config.verbose,
    )
    memory_monitor.take_sample(event_label="after_final_merge")

    if pending_results:
        missing = sorted(pending_results)
        raise RuntimeError(f"Unexpected pending results after pool completion: {missing}")

    global_summaries = merge_state.global_summaries

    finalize_loitering_started_at = time.perf_counter()
    if run_config.enable_loitering_detection:
        loitering_events = finalize_loitering_detection(merge_state)
    else:
        loitering_events = []
    finalize_loitering_elapsed_sec = time.perf_counter() - finalize_loitering_started_at

    dfsi_started_at = time.perf_counter()
    dfsi_scores = calculate_all_dfsi(global_summaries)
    ranked_scores = sorted(
        dfsi_scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    dfsi_elapsed_sec = time.perf_counter() - dfsi_started_at

    memory_monitor.take_sample(event_label="before_final_save")
    memory_monitor.stop()

    worker_memory_output_file = run_config.memory_output_file.with_name("worker_memory_profile.csv")
    memory_summary_output_file = run_config.memory_output_file.with_name("memory_summary.csv")
    profile_output_file = run_config.memory_output_file.with_name("pipeline_profile.csv")

    memory_monitor.save_aggregated_csv(run_config.memory_output_file)
    memory_monitor.save_worker_csv(worker_memory_output_file)
    memory_monitor.save_summary_csv(memory_summary_output_file)
    write_pipeline_profile_csv(profile_output_file, chunk_profiles)

    total_time = time.perf_counter() - start_time
    final_memory_rss_mb = get_rss_mb(process)
    memory_summary = memory_monitor.build_summary()

    total_worker_elapsed_sec = sum(profile.worker_elapsed_sec for profile in chunk_profiles)
    total_queue_wait_sec = sum(profile.queue_wait_sec for profile in chunk_profiles)
    total_merge_elapsed_sec = sum(profile.merge_elapsed_sec for profile in chunk_profiles)
    max_queue_wait_sec = max((profile.queue_wait_sec for profile in chunk_profiles), default=0.0)
    max_merge_elapsed_sec = max((profile.merge_elapsed_sec for profile in chunk_profiles), default=0.0)

    pipeline_profile = DetectionPipelineProfile(
        chunk_profiles=chunk_profiles,
        total_worker_elapsed_sec=total_worker_elapsed_sec,
        total_queue_wait_sec=total_queue_wait_sec,
        total_merge_elapsed_sec=total_merge_elapsed_sec,
        max_queue_wait_sec=max_queue_wait_sec,
        max_merge_elapsed_sec=max_merge_elapsed_sec,
        max_pending_results=max_pending_results_seen,
        finalize_loitering_elapsed_sec=finalize_loitering_elapsed_sec,
        dfsi_elapsed_sec=dfsi_elapsed_sec,
        profile_output_file=profile_output_file,
    )

    if run_config.verbose:
        print("\nPIPELINE PROFILING SUMMARY")
        print("-" * 80)
        print(f"Profile CSV:              {profile_output_file}")
        print(f"Chunks profiled:          {len(chunk_profiles)}")
        print(f"Total worker time sum:    {total_worker_elapsed_sec:.2f} sec")
        print(f"Total queue wait sum:     {total_queue_wait_sec:.2f} sec")
        print(f"Total merge time sum:     {total_merge_elapsed_sec:.2f} sec")
        print(f"Max queue wait per chunk: {max_queue_wait_sec:.2f} sec")
        print(f"Max merge per chunk:      {max_merge_elapsed_sec:.2f} sec")
        print(f"Max pending results:      {max_pending_results_seen}")
        print(f"Finalize loitering:       {finalize_loitering_elapsed_sec:.2f} sec")
        print(f"DFSI calculation:         {dfsi_elapsed_sec:.2f} sec")
        print("-" * 80)

    return DetectionPipelineResult(
        global_summaries=global_summaries,
        dfsi_scores=dfsi_scores,
        ranked_scores=ranked_scores,
        loitering_events=loitering_events,
        processed_valid_records=processed_valid_records,
        completed_chunks=completed_chunks,
        total_runtime_sec=total_time,
        final_memory_rss_mb=final_memory_rss_mb,
        memory_output_file=run_config.memory_output_file,
        worker_memory_output_file=worker_memory_output_file,
        memory_summary_output_file=memory_summary_output_file,
        memory_summary=memory_summary,
        pipeline_profile=pipeline_profile,
    )
