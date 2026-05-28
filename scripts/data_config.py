from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
PARTITION_DIR = DATA_DIR / "partitions"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
DATASET_PATH = DATA_DIR / "Warehouse_Inventory.csv"
FRAGMENTATION_SUMMARY_PATH = DATA_DIR / "fragmentation_summary.json"

TOTAL_WAREHOUSES = 20
SKUS_PER_WAREHOUSE = 250
EXPECTED_TOTAL_ROWS = TOTAL_WAREHOUSES * SKUS_PER_WAREHOUSE
EXPECTED_PARTITION_ROWS = EXPECTED_TOTAL_ROWS // 4
RANDOM_SEED = 20260524

SITE_REGION_MAP = {
    "site_a": "North",
    "site_b": "Central",
    "site_c": "SouthEast",
    "site_d": "Mekong",
}

SITE_WAREHOUSE_RANGES = {
    "site_a": range(1, 6),
    "site_b": range(6, 11),
    "site_c": range(11, 16),
    "site_d": range(16, 21),
}

WAREHOUSE_SITE_MAP = {
    f"WH{warehouse_number:03d}": site_id
    for site_id, warehouse_range in SITE_WAREHOUSE_RANGES.items()
    for warehouse_number in warehouse_range
}

WAREHOUSE_REGION_MAP = {
    warehouse_id: SITE_REGION_MAP[site_id]
    for warehouse_id, site_id in WAREHOUSE_SITE_MAP.items()
}

CATEGORY_LIST = [
    "Electronics",
    "Home",
    "Grocery",
    "Fashion",
    "Industrial",
]

CSV_FIELDNAMES = [
    "inventory_id",
    "sku",
    "product_name",
    "category",
    "warehouse_id",
    "warehouse_name",
    "region",
    "quantity_available",
    "reserved_quantity",
    "unit_cost",
    "reorder_level",
    "version",
    "updated_at",
]


def partition_path(site_id: str) -> Path:
    return PARTITION_DIR / f"{site_id}_inventory.csv"


def runtime_db_path(site_id: str) -> Path:
    return RUNTIME_DIR / site_id / "inventory.sqlite"


def site_for_region(region: str) -> str:
    for site_id, site_region in SITE_REGION_MAP.items():
        if site_region == region:
            return site_id
    raise ValueError(f"Unknown region: {region}")

