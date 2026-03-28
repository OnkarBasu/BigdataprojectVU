"""
RUN ALL PLOTS
=============

Purpose: Generate benchmark visualization plots from existing pipeline results.

This script is focused on performance plots (memory/time benchmarking).
It does not build anomaly A/B/D HTML maps. Those are generated separately from
CSV outputs using the dedicated map scripts.

USAGE:
======
    python visualization/run_plots.py

WORKFLOW:
=========
1. Scans pipeline_results/ for completed benchmark runs
2. Generates memory timeline plots for each configuration
3. Generates comparison plots across all configurations
4. Saves all PNG plots in visualization/output/ folder

RUNNING BENCHMARKS:
===================
To run benchmark configurations separately, use:

    # Single benchmark (performance mode, anomaly B disabled)
    python -m scripts.run_detection data/full/aisdk-2025-08-31.csv --workers 4 --chunk-size 10000

    python -m scripts.run_detection data/full/aisdk-2025-08-31.csv data/full/aisdk-2025-09-01.csv --workers 4 --chunk-size 10000

    for workers in 1 2 4; do
        for chunk in 10000 100000; do
            python -m scripts.run_detection data/full/aisdk-2025-08-31.csv data/full/aisdk-2025-09-01.csv --workers $workers --chunk-size $chunk
        done
    done

To include anomaly B in a full functional run, explicitly add:
    --enable-loitering-detection

MAP VISUALIZATION SCRIPTS:
==========================
Generate HTML maps separately from the exported CSV files:
    python visualization/going_dark_map.py
    python visualization/result_plots.py
    python visualization/loitering_map.py
"""

from pathlib import Path
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).parent.parent))

from visualization.plot_helpers import (
    collect_benchmark_results,
    plot_memory_timeline,
    plot_memory_comparison,
    plot_speed_comparison,
    plot_combined_analysis,
    plot_aggregated_memory_timeline,
    DEFAULT_WORKER_COUNTS,
    DEFAULT_CHUNK_SIZES,
)

WORKER_COUNTS = DEFAULT_WORKER_COUNTS
CHUNK_SIZES = DEFAULT_CHUNK_SIZES


def check_and_run_benchmarks(results_dir: str = "pipeline_results") -> bool:
    """Check if benchmark results exist. If not, automatically run all benchmarks."""
    results_path = Path(results_dir)

    data_files = [
        Path("data/full/aisdk-2025-08-31.csv"),
        Path("data/full/aisdk-2025-09-01.csv"),
    ]
    missing_files = [f for f in data_files if not f.exists()]

    if missing_files:
        print("\n" + "=" * 75)
        print("[!] INPUT DATA FILES MISSING")
        print("=" * 75)
        print("\nTo run benchmarks, add these CSV files to data/full/ directory:")
        for f in missing_files:
            print(f"    {f}")
        print("\nOnce files are added, run again:")
        print("    python visualization/run_plots.py")
        return False

    print("\n" + "=" * 75)
    print("RUNNING BENCHMARKS AUTOMATICALLY")
    print("=" * 75 + "\n")

    results_path.mkdir(parents=True, exist_ok=True)

    data_file_paths = [
        "data/full/aisdk-2025-08-31.csv",
        "data/full/aisdk-2025-09-01.csv",
    ]

    configs = [
        (data_file, workers, chunk_size)
        for data_file in data_file_paths
        for workers in WORKER_COUNTS
        for chunk_size in CHUNK_SIZES
    ]

    total_configs = len(configs)
    successful = 0

    print(f"Total configurations to run: {total_configs}")
    print(f"  Input files: {len(data_file_paths)}")
    print(f"  Worker counts: {WORKER_COUNTS}")
    print(f"  Chunk sizes: {CHUNK_SIZES}\n")

    for idx, (dataset, workers, chunk_size) in enumerate(configs, 1):
        config_name = Path(dataset).stem
        output_dir = results_path / f"{config_name}_w{workers}_c{chunk_size}"
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "python", "-m", "scripts.run_detection",
            dataset,
            "--workers", str(workers),
            "--chunk-size", str(chunk_size),
            "--output", str(output_dir / "dfsi_results.csv"),
            "--memory-output", str(output_dir / "memory_profile.csv"),
        ]

        print(f"[{idx}/{total_configs}] Running: {output_dir.name}")

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=3600)
            if result.returncode == 0:
                successful += 1
                print("        ✓ Completed")
            else:
                print(f"        ✗ Failed with exit code {result.returncode}")
        except subprocess.TimeoutExpired:
            print("        ✗ Timeout (>1 hour)")
        except Exception as e:
            print(f"        ✗ Error: {e}")

    print(f"\n[OK] Benchmarks complete: {successful}/{total_configs} successful\n")
    return successful == total_configs


