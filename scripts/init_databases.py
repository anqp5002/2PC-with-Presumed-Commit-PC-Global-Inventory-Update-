from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

try:
    from scripts.data_config import CSV_FIELDNAMES, SITE_REGION_MAP, partition_path, runtime_db_path
except ModuleNotFoundError:
    from data_config import CSV_FIELDNAMES, SITE_REGION_MAP, partition_path, runtime_db_path


INVENTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    inventory_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    warehouse_id TEXT NOT NULL,
    warehouse_name TEXT NOT NULL,
    region TEXT NOT NULL,
    quantity_available INTEGER NOT NULL,
    reserved_quantity INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    reorder_level INTEGER NOT NULL,
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""

APPLIED_TRANSACTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS applied_transactions (
    transaction_id TEXT PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    update_count INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);
"""


def _coerce_row(row: dict[str, str]) -> tuple[object, ...]:
    return (
        row["inventory_id"],
        row["sku"],
        row["product_name"],
        row["category"],
        row["warehouse_id"],
        row["warehouse_name"],
        row["region"],
        int(row["quantity_available"]),
        int(row["reserved_quantity"]),
        float(row["unit_cost"]),
        int(row["reorder_level"]),
        int(row["version"]),
        row["updated_at"],
    )


def init_site_database(
    site_id: str,
    partition_file: Path | None = None,
    db_file: Path | None = None,
    reset: bool = True,
) -> dict[str, object]:
    if site_id not in SITE_REGION_MAP:
        raise ValueError(f"Unknown site_id: {site_id}")

    partition_file = partition_file or partition_path(site_id)
    db_file = db_file or runtime_db_path(site_id)
    if not partition_file.exists():
        raise FileNotFoundError(f"Partition file not found: {partition_file}")

    if reset and db_file.exists():
        db_file.unlink()

    db_file.parent.mkdir(parents=True, exist_ok=True)
    with partition_file.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with sqlite3.connect(db_file) as conn:
        conn.execute(INVENTORY_SCHEMA)
        conn.execute(APPLIED_TRANSACTIONS_SCHEMA)
        conn.execute("DELETE FROM inventory")
        conn.execute("DELETE FROM applied_transactions")
        conn.executemany(
            f"""
            INSERT INTO inventory ({", ".join(CSV_FIELDNAMES)})
            VALUES ({", ".join("?" for _ in CSV_FIELDNAMES)})
            """,
            [_coerce_row(row) for row in rows],
        )
        conn.commit()

    return {
        "site_id": site_id,
        "region": SITE_REGION_MAP[site_id],
        "partition_file": str(partition_file),
        "db_file": str(db_file),
        "row_count": len(rows),
    }


def init_all_databases(reset: bool = True) -> list[dict[str, object]]:
    return [
        init_site_database(site_id, reset=reset)
        for site_id in SITE_REGION_MAP
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize local SQLite inventory databases from CSV partitions."
    )
    parser.add_argument(
        "--site",
        choices=sorted(SITE_REGION_MAP),
        help="Initialize only one site. Omit to initialize all sites.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete an existing SQLite file before importing data.",
    )
    args = parser.parse_args()

    if args.site:
        summaries = [
            init_site_database(args.site, reset=not args.keep_existing)
        ]
    else:
        summaries = init_all_databases(reset=not args.keep_existing)

    for summary in summaries:
        print(
            f"{summary['site_id']} ({summary['region']}): "
            f"{summary['row_count']} rows -> {summary['db_file']}"
        )


if __name__ == "__main__":
    main()
