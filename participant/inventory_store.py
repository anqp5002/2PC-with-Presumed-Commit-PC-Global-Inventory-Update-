from __future__ import annotations


class InventoryStore:
    """Placeholder for the future SQLite-backed local inventory store."""

    def get_inventory_item(self, inventory_id: str) -> dict[str, str]:
        return {
            "inventory_id": inventory_id,
            "status": "stub",
            "message": "SQLite inventory store will be implemented in a later phase",
        }


inventory_store = InventoryStore()

