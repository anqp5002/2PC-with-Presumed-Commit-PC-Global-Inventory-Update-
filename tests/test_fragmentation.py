from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from data_config import (  # noqa: E402
    DATASET_PATH,
    EXPECTED_PARTITION_ROWS,
    EXPECTED_TOTAL_ROWS,
    SITE_REGION_MAP,
    WAREHOUSE_SITE_MAP,
    partition_path,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def test_master_dataset_has_5000_rows() -> None:
    rows = read_csv(DATASET_PATH)
    assert len(rows) == EXPECTED_TOTAL_ROWS


def test_each_partition_has_1250_rows() -> None:
    for site_id in SITE_REGION_MAP:
        rows = read_csv(partition_path(site_id))
        assert len(rows) == EXPECTED_PARTITION_ROWS


def test_completeness_every_master_id_appears_in_a_partition() -> None:
    master_rows = read_csv(DATASET_PATH)
    partition_rows = [
        row
        for site_id in SITE_REGION_MAP
        for row in read_csv(partition_path(site_id))
    ]

    master_ids = {row["inventory_id"] for row in master_rows}
    partition_ids = {row["inventory_id"] for row in partition_rows}

    assert master_ids.issubset(partition_ids)


def test_disjointness_no_duplicate_inventory_id_across_partitions() -> None:
    partition_rows = [
        row
        for site_id in SITE_REGION_MAP
        for row in read_csv(partition_path(site_id))
    ]
    id_counts = Counter(row["inventory_id"] for row in partition_rows)

    assert all(count == 1 for count in id_counts.values())


def test_reconstruction_union_of_partitions_matches_master_ids() -> None:
    master_rows = read_csv(DATASET_PATH)
    partition_rows = [
        row
        for site_id in SITE_REGION_MAP
        for row in read_csv(partition_path(site_id))
    ]

    master_ids = {row["inventory_id"] for row in master_rows}
    partition_ids = {row["inventory_id"] for row in partition_rows}

    assert partition_ids == master_ids
    assert len(partition_rows) == len(master_rows)


def test_partition_predicates_match_region_formulas() -> None:
    for site_id, expected_region in SITE_REGION_MAP.items():
        rows = read_csv(partition_path(site_id))
        assert all(row["region"] == expected_region for row in rows)


def test_warehouse_ids_belong_to_expected_site_ranges() -> None:
    for site_id in SITE_REGION_MAP:
        rows = read_csv(partition_path(site_id))
        assert all(WAREHOUSE_SITE_MAP[row["warehouse_id"]] == site_id for row in rows)

