from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class RunConfig:
    chunk_size: int = 100_000
    workers: int = 4
    encoding: str = "utf-8"
    enable_loitering_detection: bool = True
    memory_output_file: Path = Path("data/output/memory_profile.csv")
    verbose: bool = True


DEFAULT_RUN_CONFIG = RunConfig()
