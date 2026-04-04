from __future__ import annotations

from pathlib import Path

import scripts.run_detection as run_detection
from src.models import VesselGlobalSummary


class DummyPipelineResult:
    def __init__(self):
        self.global_summaries = {
            245014000: VesselGlobalSummary(
                mmsi=245014000,
                record_count=10,
                max_gap_hours=5.0,
                total_impossible_jump_km=100.0,
                draft_change_count=1,
            )
        }
        self.ranked_scores = [(245014000, 123.0)]
        self.loitering_events = []
        self.memory_summary = type(
            "MemorySummary",
            (),
            {
                "peak_main_rss_mb": 1.0,
                "peak_workers_rss_mb": 1.0,
                "peak_total_rss_mb": 2.0,
            },
        )()

        self.memory_output_file = Path("memory.csv")
        self.worker_memory_output_file = Path("worker_memory.csv")
        self.memory_summary_output_file = Path("memory_summary.csv")

        self.processed_valid_records = 10
        self.completed_chunks = 2
        self.total_runtime_sec = 1.0
        self.final_memory_rss_mb = 100.0


def test_run_detection_main_calls_pipeline_with_correct_config(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_pipeline(input_files, run_config, detection_config):
        captured["input_files"] = input_files
        captured["run_config"] = run_config
        captured["detection_config"] = detection_config
        return DummyPipelineResult()

    monkeypatch.setattr(
        run_detection,
        "run_detection_pipeline",
        fake_pipeline,
    )

    # mock output writers (чтобы ничего не писалось)
    monkeypatch.setattr(run_detection, "write_results_csv", lambda *a, **k: None)
    monkeypatch.setattr(run_detection, "write_teleportation_visualization_csv", lambda *a, **k: None)
    monkeypatch.setattr(run_detection, "write_going_dark_visualization_csv", lambda *a, **k: None)
    monkeypatch.setattr(run_detection, "write_loitering_visualization_csv", lambda *a, **k: None)

    # mock visualization helpers
    monkeypatch.setattr(run_detection, "get_top_teleportation_d1_vessel_visualization_data", lambda *_: None)
    monkeypatch.setattr(run_detection, "get_top_teleportation_d2_vessel_visualization_data", lambda *_: None)
    monkeypatch.setattr(run_detection, "get_top_going_dark_vessel_visualization_data", lambda *_: None)
    monkeypatch.setattr(run_detection, "get_top_loitering_vessel_visualization_data", lambda *_: None)

    input_file = tmp_path / "input.csv"

    args = [
        "run_detection.py",
        str(input_file),
        "--chunk-size",
        "123",
        "--workers",
        "2",
        "--encoding",
        "utf-8",
        "--top",
        "5",
        "--disable-loitering-detection",
    ]

    monkeypatch.setattr("sys.argv", args)

    run_detection.main()

    # ---- assertions ----

    assert captured["input_files"] == [input_file]

    run_config = captured["run_config"]

    assert run_config.chunk_size == 123
    assert run_config.workers == 2
    assert run_config.encoding == "utf-8"

    assert run_config.enable_loitering_detection is False

    assert run_config.verbose is True
