from __future__ import annotations

import csv
from pathlib import Path

from participant.models import InventoryUpdateItem
from scripts.data_config import SITE_REGION_MAP, partition_path


class InventoryStore:
    """CSV-backed validation layer for the current participant.

    Phase 3 validates local data and transaction feasibility only. It does not
    mutate CSV rows. Durable inventory mutation is introduced later with SQLite.
    """

    def __init__(self, site_id: str, region: str, partition_file: Path | None = None):
        self.site_id = site_id
        self.region = region
        self.partition_file = partition_file or partition_path(site_id)
        self._rows_by_id: dict[str, dict[str, str]] | None = None

    def _load_rows(self) -> dict[str, dict[str, str]]:
        if self._rows_by_id is None:
            if not self.partition_file.exists():
                self._rows_by_id = {}
            else:
                with self.partition_file.open("r", newline="", encoding="utf-8") as f:
                    self._rows_by_id = {
                        row["inventory_id"]: row for row in csv.DictReader(f)
                    }
        return self._rows_by_id

    def get_inventory_item(self, inventory_id: str) -> dict[str, str]:
        row = self._load_rows().get(inventory_id)
        if row is None:
            return {
                "inventory_id": inventory_id,
                "status": "not_found",
                "message": f"{inventory_id} is not stored at {self.site_id}",
            }
        return row

    def validate_updates(self, updates: list[InventoryUpdateItem]) -> tuple[bool, str | None]:
        expected_region = SITE_REGION_MAP[self.site_id]
        rows = self._load_rows()

        for update in updates:
            row = rows.get(update.inventory_id)
            if row is None:
                return False, f"{update.inventory_id} is not stored at {self.site_id}"

            if update.region != expected_region or row["region"] != expected_region:
                return (
                    False,
                    f"{update.inventory_id} belongs to {row.get('region')} not {expected_region}",
                )

            if update.warehouse_id != row["warehouse_id"]:
                return (
                    False,
                    f"{update.inventory_id} warehouse mismatch: {update.warehouse_id}",
                )

            quantity_available = int(row["quantity_available"])
            if update.delta_quantity < 0 and quantity_available + update.delta_quantity < 0:
                return (
                    False,
                    f"{update.inventory_id} has insufficient stock",
                )

        return True, None

