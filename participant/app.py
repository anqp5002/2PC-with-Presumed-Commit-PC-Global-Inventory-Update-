from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from participant.config import get_settings
from participant.inventory_store import InventoryStore
from participant.log_store import ParticipantLogStore
from participant.models import (
    AckResponse,
    DebugFlagResponse,
    MessageType,
    ParticipantState,
    PrepareRequest,
    StubResponse,
    TransactionDecisionRequest,
    VoteResponse,
)
from participant.recovery import RecoveryManager

settings = get_settings()
log_store = ParticipantLogStore(settings.site_id)
inventory_store = InventoryStore(settings.site_id, settings.region)
transaction_states: dict[str, ParticipantState] = {}
pending_updates: dict[str, list[dict]] = {}
recovery_manager = RecoveryManager(
    settings.site_id,
    settings.coordinator_url,
    log_store,
    transaction_states,
    inventory_store,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        recovery_manager.recover_pending()
    except Exception as exc:
        print(f"Startup recovery for {settings.site_id} skipped: {exc}")
    yield


app = FastAPI(
    title=f"2PC Participant {settings.site_id}",
    version="0.1.0",
    description="Participant API for the distributed inventory project.",
    lifespan=lifespan,
)

debug_flags = {
    "crash_after_ready": False,
    "crash_after_global_commit": False,
    "prepare_delay_seconds": 0.0,
}


def _updates_for_transaction(transaction_id: str) -> list[dict]:
    return pending_updates.get(transaction_id) or log_store.updates_for_transaction(
        transaction_id
    )


def _apply_commit_to_store(transaction_id: str, updates: list[dict]) -> dict:
    if hasattr(inventory_store, "apply_commit"):
        return inventory_store.apply_commit(transaction_id, updates)
    return {
        "transaction_id": transaction_id,
        "applied": False,
        "reason": "inventory_store_has_no_apply_commit",
        "update_count": len(updates),
    }


def _rollback_store(transaction_id: str, updates: list[dict]) -> dict:
    if hasattr(inventory_store, "rollback"):
        return inventory_store.rollback(transaction_id, updates)
    return {
        "transaction_id": transaction_id,
        "rolled_back": True,
        "reason": "inventory_store_has_no_rollback",
        "update_count": len(updates),
    }


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.site_id,
        "region": settings.region,
        "coordinator_url": settings.coordinator_url,
    }


@app.post("/prepare")
def prepare(request: PrepareRequest) -> VoteResponse:
    """Handle PREPARE and vote commit/abort.

    TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5):
    A participant may unilaterally abort before logging READY. Once it logs
    READY and sends VOTE_COMMIT, it must wait for the coordinator's global
    decision and cannot decide commit/abort by itself.
    """

    log_store.append(
        transaction_id=request.transaction_id,
        state=ParticipantState.INIT.value,
        event="PREPARE_RECEIVED",
        payload={"mode": request.mode.value, "update_count": len(request.updates)},
    )
    delay_seconds = float(debug_flags["prepare_delay_seconds"])
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    if transaction_states.get(request.transaction_id) == ParticipantState.ABORT:
        return VoteResponse(
            transaction_id=request.transaction_id,
            site_id=settings.site_id,
            message_type=MessageType.VOTE_ABORT,
            state=ParticipantState.ABORT,
            reason="participant already received GLOBAL_ABORT",
        )

    valid, reason = inventory_store.validate_updates(request.updates)
    if not valid:
        transaction_states[request.transaction_id] = ParticipantState.ABORT
        log_store.append(
            transaction_id=request.transaction_id,
            state=ParticipantState.ABORT.value,
            event="LOCAL_ABORT",
            payload={"reason": reason},
        )
        return VoteResponse(
            transaction_id=request.transaction_id,
            site_id=settings.site_id,
            message_type=MessageType.VOTE_ABORT,
            state=ParticipantState.ABORT,
            reason=reason,
        )

    transaction_states[request.transaction_id] = ParticipantState.READY
    pending_updates[request.transaction_id] = [
        update.model_dump(mode="json") for update in request.updates
    ]
    log_store.append(
        transaction_id=request.transaction_id,
        state=ParticipantState.READY.value,
        event="READY",
        payload={"updates": pending_updates[request.transaction_id]},
    )

    if debug_flags["crash_after_ready"]:
        os._exit(1)

    return VoteResponse(
        transaction_id=request.transaction_id,
        site_id=settings.site_id,
        message_type=MessageType.VOTE_COMMIT,
        state=ParticipantState.READY,
    )


