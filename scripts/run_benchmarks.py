#!/usr/bin/env python
"""Performance Benchmarking Script

Runs the detection pipeline with different worker counts and chunk sizes.
Executes tests sequentially to ensure accurate RSS measurements.
"""

import subprocess
import sys
import time
from pathlib import Path

# Get workspace root (parent of scripts directory)
SCRIPTS_DIR = Path(__file__).parent.resolve()
WORKSPACE_ROOT = SCRIPTS_DIR.parent

# Configuration
# WORKERS = [1,2,3,4,6,10,14]
# CHUNK_SIZES = [10000, 50000, 100000, 200000, 500000, 1000000]
WORKERS = [1, 2, 3, 4]
CHUNK_SIZES = [100000, 250000, 500000, 1000000]

INPUT_FILE1 = WORKSPACE_ROOT / "data/full/aisdk-2025-08-31.csv"
INPUT_FILE2 = WORKSPACE_ROOT / "data/full/aisdk-2025-09-01.csv"
OUTPUT_BASE = WORKSPACE_ROOT / "data/output"

# Validate input files
if not INPUT_FILE1.exists():
    print(f"ERROR: Input file not found: {INPUT_FILE1}")
    exit(1)
if not INPUT_FILE2.exists():
    print(f"ERROR: Input file not found: {INPUT_FILE2}")
    exit(1)

print("=" * 80)
print("PERFORMANCE BENCHMARKING SUITE")
print("=" * 80)
print(f"Workspace root: {WORKSPACE_ROOT}")
print(f"Input files:")
print(f"  - {INPUT_FILE1}")
print(f"  - {INPUT_FILE2}")
print(f"Output base: {OUTPUT_BASE}")
print(f"Workers to test: {WORKERS}")
print(f"Chunk sizes to test: {CHUNK_SIZES}")
print("=" * 80)
print()

total_runs = len(WORKERS) * len(CHUNK_SIZES)
completed_runs = 0
failed_runs = 0
run_times = {}

start_time_all = time.time()

# Run all combinations sequentially
for w in WORKERS:
    for c in CHUNK_SIZES:
        chunk_k = c // 1000
        run_name = f"benchmark_w{w}_c{chunk_k}k"
        output_dir = OUTPUT_BASE / run_name
        
        completed_runs += 1
        print(f"[{completed_runs:2d}/{total_runs}] {run_name}")
        print(f"         Workers: {w} | Chunk Size: {c:,} rows")
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build command
        cmd = [
            sys.executable, "-m", "scripts.run_detection",
            str(INPUT_FILE1),
            str(INPUT_FILE2),
            "--chunk-size", str(c),
            "--workers", str(w),
            "--top", "10",
            "--memory-output", str(output_dir / "memory_profile.csv"),
            "--output", str(output_dir / "dfsi_results.csv"),
            "--teleportation-d1-viz-output", str(output_dir / "top_teleportation_d1_vessel_map.csv"),
            "--teleportation-d2-viz-output", str(output_dir / "top_teleportation_d2_vessel_map.csv"),
            "--going-dark-viz-output", str(output_dir / "top_going_dark_vessel_map.csv"),
            "--loitering-viz-output", str(output_dir / "top_loitering_vessel_map.csv"),
        ]
        
        # Run detection from workspace root
        start = time.time()
        try:
            result = subprocess.run(
                cmd, 
                timeout=7200,
                cwd=str(WORKSPACE_ROOT)
            )
            duration = time.time() - start
            
            # Check if output file was created
            if (output_dir / "memory_profile.csv").exists():
                run_times[run_name] = duration
                print(f"         ✓ SUCCESS in {duration:.1f}s")
                csv_files = list(output_dir.glob("*.csv"))
                print(f"         Generated {len(csv_files)} CSV files")
            else:
                print(f"         ✗ FAILED: Output file not created")
                failed_runs += 1
        except subprocess.TimeoutExpired:
            print(f"         ✗ TIMEOUT after 7200s")
            failed_runs += 1
        except Exception as e:
            print(f"         ✗ ERROR: {str(e)[:100]}")
            failed_runs += 1
        
        print()

total_time = time.time() - start_time_all

print("=" * 80)
print("BENCHMARKING RESULTS")
print("=" * 80)
print(f"Total runs:        {total_runs}")
print(f"Successful:        {completed_runs - failed_runs}")
print(f"Failed:            {failed_runs}")
print(f"Total time:        {total_time/3600:.2f} hours ({total_time/60:.1f} minutes)")
print(f"Output directory:  {OUTPUT_BASE}")
print("=" * 80)

if run_times:
    print("\nRun Times Summary:")
    for run_name in sorted(run_times.keys()):
        print(f"  {run_name}: {run_times[run_name]:.1f}s")
