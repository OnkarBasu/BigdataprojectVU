import csv
from pathlib import Path

from src.streaming import AISRowParser


FILE_PATH = Path("data/sample/head_100_000_rows.csv")


def main():
    parsed = 0
    skipped = 0

    with open(FILE_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        parser = AISRowParser(reader.fieldnames)

        for row in reader:
            record = parser.parse_row(row)

            if record is None:
                skipped += 1
            else:
                parsed += 1

                if parsed <= 5:
                    print(record)

    print()
    print("Parsed records:", parsed)
    print("Skipped rows:", skipped)


if __name__ == "__main__":
    main()
