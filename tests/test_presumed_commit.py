from __future__ import annotations

import participant.app as participant_app
from participant.log_store import ParticipantLogStore
from participant.models import (
    Decision,
    MessageType,
    ParticipantState,
    PrepareRequest,
    TransactionDecisionRequest,
)
from participant.recovery import RecoveryManager


class ValidInventoryStore:
    def validate_updates(self, updates):
        return True, None


class InvalidInventoryStore:
    def validate_updates(self, updates):
        return False, "insufficient stock"


def prepare_request(transaction_id: str = "T-participant") -> PrepareRequest:
    return PrepareRequest(
        transaction_id=transaction_id,
        updates=[
            {
                "inventory_id": "INV-000001",
                "warehouse_id": "WH001",
                "region": "North",
                "delta_quantity": -1,
            }
        ],
    )


def patch_participant_state(monkeypatch, tmp_path, inventory_store):
    store = ParticipantLogStore("site_a", tmp_path / "site_a_log.jsonl")
    states: dict[str, ParticipantState] = {}
    monkeypatch.setattr(participant_app, "log_store", store)
    monkeypatch.setattr(participant_app, "inventory_store", inventory_store)
    monkeypatch.setattr(participant_app, "transaction_states", states)
    monkeypatch.setattr(participant_app, "pending_updates", {})
    monkeypatch.setitem(participant_app.debug_flags, "crash_after_ready", False)
    monkeypatch.setitem(
        participant_app.debug_flags,
        "crash_after_global_commit",
        False,
    )
    return store, states


def test_participant_prepare_valid_logs_ready_after_prepare(monkeypatch, tmp_path) -> None:
    store, _ = patch_participant_state(monkeypatch, tmp_path, ValidInventoryStore())

    vote = participant_app.prepare(prepare_request("T-ready"))

    assert vote.message_type == MessageType.VOTE_COMMIT
    records = store.read_by_transaction("T-ready")
    assert [record.event for record in records] == [
        "PREPARE_RECEIVED",
        "READY",
    ]


def test_participant_prepare_invalid_logs_local_abort(monkeypatch, tmp_path) -> None:
    store, _ = patch_participant_state(monkeypatch, tmp_path, InvalidInventoryStore())

    vote = participant_app.prepare(prepare_request("T-local-abort"))

    assert vote.message_type == MessageType.VOTE_ABORT
    records = store.read_by_transaction("T-local-abort")
    assert [record.event for record in records] == [
        "PREPARE_RECEIVED",
        "LOCAL_ABORT",
    ]


def test_participant_global_commit_logs_commit_and_ack(monkeypatch, tmp_path) -> None:
    store, _ = patch_participant_state(monkeypatch, tmp_path, ValidInventoryStore())

    ack = participant_app.global_commit(
        TransactionDecisionRequest(transaction_id="T-global-commit")
    )

    assert ack.message_type == MessageType.ACK_COMMIT
    assert [
        record.event for record in store.read_by_transaction("T-global-commit")
    ] == [
        "GLOBAL_COMMIT_RECEIVED",
        "APPLIED_COMMIT",
        "ACK_COMMIT_SENT",
    ]


def test_participant_global_abort_logs_rollback_and_ack(monkeypatch, tmp_path) -> None:
    store, _ = patch_participant_state(monkeypatch, tmp_path, ValidInventoryStore())

    ack = participant_app.global_abort(
        TransactionDecisionRequest(transaction_id="T-global-abort")
    )

    assert ack.message_type == MessageType.ACK_ABORT
    assert [
        record.event for record in store.read_by_transaction("T-global-abort")
    ] == [
        "GLOBAL_ABORT_RECEIVED",
        "ROLLED_BACK",
        "ACK_ABORT_SENT",
    ]


def test_recovery_ready_and_not_found_presumes_commit(tmp_path) -> None:
    store = ParticipantLogStore("site_b", tmp_path / "site_b_log.jsonl")
    states: dict[str, ParticipantState] = {}
    store.append("T-presumed", "INIT", "PREPARE_RECEIVED")
    store.append("T-presumed", "READY", "READY")
    recovery = RecoveryManager(
        site_id="site_b",
        coordinator_url="http://coordinator",
        log_store=store,
        state_registry=states,
    )

    result = recovery.recover_pending(lambda transaction_id: Decision.NOT_FOUND)

    assert result["recovered_transactions"] == [
        {"transaction_id": "T-presumed", "decision": "COMMIT"}
    ]
    assert states["T-presumed"] == ParticipantState.COMMIT
    assert store.has_event("T-presumed", "RECOVERY_QUERY")
    assert store.has_event("T-presumed", "RECOVERY_DECISION")
    assert store.has_event("T-presumed", "APPLIED_COMMIT")

