from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from participant.models import InventoryUpdateItem
from scripts.data_config import SITE_REGION_MAP, partition_path, runtime_db_path


class InventoryStore:
    """SQLite-backed inventory store for the current participant.

    Phase 4 keeps the CSV partitions immutable and uses SQLite files in
    runtime/site_x/ as the local site databases. This lets crash-recovery tests
    prove idempotent apply without corrupting the original 5,000-row dataset.
    """

    def __init__(
        self,
        site_id: str,
        region: str,
        partition_file: Path | None = None,
        db_file: Path | None = None,
    ):
        self.site_id = site_id
        self.region = region
        self.partition_file = partition_file or partition_path(site_id)
        self.db_file = db_file or runtime_db_path(site_id)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def _database_ready(self) -> bool:
        return self.db_file.exists()

    def _update_dict(self, update: InventoryUpdateItem | dict[str, Any]) -> dict[str, Any]:
        if isinstance(update, InventoryUpdateItem):
            return update.model_dump(mode="json")
        return dict(update)

    def _normalize_updates(
        self,
        updates: list[InventoryUpdateItem] | list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [self._update_dict(update) for update in updates]

    def _payload_hash(self, updates: list[dict[str, Any]]) -> str:
        payload_json = json.dumps(updates, sort_keys=True, ensure_ascii=False)
        return sha256(payload_json.encode("utf-8")).hexdigest()

    def _validate_updates_with_conn(
        self,
        conn: sqlite3.Connection,
        updates: list[dict[str, Any]],
    ) -> tuple[bool, str | None]:
        expected_region = SITE_REGION_MAP[self.site_id]
        for update in updates:
            row = conn.execute(
                "SELECT * FROM inventory WHERE inventory_id = ?",
                (update["inventory_id"],),
            ).fetchone()
            if row is None:
                return (
                    False,
                    f"{update['inventory_id']} is not stored at {self.site_id}",
                )

            if update["region"] != expected_region or row["region"] != expected_region:
                return (
                    False,
                    f"{update['inventory_id']} belongs to {row['region']} not {expected_region}",
                )

            if update["warehouse_id"] != row["warehouse_id"]:
                return (
                    False,
                    f"{update['inventory_id']} warehouse mismatch: {update['warehouse_id']}",
                )

            quantity_available = int(row["quantity_available"])
            delta_quantity = int(update["delta_quantity"])
            if delta_quantity < 0 and quantity_available + delta_quantity < 0:
                return False, f"{update['inventory_id']} has insufficient stock"

        return True, None

    def get_inventory_item(self, inventory_id: str) -> dict[str, Any]:
        if not self._database_ready():
            return {
                "inventory_id": inventory_id,
                "status": "database_not_initialized",
                "message": f"Run python scripts/init_databases.py before using {self.site_id}",
            }

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM inventory WHERE inventory_id = ?",
                (inventory_id,),
            ).fetchone()

        if row is None:
            return {
                "inventory_id": inventory_id,
                "status": "not_found",
                "message": f"{inventory_id} is not stored at {self.site_id}",
            }
        return dict(row)

    def validate_updates(
        self,
        updates: list[InventoryUpdateItem] | list[dict[str, Any]],
    ) -> tuple[bool, str | None]:
        if not self._database_ready():
            return False, f"SQLite database is not initialized for {self.site_id}"

        normalized_updates = self._normalize_updates(updates)
        with self._connect() as conn:
            return self._validate_updates_with_conn(conn, normalized_updates)

    def apply_commit(
        self,
        transaction_id: str,
        updates: list[InventoryUpdateItem] | list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self._database_ready():
            raise FileNotFoundError(
                f"SQLite database is not initialized for {self.site_id}: {self.db_file}"
            )

        normalized_updates = self._normalize_updates(updates)
        payload_hash = self._payload_hash(normalized_updates)
        applied_at = datetime.now(timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT transaction_id FROM applied_transactions WHERE transaction_id = ?",
                (transaction_id,),
            ).fetchone()
            if existing is not None:
                conn.rollback()
                return {
                    "transaction_id": transaction_id,
                    "applied": False,
                    "already_applied": True,
                    "update_count": len(normalized_updates),
                }

            valid, reason = self._validate_updates_with_conn(conn, normalized_updates)
            if not valid:
                conn.rollback()
                raise ValueError(reason)

            changed_items: list[dict[str, Any]] = []
            for update in normalized_updates:
                row = conn.execute(
                    "SELECT quantity_available, version FROM inventory WHERE inventory_id = ?",
                    (update["inventory_id"],),
                ).fetchone()
                before_quantity = int(row["quantity_available"])
                before_version = int(row["version"])
                after_quantity = before_quantity + int(update["delta_quantity"])
                conn.execute(
                    """
                    UPDATE inventory
                    SET quantity_available = ?,
                        version = ?,
                        updated_at = ?
                    WHERE inventory_id = ?
                    """,
                    (
                        after_quantity,
                        before_version + 1,
                        applied_at,
                        update["inventory_id"],
                    ),
                )
                changed_items.append(
                    {
                        "inventory_id": update["inventory_id"],
                        "before_quantity": before_quantity,
                        "after_quantity": after_quantity,
                    }
                )

            conn.execute(
                """
                INSERT INTO applied_transactions (
                    transaction_id,
                    payload_hash,
                    update_count,
                    applied_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (transaction_id, payload_hash, len(normalized_updates), applied_at),
            )
            conn.commit()

        return {
            "transaction_id": transaction_id,
            "applied": True,
            "already_applied": False,
            "update_count": len(normalized_updates),
            "changed_items": changed_items,
        }

    def rollback(
        self,
        transaction_id: str,
        updates: list[InventoryUpdateItem] | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "transaction_id": transaction_id,
            "rolled_back": True,
            "reason": "no inventory mutation happens before GLOBAL_COMMIT",
            "update_count": len(updates or []),
        }
