"""
RUN ALL PLOTS
=============

Purpose: Generate benchmark visualization plots from existing pipeline results.

USAGE:
======
    python visualization/run_plots.py

WORKFLOW:
=========
1. Scans pipeline_results/ for completed benchmark runs
2. Generates memory timeline plots for each configuration
3. Generates comparison plots across all configurations
4. Saves all PNG plots in pipeline_results/additional_report/ folder

RUNNING BENCHMARKS:
===================
To run benchmark configurations separately, use:
    
    # Single benchmark
    python -m scripts.run_detection data/full/aisdk-2025-08-31.csv --workers 4 --chunk-size 10000
    
    python -m scripts.run_detection data/full/aisdk-2025-08-31.csv data/full/aisdk-2025-09-01.csv --workers 4 --chunk-size 10000
    
    for workers in 1 2 4; do
        for chunk in 10000 100000; do
            python -m scripts.run_detection data/full/aisdk-2025-08-31.csv data/full/aisdk-2025-09-01.csv --workers $workers --chunk-size $chunk
        done
    done

MEMORY PROFILING:
=================
Memory profiling is automatically collected during benchmark execution:
    - Samples are captured at regular intervals during chunk processing
    - Output is saved to: pipeline_results/<config>/memory_profile.csv
    - Columns: elapsed_time_sec, completed_chunks, processed_valid_records, 
              main_rss_mb, workers_rss_mb, total_rss_mb
    
To generate visualization graphs from memory profile data:
    - Use the plot_memory_timeline() function to visualize RAM usage over time
    - Use plot_memory_comparison() to compare memory usage across configurations
    - Generated plots are saved as PNG files in pipeline_results/additional_report/



INPUT FILES REQUIRED:
====================
Place these CSV files in data/full/ directory:
    - data/full/aisdk-2025-08-31.csv  (August 31 AIS data)
    - data/full/aisdk-2025-09-01.csv  (September 1 AIS data)

Example structure:
    BigdataprojectVU/
    ├── data/
    │   └── full/
    │       ├── aisdk-2025-08-31.csv  <- Add this file
    │       └── aisdk-2025-09-01.csv  <- Add this file
    ├── pipeline_results/  (generated automatically)
    ├── additional_report/ (generated automatically)
    └── visualization/

OUTPUTS:
========
For each benchmark configuration, generates:
    - dfsi_results.csv (anomaly detection results with DFSI scores)
    - memory_profile.csv (memory usage timeline with samples)
    - top_teleportation_vessel_map.csv (coordinates for top anomalies)

Visualization plots in pipeline_results/additional_report/ folder:
    - memory_timeline_*.png (one per benchmark run, ~12 files showing RAM over time)
    - memory_usage_comparison.png (memory vs workers comparison)
    - execution_speed_comparison.png (time vs workers comparison)
    - combined_performance_analysis.png (4-panel overview)
    - aggregated_memory_timeline.png (memory trends over time per config, aggregated across input files)
"""

from pathlib import Path
import sys
import subprocess

# Add parent directory to path for imports
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

# Benchmark configuration - adjust these to change tested configurations
WORKER_COUNTS = DEFAULT_WORKER_COUNTS  # [1, 2, 4]
CHUNK_SIZES = DEFAULT_CHUNK_SIZES      # [10000, 100000]


def check_and_run_benchmarks(results_dir: str = "pipeline_results") -> bool:
    """
    Check if benchmark results exist. If not, automatically run all benchmarks.
    
    Runs benchmarks on multiple input files (treated as a unified streaming chunk flow):
    - Input files: aisdk-2025-08-31.csv, aisdk-2025-09-01.csv
    - 3 worker counts: 1, 2, 4 workers
    - 2 chunk sizes: 10,000 and 100,000 rows
    - Total: 12 configurations
    
    Note: Visualizations aggregate results across all input files since the system
    processes data in chunks independent of file boundaries (streaming paradigm).
    
    Args:
        results_dir: Directory containing benchmark results
        
    Returns:
        True if benchmarks exist or were successfully run, False if input files missing
    """
    results_path = Path(results_dir)
    
    # Check if input files exist
    data_files = [
        Path("data/full/aisdk-2025-08-31.csv"),
        Path("data/full/aisdk-2025-09-01.csv"),
    ]
    
    missing_files = [f for f in data_files if not f.exists()]
    
    if missing_files:
        print("\n" + "="*75)
        print("[!] INPUT DATA FILES MISSING")
        print("="*75)
        print("\nTo run benchmarks, add these CSV files to data/full/ directory:")
        for f in missing_files:
            print(f"    {f}")
        print("\nExpected structure:")
        print("    BigdataprojectVU/")
        print("    ├── data/")
        print("    │   └── full/")
        print("    │       ├── aisdk-2025-08-31.csv")
        print("    │       └── aisdk-2025-09-01.csv")
        print("    └── visualization/")
        print("\nOnce files are added, run again:")
        print("    python visualization/run_plots.py")
        return False
    
    # Run benchmark configurations with dynamic worker/chunk combinations
    print("\n" + "="*75)
    print("RUNNING BENCHMARKS AUTOMATICALLY")
    print("="*75 + "\n")
    
    results_path.mkdir(parents=True, exist_ok=True)
    
    # Generate all combinations of input files, workers, and chunk sizes
    data_files = [
        "data/full/aisdk-2025-08-31.csv",
        "data/full/aisdk-2025-09-01.csv",
    ]
    
    configs = [
        (data_file, workers, chunk_size)
        for data_file in data_files
        for workers in WORKER_COUNTS
        for chunk_size in CHUNK_SIZES
    ]
    
    total_configs = len(configs)
    successful = 0
    
    print(f"Total configurations to run: {total_configs}")
    print(f"  Input files: {len(data_files)}")
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
                print(f"        ✓ Completed")
            else:
                print(f"        ✗ Failed with exit code {result.returncode}")
        except subprocess.TimeoutExpired:
            print(f"        ✗ Timeout (>1 hour)")
        except Exception as e:
            print(f"        ✗ Error: {e}")
    
    print(f"\n[OK] Benchmarks complete: {successful}/{total_configs} successful\n")
    return successful == total_configs


