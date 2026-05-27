from __future__ import annotations

from coordinator.log_store import CoordinatorLogStore
from participant.log_store import ParticipantLogStore


def test_coordinator_log_store_appends_jsonl_records(tmp_path) -> None:
    store = CoordinatorLogStore(tmp_path / "coordinator_log.jsonl")

    store.append(
        transaction_id="T-log-1",
        site_id="coordinator",
        state="ABORT",
        event="GLOBAL_ABORT",
        payload={"reason": "unit test"},
    )

    records = store.read_by_transaction("T-log-1")
    assert len(records) == 1
    assert records[0].transaction_id == "T-log-1"
    assert records[0].event == "GLOBAL_ABORT"
    assert records[0].payload_hash
    assert store.has_abort("T-log-1")


def test_participant_log_store_finds_ready_without_final_state(tmp_path) -> None:
    store = ParticipantLogStore("site_b", tmp_path / "site_b_log.jsonl")

    store.append("T-ready", "INIT", "PREPARE_RECEIVED")
    store.append("T-ready", "READY", "READY")
    store.append("T-done", "READY", "READY")
    store.append("T-done", "COMMIT", "APPLIED_COMMIT")

    assert store.ready_transactions_without_final_state() == ["T-ready"]

