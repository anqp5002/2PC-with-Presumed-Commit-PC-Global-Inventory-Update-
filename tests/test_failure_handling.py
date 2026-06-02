from __future__ import annotations

import csv

import httpx

import participant.app as participant_app
from coordinator.config import ParticipantConfig
from coordinator.log_store import CoordinatorLogStore
from coordinator.models import Decision, GlobalInventoryUpdateRequest
from coordinator.protocol import CoordinatorProtocol
from participant.inventory_store import InventoryStore
from participant.log_store import ParticipantLogStore
from participant.models import MessageType, ParticipantState, PrepareRequest
from scripts.data_config import CSV_FIELDNAMES
from scripts.init_databases import init_site_database


PARTICIPANTS = {
    "site_a": ParticipantConfig("site_a", "North", "http://site-a"),
    "site_b": ParticipantConfig("site_b", "Central", "http://site-b"),
}


def update(region: str, inventory_id: str, delta_quantity: int = -1) -> dict:
    return {
        "inventory_id": inventory_id,
        "warehouse_id": "WH001" if region == "North" else "WH006",
        "region": region,
        "delta_quantity": delta_quantity,
    }


class TimeoutOnSiteBPrepareProtocol(CoordinatorProtocol):
    def _post_json(self, url: str, payload: dict) -> dict:
        if url.endswith("/prepare") and "site-b" in url:
            raise httpx.TimeoutException("site_b prepare timeout")
        if url.endswith("/prepare"):
            return {
                "transaction_id": payload["transaction_id"],
                "site_id": "site_a",
                "message_type": "VOTE_COMMIT",
                "state": "READY",
                "reason": None,
            }
        if url.endswith("/global-abort"):
            site_id = "site_a" if "site-a" in url else "site_b"
            return {
                "transaction_id": payload["transaction_id"],
                "site_id": site_id,
                "message_type": "ACK_ABORT",
                "state": "ABORT",
                "reason": None,
            }
        raise AssertionError(f"unexpected URL {url}")


class CrashOnSiteBGlobalCommitProtocol(CoordinatorProtocol):
    def _post_json(self, url: str, payload: dict) -> dict:
        if url.endswith("/prepare"):
            site_id = "site_a" if "site-a" in url else "site_b"
            return {
                "transaction_id": payload["transaction_id"],
                "site_id": site_id,
                "message_type": "VOTE_COMMIT",
                "state": "READY",
                "reason": None,
            }
        if url.endswith("/global-commit") and "site-b" in url:
            raise httpx.ConnectError("site_b crashed before ACK_COMMIT")
        if url.endswith("/global-commit"):
            return {
                "transaction_id": payload["transaction_id"],
                "site_id": "site_a",
                "message_type": "ACK_COMMIT",
                "state": "COMMIT",
                "reason": None,
            }
        raise AssertionError(f"unexpected URL {url}")


def test_prepare_insufficient_stock_votes_abort(monkeypatch, tmp_path) -> None:
    partition_file = tmp_path / "site_a_inventory.csv"
    db_file = tmp_path / "inventory.sqlite"
    row = {
        "inventory_id": "INV-LOW-001",
        "sku": "SKU-0001",
        "product_name": "Low Stock Product",
        "category": "Electronics",
        "warehouse_id": "WH001",
        "warehouse_name": "North Warehouse 001",
        "region": "North",
        "quantity_available": "2",
        "reserved_quantity": "0",
        "unit_cost": "10.50",
        "reorder_level": "10",
        "version": "1",
        "updated_at": "2026-05-28T00:00:00+00:00",
    }
    with partition_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(row)
    init_site_database("site_a", partition_file=partition_file, db_file=db_file)

    monkeypatch.setattr(
        participant_app,
        "inventory_store",
        InventoryStore("site_a", "North", partition_file, db_file),
    )
    monkeypatch.setattr(
        participant_app,
        "log_store",
        ParticipantLogStore("site_a", tmp_path / "site_a_log.jsonl"),
    )
    monkeypatch.setattr(participant_app, "transaction_states", {})
    monkeypatch.setitem(participant_app.debug_flags, "prepare_delay_seconds", 0.0)

    vote = participant_app.prepare(
        PrepareRequest(
            transaction_id="T-insufficient",
            updates=[update("North", "INV-LOW-001", delta_quantity=-3)],
        )
    )

    assert vote.message_type == MessageType.VOTE_ABORT
    assert vote.state == ParticipantState.ABORT
    assert participant_app.log_store.has_event("T-insufficient", "LOCAL_ABORT")


def test_prepare_timeout_causes_global_abort(tmp_path) -> None:
    durable_log = CoordinatorLogStore(tmp_path / "coordinator_log.jsonl")
    protocol = TimeoutOnSiteBPrepareProtocol(durable_log, PARTICIPANTS)
    request = GlobalInventoryUpdateRequest(
        transaction_id="T-timeout",
        updates=[
            update("North", "INV-000001"),
            update("Central", "INV-001251"),
        ],
    )

    result = protocol.run_transaction(request)

    assert result.decision == Decision.ABORT
    assert durable_log.has_event("T-timeout", "GLOBAL_ABORT")
    assert result.votes["site_b"] == MessageType.VOTE_ABORT.value


def test_commit_delivery_failure_keeps_commit_decision_for_recovery(tmp_path) -> None:
    durable_log = CoordinatorLogStore(tmp_path / "coordinator_log.jsonl")
    protocol = CrashOnSiteBGlobalCommitProtocol(durable_log, PARTICIPANTS)
    request = GlobalInventoryUpdateRequest(
        transaction_id="T-commit-crash",
        updates=[
            update("North", "INV-000001"),
            update("Central", "INV-001251"),
        ],
    )

    result = protocol.run_transaction(request)

    assert result.decision == Decision.COMMIT
    assert result.state == "COMMIT"
    assert "T-commit-crash" in protocol.transactions
    assert protocol.lookup_decision("T-commit-crash").decision == Decision.COMMIT
    assert durable_log.read_by_transaction("T-commit-crash") == []
