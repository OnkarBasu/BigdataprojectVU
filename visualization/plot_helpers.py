"""
PLOTTING HELPER FUNCTIONS
=========================

Purpose: Utility functions for benchmark data collection and visualization generation.

Key Functions:
- collect_benchmark_results()          : Auto-discover and parse benchmark directories
- plot_memory_timeline()               : Generate time-series memory plot for single run
- plot_aggregated_memory_timeline()    : Generate aggregated memory trends over time per config
- plot_memory_comparison()             : Generate 2-panel memory usage comparison
- plot_speed_comparison()              : Generate 2-panel execution time comparison  
- plot_combined_analysis()             : Generate 4-panel comprehensive analysis
- _setup_plot_style()                  : Apply consistent matplotlib styling

All functions are self-contained with descriptive docstrings.
"""

from pathlib import Path
from dataclasses import dataclass
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Default benchmark configuration parameters
DEFAULT_WORKER_COUNTS = [1, 2, 4]
DEFAULT_CHUNK_SIZES = [10000, 100000]


@dataclass
class BenchmarkRun:
    """Single benchmark execution result containing timing, memory, and record metrics"""
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
    
    Auto-discovers directories matching pattern: aisdk-*_wN_cSIZE
    Extracts timing, memory, and record count metrics from CSV files.
    Aggregates results across all input files/datasets (treats as streaming chunks).
    
    Expected directory structure:
        pipeline_results/
        ├── aisdk-2025-08-31_w1_c10000/
        │   ├── dfsi_results.csv
        │   └── memory_profile.csv
        ├── aisdk-2025-09-01_w1_c10000/
        ├── aisdk-2025-08-31_w2_c10000/
        └── ... (more run directories, aggregated by workers & chunk_size)
    
    Args:
        results_dir: Path to pipeline_results directory
        
    Returns:
        List of BenchmarkRun objects aggregated by workers and chunk_size
    """
    runs = []
    
    for run_dir in results_dir.glob('aisdk-*_w*_c*'):
        if not run_dir.is_dir():
            continue
        
        # Extract config from dirname: aisdk-2025-08-31_w2_c100000
        try:
            name_no_prefix = run_dir.name.replace('aisdk-', '')  # '2025-08-31_w2_c100000'
            parts = name_no_prefix.split('_')  # ['2025-08-31', 'w2', 'c100000']
            # Skip date extraction - treat all files as streaming data
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
            workers=workers,
            chunk_size=chunk_size,
            elapsed_time=elapsed,
            peak_memory=peak_mem,
            records=records
        ))
    
    return sorted(runs, key=lambda x: (x.chunk_size, x.workers))


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
        print(f"[!] Memory CSV not found: {memory_csv}")
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
        
        print(f"[OK] Saved: {output_png.name}")
        return True
        
    except Exception as e:
        print(f"[ERR] Error creating memory timeline: {e}")
        return False


def plot_aggregated_memory_timeline(
    results_dir: Path,
    output_png: Path,
    worker_counts: list[int] = None,
    chunk_sizes: list[int] = None,
) -> bool:
    """
    Create aggregated memory timeline plot showing overall trends over time.
    
    Aggregates memory profiles across all input files for each (workers, chunk_size)
    configuration. Creates multi-panel plot with one panel per configuration,
    showing how memory usage evolves independently of input file boundaries.
    
    Displays average memory usage and variability across multiple runs with same config.
    
    Args:
        results_dir: Path to pipeline_results directory containing benchmark runs
        output_png: Output PNG file path
        worker_counts: List of worker counts to plot (default from function parameter)
        chunk_sizes: List of chunk sizes to plot (default from function parameter)
        
    Returns:
        True if successful, False if no valid data
    """
    if worker_counts is None:
        worker_counts = DEFAULT_WORKER_COUNTS
    if chunk_sizes is None:
        chunk_sizes = DEFAULT_CHUNK_SIZES
    
    try:
        _setup_plot_style()
        
        # Collect memory profiles grouped by (workers, chunk_size)
        aggregated_data = {}
        
        for run_dir in results_dir.glob('aisdk-*_w*_c*'):
            if not run_dir.is_dir():
                continue
            
            # Parse config from dirname
            try:
                name_no_prefix = run_dir.name.replace('aisdk-', '')
                parts = name_no_prefix.split('_')
                workers = int(parts[1].replace('w', ''))
                chunk_size = int(parts[2].replace('c', ''))
            except (ValueError, IndexError):
                continue
            
            key = (workers, chunk_size)
            if key not in aggregated_data:
                aggregated_data[key] = []
            
            memory_csv = run_dir / 'memory_profile.csv'
            if memory_csv.exists():
                try:
                    df = pd.read_csv(memory_csv)
                    aggregated_data[key].append(df)
                except:
                    continue
        
        if not aggregated_data:
            print(f"[!] No memory profile data found in {results_dir}")
            return False
        
        # Create subplots: 2 rows x N cols for chunk sizes and worker configs
        num_configs = len(aggregated_data)
        num_cols = min(3, (num_configs + 1) // 2)
        num_rows = (num_configs + num_cols - 1) // num_cols
        
        fig, axes = plt.subplots(num_rows, num_cols, figsize=(16, 5 * num_rows))
        axes = axes.flatten() if isinstance(axes, np.ndarray) else [axes]
        
        sorted_configs = sorted(aggregated_data.keys())
        
        for idx, (workers, chunk_size) in enumerate(sorted_configs):
            ax = axes[idx]
            dfs = aggregated_data[(workers, chunk_size)]
            
            if not dfs:
                continue
            
            # Plot each run with some transparency
            for df in dfs:
                ax.plot(df['elapsed_time_sec'], df['total_rss_mb'],
                       alpha=0.4, linewidth=1.5, color='steelblue')
            
            # Plot average line with higher visibility
            min_len = min(len(df) for df in dfs)
            time_points = dfs[0]['elapsed_time_sec'].iloc[:min_len].values
            avg_memory = np.mean([df['total_rss_mb'].iloc[:min_len].values for df in dfs], axis=0)
            ax.plot(time_points, avg_memory, color='darkblue', linewidth=2.5, 
                   label='Average', marker='o', markersize=4)
            
            # Add shaded confidence band
            std_memory = np.std([df['total_rss_mb'].iloc[:min_len].values for df in dfs], axis=0)
            ax.fill_between(time_points, avg_memory - std_memory, avg_memory + std_memory,
                           alpha=0.2, color='steelblue', label='±1 SD')
            
            ax.set_xlabel('Elapsed Time (seconds)', fontsize=10, fontweight='bold')
            ax.set_ylabel('Memory (MB)', fontsize=10, fontweight='bold')
            ax.set_title(f'Workers: {workers}, Chunk: {chunk_size:,}', fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.legend(loc='best', fontsize=9)
        
        # Remove empty subplots
        for idx in range(len(sorted_configs), len(axes)):
            fig.delaxes(axes[idx])
        
        plt.suptitle('Aggregated Memory Timeline (Combined Input Files)', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(output_png, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"[OK] Saved: {output_png.name}")
        return True
        
    except Exception as e:
        print(f"[ERR] Error creating aggregated memory timeline: {e}")
        return False


# ==============================================================================
# COMPARISON PLOT GENERATORS
# ==============================================================================

def plot_memory_comparison(
    runs: list[BenchmarkRun],
    output_png: Path,
    chunk_sizes: list[int] = None,
) -> bool:
    """
    Create 2-panel memory usage comparison plot (one panel per chunk size).
    
    Left panel shows peak memory vs worker count for first chunk size.
    Right panel shows peak memory vs worker count for second chunk size.
    Data aggregated across all input files (treated as unified chunk stream).
    
    Helps identify memory scaling characteristics with parallelism.
    
    Args:
        runs: List of BenchmarkRun objects from all configurations
        output_png: Output PNG file path
        chunk_sizes: List of chunk sizes to plot (default: [10000, 100000])
        
    Returns:
        True if successful, False if no valid data
    """
    if chunk_sizes is None:
        chunk_sizes = DEFAULT_CHUNK_SIZES
    
    try:
        _setup_plot_style()
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        
        for chunk_idx, chunk_size in enumerate(chunk_sizes[:2]):  # Only show first 2 sizes
            ax = axes[chunk_idx]
            
            data = [r for r in runs if r.chunk_size == chunk_size]
            if not data:
                continue
            
            workers = sorted(set([r.workers for r in data]))
            memory = [next(r.peak_memory for r in data if r.workers == w) for w in workers]
            ax.plot(workers, memory, marker='o', linewidth=2.5, markersize=8, color='steelblue', label='Aggregated')
            
            ax.set_xlabel('Number of Workers', fontsize=11, fontweight='bold')
            ax.set_ylabel('Peak Memory (MB)', fontsize=11, fontweight='bold')
            ax.set_title(f'Chunk Size: {chunk_size:,}', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.4)
            ax.set_xticks(workers)
        
        plt.suptitle('Memory Usage Comparison', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(output_png, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"[OK] Saved: {output_png.name}")
        return True
    except Exception as e:
        print(f"[ERR] Error generating memory comparison: {e}")
def plot_speed_comparison(
    runs: list[BenchmarkRun],
    output_png: Path,
    chunk_sizes: list[int] = None,
) -> bool:
    """
    Create 2-panel execution time comparison plot (one panel per chunk size).
    
    Left panel shows execution time vs worker count for first chunk size.
    Right panel shows execution time vs worker count for second chunk size.
    Data aggregated across all input files (treated as unified chunk stream).
    
    Helps identify optimal worker count and chunk size trade-offs.
    
    Args:
        runs: List of BenchmarkRun objects from all configurations
        output_png: Output PNG file path
        chunk_sizes: List of chunk sizes to plot (default: [10000, 100000])
        
    Returns:
        True if successful, False if no valid data
    """
    if chunk_sizes is None:
        chunk_sizes = DEFAULT_CHUNK_SIZES
    
    try:
        _setup_plot_style()
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        
        for chunk_idx, chunk_size in enumerate(chunk_sizes[:2]):  # Only show first 2 sizes
            ax = axes[chunk_idx]
            
            data = [r for r in runs if r.chunk_size == chunk_size]
            if not data:
                continue
            
            workers = sorted(set([r.workers for r in data]))
            times = [next(r.elapsed_time for r in data if r.workers == w) for w in workers]
            ax.plot(workers, times, marker='s', linewidth=2.5, markersize=8, color='seagreen', label='Aggregated')
            
            ax.set_xlabel('Number of Workers', fontsize=11, fontweight='bold')
            ax.set_ylabel('Execution Time (seconds)', fontsize=11, fontweight='bold')
            ax.set_title(f'Chunk Size: {chunk_size:,}', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.4)
            ax.set_xticks(workers)
        
        plt.suptitle('Execution Speed Comparison', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(output_png, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"[OK] Saved: {output_png.name}")
        return True
    except Exception as e:
        print(f"[ERR] Error generating speed comparison: {e}")
        return False


def plot_combined_analysis(
    runs: list[BenchmarkRun],
    output_png: Path,
    chunk_sizes: list[int] = None,
) -> bool:
    """
    Create 4-panel combined performance analysis plot.
    
    Layout:
    - Top-left: Memory usage for first chunk size
    - Top-right: Memory usage for second chunk size
    - Bottom-left: Execution time for first chunk size
    - Bottom-right: Execution time for second chunk size
    
    Data aggregated across all input files (unified chunk stream).
    Provides comprehensive overview of all performance metrics in single figure.
    
    Args:
        runs: List of BenchmarkRun objects from all configurations
        output_png: Output PNG file path
        chunk_sizes: List of chunk sizes to plot (default: [10000, 100000])
        
    Returns:
        True if successful, False if no valid data
    """
    if chunk_sizes is None:
        chunk_sizes = DEFAULT_CHUNK_SIZES
    
    try:
        _setup_plot_style()
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # Create metrics for first 2 chunk sizes only
        metrics = [
            (0, 'memory', chunk_sizes[0], 'Memory (MB)'),
            (1, 'memory', chunk_sizes[1] if len(chunk_sizes) > 1 else chunk_sizes[0], 'Memory (MB)'),
            (2, 'speed', chunk_sizes[0], 'Time (sec)'),
            (3, 'speed', chunk_sizes[1] if len(chunk_sizes) > 1 else chunk_sizes[0], 'Time (sec)'),
        ]
        
        colors = ['steelblue', 'seagreen']
        
        for idx, metric_type, chunk_size, ylabel in metrics:
            ax = axes[idx // 2, idx % 2]
            
            data = [r for r in runs if r.chunk_size == chunk_size]
            if not data:
                continue
            
            workers = sorted(set([r.workers for r in data]))
            if metric_type == 'memory':
                values = [next(r.peak_memory for r in data if r.workers == w) for w in workers]
                color = colors[0]
            else:
                values = [next(r.elapsed_time for r in data if r.workers == w) for w in workers]
                color = colors[1]
            
            ax.plot(workers, values, marker='o', linewidth=2.5, markersize=7, color=color, label='Aggregated')
            
            chunk_label = f"{chunk_size//1000}K"
            metric_label = "Memory" if metric_type == 'memory' else "Time"
            ax.set_xlabel('Workers', fontsize=11, fontweight='bold')
            ax.set_ylabel(ylabel, fontsize=11, fontweight='bold')
            ax.set_title(f'{metric_label} - {chunk_label} chunks', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.4)
            ax.set_xticks(workers)
        
        plt.suptitle('Performance Analysis Summary', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(output_png, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"[OK] Saved: {output_png.name}")
        return True
    except Exception as e:
        print(f"[ERR] Error generating combined analysis: {e}")
        return False
