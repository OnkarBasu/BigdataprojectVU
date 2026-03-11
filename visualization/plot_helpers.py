"""
PLOTTING HELPER FUNCTIONS
=========================

Purpose: Utility functions for benchmark data collection and visualization generation.

Key Functions:
- collect_benchmark_results()    : Auto-discover and parse benchmark directories
- plot_memory_comparison()       : Generate 2-panel memory usage comparison
- plot_speed_comparison()        : Generate 2-panel execution time comparison  
- plot_combined_analysis()       : Generate 4-panel comprehensive analysis
- plot_memory_timeline()         : Generate time-series memory plot for single run
- _setup_plot_style()            : Apply consistent matplotlib styling

All functions are self-contained with descriptive docstrings.
"""

from pathlib import Path
from dataclasses import dataclass
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np


@dataclass
class BenchmarkRun:
    """Single benchmark execution result containing timing, memory, and record metrics"""
    dataset: str
    workers: int
    chunk_size: int
    elapsed_time: float
    peak_memory: float
    records: int


def _setup_plot_style():
    """Apply consistent matplotlib styling to all plots (16" width, 300 DPI output)"""
    plt.rcParams.update({
        "figure.figsize": (14, 6),
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "grid.alpha": 0.3,
        "lines.linewidth": 2.5,
        "lines.markersize": 8,
        "legend.fontsize": 10,
    })


# ==============================================================================
# BENCHMARK DATA COLLECTION
# ==============================================================================

def collect_benchmark_results(results_dir: Path) -> list[BenchmarkRun]:
    """
    Scan pipeline_results/ directory for all completed benchmark runs.
    
    Auto-discovers directories matching pattern: aisdk-YYYY-MM-DD_wN_cSIZE
    Extracts timing, memory, and record count metrics from CSV files.
    
    Expected directory structure:
        pipeline_results/
        ├── aisdk-2025-08-31_w1_c10000/
        │   ├── dfsi_results.csv
        │   └── memory_profile.csv
        ├── aisdk-2025-08-31_w2_c10000/
        └── ... (more run directories)
    
    Args:
        results_dir: Path to pipeline_results directory
        
    Returns:
        List of BenchmarkRun objects sorted by dataset, chunk_size, workers
    """
    runs = []
    
    for run_dir in results_dir.glob('aisdk-*_w*_c*'):
        if not run_dir.is_dir():
            continue
        
        # Extract config from dirname: aisdk-2025-08-31_w2_c100000
        try:
            name_no_prefix = run_dir.name.replace('aisdk-', '')  # '2025-08-31_w2_c100000'
            parts = name_no_prefix.split('_')  # ['2025-08-31', 'w2', 'c100000']
            date = parts[0]  # '2025-08-31'
            workers = int(parts[1].replace('w', ''))  # 'w2' -> 2
            chunk_size = int(parts[2].replace('c', ''))  # 'c100000' -> 100000
        except (ValueError, IndexError) as e:
            continue
        
        # Extract metrics from CSVs
        memory_csv = run_dir / 'memory_profile.csv'
        dfsi_csv = run_dir / 'dfsi_results.csv'
        
        # Get peak memory from memory_profile.csv
        try:
            if not memory_csv.exists():
                continue
            df_mem = pd.read_csv(memory_csv)
            peak_mem = df_mem['total_rss_mb'].max()
            elapsed = df_mem['elapsed_time_sec'].max()
        except:
            continue
        
        # Get record count from DFSI results
        try:
            records = len(pd.read_csv(dfsi_csv)) if dfsi_csv.exists() else 0
        except:
            records = 0
        
        runs.append(BenchmarkRun(
            dataset=date,
            workers=workers,
            chunk_size=chunk_size,
            elapsed_time=elapsed,
            peak_memory=peak_mem,
            records=records
        ))
    
    return sorted(runs, key=lambda x: (x.dataset, x.chunk_size, x.workers))


# ==============================================================================
# MEMORY TIMELINE PLOTTING
# ==============================================================================

