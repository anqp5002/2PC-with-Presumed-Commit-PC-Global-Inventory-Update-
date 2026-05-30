from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import httpx

from coordinator.config import (
    PARTICIPANTS,
    PARTICIPANT_TIMEOUT_SECONDS,
    SERVICE_NAME,
    ParticipantConfig,
)
from coordinator.log_store import CoordinatorLogStore, log_store
from coordinator.message_counter import message_counter
from coordinator.models import (
    AckResponse,
    CoordinatorState,
    Decision,
    DecisionResponse,
    GlobalInventoryUpdateRequest,
    InventoryUpdateItem,
    MessageType,
    PrepareRequest,
    TransactionMode,
    TransactionStateResponse,
    VoteResponse,
)


@dataclass
class RuntimeTransaction:
    transaction_id: str
    mode: TransactionMode
    state: CoordinatorState
    participants: list[str]
    votes: dict[str, str] = field(default_factory=dict)
    acks: dict[str, str] = field(default_factory=dict)
    decision: Decision | None = None
    reason: str | None = None

    def to_response(self) -> TransactionStateResponse:
        return TransactionStateResponse(
            transaction_id=self.transaction_id,
            mode=self.mode,
            state=self.state,
            participants=self.participants,
            votes=self.votes,
            acks=self.acks,
            decision=self.decision,
            reason=self.reason,
        )


