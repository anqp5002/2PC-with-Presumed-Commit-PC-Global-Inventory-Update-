from __future__ import annotations

import csv
import random
from decimal import Decimal

from data_config import (
    CATEGORY_LIST,
    CSV_FIELDNAMES,
    DATA_DIR,
    DATASET_PATH,
    RANDOM_SEED,
    SKUS_PER_WAREHOUSE,
    TOTAL_WAREHOUSES,
    WAREHOUSE_REGION_MAP,
)


def build_rows() -> list[dict[str, str]]:
    random.seed(RANDOM_SEED)
    rows: list[dict[str, str]] = []
    categories = CATEGORY_LIST

    for warehouse_number in range(1, TOTAL_WAREHOUSES + 1):
        warehouse_id = f"WH{warehouse_number:03d}"
        region = WAREHOUSE_REGION_MAP[warehouse_id]
        warehouse_name = f"{region} Warehouse {warehouse_number:03d}"

        for sku_number in range(1, SKUS_PER_WAREHOUSE + 1):
            inventory_number = (warehouse_number - 1) * SKUS_PER_WAREHOUSE + sku_number
            category = categories[(sku_number + warehouse_number) % len(categories)]
            base_quantity = random.randint(80, 800)
            reserved_quantity = random.randint(0, min(80, base_quantity // 4))
            reorder_level = random.randint(25, 120)
            unit_cost = Decimal(random.randint(500, 250000)) / Decimal("100")

            rows.append(
                {
                    "inventory_id": f"INV-{inventory_number:06d}",
                    "sku": f"SKU-{sku_number:04d}",
                    "product_name": f"{category} Item {sku_number:04d}",
                    "category": category,
                    "warehouse_id": warehouse_id,
                    "warehouse_name": warehouse_name,
                    "region": region,
                    "quantity_available": str(base_quantity),
                    "reserved_quantity": str(reserved_quantity),
                    "unit_cost": f"{unit_cost:.2f}",
                    "reorder_level": str(reorder_level),
                    "version": "1",
                    "updated_at": "2026-05-24T00:00:00+07:00",
                }
            )

    return rows


def write_dataset(rows: list[dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with DATASET_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = build_rows()
    write_dataset(rows)
    print(f"Generated {len(rows)} rows at {DATASET_PATH}")


if __name__ == "__main__":
    main()