def plot_memory_timeline(memory_csv: Path, output_png: Path) -> bool:
    """
    Create memory usage timeline plot from memory_profile.csv.
    
    Displays three memory components over time:
    - Main process RSS (purple line with markers)
    - Worker processes RSS (orange line with markers)
    - Total RSS (red dashed line)
    - Shaded area between main and total showing worker memory usage
    
    Includes peak memory, final memory, and duration statistics box.
    
    Args:
        memory_csv: Path to memory_profile.csv from benchmark run
        output_png: Output PNG file path
        
    Returns:
        True if successful, False if file missing or error occurred
    """
    if not memory_csv.exists():
        print(f"⚠ Memory CSV not found: {memory_csv}")
        return False
    
    try:
        _setup_plot_style()
        df = pd.read_csv(memory_csv)
        
        fig, ax = plt.subplots(figsize=(14, 6))
        
        # Plot three memory lines
        ax.plot(df['elapsed_time_sec'], df['main_rss_mb'], 
               color='purple', linewidth=2, label='Main Process', marker='o', markersize=3)
        ax.plot(df['elapsed_time_sec'], df['workers_rss_mb'], 
               color='orange', linewidth=2, label='Workers', marker='s', markersize=3)
        ax.plot(df['elapsed_time_sec'], df['total_rss_mb'], 
               color='red', linewidth=2.5, label='Total RSS', marker='^', markersize=3, linestyle='--')
        
        # Shade worker memory region
        ax.fill_between(df['elapsed_time_sec'], df['main_rss_mb'], df['total_rss_mb'],
                       alpha=0.15, color='blue')
        
        ax.set_xlabel('Elapsed Time (seconds)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Memory (MB)', fontsize=12, fontweight='bold')
        ax.set_title(f'Memory Timeline: {memory_csv.parent.name}', fontsize=13, fontweight='bold')
        ax.legend(loc='center right')
        ax.grid(True, alpha=0.4)
        
        # Add statistics box
        max_total = df['total_rss_mb'].max()
        final_total = df['total_rss_mb'].iloc[-1]
        duration = df['elapsed_time_sec'].iloc[-1]
        stats_text = f"Peak: {max_total:.1f} MB\nFinal: {final_total:.1f} MB\nDuration: {duration:.1f}s"
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=10,
               verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        plt.tight_layout()
        plt.savefig(output_png, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"✓ Saved: {output_png.name}")
        return True
        
    except Exception as e:
        print(f"✗ Error creating memory timeline: {e}")
        return False


# ==============================================================================
# COMPARISON PLOT GENERATORS
# ==============================================================================