def run_all_plots(
    results_dir: str = "pipeline_results",
    output_dir: str = "pipeline_results/additional_report",
    auto_benchmark: bool = True,
) -> None:
    """
    Generate benchmark visualization plots from existing results.
    
    Main orchestrator that:
    1. Scans results_dir for all completed benchmark runs
    2. Creates output_dir directory structure
    3. Generates individual memory timeline plots for each run
    4. Generates comparison plots across all runs
    5. Prints summary of generated files
    
    Args:
        results_dir: Directory containing benchmark results (default: pipeline_results/)
        output_dir: Directory where PNG plots will be saved (default: pipeline_results/additional_report/)
        auto_benchmark: Unused (benchmarks must be run separately)
    """
    results_path = Path(results_dir)
    output_path = Path(output_dir)
    
    # Check if benchmarks exist, if not try to run them
    existing_runs = list(results_path.glob("aisdk-*_w*_c*"))
    if len(existing_runs) < 12:
        print("\n[!] Insufficient benchmark results found")
        if not check_and_run_benchmarks(results_dir):
            print("[!] Cannot run benchmarks (missing input CSV files in data/full/)")
            return
    
    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*75)
    print("GENERATING BENCHMARK VISUALIZATIONS")
    print("="*75 + "\n")
    
    # Collect all benchmark runs
    print(f"Scanning {results_dir}/ for benchmark runs...")
    runs = collect_benchmark_results(results_path)
    
    if not runs:
        print(f"[!] No benchmark results found in {results_dir}/")
        return
    
    print(f"✓ Found {len(runs)} benchmark configurations\n")
    
    # Generate memory timeline plots for each run
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
    # Generate comparison plots
    print("Generating comparison plots...")
    
    memory_comp_ok = plot_memory_comparison(
        runs, output_path / "memory_usage_comparison.png", chunk_sizes=CHUNK_SIZES
    )
    
    speed_comp_ok = plot_speed_comparison(
        runs, output_path / "execution_speed_comparison.png", chunk_sizes=CHUNK_SIZES
    )
    
    combined_ok = plot_combined_analysis(
        runs, output_path / "combined_performance_analysis.png", chunk_sizes=CHUNK_SIZES
    )
    
    aggregated_ok = plot_aggregated_memory_timeline(
        results_path, output_path / "aggregated_memory_timeline.png",
        worker_counts=WORKER_COUNTS, chunk_sizes=CHUNK_SIZES
    )
    
    # Print summary
    print("\n" + "="*75)
    print("✓ VISUALIZATION GENERATION COMPLETE")
    print("="*75)
    
    print(f"\nOutput directory: {output_path.absolute()}/")
    print("\nGenerated files:")
    print(f"  • memory_timeline_*.png ({memory_plots_created} files)")
    print("  • memory_usage_comparison.png")
    print("  • execution_speed_comparison.png")
    print("  • combined_performance_analysis.png")
    print("  • aggregated_memory_timeline.png (overall analysis over time)")
    print()


if __name__ == "__main__":
    # Allow optional arguments for custom directories
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
        default="pipeline_results/additional_report",
        help="Directory to save plots (default: pipeline_results/additional_report/)",
    )
    
    args = parser.parse_args()
    
    run_all_plots(
        results_dir=args.results_dir,
        output_dir=args.output_dir,
    )
