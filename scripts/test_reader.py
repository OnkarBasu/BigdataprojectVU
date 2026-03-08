import time
from pathlib import Path

from src.streaming import stream_csv_in_chunks


FILE_PATH = Path("data/sample/2025-09-01_head_100_000_rows.csv")
CHUNK_SIZE = 5000
MAX_CHUNKS_TO_SHOW = 3


def main() -> None:
    total_records = 0
    total_chunks = 0
    start = time.perf_counter()

    for chunk_id, chunk in stream_csv_in_chunks(FILE_PATH, chunk_size=CHUNK_SIZE):
        total_chunks += 1
        total_records += len(chunk)

        if chunk_id <= MAX_CHUNKS_TO_SHOW:
            print(f"Chunk {chunk_id}: {len(chunk)} records")

            if chunk:
                print("  First record:", chunk[0])
                print("  Last record: ", chunk[-1])
                print()

    elapsed = time.perf_counter() - start

    print(f"Total chunks: {total_chunks}")
    print(f"Total valid records: {total_records}")
    print(f"Elapsed time: {elapsed:.2f}s")

    if elapsed > 0:
        print(f"Records/sec: {total_records / elapsed:.0f}")


if __name__ == "__main__":
    main()
