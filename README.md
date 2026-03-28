# BigdataprojectVU

Shadow Fleet Anomaly Detection on AIS Data

---

## Project task

The goal of this project is to process large-scale AIS (Automatic Identification System) data and detect suspicious vessel behavior associated with the so-called *shadow fleet*.

The system identifies several types of anomalies:

- **A — Going Dark**  
  Long AIS gaps where the vessel likely continued moving.

- **B — Loitering & Transfers**  
  Two vessels staying close together at low speed for a prolonged time at sea.

- **C — Draft Changes at Sea**  
  Significant draught changes during AIS blackout outside port areas.

- **D — Identity Issues (Teleportation)**  
  - **D1**: near-simultaneous MMSI cloning  
  - **D2**: impossible relocation requiring unrealistic speed  

Finally, each vessel is assigned a **DFSI (Dark Fleet Suspicion Index)** score.

---

## Main detection pipeline

```mermaid
flowchart TD
    A[Input AIS CSV file(s)] --> B[Main process: stream raw rows]
    B --> C[Extract required columns only]
    C --> D[Split stream into chunks]

    D --> E[Worker pool]
    E --> F[Parse and validate raw rows]
    F --> G[Group records by MMSI]
    G --> H[Sort records inside each vessel]

    H --> I[Downsample records for A and C]
    H --> J[Use full-resolution records for D]

    I --> K[Detect anomaly A<br/>Going Dark]
    I --> L[Detect anomaly C<br/>Draft Change at Sea]
    J --> M[Detect anomaly D<br/>D1 / D2 Teleportation]

    K --> N[Build VesselChunkSummary]
    L --> N
    M --> N

    N --> O[Main process: collect chunk results]
    O --> P[Ordered merge by chunk_id]
    P --> Q[Cross-chunk boundary anomaly detection]

    Q --> R{Loitering detection enabled?}
    R -- Yes --> S[Detect anomaly B<br/>Loitering & Transfers]
    R -- No --> T[Skip anomaly B]

    S --> U[Attach anomaly B events]
    T --> V[Compute DFSI]
    U --> V

    V --> W[Rank vessels]
    W --> X[Write dfsi_results.csv]
    W --> Y[Write memory_profile.csv]
    W --> Z[Write map visualization CSVs]
```

### Pipeline explanation

The pipeline is designed as a **streaming + multiprocessing system**:

- The **main process** performs lightweight work:
  - reading CSV files
  - extracting required columns
  - splitting data into chunks

- **Worker processes** handle heavy computation:
  - parsing and validating AIS data
  - grouping by vessel (MMSI)
  - detecting anomalies A, C, and D

- The **main process merges results in strict order**:
  - ensures correct detection across chunk boundaries
  - aggregates global vessel statistics

- Optional step:
  - anomaly B (loitering) is computed **after full merge**

- Final stage:
  - DFSI is computed
  - results and visualization datasets are exported

---

## Project structure

```text
.
├── data/
│   ├── full/              # full AIS dataset placeholder / input location
│   ├── output/            # detection results and exported CSV files
│   ├── sample/            # sample AIS datasets for testing
│   └── ports_dma_region.csv
├── scripts/
│   └── run_detection.py   # main CLI entry point
├── slides/
│   └── presentation.pdf
├── src/
│   ├── anomaly_detection/ # anomaly rules, merge logic, DFSI scoring
│   ├── models/            # AIS records, events, processing summaries
│   ├── parallel/          # worker pool logic
│   ├── performance/       # memory profiling
│   ├── streaming/         # CSV reading, raw row extraction, chunking
│   ├── utils/             # geo and port utilities
│   └── config.py
├── visualization/         # plotting and map generation scripts
├── CONTRIBUTING.md
├── README.md
└── requirements.txt
```

---

## Output files

- dfsi_results.csv — final ranking of vessels  
- memory_profile.csv — memory usage over time  
- visualization datasets for anomalies A, B, D  

---

## How to run

### Minimal example

```bash
python -m scripts.run_detection data/sample/2025-09-01_head_100_000_rows.csv \
    --chunk-size 100000 \
    --workers 4
```

### Example with optional arguments
```bash
python -m scripts.run_detection \
    data/sample/2025-09-01_head_100_000_rows.csv \
    --chunk-size 100000 \
    --workers 4 \
    --top 10 \
    --output data/output/dfsi_results.csv \
    --memory-output data/output/memory_profile.csv \
    --teleportation-d1-viz-output data/output/top_teleportation_d1_vessel_map.csv \
    --teleportation-d2-viz-output data/output/top_teleportation_d2_vessel_map.csv \
    --going-dark-viz-output data/output/top_going_dark_vessel_map.csv \
    --loitering-viz-output data/output/top_loitering_vessel_map.csv \
    --enable-loitering-detection
```

### Main arguments

| Main argument              | Desc |
|----------------------------|------|
| input_files                | one or more AIS CSV files |
| chunk-size                 | number of raw rows per chunk |
| workers                    | number of worker processes |
| top                        | number of top vessels to display |
| output                     | final DFSI results CSV |
| memory-output              | memory profiling CSV |
| enable-loitering-detection | enables anomaly B detection |


---

## DFSI formula

```
DFSI = (Max Gap Hours / 2)
     + (D2 Distance in Nautical Miles / 10)
     + (Draft Changes * 15)
```

---

## Contributing
Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for the branching strategy, pull request process, and repository workflow.