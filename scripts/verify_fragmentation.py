from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from data_config import (
    DATASET_PATH,
    EXPECTED_PARTITION_ROWS,
    EXPECTED_TOTAL_ROWS,
    FRAGMENTATION_SUMMARY_PATH,
    SITE_REGION_MAP,
    WAREHOUSE_SITE_MAP,
    partition_path,
)


def read_csv(path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required CSV file: {path}")
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def pass_fail(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def verify() -> dict[str, Any]:
    """Verify primary horizontal fragmentation correctness.

    TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 2):
    A horizontal fragmentation design must preserve completeness,
    reconstruction, and disjointness. The checks below compare the master
    relation's inventory_id set with the union of all region fragments and
    verify that each fragment satisfies its region predicate.
    """

    master_rows = read_csv(DATASET_PATH)
    master_by_id = {row["inventory_id"]: row for row in master_rows}

    partitions = {
        site_id: read_csv(partition_path(site_id)) for site_id in SITE_REGION_MAP
    }
    partition_rows = [row for rows in partitions.values() for row in rows]
    partition_ids = [row["inventory_id"] for row in partition_rows]
    partition_id_set = set(partition_ids)
    master_id_set = set(master_by_id)
    duplicate_partition_ids = sorted(
        inventory_id
        for inventory_id, count in Counter(partition_ids).items()
        if count > 1
    )

    row_count_check = len(master_rows) == EXPECTED_TOTAL_ROWS
    partition_count_checks = {
        site_id: len(rows) == EXPECTED_PARTITION_ROWS
        for site_id, rows in partitions.items()
    }
    completeness_check = master_id_set.issubset(partition_id_set)
    reconstruction_check = master_id_set == partition_id_set and len(
        partition_rows
    ) == len(master_rows)
    disjointness_check = not duplicate_partition_ids

    predicate_checks: dict[str, bool] = {}
    warehouse_allocation_checks: dict[str, bool] = {}

    for site_id, rows in partitions.items():
        expected_region = SITE_REGION_MAP[site_id]
        predicate_checks[site_id] = all(
            row["region"] == expected_region for row in rows
        )
        warehouse_allocation_checks[site_id] = all(
            WAREHOUSE_SITE_MAP[row["warehouse_id"]] == site_id for row in rows
        )

    checks = {
        "dataset_row_count": row_count_check,
        "partition_row_counts": all(partition_count_checks.values()),
        "completeness": completeness_check,
        "reconstruction": reconstruction_check,
        "disjointness": disjointness_check,
        "predicate_correctness": all(predicate_checks.values()),
        "warehouse_allocation": all(warehouse_allocation_checks.values()),
    }

    summary = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "textbook_alignment": {
            "fragmentation_type": "Primary horizontal fragmentation",
            "relation": "Warehouse_Inventory",
            "simple_predicates": {
                "p1": "region = 'North'",
                "p2": "region = 'Central'",
                "p3": "region = 'SouthEast'",
                "p4": "region = 'Mekong'",
            },
            "fragment_formulas": {
                "Inventory_North": "select region='North' from Warehouse_Inventory",
                "Inventory_Central": "select region='Central' from Warehouse_Inventory",
                "Inventory_SouthEast": "select region='SouthEast' from Warehouse_Inventory",
                "Inventory_Mekong": "select region='Mekong' from Warehouse_Inventory",
            },
            "allocation": {
                "Inventory_North": "site_a",
                "Inventory_Central": "site_b",
                "Inventory_SouthEast": "site_c",
                "Inventory_Mekong": "site_d",
            },
        },
        "expected": {
            "total_rows": EXPECTED_TOTAL_ROWS,
            "partition_rows": EXPECTED_PARTITION_ROWS,
        },
        "actual": {
            "total_rows": len(master_rows),
            "partition_rows": {
                site_id: len(rows) for site_id, rows in partitions.items()
            },
        },
        "checks": {name: pass_fail(result) for name, result in checks.items()},
        "details": {
            "duplicate_partition_ids": duplicate_partition_ids,
            "missing_from_partitions": sorted(master_id_set - partition_id_set),
            "extra_in_partitions": sorted(partition_id_set - master_id_set),
            "predicate_checks": {
                site_id: pass_fail(result)
                for site_id, result in predicate_checks.items()
            },
            "warehouse_allocation_checks": {
                site_id: pass_fail(result)
                for site_id, result in warehouse_allocation_checks.items()
            },
        },
    }

    FRAGMENTATION_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRAGMENTATION_SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    summary = verify()
    print("Fragmentation verification")
    for name, result in summary["checks"].items():
        print(f"- {name}: {result}")
    print(f"Summary written to {FRAGMENTATION_SUMMARY_PATH}")

    if any(result != "PASS" for result in summary["checks"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

