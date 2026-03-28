from __future__ import annotations

import csv
import os
import threading
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Callable

import psutil


BYTES_IN_MB = 1024 * 1024


@dataclass(slots=True, frozen=True)
class MemorySample:
    """
    Aggregated memory usage sample for the whole pipeline.

    Attributes:
        elapsed_time_sec: Seconds elapsed since profiling start.
        sample_kind: Either "timer" or "event".
        event_label: Optional label for event-driven samples.
        main_rss_mb: RSS memory of the main process.
        workers_rss_mb: Summed RSS memory of all worker child processes.
        total_rss_mb: Total RSS memory (main + workers).
        peak_worker_rss_mb: Maximum RSS among currently alive worker processes.
        num_alive_workers: Number of currently alive worker child processes.
        completed_chunks: Number of completed chunks reported by callback.
        processed_valid_records: Number of processed valid records reported by callback.
    """

    elapsed_time_sec: float
    sample_kind: str
    event_label: str
    main_rss_mb: float
    workers_rss_mb: float
    total_rss_mb: float
    peak_worker_rss_mb: float
    num_alive_workers: int
    completed_chunks: int
    processed_valid_records: int


@dataclass(slots=True, frozen=True)
class WorkerMemorySample:
    """
    Per-worker memory usage sample.

    Attributes:
        elapsed_time_sec: Seconds elapsed since profiling start.
        sample_kind: Either "timer" or "event".
        event_label: Optional label for event-driven samples.
        pid: Worker process PID.
        worker_index: Stable index assigned by PID ordering within current sample.
        rss_mb: RSS memory of the worker process.
    """

    elapsed_time_sec: float
    sample_kind: str
    event_label: str
    pid: int
    worker_index: int
    rss_mb: float


@dataclass(slots=True, frozen=True)
class MemorySummary:
    """Final summary statistics for a profiling session."""

    duration_sec: float
    peak_main_rss_mb: float
    peak_workers_rss_mb: float
    peak_total_rss_mb: float
    peak_single_worker_rss_mb: float
    max_alive_workers: int
    total_samples: int
    total_worker_samples: int


def bytes_to_mb(value: int) -> float:
    """Convert bytes to megabytes."""
    return value / BYTES_IN_MB


def get_current_process() -> psutil.Process:
    """Return the current Python process object."""
    return psutil.Process(os.getpid())


def _safe_rss_mb(process: psutil.Process) -> float | None:
    """Safely return RSS memory of a process in MB."""
    try:
        return bytes_to_mb(process.memory_info().rss)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def get_rss_mb(process: psutil.Process | None = None) -> float:
    """Get RSS memory usage of a process in megabytes."""
    current_process = process or get_current_process()
    rss_mb = _safe_rss_mb(current_process)
    return rss_mb if rss_mb is not None else 0.0


def get_child_processes(
    process: psutil.Process | None = None,
    recursive: bool = True,
) -> list[psutil.Process]:
    """Return currently alive child processes."""
    current_process = process or get_current_process()

    try:
        children = current_process.children(recursive=recursive)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return []

    alive_children: list[psutil.Process] = []
    for child in children:
        try:
            if child.is_running():
                alive_children.append(child)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return alive_children


def get_children_rss_details(
    process: psutil.Process | None = None,
    recursive: bool = True,
) -> list[tuple[int, float]]:
    """Return per-child RSS details as (pid, rss_mb)."""
    current_process = process or get_current_process()
    details: list[tuple[int, float]] = []

    for child in get_child_processes(current_process, recursive=recursive):
        rss_mb = _safe_rss_mb(child)
        if rss_mb is None:
            continue
        details.append((child.pid, rss_mb))

    details.sort(key=lambda item: item[0])
    return details


def get_children_rss_mb(
    process: psutil.Process | None = None,
    recursive: bool = True,
) -> float:
    """Get the summed RSS memory usage of child processes in megabytes."""
    return sum(rss_mb for _, rss_mb in get_children_rss_details(process, recursive))


def get_total_rss_mb(process: psutil.Process | None = None) -> float:
    """Get total RSS memory usage of main process and child processes."""
    current_process = process or get_current_process()
    return get_rss_mb(current_process) + get_children_rss_mb(current_process)


def collect_memory_snapshot(
    start_time: float,
    completed_chunks: int,
    processed_valid_records: int,
    process: psutil.Process | None = None,
    sample_kind: str = "timer",
    event_label: str = "",
) -> tuple[MemorySample, list[WorkerMemorySample]]:
    """Collect one aggregated memory sample and optional per-worker samples."""
    current_process = process or get_current_process()

    main_rss_mb = _safe_rss_mb(current_process) or 0.0
    worker_details = get_children_rss_details(current_process, recursive=True)

    workers_rss_mb = sum(rss_mb for _, rss_mb in worker_details)
    peak_worker_rss_mb = max((rss_mb for _, rss_mb in worker_details), default=0.0)
    total_rss_mb = main_rss_mb + workers_rss_mb
    elapsed_time_sec = time.perf_counter() - start_time

    aggregated_sample = MemorySample(
        elapsed_time_sec=elapsed_time_sec,
        sample_kind=sample_kind,
        event_label=event_label,
        main_rss_mb=main_rss_mb,
        workers_rss_mb=workers_rss_mb,
        total_rss_mb=total_rss_mb,
        peak_worker_rss_mb=peak_worker_rss_mb,
        num_alive_workers=len(worker_details),
        completed_chunks=completed_chunks,
        processed_valid_records=processed_valid_records,
    )

    per_worker_samples = [
        WorkerMemorySample(
            elapsed_time_sec=elapsed_time_sec,
            sample_kind=sample_kind,
            event_label=event_label,
            pid=pid,
            worker_index=index,
            rss_mb=rss_mb,
        )
        for index, (pid, rss_mb) in enumerate(worker_details)
    ]

    return aggregated_sample, per_worker_samples


