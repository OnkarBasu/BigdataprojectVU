from __future__ import annotations

import os
import time
from dataclasses import dataclass

import psutil


BYTES_IN_MB = 1024 * 1024


@dataclass(slots=True, frozen=True)
class MemorySample:
    """
    Single memory usage sample collected during pipeline execution.

    Attributes:
        elapsed_time_sec: Seconds elapsed since the start of profiling.
        main_rss_mb: RSS memory used by the main process.
        workers_rss_mb: Sum of RSS memory used by child worker processes.
        total_rss_mb: Total RSS memory used by main process and workers.
        completed_chunks: Number of completed chunks at sampling time.
        processed_valid_records: Number of processed valid AIS records.
    """

    elapsed_time_sec: float
    main_rss_mb: float
    workers_rss_mb: float
    total_rss_mb: float
    completed_chunks: int
    processed_valid_records: int


def get_current_process() -> psutil.Process:
    """
    Return the current Python process object.

    Returns:
        psutil.Process object for the current process.
    """
    return psutil.Process(os.getpid())


def bytes_to_mb(value: int) -> float:
    """
    Convert bytes to megabytes.

    Args:
        value: Memory size in bytes.

    Returns:
        Memory size in megabytes.
    """
    return value / BYTES_IN_MB


def get_rss_mb(process: psutil.Process | None = None) -> float:
    """
    Get RSS memory usage of a process in megabytes.

    Args:
        process: Process object. If not provided, the current process is used.

    Returns:
        RSS memory usage in megabytes.
    """
    current_process = process or get_current_process()
    return bytes_to_mb(current_process.memory_info().rss)


def get_children_rss_mb(
    process: psutil.Process | None = None,
    recursive: bool = True,
) -> float:
    """
    Get the summed RSS memory usage of child processes in megabytes.

    Args:
        process: Parent process object. If not provided, the current process is used.
        recursive: Whether to include all descendants recursively.

    Returns:
        Total RSS memory usage of child processes in megabytes.
    """
    current_process = process or get_current_process()
    total_bytes = 0

    for child in current_process.children(recursive=recursive):
        try:
            total_bytes += child.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return bytes_to_mb(total_bytes)


def get_total_rss_mb(process: psutil.Process | None = None) -> float:
    """
    Get total RSS memory usage of main process and child processes.

    Args:
        process: Parent process object. If not provided, the current process is used.

    Returns:
        Total RSS memory usage in megabytes.
    """
    current_process = process or get_current_process()
    return get_rss_mb(current_process) + get_children_rss_mb(current_process)


def collect_memory_sample(
    start_time: float,
    completed_chunks: int,
    processed_valid_records: int,
    process: psutil.Process | None = None,
) -> MemorySample:
    """
    Collect a memory usage snapshot for the current pipeline state.

    Args:
        start_time: Pipeline start time from ``time.perf_counter()``.
        completed_chunks: Number of completed chunks.
        processed_valid_records: Number of processed valid AIS records.
        process: Parent process object. If not provided, the current process is used.

    Returns:
        MemorySample with current RAM usage metrics.
    """
    current_process = process or get_current_process()
    main_rss_mb = get_rss_mb(current_process)
    workers_rss_mb = get_children_rss_mb(current_process)
    total_rss_mb = main_rss_mb + workers_rss_mb

    return MemorySample(
        elapsed_time_sec=time.perf_counter() - start_time,
        main_rss_mb=main_rss_mb,
        workers_rss_mb=workers_rss_mb,
        total_rss_mb=total_rss_mb,
        completed_chunks=completed_chunks,
        processed_valid_records=processed_valid_records,
    )
