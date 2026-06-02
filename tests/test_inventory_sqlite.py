from __future__ import annotations

import csv

from participant.inventory_store import InventoryStore
from scripts.data_config import CSV_FIELDNAMES
from scripts.init_databases import init_site_database


def write_partition(path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def inventory_row(quantity_available: int = 100) -> dict[str, str]:
    return {
        "inventory_id": "INV-TEST-001",
        "sku": "SKU-0001",
        "product_name": "Test Product",
        "category": "Electronics",
        "warehouse_id": "WH001",
        "warehouse_name": "North Warehouse 001",
        "region": "North",
        "quantity_available": str(quantity_available),
        "reserved_quantity": "0",
        "unit_cost": "10.50",
        "reorder_level": "10",
        "version": "1",
        "updated_at": "2026-05-28T00:00:00+00:00",
    }


def test_init_site_database_imports_partition_rows(tmp_path) -> None:
    partition_file = tmp_path / "site_a_inventory.csv"
    db_file = tmp_path / "inventory.sqlite"
    write_partition(partition_file, [inventory_row()])

    summary = init_site_database(
        "site_a",
        partition_file=partition_file,
        db_file=db_file,
    )
    store = InventoryStore(
        "site_a",
        "North",
        partition_file=partition_file,
        db_file=db_file,
    )

    assert summary["row_count"] == 1
    assert db_file.exists()
    assert store.get_inventory_item("INV-TEST-001")["quantity_available"] == 100


def test_apply_commit_is_idempotent_by_transaction_id(tmp_path) -> None:
    partition_file = tmp_path / "site_a_inventory.csv"
    db_file = tmp_path / "inventory.sqlite"
    write_partition(partition_file, [inventory_row(quantity_available=100)])
    init_site_database("site_a", partition_file=partition_file, db_file=db_file)
    store = InventoryStore("site_a", "North", partition_file, db_file)
    updates = [
        {
            "inventory_id": "INV-TEST-001",
            "warehouse_id": "WH001",
            "region": "North",
            "delta_quantity": -7,
        }
    ]

    first = store.apply_commit("T-idempotent", updates)
    second = store.apply_commit("T-idempotent", updates)
    item = store.get_inventory_item("INV-TEST-001")

    assert first["applied"] is True
    assert second["already_applied"] is True
    assert item["quantity_available"] == 93


def test_validate_rejects_insufficient_stock(tmp_path) -> None:
    partition_file = tmp_path / "site_a_inventory.csv"
    db_file = tmp_path / "inventory.sqlite"
    write_partition(partition_file, [inventory_row(quantity_available=3)])
    init_site_database("site_a", partition_file=partition_file, db_file=db_file)
    store = InventoryStore("site_a", "North", partition_file, db_file)

    valid, reason = store.validate_updates(
        [
            {
                "inventory_id": "INV-TEST-001",
                "warehouse_id": "WH001",
                "region": "North",
                "delta_quantity": -4,
            }
        ]
    )

    assert valid is False
    assert reason == "INV-TEST-001 has insufficient stock"