def plot_memory_comparison(runs: list[BenchmarkRun], output_png: Path) -> bool:
    """
    Create 2-panel memory usage comparison plot (10K vs 100K chunks).
    
    Left panel shows peak memory vs worker count for 10K chunk size.
    Right panel shows peak memory vs worker count for 100K chunk size.
    Separate line for each dataset (2025-08-31 vs 2025-09-01).
    
    Helps identify memory scaling characteristics with parallelism.
    
    Args:
        runs: List of BenchmarkRun objects from all configurations
        output_png: Output PNG file path
        
    Returns:
        True if successful, False if no valid data
    """
    try:
        _setup_plot_style()
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        
        for chunk_idx, chunk_size in enumerate([10000, 100000]):
            ax = axes[chunk_idx]
            
            for dataset in sorted(set(r.dataset for r in runs)):
                data = [r for r in runs if r.dataset == dataset and r.chunk_size == chunk_size]
                if not data:
                    continue
                
                workers = sorted([r.workers for r in data])
                memory = [next(r.peak_memory for r in data if r.workers == w) for w in workers]
                ax.plot(workers, memory, marker='o', linewidth=2.5, markersize=8, label=dataset)
            
            ax.set_xlabel('Number of Workers', fontsize=11, fontweight='bold')
            ax.set_ylabel('Peak Memory (MB)', fontsize=11, fontweight='bold')
            ax.set_title(f'Chunk Size: {chunk_size:,}', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.4)
            ax.legend()
        
        plt.suptitle('Memory Usage Comparison', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(output_png, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"✓ Saved: {output_png.name}")
        return True
    except Exception as e:
        print(f"✗ Error generating memory comparison: {e}")
        return False


def plot_speed_comparison(runs: list[BenchmarkRun], output_png: Path) -> bool:
    """
    Create 2-panel execution time comparison plot (10K vs 100K chunks).
    
    Left panel shows execution time vs worker count for 10K chunk size.
    Right panel shows execution time vs worker count for 100K chunk size.
    Separate line for each dataset.
    
    Helps identify optimal worker count and chunk size trade-offs.
    
    Args:
        runs: List of BenchmarkRun objects from all configurations
        output_png: Output PNG file path
        
    Returns:
        True if successful, False if no valid data
    """
    try:
        _setup_plot_style()
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        
        for chunk_idx, chunk_size in enumerate([10000, 100000]):
            ax = axes[chunk_idx]
            
            for dataset in sorted(set(r.dataset for r in runs)):
                data = [r for r in runs if r.dataset == dataset and r.chunk_size == chunk_size]
                if not data:
                    continue
                
                workers = sorted([r.workers for r in data])
                times = [next(r.elapsed_time for r in data if r.workers == w) for w in workers]
                ax.plot(workers, times, marker='s', linewidth=2.5, markersize=8, label=dataset)
            
            ax.set_xlabel('Number of Workers', fontsize=11, fontweight='bold')
            ax.set_ylabel('Execution Time (seconds)', fontsize=11, fontweight='bold')
            ax.set_title(f'Chunk Size: {chunk_size:,}', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.4)
            ax.legend()
        
        plt.suptitle('Execution Speed Comparison', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(output_png, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"✓ Saved: {output_png.name}")
        return True
    except Exception as e:
        print(f"✗ Error generating speed comparison: {e}")
        return False


def plot_combined_analysis(runs: list[BenchmarkRun], output_png: Path) -> bool:
    """
    Create 4-panel combined performance analysis plot.
    
    Layout:
    - Top-left: Memory usage for 10K chunks
    - Top-right: Memory usage for 100K chunks
    - Bottom-left: Execution time for 10K chunks
    - Bottom-right: Execution time for 100K chunks
    
    Provides comprehensive overview of all performance metrics in single figure.
    
    Args:
        runs: List of BenchmarkRun objects from all configurations
        output_png: Output PNG file path
        
    Returns:
        True if successful, False if no valid data
    """
    try:
        _setup_plot_style()
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        metrics = [
            (0, 'memory', 10000, 'Memory (MB)'),
            (1, 'memory', 100000, 'Memory (MB)'),
            (2, 'speed', 10000, 'Time (sec)'),
            (3, 'speed', 100000, 'Time (sec)'),
        ]
        
        for idx, metric_type, chunk_size, ylabel in metrics:
            ax = axes[idx // 2, idx % 2]
            
            for dataset in sorted(set(r.dataset for r in runs)):
                data = [r for r in runs if r.dataset == dataset and r.chunk_size == chunk_size]
                if not data:
                    continue
                
                workers = sorted([r.workers for r in data])
                if metric_type == 'memory':
                    values = [next(r.peak_memory for r in data if r.workers == w) for w in workers]
                else:
                    values = [next(r.elapsed_time for r in data if r.workers == w) for w in workers]
                
                ax.plot(workers, values, marker='o', linewidth=2.5, markersize=7, label=dataset)
            
            chunk_label = f"{chunk_size//1000}K"
            metric_label = "Memory" if metric_type == 'memory' else "Time"
            ax.set_xlabel('Workers', fontsize=11, fontweight='bold')
            ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
            ax.set_title(f'{metric_label} - {chunk_label} chunks', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.4)
            ax.legend()
        
        plt.suptitle('Performance Analysis Summary', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(output_png, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"✓ Saved: {output_png.name}")
        return True
    except Exception as e:
        print(f"✗ Error generating combined analysis: {e}")
        return False
