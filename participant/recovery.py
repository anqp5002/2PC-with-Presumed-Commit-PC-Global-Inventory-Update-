from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from participant.inventory_store import InventoryStore
from participant.log_store import ParticipantLogStore
from participant.models import Decision, ParticipantState


class RecoveryManager:
    def __init__(
        self,
        site_id: str,
        coordinator_url: str,
        log_store: ParticipantLogStore,
        state_registry: dict[str, ParticipantState],
        inventory_store: InventoryStore | None = None,
    ) -> None:
        self.site_id = site_id
        self.coordinator_url = coordinator_url
        self.log_store = log_store
        self.state_registry = state_registry
        self.inventory_store = inventory_store

    def _lookup_decision(self, transaction_id: str) -> Decision:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{self.coordinator_url}/transactions/{transaction_id}/decision"
            )
            response.raise_for_status()
            return Decision(response.json()["decision"])

    def _apply_commit(
        self,
        transaction_id: str,
        source: str,
    ) -> dict[str, Any]:
        updates = self.log_store.updates_for_transaction(transaction_id)
        if self.inventory_store is None:
            return {
                "transaction_id": transaction_id,
                "applied": False,
                "reason": "inventory_store_not_configured",
                "update_count": len(updates),
            }
        return self.inventory_store.apply_commit(transaction_id, updates)

    def _rollback(self, transaction_id: str) -> dict[str, Any]:
        updates = self.log_store.updates_for_transaction(transaction_id)
        if self.inventory_store is None:
            return {
                "transaction_id": transaction_id,
                "rolled_back": True,
                "reason": "inventory_store_not_configured",
                "update_count": len(updates),
            }
        return self.inventory_store.rollback(transaction_id, updates)

    def recover_pending(
        self,
        decision_lookup: Callable[[str], Decision] | None = None,
    ) -> dict[str, object]:
        """Recover READY transactions using coordinator outcome.

        TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5):
        A participant that has logged READY cannot unilaterally abort or commit
        under basic 2PC. During recovery it must obtain the global decision. In
        Presumed Commit, if the coordinator has no active/durable abort record
        and returns NOT_FOUND, the participant presumes COMMIT.
        """

        lookup = decision_lookup or self._lookup_decision
        recovered: list[dict[str, str]] = []
        errors: list[dict[str, str]] = []

        for transaction_id in self.log_store.commit_received_without_applied():
            # TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5):
            # GLOBAL_COMMIT_RECEIVED is already the global decision. If the
            # participant crashed before APPLIED_COMMIT, recovery can apply the
            # logged commit payload without asking the coordinator again.
            try:
                apply_result = self._apply_commit(
                    transaction_id,
                    source="recovery_global_commit_received",
                )
            except Exception as exc:
                errors.append(
                    {
                        "transaction_id": transaction_id,
                        "stage": "apply_commit_after_global_commit",
                        "error": str(exc),
                    }
                )
                continue

            self.log_store.append(
                transaction_id=transaction_id,
                state=ParticipantState.COMMIT.value,
                event="APPLIED_COMMIT",
                payload={
                    "source": "recovery_global_commit_received",
                    "apply_result": apply_result,
                },
            )
            self.state_registry[transaction_id] = ParticipantState.COMMIT
            recovered.append(
                {
                    "transaction_id": transaction_id,
                    "decision": "COMMIT",
                    "source": "GLOBAL_COMMIT_RECEIVED",
                }
            )

        for transaction_id in self.log_store.ready_transactions_without_final_state():
            self.log_store.append(
                transaction_id=transaction_id,
                state=ParticipantState.READY.value,
                event="RECOVERY_QUERY",
                payload={"coordinator_url": self.coordinator_url},
            )
            try:
                decision = lookup(transaction_id)
            except Exception as exc:
                errors.append(
                    {
                        "transaction_id": transaction_id,
                        "stage": "lookup_decision",
                        "error": str(exc),
                    }
                )
                continue

            self.log_store.append(
                transaction_id=transaction_id,
                state=ParticipantState.READY.value,
                event="RECOVERY_DECISION",
                payload={"decision": decision.value},
            )

            if decision == Decision.ABORT:
                rollback_result = self._rollback(transaction_id)
                self.log_store.append(
                    transaction_id=transaction_id,
                    state=ParticipantState.ABORT.value,
                    event="ROLLED_BACK",
                    payload={
                        "source": "recovery",
                        "rollback_result": rollback_result,
                    },
                )
                self.state_registry[transaction_id] = ParticipantState.ABORT
                recovered.append({"transaction_id": transaction_id, "decision": "ABORT"})
            else:
                try:
                    apply_result = self._apply_commit(transaction_id, source="recovery")
                except Exception as exc:
                    errors.append(
                        {
                            "transaction_id": transaction_id,
                            "stage": "apply_commit_after_decision",
                            "error": str(exc),
                        }
                    )
                    continue
                self.log_store.append(
                    transaction_id=transaction_id,
                    state=ParticipantState.COMMIT.value,
                    event="APPLIED_COMMIT",
                    payload={
                        "source": "recovery",
                        "presumed": decision == Decision.NOT_FOUND,
                        "apply_result": apply_result,
                    },
                )
                self.state_registry[transaction_id] = ParticipantState.COMMIT
                recovered.append({"transaction_id": transaction_id, "decision": "COMMIT"})

        return {
            "status": "ok" if not errors else "partial",
            "recovered_transactions": recovered,
            "errors": errors,
        }
