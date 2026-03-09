from __future__ import annotations

import os

import psutil


BYTES_IN_MB = 1024 * 1024


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
    Get resident memory size (RSS) of a process in megabytes.

    RSS is the amount of non-swapped physical memory currently used
    by the process.

    Args:
        process: Process object. If not provided, the current process is used.

    Returns:
        RSS memory usage in megabytes.
    """
    current_process = process or get_current_process()
    return bytes_to_mb(current_process.memory_info().rss)