@app.post("/global-commit")
def global_commit(request: TransactionDecisionRequest) -> AckResponse:
    """Apply the global commit decision.

    TEXTBOOK ALIGNMENT (Ozsu & Valduriez, Ch. 5.4.2):
    In Presumed Commit with ACD, the participant acknowledges commit after it
    records the local commit outcome. The coordinator can then discard volatile
    commit state without forcing a durable commit log record.
    """

    log_store.append(
        transaction_id=request.transaction_id,
        state=ParticipantState.READY.value,
        event="GLOBAL_COMMIT_RECEIVED",
        payload={"mode": request.mode.value},
    )
    if debug_flags["crash_after_global_commit"]:
        os._exit(1)

    if not log_store.has_event(request.transaction_id, "APPLIED_COMMIT"):
        updates = _updates_for_transaction(request.transaction_id)
        apply_result = _apply_commit_to_store(request.transaction_id, updates)
        log_store.append(
            transaction_id=request.transaction_id,
            state=ParticipantState.COMMIT.value,
            event="APPLIED_COMMIT",
            payload={
                "source": "global_commit",
                "apply_result": apply_result,
            },
        )
    transaction_states[request.transaction_id] = ParticipantState.COMMIT
    pending_updates.pop(request.transaction_id, None)
    log_store.append(
        transaction_id=request.transaction_id,
        state=ParticipantState.COMMIT.value,
        event="ACK_COMMIT_SENT",
        payload={"mode": request.mode.value},
    )
    return AckResponse(
        transaction_id=request.transaction_id,
        site_id=settings.site_id,
        message_type=MessageType.ACK_COMMIT,
        state=ParticipantState.COMMIT,
    )


@app.post("/global-abort")
def global_abort(request: TransactionDecisionRequest) -> AckResponse:
    """Apply the global abort decision."""

    log_store.append(
        transaction_id=request.transaction_id,
        state=transaction_states.get(
            request.transaction_id,
            ParticipantState.READY,
        ).value,
        event="GLOBAL_ABORT_RECEIVED",
        payload={"mode": request.mode.value},
    )
    if not log_store.has_event(request.transaction_id, "ROLLED_BACK"):
        updates = _updates_for_transaction(request.transaction_id)
        rollback_result = _rollback_store(request.transaction_id, updates)
        log_store.append(
            transaction_id=request.transaction_id,
            state=ParticipantState.ABORT.value,
            event="ROLLED_BACK",
            payload={
                "source": "global_abort",
                "rollback_result": rollback_result,
            },
        )
    transaction_states[request.transaction_id] = ParticipantState.ABORT
    pending_updates.pop(request.transaction_id, None)
    log_store.append(
        transaction_id=request.transaction_id,
        state=ParticipantState.ABORT.value,
        event="ACK_ABORT_SENT",
        payload={"mode": request.mode.value},
    )
    return AckResponse(
        transaction_id=request.transaction_id,
        site_id=settings.site_id,
        message_type=MessageType.ACK_ABORT,
        state=ParticipantState.ABORT,
    )


@app.post("/recover-pending")
def recover_pending() -> StubResponse:
    return StubResponse(
        service=settings.site_id,
        message="recover pending completed",
        data=recovery_manager.recover_pending(),
    )


@app.post("/debug/crash-after-ready")
def set_crash_after_ready(enabled: bool = True) -> DebugFlagResponse:
    debug_flags["crash_after_ready"] = enabled
    return DebugFlagResponse(
        service=settings.site_id,
        flag="crash_after_ready",
        enabled=enabled,
    )


@app.post("/debug/crash-after-global-commit")
def set_crash_after_global_commit(enabled: bool = True) -> DebugFlagResponse:
    debug_flags["crash_after_global_commit"] = enabled
    return DebugFlagResponse(
        service=settings.site_id,
        flag="crash_after_global_commit",
        enabled=enabled,
    )


@app.post("/debug/prepare-delay")
def set_prepare_delay(seconds: float = 0.0) -> StubResponse:
    debug_flags["prepare_delay_seconds"] = max(0.0, seconds)
    return StubResponse(
        service=settings.site_id,
        message="prepare delay updated",
        data={"prepare_delay_seconds": debug_flags["prepare_delay_seconds"]},
    )


@app.post("/debug/reset")
def reset_debug_flags() -> StubResponse:
    debug_flags["crash_after_ready"] = False
    debug_flags["crash_after_global_commit"] = False
    debug_flags["prepare_delay_seconds"] = 0.0
    return StubResponse(
        service=settings.site_id,
        message="debug flags reset",
        data=dict(debug_flags),
    )


@app.get("/inventory/{inventory_id}")
def get_inventory(inventory_id: str) -> StubResponse:
    return StubResponse(
        service=settings.site_id,
        message="inventory lookup completed",
        data=inventory_store.get_inventory_item(inventory_id),
    )


@app.get("/logs/{transaction_id}")
def get_logs(transaction_id: str) -> StubResponse:
    return StubResponse(
        service=settings.site_id,
        message="transaction log lookup completed",
        data={
            "transaction_id": transaction_id,
            "logs": [
                record.model_dump(mode="json")
                for record in log_store.read_by_transaction(transaction_id)
            ],
        },
    )