class CoordinatorProtocol:
    """Coordinator-side 2PC protocol with Presumed Commit semantics."""

    def __init__(
        self,
        durable_log: CoordinatorLogStore = log_store,
        participant_configs: dict[str, ParticipantConfig] = PARTICIPANTS,
    ) -> None:
        self.transactions: dict[str, RuntimeTransaction] = {}
        self.durable_log = durable_log
        self.participant_configs = participant_configs

    def _post_json(self, url: str, payload: dict) -> dict:
        with httpx.Client(timeout=PARTICIPANT_TIMEOUT_SECONDS) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    def _site_for_region(self, region: str) -> str:
        for site_id, config in self.participant_configs.items():
            if config.region == region:
                return site_id
        raise ValueError(f"No participant configured for region {region!r}")

    def _group_updates_by_site(
        self, updates: list[InventoryUpdateItem]
    ) -> dict[str, list[InventoryUpdateItem]]:
        grouped: dict[str, list[InventoryUpdateItem]] = {}
        for update in updates:
            site_id = self._site_for_region(update.region)
            grouped.setdefault(site_id, []).append(update)
        return grouped

    def _count(self, message_type: MessageType) -> None:
        message_counter.increment(message_type.value)

    def _send_prepare(
        self,
        transaction_id: str,
        mode: TransactionMode,
        site_id: str,
        updates: list[InventoryUpdateItem],
    ) -> VoteResponse:
        """Send the 2PC prepare request and count both network directions."""
        config = self.participant_configs[site_id]
        request = PrepareRequest(
            transaction_id=transaction_id,
            mode=mode,
            updates=updates,
        )
        self._count(MessageType.PREPARE)
        response = self._post_json(
            f"{config.base_url}/prepare",
            request.model_dump(mode="json"),
        )
        self._count(MessageType(response["message_type"]))
        return VoteResponse.model_validate(response)

    def _send_global_commit(
        self,
        transaction: RuntimeTransaction,
        site_id: str,
    ) -> AckResponse:
        """Send GLOBAL_COMMIT and optionally count ACD.

        TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5.4.2):
        Presumed Commit may use acknowledgment of commit (ACD) so the
        coordinator knows each participant has received the commit decision.
        `PC_NO_ACD` keeps the commit decision rule but omits ACK_COMMIT from
        the measured network path.
        """

        config = self.participant_configs[site_id]
        self._count(MessageType.GLOBAL_COMMIT)
        response = self._post_json(
            f"{config.base_url}/global-commit",
            {
                "transaction_id": transaction.transaction_id,
                "mode": transaction.mode.value,
            },
        )
        ack = AckResponse.model_validate(response)
        if transaction.mode != TransactionMode.PC_NO_ACD:
            self._count(MessageType(ack.message_type))
        return ack

    def _send_global_abort(
        self,
        transaction: RuntimeTransaction,
        site_id: str,
    ) -> AckResponse:
        """Send GLOBAL_ABORT and count abort ACK according to the comparison mode.

        TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5):
        After one abort vote or timeout, the coordinator must tell every
        participant in the transaction to abort. `PA_COMPARISON` is only a
        message-count baseline here, so ACK_ABORT is excluded for that chart
        path while Presumed Commit keeps it.
        """

        config = self.participant_configs[site_id]
        self._count(MessageType.GLOBAL_ABORT)
        response = self._post_json(
            f"{config.base_url}/global-abort",
            {
                "transaction_id": transaction.transaction_id,
                "mode": transaction.mode.value,
            },
        )
        ack = AckResponse.model_validate(response)
        if transaction.mode != TransactionMode.PA_COMPARISON:
            self._count(MessageType(ack.message_type))
        return ack

    def _record_abort(self, transaction: RuntimeTransaction, reason: str) -> None:
        """Durably record a global abort decision.

        TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5.4.2):
        In Presumed Commit, abort is the exceptional outcome and must be
        durable. A later recovery lookup can then distinguish a real abort from
        a missing commit record.
        """

        self.durable_log.append(
            transaction_id=transaction.transaction_id,
            site_id=SERVICE_NAME,
            state=CoordinatorState.ABORT.value,
            event="GLOBAL_ABORT",
            payload={
                "reason": reason,
                "participants": transaction.participants,
                "votes": transaction.votes,
            },
        )

    def _complete_abort(self, transaction: RuntimeTransaction) -> None:
        self.durable_log.append(
            transaction_id=transaction.transaction_id,
            site_id=SERVICE_NAME,
            state=CoordinatorState.END.value,
            event="END_ABORT",
            payload={"acks": transaction.acks},
        )

    def create_stub_transaction(
        self, request: GlobalInventoryUpdateRequest
    ) -> tuple[str, CoordinatorState]:
        transaction_id = request.transaction_id or f"T-{uuid4().hex[:12]}"
        self.transactions[transaction_id] = RuntimeTransaction(
            transaction_id=transaction_id,
            mode=request.mode,
            state=CoordinatorState.INIT,
            participants=[],
        )
        return transaction_id, CoordinatorState.INIT

    def run_transaction(
        self, request: GlobalInventoryUpdateRequest
    ) -> TransactionStateResponse:
        """Run centralized 2PC with the Presumed Commit durable-log policy.

        TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5):
        The coordinator applies the global-commit rule: all participants must
        vote commit for a global commit; one abort vote is enough for a global
        abort. For Presumed Commit, this coordinator does not force a durable
        commit log record. It keeps commit state only long enough to collect
        ACD acknowledgments, then may forget the transaction.
        """

        transaction_id = request.transaction_id or f"T-{uuid4().hex[:12]}"
        grouped_updates = self._group_updates_by_site(request.updates)
        participants = sorted(grouped_updates)
        transaction = RuntimeTransaction(
            transaction_id=transaction_id,
            mode=request.mode,
            state=CoordinatorState.WAIT,
            participants=participants,
        )
        self.transactions[transaction_id] = transaction

        abort_reason: str | None = None
        for site_id in participants:
            try:
                vote = self._send_prepare(
                    transaction_id=transaction_id,
                    mode=request.mode,
                    site_id=site_id,
                    updates=grouped_updates[site_id],
                )
            except Exception as exc:  # timeout/unavailable participant
                vote = None
                abort_reason = f"{site_id} did not respond to PREPARE: {exc}"

            if vote is None:
                transaction.votes[site_id] = MessageType.VOTE_ABORT.value
                break

            transaction.votes[site_id] = vote.message_type.value
            if vote.message_type == MessageType.VOTE_ABORT:
                abort_reason = vote.reason or f"{site_id} voted abort"
                break

        if abort_reason is not None or len(transaction.votes) != len(participants):
            return self._abort_transaction(
                transaction,
                abort_reason or "not all participants voted commit",
            )

        transaction.state = CoordinatorState.COMMIT
        transaction.decision = Decision.COMMIT

        commit_delivery_errors: dict[str, str] = {}
        for site_id in participants:
            try:
                ack = self._send_global_commit(transaction, site_id)
                if request.mode != TransactionMode.PC_NO_ACD:
                    transaction.acks[site_id] = ack.message_type.value
            except Exception as exc:
                commit_delivery_errors[site_id] = str(exc)
                transaction.acks[site_id] = f"ACK_COMMIT_FAILED: {exc}"

        response = transaction.to_response()
        if request.mode == TransactionMode.PC_WITH_ACD and not commit_delivery_errors:
            transaction.state = CoordinatorState.END
            response = transaction.to_response()
            self.transactions.pop(transaction_id, None)
        return response

    def _abort_transaction(
        self,
        transaction: RuntimeTransaction,
        reason: str,
    ) -> TransactionStateResponse:
        """Move WAIT to ABORT after an abort vote, timeout, or missing vote.

        TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5):
        The global abort rule is conservative: one negative vote, timeout, or
        unreachable participant is enough to abort the distributed transaction.
        """

        transaction.state = CoordinatorState.ABORT
        transaction.decision = Decision.ABORT
        transaction.reason = reason
        self._record_abort(transaction, reason)

        for site_id in transaction.participants:
            try:
                ack = self._send_global_abort(transaction, site_id)
                transaction.acks[site_id] = ack.message_type.value
            except Exception as exc:
                transaction.acks[site_id] = f"ACK_ABORT_FAILED: {exc}"

        transaction.state = CoordinatorState.END
        self._complete_abort(transaction)
        return transaction.to_response()

    def get_state(self, transaction_id: str) -> TransactionStateResponse | None:
        transaction = self.transactions.get(transaction_id)
        if transaction is None:
            return None
        return transaction.to_response()

    def lookup_decision(self, transaction_id: str) -> DecisionResponse:
        """Resolve a transaction outcome for participant recovery.

        TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5.4.2):
        In Presumed Commit, the absence of coordinator state is not treated as
        an error for a READY participant. If no active transaction and no
        durable abort record exists, participants may presume COMMIT.
        """

        transaction = self.transactions.get(transaction_id)
        if transaction and transaction.decision == Decision.ABORT:
            decision = Decision.ABORT
        elif transaction and transaction.decision == Decision.COMMIT:
            decision = Decision.COMMIT
        elif self.durable_log.has_abort(transaction_id):
            decision = Decision.ABORT
        else:
            decision = Decision.NOT_FOUND

        if decision != Decision.COMMIT:
            self.durable_log.append(
                transaction_id=transaction_id,
                site_id=SERVICE_NAME,
                state=decision.value,
                event="RECOVERY_DECISION",
                payload={"decision": decision.value},
            )
        return DecisionResponse(transaction_id=transaction_id, decision=decision)

    def forget_transaction(self, transaction_id: str) -> bool:
        return self.transactions.pop(transaction_id, None) is not None


protocol = CoordinatorProtocol()