def run_all_plots(
    results_dir: str = "pipeline_results",
    output_dir: str = "visualization/output",
    auto_benchmark: bool = True,
) -> None:
    """Generate benchmark visualization plots from existing results."""
    results_path = Path(results_dir)
    output_path = Path(output_dir)

    existing_runs = list(results_path.glob("aisdk-*_w*_c*"))
    if len(existing_runs) < 12:
        print("\n[!] Insufficient benchmark results found")
        if not check_and_run_benchmarks(results_dir):
            print("[!] Cannot run benchmarks (missing input CSV files in data/full/)")
            return

    output_path.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 75)
    print("GENERATING BENCHMARK VISUALIZATIONS")
    print("=" * 75 + "\n")

    print(f"Scanning {results_dir}/ for benchmark runs...")
    runs = collect_benchmark_results(results_path)

    if not runs:
        print(f"[!] No benchmark results found in {results_dir}/")
        return

    print(f"✓ Found {len(runs)} benchmark configurations\n")

    print("Generating memory timeline plots...")
    memory_plots_created = 0
    for run_dir in sorted(results_path.glob("aisdk-*_w*_c*")):
        if not run_dir.is_dir():
            continue

        memory_csv = run_dir / "memory_profile.csv"
        if memory_csv.exists():
            output_png = output_path / f"memory_timeline_{run_dir.name}.png"
            if plot_memory_timeline(memory_csv, output_png):
                memory_plots_created += 1

    print(f"✓ Created {memory_plots_created} memory timeline plots\n")
    print("Generating comparison plots...")

    plot_memory_comparison(
        runs, output_path / "memory_usage_comparison.png", chunk_sizes=CHUNK_SIZES
    )
    plot_speed_comparison(
        runs, output_path / "execution_speed_comparison.png", chunk_sizes=CHUNK_SIZES
    )
    plot_combined_analysis(
        runs, output_path / "combined_performance_analysis.png", chunk_sizes=CHUNK_SIZES
    )
    plot_aggregated_memory_timeline(
        results_path,
        output_path / "aggregated_memory_timeline.png",
        worker_counts=WORKER_COUNTS,
        chunk_sizes=CHUNK_SIZES,
    )

    print("\n" + "=" * 75)
    print("✓ VISUALIZATION GENERATION COMPLETE")
    print("=" * 75)
    print(f"\nOutput directory: {output_path.absolute()}/")
    print("\nGenerated files:")
    print(f"  • memory_timeline_*.png ({memory_plots_created} files)")
    print("  • memory_usage_comparison.png")
    print("  • execution_speed_comparison.png")
    print("  • combined_performance_analysis.png")
    print("  • aggregated_memory_timeline.png")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate all benchmark visualization reports"
    )
    parser.add_argument(
        "--results-dir",
        default="pipeline_results",
        help="Directory containing benchmark results (default: pipeline_results/)",
    )
    parser.add_argument(
        "--output-dir",
        default="visualization/output",
        help="Directory to save plots (default: visualization/output/)",
    )
    args = parser.parse_args()

    run_all_plots(
        results_dir=args.results_dir,
        output_dir=args.output_dir,
    )
