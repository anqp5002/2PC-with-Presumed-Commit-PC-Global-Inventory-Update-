from __future__ import annotations

import csv

from data_config import (
    CSV_FIELDNAMES,
    DATASET_PATH,
    PARTITION_DIR,
    SITE_REGION_MAP,
    partition_path,
    site_for_region,
)


def read_dataset() -> list[dict[str, str]]:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"{DATASET_PATH} does not exist. Run scripts/generate_dataset.py first."
        )

    with DATASET_PATH.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def partition_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    partitions: dict[str, list[dict[str, str]]] = {
        site_id: [] for site_id in SITE_REGION_MAP
    }

    for row in rows:
        site_id = site_for_region(row["region"])
        partitions[site_id].append(row)

    return partitions


def write_partitions(partitions: dict[str, list[dict[str, str]]]) -> None:
    PARTITION_DIR.mkdir(parents=True, exist_ok=True)

    for site_id, rows in partitions.items():
        path = partition_path(site_id)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} rows to {path}")


def main() -> None:
    rows = read_dataset()
    partitions = partition_rows(rows)
    write_partitions(partitions)


if __name__ == "__main__":
    main()

