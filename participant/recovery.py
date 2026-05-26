from __future__ import annotations

from collections.abc import Callable

import httpx

from participant.log_store import ParticipantLogStore
from participant.models import Decision, ParticipantState


class RecoveryManager:
    def __init__(
        self,
        site_id: str,
        coordinator_url: str,
        log_store: ParticipantLogStore,
        state_registry: dict[str, ParticipantState],
    ) -> None:
        self.site_id = site_id
        self.coordinator_url = coordinator_url
        self.log_store = log_store
        self.state_registry = state_registry

    def _lookup_decision(self, transaction_id: str) -> Decision:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f"{self.coordinator_url}/transactions/{transaction_id}/decision"
            )
            response.raise_for_status()
            return Decision(response.json()["decision"])

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

        for transaction_id in self.log_store.ready_transactions_without_final_state():
            self.log_store.append(
                transaction_id=transaction_id,
                state=ParticipantState.READY.value,
                event="RECOVERY_QUERY",
                payload={"coordinator_url": self.coordinator_url},
            )
            decision = lookup(transaction_id)
            self.log_store.append(
                transaction_id=transaction_id,
                state=ParticipantState.READY.value,
                event="RECOVERY_DECISION",
                payload={"decision": decision.value},
            )

            if decision == Decision.ABORT:
                self.log_store.append(
                    transaction_id=transaction_id,
                    state=ParticipantState.ABORT.value,
                    event="ROLLED_BACK",
                    payload={"source": "recovery"},
                )
                self.state_registry[transaction_id] = ParticipantState.ABORT
                recovered.append({"transaction_id": transaction_id, "decision": "ABORT"})
            else:
                self.log_store.append(
                    transaction_id=transaction_id,
                    state=ParticipantState.COMMIT.value,
                    event="APPLIED_COMMIT",
                    payload={
                        "source": "recovery",
                        "presumed": decision == Decision.NOT_FOUND,
                    },
                )
                self.state_registry[transaction_id] = ParticipantState.COMMIT
                recovered.append({"transaction_id": transaction_id, "decision": "COMMIT"})

        return {
            "status": "ok",
            "recovered_transactions": recovered,
        }

