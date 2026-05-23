from __future__ import annotations

from uuid import uuid4

from coordinator.models import (
    CoordinatorState,
    Decision,
    DecisionResponse,
    GlobalInventoryUpdateRequest,
)


class CoordinatorProtocol:
    """Phase 1 protocol facade.

    Real Presumed Commit 2PC behavior is implemented in later phases. This
    class currently provides stable method boundaries for the API layer.
    """

    def __init__(self) -> None:
        self.transactions: dict[str, CoordinatorState] = {}

    def create_stub_transaction(
        self, request: GlobalInventoryUpdateRequest
    ) -> tuple[str, CoordinatorState]:
        transaction_id = request.transaction_id or f"T-{uuid4().hex[:12]}"
        self.transactions[transaction_id] = CoordinatorState.INIT
        return transaction_id, CoordinatorState.INIT

    def get_state(self, transaction_id: str) -> CoordinatorState | None:
        return self.transactions.get(transaction_id)

    def lookup_decision(self, transaction_id: str) -> DecisionResponse:
        state = self.transactions.get(transaction_id)
        if state == CoordinatorState.ABORT:
            decision = Decision.ABORT
        elif state in {CoordinatorState.COMMIT, CoordinatorState.END}:
            decision = Decision.COMMIT
        else:
            decision = Decision.NOT_FOUND
        return DecisionResponse(transaction_id=transaction_id, decision=decision)

    def forget_transaction(self, transaction_id: str) -> bool:
        return self.transactions.pop(transaction_id, None) is not None


protocol = CoordinatorProtocol()

