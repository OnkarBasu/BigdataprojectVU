from __future__ import annotations

import csv
from pathlib import Path

from src.config import DetectionConfig, RunConfig
from src.pipeline.detection_pipeline import run_detection_pipeline


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def make_header() -> list[str]:
    return [
        "# Timestamp",
        "Type of mobile",
        "MMSI",
        "Latitude",
        "Longitude",
        "SOG",
        "Draught",
    ]


def make_row(
    timestamp: str,
    mmsi: str,
    latitude: str,
    longitude: str,
    sog: str = "7.2",
    draught: str = "8.5",
    mobile_type: str = "Class A",
) -> list[str]:
    return [
        timestamp,
        mobile_type,
        mmsi,
        latitude,
        longitude,
        sog,
        draught,
    ]


def test_run_detection_pipeline_smoke(tmp_path: Path) -> None:
    input_file = tmp_path / "sample.csv"
    memory_output_file = tmp_path / "memory_profile.csv"

    write_csv(
        input_file,
        make_header(),
        [
            make_row(
                timestamp="01/09/2025 00:00:00",
                mmsi="245014000",
                latitude="10.0",
                longitude="20.0",
                sog="8.0",
                draught="10.0",
            ),
            make_row(
                timestamp="01/09/2025 00:05:00",
                mmsi="245014000",
                latitude="10.01",
                longitude="20.0",
                sog="8.1",
                draught="10.0",
            ),
            make_row(
                timestamp="01/09/2025 05:30:00",
                mmsi="245014000",
                latitude="10.03",
                longitude="20.0",
                sog="8.0",
                draught="11.0",
            ),
            make_row(
                timestamp="01/09/2025 00:02:00",
                mmsi="538009722",
                latitude="30.0",
                longitude="40.0",
                sog="9.0",
                draught="7.0",
            ),
            make_row(
                timestamp="01/09/2025 00:20:00",
                mmsi="538009722",
                latitude="32.0",
                longitude="40.0",
                sog="9.0",
                draught="7.0",
            ),
            make_row(
                timestamp="01/09/2025 00:25:00",
                mmsi="111111111",  # invalid MMSI, should be filtered out
                latitude="50.0",
                longitude="60.0",
                sog="5.0",
                draught="6.0",
            ),
        ],
    )

    run_config = RunConfig(
        chunk_size=2,
        workers=1,
        encoding="utf-8",
        enable_loitering_detection=False,
        memory_output_file=memory_output_file,
        verbose=False,
    )

    result = run_detection_pipeline(
        input_files=[input_file],
        run_config=run_config,
        detection_config=DetectionConfig(),
    )

    assert result.completed_chunks == 3
    assert result.processed_valid_records == 5
    assert result.total_runtime_sec >= 0.0
    assert result.final_memory_rss_mb >= 0.0

    assert 245014000 in result.global_summaries
    assert 538009722 in result.global_summaries
    assert 111111111 not in result.global_summaries

    summary_a = result.global_summaries[245014000]
    summary_b = result.global_summaries[538009722]

    assert summary_a.record_count == 3
    assert summary_b.record_count == 2

    assert isinstance(result.dfsi_scores, dict)
    assert 245014000 in result.dfsi_scores
    assert 538009722 in result.dfsi_scores

    assert isinstance(result.ranked_scores, list)
    assert len(result.ranked_scores) == 2

    assert result.loitering_events == []

    assert result.memory_output_file.exists()
    assert result.worker_memory_output_file.exists()
    assert result.memory_summary_output_file.exists()
