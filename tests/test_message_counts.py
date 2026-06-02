from __future__ import annotations

from coordinator.config import ParticipantConfig
from coordinator.log_store import CoordinatorLogStore
from coordinator.message_counter import message_counter
from coordinator.models import GlobalInventoryUpdateRequest, TransactionMode
from coordinator.protocol import CoordinatorProtocol


PARTICIPANTS = {
    "site_a": ParticipantConfig("site_a", "North", "http://site-a"),
    "site_b": ParticipantConfig("site_b", "Central", "http://site-b"),
    "site_c": ParticipantConfig("site_c", "SouthEast", "http://site-c"),
    "site_d": ParticipantConfig("site_d", "Mekong", "http://site-d"),
}


def site_from_url(url: str) -> str:
    if "site-a" in url:
        return "site_a"
    if "site-b" in url:
        return "site_b"
    if "site-c" in url:
        return "site_c"
    if "site-d" in url:
        return "site_d"
    raise AssertionError(f"unexpected URL {url}")


def update(region: str, inventory_id: str, warehouse_id: str, delta_quantity: int = -1):
    return {
        "inventory_id": inventory_id,
        "warehouse_id": warehouse_id,
        "region": region,
        "delta_quantity": delta_quantity,
    }


def request(mode: TransactionMode, transaction_id: str = "T-message-count"):
    return GlobalInventoryUpdateRequest(
        transaction_id=transaction_id,
        mode=mode,
        updates=[
            update("North", "INV-000001", "WH001"),
            update("Central", "INV-001251", "WH006"),
            update("SouthEast", "INV-002501", "WH011"),
            update("Mekong", "INV-003751", "WH016"),
        ],
    )


class MessageCountProtocol(CoordinatorProtocol):
    def __init__(self, durable_log, abort_site_d: bool = False) -> None:
        super().__init__(durable_log, PARTICIPANTS)
        self.abort_site_d = abort_site_d

    def _post_json(self, url: str, payload: dict) -> dict:
        site_id = site_from_url(url)
        if url.endswith("/prepare"):
            if self.abort_site_d and site_id == "site_d":
                return {
                    "transaction_id": payload["transaction_id"],
                    "site_id": site_id,
                    "message_type": "VOTE_ABORT",
                    "state": "ABORT",
                    "reason": "controlled site_d abort",
                }
            return {
                "transaction_id": payload["transaction_id"],
                "site_id": site_id,
                "message_type": "VOTE_COMMIT",
                "state": "READY",
                "reason": None,
            }
        if url.endswith("/global-commit"):
            return {
                "transaction_id": payload["transaction_id"],
                "site_id": site_id,
                "message_type": "ACK_COMMIT",
                "state": "COMMIT",
                "reason": None,
            }
        if url.endswith("/global-abort"):
            return {
                "transaction_id": payload["transaction_id"],
                "site_id": site_id,
                "message_type": "ACK_ABORT",
                "state": "ABORT",
                "reason": None,
            }
        raise AssertionError(f"unexpected URL {url}")


def run_message_count_case(tmp_path, mode: TransactionMode, abort_site_d: bool = False):
    message_counter.reset()
    protocol = MessageCountProtocol(
        CoordinatorLogStore(tmp_path / f"{mode.value}.jsonl"),
        abort_site_d=abort_site_d,
    )
    result = protocol.run_transaction(
        request(mode, transaction_id=f"T-{mode.value}-{abort_site_d}")
    )
    return result, message_counter.snapshot()


def test_pa_comparison_commit_with_four_sites_counts_16_messages(tmp_path) -> None:
    result, counts = run_message_count_case(tmp_path, TransactionMode.PA_COMPARISON)

    assert result.decision == "COMMIT"
    assert counts["PREPARE"] == 4
    assert counts["VOTE_COMMIT"] == 4
    assert counts["GLOBAL_COMMIT"] == 4
    assert counts["ACK_COMMIT"] == 4
    assert counts["TOTAL"] == 16


def test_pc_no_acd_commit_with_four_sites_counts_12_messages(tmp_path) -> None:
    result, counts = run_message_count_case(tmp_path, TransactionMode.PC_NO_ACD)

    assert result.decision == "COMMIT"
    assert counts["PREPARE"] == 4
    assert counts["VOTE_COMMIT"] == 4
    assert counts["GLOBAL_COMMIT"] == 4
    assert counts.get("ACK_COMMIT", 0) == 0
    assert counts["TOTAL"] == 12


def test_pc_with_acd_commit_with_four_sites_counts_16_messages(tmp_path) -> None:
    result, counts = run_message_count_case(tmp_path, TransactionMode.PC_WITH_ACD)

    assert result.decision == "COMMIT"
    assert counts["PREPARE"] == 4
    assert counts["VOTE_COMMIT"] == 4
    assert counts["GLOBAL_COMMIT"] == 4
    assert counts["ACK_COMMIT"] == 4
    assert counts["TOTAL"] == 16


def test_pa_comparison_abort_with_four_sites_counts_12_messages(tmp_path) -> None:
    result, counts = run_message_count_case(
        tmp_path,
        TransactionMode.PA_COMPARISON,
        abort_site_d=True,
    )

    assert result.decision == "ABORT"
    assert counts["PREPARE"] == 4
    assert counts["VOTE_COMMIT"] == 3
    assert counts["VOTE_ABORT"] == 1
    assert counts["GLOBAL_ABORT"] == 4
    assert counts.get("ACK_ABORT", 0) == 0
    assert counts["TOTAL"] == 12


def test_pc_abort_with_four_sites_counts_16_messages(tmp_path) -> None:
    result, counts = run_message_count_case(
        tmp_path,
        TransactionMode.PC_WITH_ACD,
        abort_site_d=True,
    )

    assert result.decision == "ABORT"
    assert counts["PREPARE"] == 4
    assert counts["VOTE_COMMIT"] == 3
    assert counts["VOTE_ABORT"] == 1
    assert counts["GLOBAL_ABORT"] == 4
    assert counts["ACK_ABORT"] == 4
    assert counts["TOTAL"] == 16


def test_acd_overhead_with_four_sites_is_four_messages(tmp_path) -> None:
    _, no_acd = run_message_count_case(tmp_path, TransactionMode.PC_NO_ACD)
    _, with_acd = run_message_count_case(tmp_path, TransactionMode.PC_WITH_ACD)

    assert with_acd["TOTAL"] - no_acd["TOTAL"] == 4