class MemoryMonitor:
    """
    Lightweight RAM profiler for the pipeline.

    Features:
    - periodic timer-based sampling in a background thread
    - optional event-driven sampling
    - aggregated samples for main/workers/total RSS
    - optional per-worker RSS snapshots
    - CSV export and summary statistics
    """

    def __init__(
        self,
        sampling_interval_sec: float = 0.5,
        progress_callback: Callable[[], tuple[int, int]] | None = None,
        track_per_worker: bool = True,
    ) -> None:
        if sampling_interval_sec <= 0:
            raise ValueError("sampling_interval_sec must be > 0")

        self.sampling_interval_sec = sampling_interval_sec
        self.progress_callback = progress_callback
        self.track_per_worker = track_per_worker

        self._process = get_current_process()
        self._start_time: float | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        self._samples: list[MemorySample] = []
        self._worker_samples: list[WorkerMemorySample] = []

    def start(self) -> None:
        """Start background timer-based profiling."""
        if self._thread is not None:
            return

        self._start_time = time.perf_counter()
        self._stop_event.clear()

        self.take_sample(sample_kind="event", event_label="monitor_started")

        self._thread = threading.Thread(
            target=self._run,
            name="memory-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop background profiling and take final sample."""
        if self._thread is None:
            return

        self._stop_event.set()
        self._thread.join()
        self._thread = None

        self.take_sample(sample_kind="event", event_label="monitor_stopped")

    def _run(self) -> None:
        """Background sampling loop."""
        while not self._stop_event.wait(self.sampling_interval_sec):
            self.take_sample(sample_kind="timer", event_label="")

    def _get_progress(self) -> tuple[int, int]:
        """Read lightweight progress metrics from callback."""
        if self.progress_callback is None:
            return 0, 0

        try:
            result = self.progress_callback()
        except (TypeError, ValueError, AttributeError):
            return 0, 0

        if not isinstance(result, tuple) or len(result) != 2:
            return 0, 0

        completed_chunks, processed_valid_records = result
        return int(completed_chunks), int(processed_valid_records)

    def take_sample(
        self,
        sample_kind: str = "event",
        event_label: str = "",
    ) -> None:
        """Manually take a profiling sample."""
        if self._start_time is None:
            return

        completed_chunks, processed_valid_records = self._get_progress()
        aggregated_sample, per_worker_samples = collect_memory_snapshot(
            start_time=self._start_time,
            completed_chunks=completed_chunks,
            processed_valid_records=processed_valid_records,
            process=self._process,
            sample_kind=sample_kind,
            event_label=event_label,
        )

        with self._lock:
            self._samples.append(aggregated_sample)
            if self.track_per_worker:
                self._worker_samples.extend(per_worker_samples)

    @property
    def samples(self) -> list[MemorySample]:
        """Return a copy of aggregated samples."""
        with self._lock:
            return list(self._samples)

    @property
    def worker_samples(self) -> list[WorkerMemorySample]:
        """Return a copy of per-worker samples."""
        with self._lock:
            return list(self._worker_samples)

    def build_summary(self) -> MemorySummary:
        """Build summary statistics from collected samples."""
        samples = self.samples
        worker_samples = self.worker_samples if self.track_per_worker else []

        if not samples:
            return MemorySummary(
                duration_sec=0.0,
                peak_main_rss_mb=0.0,
                peak_workers_rss_mb=0.0,
                peak_total_rss_mb=0.0,
                peak_single_worker_rss_mb=0.0,
                max_alive_workers=0,
                total_samples=0,
                total_worker_samples=0,
            )

        return MemorySummary(
            duration_sec=max(sample.elapsed_time_sec for sample in samples),
            peak_main_rss_mb=max(sample.main_rss_mb for sample in samples),
            peak_workers_rss_mb=max(sample.workers_rss_mb for sample in samples),
            peak_total_rss_mb=max(sample.total_rss_mb for sample in samples),
            peak_single_worker_rss_mb=max(
                (sample.peak_worker_rss_mb for sample in samples),
                default=0.0,
            ),
            max_alive_workers=max(sample.num_alive_workers for sample in samples),
            total_samples=len(samples),
            total_worker_samples=len(worker_samples),
        )

    def save_aggregated_csv(self, output_path: Path | str) -> None:
        """Save aggregated samples to CSV."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [field.name for field in fields(MemorySample)]
        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for sample in self.samples:
                writer.writerow(asdict(sample))

    def save_worker_csv(self, output_path: Path | str) -> None:
        """Save per-worker samples to CSV."""
        if not self.track_per_worker:
            return

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [field.name for field in fields(WorkerMemorySample)]
        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for sample in self.worker_samples:
                writer.writerow(asdict(sample))

    def save_summary_csv(self, output_path: Path | str) -> None:
        """Save one-row summary CSV."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        summary = self.build_summary()
        fieldnames = [field.name for field in fields(MemorySummary)]
        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(asdict(summary))


# Backward-compatible helper for simple one-shot sampling if needed.
def collect_memory_sample(
    start_time: float,
    completed_chunks: int,
    processed_valid_records: int,
    process: psutil.Process | None = None,
) -> MemorySample:
    """Compatibility wrapper that returns a single aggregated memory sample."""
    sample, _ = collect_memory_snapshot(
        start_time=start_time,
        completed_chunks=completed_chunks,
        processed_valid_records=processed_valid_records,
        process=process,
        sample_kind="event",
        event_label="legacy_collect_memory_sample",
    )
    return sample
