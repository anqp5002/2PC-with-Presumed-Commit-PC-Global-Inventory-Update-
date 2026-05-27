from __future__ import annotations

from coordinator.config import ParticipantConfig
from coordinator.log_store import CoordinatorLogStore
from coordinator.message_counter import message_counter
from coordinator.models import Decision, GlobalInventoryUpdateRequest
from coordinator.protocol import CoordinatorProtocol


PARTICIPANTS = {
    "site_a": ParticipantConfig("site_a", "North", "http://site-a"),
    "site_b": ParticipantConfig("site_b", "Central", "http://site-b"),
}


def update(region: str, inventory_id: str):
    return {
        "inventory_id": inventory_id,
        "warehouse_id": "WH001" if region == "North" else "WH006",
        "region": region,
        "delta_quantity": -1,
    }


class FakeCommitCoordinatorProtocol(CoordinatorProtocol):
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
        if url.endswith("/global-commit"):
            site_id = "site_a" if "site-a" in url else "site_b"
            return {
                "transaction_id": payload["transaction_id"],
                "site_id": site_id,
                "message_type": "ACK_COMMIT",
                "state": "COMMIT",
                "reason": None,
            }
        raise AssertionError(f"unexpected URL {url}")


class FakeAbortCoordinatorProtocol(CoordinatorProtocol):
    def _post_json(self, url: str, payload: dict) -> dict:
        if url.endswith("/prepare"):
            site_id = "site_a" if "site-a" in url else "site_b"
            if site_id == "site_b":
                return {
                    "transaction_id": payload["transaction_id"],
                    "site_id": site_id,
                    "message_type": "VOTE_ABORT",
                    "state": "ABORT",
                    "reason": "insufficient stock",
                }
            return {
                "transaction_id": payload["transaction_id"],
                "site_id": site_id,
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


def test_coordinator_commit_path_does_not_durable_log_commit(tmp_path) -> None:
    message_counter.reset()
    durable_log = CoordinatorLogStore(tmp_path / "coordinator_log.jsonl")
    protocol = FakeCommitCoordinatorProtocol(durable_log, PARTICIPANTS)
    request = GlobalInventoryUpdateRequest(
        transaction_id="T-commit",
        updates=[
            update("North", "INV-000001"),
            update("Central", "INV-001251"),
        ],
    )

    result = protocol.run_transaction(request)

    assert result.decision == Decision.COMMIT
    assert result.state == "END"
    assert "T-commit" not in protocol.transactions
    assert durable_log.read_by_transaction("T-commit") == []
    assert message_counter.snapshot()["PREPARE"] == 2
    assert message_counter.snapshot()["VOTE_COMMIT"] == 2
    assert message_counter.snapshot()["GLOBAL_COMMIT"] == 2
    assert message_counter.snapshot()["ACK_COMMIT"] == 2


def test_coordinator_abort_path_durable_logs_global_abort(tmp_path) -> None:
    message_counter.reset()
    durable_log = CoordinatorLogStore(tmp_path / "coordinator_log.jsonl")
    protocol = FakeAbortCoordinatorProtocol(durable_log, PARTICIPANTS)
    request = GlobalInventoryUpdateRequest(
        transaction_id="T-abort",
        updates=[
            update("North", "INV-000001"),
            update("Central", "INV-001251"),
        ],
    )

    result = protocol.run_transaction(request)

    assert result.decision == Decision.ABORT
    assert durable_log.has_event("T-abort", "GLOBAL_ABORT")
    assert protocol.lookup_decision("T-abort").decision == Decision.ABORT

