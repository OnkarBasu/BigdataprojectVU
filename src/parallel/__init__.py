"""
Parallel processing utilities for chunk-based AIS analytics.
"""

from .worker_pool import process_chunk, worker_init

__all__ = [
    "process_chunk",
    "worker_init",
]
