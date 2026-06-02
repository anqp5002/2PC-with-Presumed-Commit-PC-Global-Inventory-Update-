from __future__ import annotations

import csv

from participant.inventory_store import InventoryStore
from participant.log_store import ParticipantLogStore
from participant.models import Decision, ParticipantState
from participant.recovery import RecoveryManager
from scripts.data_config import CSV_FIELDNAMES
from scripts.init_databases import init_site_database


def write_partition(path, quantity_available: int = 100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "inventory_id": "INV-REC-001",
        "sku": "SKU-0001",
        "product_name": "Recovery Product",
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
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(row)


def update(delta_quantity: int = -5) -> dict[str, object]:
    return {
        "inventory_id": "INV-REC-001",
        "warehouse_id": "WH001",
        "region": "North",
        "delta_quantity": delta_quantity,
    }


def make_recovery(tmp_path, transaction_id: str = "T-recovery"):
    partition_file = tmp_path / "site_a_inventory.csv"
    db_file = tmp_path / "inventory.sqlite"
    write_partition(partition_file)
    init_site_database("site_a", partition_file=partition_file, db_file=db_file)
    inventory_store = InventoryStore("site_a", "North", partition_file, db_file)
    log_store = ParticipantLogStore("site_a", tmp_path / "site_a_log.jsonl")
    log_store.append(transaction_id, "INIT", "PREPARE_RECEIVED")
    log_store.append(
        transaction_id,
        "READY",
        "READY",
        payload={"updates": [update()]},
    )
    states: dict[str, ParticipantState] = {}
    recovery = RecoveryManager(
        site_id="site_a",
        coordinator_url="http://coordinator",
        log_store=log_store,
        state_registry=states,
        inventory_store=inventory_store,
    )
    return recovery, log_store, inventory_store, states


def test_recovery_ready_and_commit_applies_inventory(tmp_path) -> None:
    recovery, log_store, inventory_store, states = make_recovery(tmp_path, "T-commit")

    result = recovery.recover_pending(lambda transaction_id: Decision.COMMIT)

    assert result["status"] == "ok"
    assert states["T-commit"] == ParticipantState.COMMIT
    assert log_store.has_event("T-commit", "RECOVERY_QUERY")
    assert log_store.has_event("T-commit", "APPLIED_COMMIT")
    assert inventory_store.get_inventory_item("INV-REC-001")["quantity_available"] == 95


def test_recovery_ready_and_not_found_presumes_commit(tmp_path) -> None:
    recovery, log_store, inventory_store, states = make_recovery(tmp_path, "T-presumed")

    result = recovery.recover_pending(lambda transaction_id: Decision.NOT_FOUND)

    assert result["status"] == "ok"
    assert states["T-presumed"] == ParticipantState.COMMIT
    assert log_store.has_event("T-presumed", "RECOVERY_DECISION")
    assert inventory_store.get_inventory_item("INV-REC-001")["quantity_available"] == 95


def test_recovery_after_global_commit_received_does_not_query_coordinator(tmp_path) -> None:
    recovery, log_store, inventory_store, states = make_recovery(
        tmp_path,
        "T-global-commit-received",
    )
    log_store.append(
        "T-global-commit-received",
        "READY",
        "GLOBAL_COMMIT_RECEIVED",
        payload={"mode": "PC_WITH_ACD"},
    )

    def fail_lookup(transaction_id: str) -> Decision:
        raise AssertionError("coordinator lookup should not be called")

    result = recovery.recover_pending(fail_lookup)

    assert result["status"] == "ok"
    assert states["T-global-commit-received"] == ParticipantState.COMMIT
    assert inventory_store.get_inventory_item("INV-REC-001")["quantity_available"] == 95
    assert not log_store.has_event("T-global-commit-received", "RECOVERY_QUERY")
